"""
People, trips, disputes and fraud flags: the history an agent looks up about a rider or driver.

Tables (all in the same record store as rulings/reviews, see src/store/db.py)
- drivers / riders  one row per person. prior_* columns hold the history the platform had
                    before this system (imported from the dataset profiles); everything after
                    that is counted from the rows below, so totals always trace to records.
- trips             one row per trip (order), with both parties and their ratings of each other
- disputes          one row per dispute: who filed it, against whom, type, description.
                    Its outcome is not stored here; it is read from rulings and reviews.
- user_flags        fraud / bad-faith flags. Only status "confirmed" (set by a human) counts
                    toward a person's fraud total; the agent's own suspicions stay "pending"
                    and are listed but never counted (docs/09 principle 4).

No age or date of birth is stored: it must not feed any judgement about a person.
"""
from datetime import datetime, timedelta

from sqlalchemy import Float, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from src.store.db import Base, Review, Ruling, _now

RIDER, DRIVER = "rider", "driver"
FLAG_PENDING, FLAG_CONFIRMED, FLAG_REJECTED = "pending", "confirmed", "rejected"
UPHELD_VERDICTS = ("upheld", "partially_upheld")  # the filer's claim was found valid (fully or in part)


class _Person:
    name: Mapped[str | None] = mapped_column(String(120))
    joined_on: Mapped[str | None] = mapped_column(String(10))  # YYYY-MM-DD, platform sign-up
    # History before this system, from the platform profile
    prior_trips: Mapped[int] = mapped_column(Integer, default=0)
    prior_avg_rating: Mapped[float | None] = mapped_column(Float)
    prior_complaints_filed: Mapped[int] = mapped_column(Integer, default=0)
    prior_complaints_filed_upheld: Mapped[int] = mapped_column(Integer, default=0)
    prior_complaints_received: Mapped[int] = mapped_column(Integer, default=0)
    prior_complaints_received_upheld: Mapped[int] = mapped_column(Integer, default=0)
    prior_fraud_confirmed: Mapped[int] = mapped_column(Integer, default=0)
    prior_fraud_detail: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="live")  # seed / live
    created_at: Mapped[str] = mapped_column(String(32), default=_now)


class Driver(_Person, Base):
    __tablename__ = "drivers"
    driver_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    vehicle: Mapped[str | None] = mapped_column(String(120))


class Rider(_Person, Base):
    __tablename__ = "riders"
    rider_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    payment_method: Mapped[str | None] = mapped_column(String(40))


class Trip(Base):
    __tablename__ = "trips"
    trip_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rider_id: Mapped[str | None] = mapped_column(String(32), index=True)
    driver_id: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str | None] = mapped_column(String(40))
    fare: Mapped[float | None] = mapped_column(Float)
    trip_time: Mapped[str | None] = mapped_column(String(32))
    rider_rating_of_driver: Mapped[float | None] = mapped_column(Float)
    driver_rating_of_rider: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16), default="live")
    created_at: Mapped[str] = mapped_column(String(32), default=_now)


class Dispute(Base):
    __tablename__ = "disputes"
    dispute_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trip_id: Mapped[str | None] = mapped_column(String(64), index=True)
    filed_by_role: Mapped[str] = mapped_column(String(8))  # rider / driver
    filer_id: Mapped[str | None] = mapped_column(String(32), index=True)
    respondent_id: Mapped[str | None] = mapped_column(String(32), index=True)
    dispute_type: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    filed_at: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16), default="live")
    created_at: Mapped[str] = mapped_column(String(32), default=_now)


class UserFlag(Base):
    __tablename__ = "user_flags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_role: Mapped[str] = mapped_column(String(8))  # rider / driver
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    dispute_id: Mapped[str | None] = mapped_column(String(64), index=True)
    signal: Mapped[str] = mapped_column(String(64))  # e.g. repeat_fee_refund_claims, collusion_offer_in_chat
    detail: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=FLAG_PENDING, index=True)
    raised_by: Mapped[str] = mapped_column(String(64))  # "fraud_agent" or a reviewer
    reviewed_by: Mapped[str | None] = mapped_column(String(64))
    review_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32), default=_now)
    reviewed_at: Mapped[str | None] = mapped_column(String(32))


def _model(role: str):
    if role not in (RIDER, DRIVER):
        raise ValueError("role must be 'rider' or 'driver'")
    return (Rider, Rider.rider_id) if role == RIDER else (Driver, Driver.driver_id)


def role_of(user_id: str) -> str:
    """Dataset ids are R-... for riders and D-... for drivers."""
    return DRIVER if (user_id or "").upper().startswith("D") else RIDER


# -- writing -----------------------------------------------------------------

