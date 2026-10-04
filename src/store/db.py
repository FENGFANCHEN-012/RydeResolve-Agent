"""
Record store for the learning feedback loop (SQLAlchemy; SQLite by default).

Tables
- rulings     every result the pipeline produced (auto-executed or escalated)
- reviews     a human reviewer's confirm / override of a ruling
- precedents  human-reviewed outcomes that may guide later rulings, with a status:
              pending -> staged -> active | rejected, and active -> retired
- audit_log   append-only, hash-chained log of every change above
- traces      every streamed pipeline run's events, for replay in the dashboard

STORE_URL (else DATABASE_URL) picks the database (default: sqlite file
data/ryde_resolve.db). For a
hosted Postgres such as Supabase, set it to the project's connection string; a
plain postgres:// URL is given the psycopg driver automatically.
"""
import hashlib
import json
import os
from datetime import datetime, timezone

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from src import config

DEFAULT_URL = "sqlite:///" + os.path.join(config.DATA_DIR, "ryde_resolve.db").replace("\\", "/")

# Precedent lifecycle. Only "active" guides live rulings; "staged" is visible to the
# evaluation gate only; "rejected" and "retired" are kept for the record.
PENDING, STAGED, ACTIVE, REJECTED, RETIRED = "pending", "staged", "active", "rejected", "retired"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Base(DeclarativeBase):
    pass


class Ruling(Base):
    __tablename__ = "rulings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dispute_id: Mapped[str] = mapped_column(String(64), index=True)
    order_id: Mapped[str | None] = mapped_column(String(64))
    dispute_type: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40))  # resolved / escalated_to_human / failed
    verdict: Mapped[str | None] = mapped_column(String(40))
    refund_amount: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    rationale: Mapped[str | None] = mapped_column(Text)
    policy_refs: Mapped[list] = mapped_column(JSON, default=list)
    precedent_ids: Mapped[list] = mapped_column(JSON, default=list)  # precedents the Judge was shown
    case_summary: Mapped[str | None] = mapped_column(Text)  # facts used to match later precedents
    pipeline_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(32), default=_now)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ruling_id: Mapped[int] = mapped_column(ForeignKey("rulings.id"), index=True)
    reviewer: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))  # confirm / override
    final_verdict: Mapped[str | None] = mapped_column(String(40))
    final_refund: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32), default=_now)


class Precedent(Base):
    __tablename__ = "precedents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"))
    dispute_id: Mapped[str] = mapped_column(String(64), index=True)
    family: Mapped[str] = mapped_column(String(64), index=True)  # base case id: variants share it
    dispute_type: Mapped[str | None] = mapped_column(String(40))
    case_summary: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str | None] = mapped_column(String(40))
    refund_amount: Mapped[float | None] = mapped_column(Float)
    principle: Mapped[str] = mapped_column(Text)  # why the reviewer ruled this way
    ai_verdict: Mapped[str | None] = mapped_column(String(40))  # what the AI had said, for the record
    status: Mapped[str] = mapped_column(String(16), default=PENDING, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    approved_by: Mapped[str | None] = mapped_column(String(64))
    gate_result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32), default=_now)
    updated_at: Mapped[str] = mapped_column(String(32), default=_now)


class AuditEntry(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[str] = mapped_column(String(32), default=_now)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(40))
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Trace(Base):
    __tablename__ = "traces"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)  # <timestamp>_<order id>.json
    order_id: Mapped[str | None] = mapped_column(String(64), index=True)
    events: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String(32), default=_now)


