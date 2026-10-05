"""Record store: traces table and the engine settings used for a hosted Postgres (Supabase)."""
from sqlalchemy.pool import NullPool

from src.store.db import Store, _make_engine


def _store(tmp_path):
    return Store(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")


def test_trace_round_trip_and_newest_first(tmp_path):
    store = _store(tmp_path)
    store.save_trace("20261004-100000_A.json", "A", [{"type": "run_start", "n": 1}])
    store.save_trace("20261004-110000_B.json", "B", [{"type": "result", "text": "退款"}])
    assert store.list_trace_names() == ["20261004-110000_B.json", "20261004-100000_A.json"]
    assert store.get_trace("20261004-110000_B.json") == [{"type": "result", "text": "退款"}]
    assert store.get_trace("missing.json") is None


def test_traces_are_not_audited(tmp_path):
    store = _store(tmp_path)
    store.save_trace("t.json", "A", [])
    ok, bad = store.verify_audit_chain()
    assert ok and bad is None
    with store.session() as s:
        from src.store.db import AuditEntry
        assert s.query(AuditEntry).count() == 0


def test_plain_postgres_url_gets_psycopg_driver():
    engine = _make_engine("postgresql://u:p@db.example.supabase.co:5432/postgres")
    assert engine.url.drivername == "postgresql+psycopg"
    assert not isinstance(engine.pool, NullPool)


def test_transaction_pooler_uses_no_client_pool():
    engine = _make_engine("postgres://u:p@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres")
    assert engine.url.drivername == "postgresql+psycopg"
    assert isinstance(engine.pool, NullPool)


def test_sqlite_url_unchanged(tmp_path):
    engine = _make_engine(f"sqlite:///{(tmp_path / 'x.db').as_posix()}")
    assert engine.dialect.name == "sqlite"