def person_from_profile(role: str, profile: dict, as_of: str | None = None, source: str = "live"):
    """Build a Driver/Rider row from a platform profile dict (the dataset format). The profile's
    dispute_history describes complaints the person FILED (riders) or RECEIVED (drivers)."""
    model, _ = _model(role)
    hist = profile.get("dispute_history") or {}
    joined = None
    if profile.get("account_age_days") is not None:
        try:
            ref = datetime.fromisoformat(as_of) if as_of else datetime.now()
            joined = (ref - timedelta(days=int(profile["account_age_days"]))).date().isoformat()
        except ValueError:
            pass
    detail = profile.get("fraud_flag_details")
    common = dict(
        name=profile.get("name"), joined_on=joined,
        prior_trips=int(profile.get("total_trips") or 0), prior_avg_rating=profile.get("avg_rating"),
        prior_fraud_confirmed=int(profile.get("fraud_flags") or 0),
        prior_fraud_detail=detail if isinstance(detail, str) or detail is None else str(detail),
        source=source,
    )
    if role == DRIVER:
        return model(driver_id=profile["driver_id"], vehicle=_vehicle_text(profile.get("vehicle")),
                     prior_complaints_received=int(hist.get("total_disputes") or 0),
                     prior_complaints_received_upheld=int(hist.get("upheld_against") or 0), **common)
    return model(rider_id=profile["rider_id"], payment_method=profile.get("payment_method"),
                 prior_complaints_filed=int(hist.get("total_disputes") or 0),
                 prior_complaints_filed_upheld=int(hist.get("upheld") or 0), **common)


def _vehicle_text(v) -> str | None:
    if isinstance(v, dict):
        return " ".join(str(v[k]) for k in ("make", "model", "plate", "color", "colour") if v.get(k)) or None
    return v


def register_case(store, *, dispute_id: str, filed_by_role: str, trip: dict | None,
                  rider_profile: dict | None, driver_profile: dict | None, dispute_type: str | None,
                  description: str | None, filed_at: str | None, ratings: dict | None = None,
                  source: str = "live") -> None:
    """Record the people, trip and dispute behind a case. Existing rows are left as they are:
    a person's prior history is fixed at the first sighting, and the rest is counted from records."""
    trip = trip or {}
    rider_id = (rider_profile or {}).get("rider_id") or trip.get("rider_id")
    driver_id = (driver_profile or {}).get("driver_id") or trip.get("driver_id")
    with store.session() as s:
        for role, pid, profile in ((RIDER, rider_id, rider_profile), (DRIVER, driver_id, driver_profile)):
            model, _ = _model(role)
            if pid and s.get(model, pid) is None:
                s.add(person_from_profile(role, profile, filed_at, source) if profile
                      else model(**{f"{role}_id": pid, "source": source}))
        trip_id = trip.get("trip_id")
        if trip_id and s.get(Trip, trip_id) is None:
            ratings = ratings or {}
            s.add(Trip(trip_id=trip_id, rider_id=rider_id, driver_id=driver_id,
                       status=trip.get("status") or trip.get("cancellation_reason"),
                       fare=trip.get("actual_fare") or trip.get("fare") or trip.get("total_fare"),
                       trip_time=trip.get("scheduled_time") or trip.get("pickup_time"),
                       rider_rating_of_driver=ratings.get("rider_rating_of_driver"),
                       driver_rating_of_rider=ratings.get("driver_rating_of_rider"), source=source))
        if dispute_id and s.get(Dispute, dispute_id) is None:
            filer, respondent = (rider_id, driver_id) if filed_by_role == RIDER else (driver_id, rider_id)
            s.add(Dispute(dispute_id=dispute_id, trip_id=trip_id, filed_by_role=filed_by_role,
                          filer_id=filer, respondent_id=respondent, dispute_type=dispute_type,
                          description=description, filed_at=filed_at, source=source))
        s.commit()


def raise_flag(store, *, user_id: str, signal: str, detail: str, dispute_id: str | None = None,
               raised_by: str = "fraud_agent") -> UserFlag:
    """A suspicion. It stays pending (and uncounted) until a person confirms it."""
    with store.session() as s:
        flag = UserFlag(user_role=role_of(user_id), user_id=user_id, dispute_id=dispute_id,
                        signal=signal, detail=detail, raised_by=raised_by)
        s.add(flag)
        s.flush()
        store._audit(s, raised_by, "flag_raised", "user_flag", flag.id,
                     {"user_id": user_id, "signal": signal, "dispute_id": dispute_id})
        s.commit()
        return flag


def review_flag(store, flag_id: int, reviewer: str, decision: str, reason: str) -> UserFlag:
    """A person confirms or rejects a flag. Only confirmed flags count toward fraud history."""
    if decision not in (FLAG_CONFIRMED, FLAG_REJECTED):
        raise ValueError("decision must be 'confirmed' or 'rejected'")
    if not reason.strip():
        raise ValueError("a flag review needs a reason")
    with store.session() as s:
        flag = s.get(UserFlag, flag_id)
        if flag is None:
            raise KeyError(f"no flag {flag_id}")
        if flag.status != FLAG_PENDING:
            raise ValueError(f"flag {flag_id} is already {flag.status}")
        flag.status, flag.reviewed_by, flag.review_reason, flag.reviewed_at = decision, reviewer, reason, _now()
        store._audit(s, reviewer, f"flag_{decision}", "user_flag", flag.id,
                     {"user_id": flag.user_id, "signal": flag.signal, "reason": reason})
        s.commit()
        return flag