def entry_hash(prev_hash: str, ts: str, actor: str, action: str, object_type: str,
               object_id: int | None, detail: dict) -> str:
    """Each entry hashes the previous one, so editing or deleting any row breaks the chain."""
    body = json.dumps([prev_hash, ts, actor, action, object_type, object_id, detail],
                      sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class Store:
    """All writes go through here so each one lands in the audit log."""

    def __init__(self, url: str | None = None):
        self.engine = _make_engine(url or os.getenv("STORE_URL") or os.getenv("DATABASE_URL") or DEFAULT_URL)
        self.is_postgres = self.engine.dialect.name == "postgresql"
        Base.metadata.create_all(self.engine)
        if self.is_postgres:
            self._lock_public_api()

    def _lock_public_api(self) -> None:
        """Supabase serves every table in the public schema over its REST API, where the anon
        key could read or edit them. Row-level security with no policies closes that; this
        backend connects as the table owner, which RLS does not restrict."""
        with self.engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                conn.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))

    def session(self) -> Session:
        return Session(self.engine, expire_on_commit=False)

    # -- audit ------------------------------------------------------------

    def _audit(self, s: Session, actor: str, action: str, object_type: str,
               object_id: int | None, detail: dict | None = None) -> None:
        if self.is_postgres:
            # Two requests writing at once must not both chain onto the same last entry:
            # hold a transaction-scoped lock until this entry is committed.
            s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": AUDIT_LOCK_KEY})
        last = s.scalars(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(1)).first()
        prev = last.hash if last else "0" * 64
        ts, detail = _now(), detail or {}
        s.add(AuditEntry(ts=ts, actor=actor, action=action, object_type=object_type, object_id=object_id,
                         detail=detail, prev_hash=prev,
                         hash=entry_hash(prev, ts, actor, action, object_type, object_id, detail)))

    def verify_audit_chain(self) -> tuple[bool, int | None]:
        """(True, None) if intact, else (False, id of the first entry that does not match)."""
        prev = "0" * 64
        with self.session() as s:
            for e in s.scalars(select(AuditEntry).order_by(AuditEntry.id)):
                expected = entry_hash(prev, e.ts, e.actor, e.action, e.object_type, e.object_id, e.detail)
                if e.prev_hash != prev or e.hash != expected:
                    return False, e.id
                prev = e.hash
        return True, None

    # -- rulings and reviews ---------------------------------------------

    def record_ruling(self, **fields) -> Ruling:
        with self.session() as s:
            ruling = Ruling(**fields)
            s.add(ruling)
            s.flush()
            self._audit(s, "pipeline", "ruling_recorded", "ruling", ruling.id,
                        {"dispute_id": ruling.dispute_id, "status": ruling.status, "verdict": ruling.verdict,
                         "refund_amount": ruling.refund_amount})
            s.commit()
            return ruling

    def submit_review(self, ruling_id: int, reviewer: str, action: str, reason: str,
                      final_verdict: str | None = None, final_refund: float | None = None) -> tuple[Review, Precedent | None]:
        """A reviewer confirms or overrides a ruling. An override, or any human decision on an
        escalated case, becomes a pending precedent: something the AI did not get right alone."""
        if action not in ("confirm", "override"):
            raise ValueError("action must be 'confirm' or 'override'")
        if not reason.strip():
            raise ValueError("a review needs a reason; it becomes the precedent's principle")
        with self.session() as s:
            ruling = s.get(Ruling, ruling_id)
            if ruling is None:
                raise KeyError(f"no ruling {ruling_id}")
            if action == "confirm":
                final_verdict, final_refund = final_verdict or ruling.verdict, (
                    final_refund if final_refund is not None else ruling.refund_amount)
            review = Review(ruling_id=ruling_id, reviewer=reviewer, action=action, reason=reason,
                            final_verdict=final_verdict, final_refund=final_refund)
            s.add(review)
            s.flush()
            self._audit(s, reviewer, f"review_{action}", "review", review.id,
                        {"ruling_id": ruling_id, "ai_verdict": ruling.verdict, "final_verdict": final_verdict,
                         "final_refund": final_refund})
            precedent = None
            if action == "override" or ruling.status != "resolved":
                precedent = Precedent(review_id=review.id, dispute_id=ruling.dispute_id,
                                      family=case_family(ruling.dispute_id), dispute_type=ruling.dispute_type,
                                      case_summary=ruling.case_summary or "", verdict=final_verdict,
                                      refund_amount=final_refund, principle=reason, ai_verdict=ruling.verdict)
                s.add(precedent)
                s.flush()
                self._audit(s, reviewer, "precedent_proposed", "precedent", precedent.id,
                            {"dispute_id": ruling.dispute_id, "verdict": final_verdict})
            s.commit()
            return review, precedent

    # -- precedent lifecycle ---------------------------------------------

    def get_precedent(self, precedent_id: int) -> Precedent:
        with self.session() as s:
            p = s.get(Precedent, precedent_id)
            if p is None:
                raise KeyError(f"no precedent {precedent_id}")
            return p

    def list_precedents(self, status: str | None = None) -> list[Precedent]:
        with self.session() as s:
            q = select(Precedent).order_by(Precedent.id)
            if status:
                q = q.where(Precedent.status == status)
            return list(s.scalars(q))

    def set_status(self, precedent_id: int, status: str, actor: str, *, allowed_from: tuple[str, ...],
                   gate_result: dict | None = None) -> Precedent:
        with self.session() as s:
            p = s.get(Precedent, precedent_id)
            if p is None:
                raise KeyError(f"no precedent {precedent_id}")
            if p.status not in allowed_from:
                raise ValueError(f"precedent {precedent_id} is {p.status}; {status} needs one of {allowed_from}")
            old, p.status, p.updated_at = p.status, status, _now()
            if status == STAGED:
                p.approved_by = actor
            if gate_result is not None:
                p.gate_result = gate_result
            self._audit(s, actor, f"precedent_{status}", "precedent", p.id,
                        {"from": old, "to": status, **({"gate": gate_result} if gate_result else {})})
            s.commit()
            return p


    # -- traces -----------------------------------------------------------
    # Traces are run logs, not decisions, so they are not written to the audit log.

    def save_trace(self, name: str, order_id: str | None, events: list[dict]) -> None:
        with self.session() as s:
            s.add(Trace(name=name, order_id=order_id, events=events))
            s.commit()

    def list_trace_names(self, limit: int = 50) -> list[str]:
        with self.session() as s:
            return list(s.scalars(select(Trace.name).order_by(Trace.name.desc()).limit(limit)))

    def get_trace(self, name: str) -> list[dict] | None:
        with self.session() as s:
            t = s.scalars(select(Trace).where(Trace.name == name)).first()
            return t.events if t else None


AUDIT_LOCK_KEY = 7310  # any constant; only audit writes take this advisory lock


def _make_engine(url: str):
    """SQLite as is. Postgres gets the psycopg driver and, behind a transaction pooler
    (Supabase port 6543), no client-side pool and no prepared statements, which such a
    pooler cannot keep across transactions."""
    u = make_url(url)
    if u.drivername in ("postgres", "postgresql"):
        u = u.set(drivername="postgresql+psycopg")
    if not u.drivername.startswith("postgresql"):
        return create_engine(u, future=True)
    if u.port == 6543:
        return create_engine(u, future=True, poolclass=NullPool, connect_args={"prepare_threshold": None})
    return create_engine(u, future=True, pool_pre_ping=True)


def case_family(dispute_id: str) -> str:
    """Base case id shared by a case and its evaluation variants: NS-002-C1 -> NS-002."""
    parts = dispute_id.split("-")
    return "-".join(parts[:2]) if len(parts) > 2 else dispute_id


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store