# -- reading -----------------------------------------------------------------

def list_flags(store, status: str | None = None, user_id: str | None = None) -> list[UserFlag]:
    with store.session() as s:
        q = select(UserFlag).order_by(UserFlag.id)
        if status:
            q = q.where(UserFlag.status == status)
        if user_id:
            q = q.where(UserFlag.user_id == user_id)
        return list(s.scalars(q))


def dispute_outcome(s, dispute_id: str) -> dict:
    """Final outcome of a dispute: the latest human review wins; otherwise the latest ruling
    the system resolved on its own; a case still waiting for a person is 'pending'."""
    rulings = list(s.scalars(select(Ruling).where(Ruling.dispute_id == dispute_id).order_by(Ruling.id)))
    if not rulings:
        return {"outcome": "pending", "decided_by": None}
    review = s.scalars(select(Review).where(Review.ruling_id.in_([r.id for r in rulings]))
                       .order_by(Review.id.desc()).limit(1)).first()
    if review is not None:
        return {"outcome": review.final_verdict or "pending", "decided_by": "human",
                "refund_amount": review.final_refund, "reason": review.reason}
    last = rulings[-1]
    if last.status == "resolved" and last.verdict:
        return {"outcome": last.verdict, "decided_by": "ai", "refund_amount": last.refund_amount}
    return {"outcome": "pending", "decided_by": None}


def get_user_history(store, user_id: str, exclude_dispute_id: str | None = None,
                     recent_limit: int = 10) -> dict | None:
    """Everything known about one rider or driver, for an agent or a reviewer. The case being
    decided is left out (exclude_dispute_id), so a case never counts as its own history."""
    role = role_of(user_id)
    model, _ = _model(role)
    with store.session() as s:
        person = s.get(model, user_id)
        if person is None:
            return None
        q = select(Dispute).where((Dispute.filer_id == user_id) | (Dispute.respondent_id == user_id))
        if exclude_dispute_id:
            q = q.where(Dispute.dispute_id != exclude_dispute_id)
        disputes = list(s.scalars(q.order_by(Dispute.filed_at.desc(), Dispute.dispute_id)))
        filed = received = filed_upheld = received_upheld = pending = 0
        recent = []
        for d in disputes:
            out = dispute_outcome(s, d.dispute_id)
            upheld = out["outcome"] in UPHELD_VERDICTS
            pending += out["outcome"] == "pending"
            if d.filer_id == user_id:
                filed += 1
                filed_upheld += upheld
            else:
                received += 1
                received_upheld += upheld
            if len(recent) < recent_limit:
                recent.append({"dispute_id": d.dispute_id, "role": "filer" if d.filer_id == user_id else "respondent",
                               "type": d.dispute_type, "filed_at": d.filed_at,
                               "counterparty": d.respondent_id if d.filer_id == user_id else d.filer_id,
                               **{k: out.get(k) for k in ("outcome", "decided_by")}})

        flags = list(s.scalars(select(UserFlag).where(UserFlag.user_id == user_id).order_by(UserFlag.id)))
        if exclude_dispute_id:
            flags = [f for f in flags if f.dispute_id != exclude_dispute_id]
        confirmed = [f for f in flags if f.status == FLAG_CONFIRMED]

        trip_col = Trip.rider_id if role == RIDER else Trip.driver_id
        rating_col = Trip.driver_rating_of_rider if role == RIDER else Trip.rider_rating_of_driver
        trips = list(s.scalars(select(Trip).where(trip_col == user_id)))
        new_ratings = [getattr(t, rating_col.key) for t in trips if getattr(t, rating_col.key) is not None]

    n_prior = person.prior_trips or 0
    rated = (n_prior if person.prior_avg_rating is not None else 0) + len(new_ratings)
    rating = (round(((person.prior_avg_rating or 0) * (n_prior if person.prior_avg_rating is not None else 0)
                     + sum(new_ratings)) / rated, 2) if rated else None)
    return {
        "user_id": user_id,
        "role": role,
        "joined_on": person.joined_on,
        "total_trips": n_prior + len(trips),
        "avg_rating": rating,
        "complaints_received": person.prior_complaints_received + received,
        "complaints_received_upheld": person.prior_complaints_received_upheld + received_upheld,
        "complaints_filed": person.prior_complaints_filed + filed,
        "complaints_filed_upheld": person.prior_complaints_filed_upheld + filed_upheld,
        "disputes_awaiting_outcome": pending,
        "fraud_confirmed": person.prior_fraud_confirmed + len(confirmed),
        "fraud_confirmed_details": ([person.prior_fraud_detail] if person.prior_fraud_detail else [])
                                   + [f"{f.signal}: {f.review_reason}" for f in confirmed],
        "flags_pending_review": sum(f.status == FLAG_PENDING for f in flags),  # listed, never counted
        "recent_disputes": recent,
        **({"vehicle": person.vehicle} if role == DRIVER else {}),
    }
