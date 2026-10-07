"""People's history: prior counts + records, outcomes from rulings/reviews, only confirmed flags count."""
import pytest

from src.store import people
from src.store.db import Store

RIDER = {"rider_id": "R-1", "name": "Ann", "account_age_days": 100, "total_trips": 40, "avg_rating": 4.5,
         "dispute_history": {"total_disputes": 2, "upheld": 1, "rejected": 1},
         "fraud_flags": 1, "fraud_flag_details": "frequent_cancellations", "payment_method": "card"}
DRIVER = {"driver_id": "D-1", "name": "Bob", "account_age_days": 800, "total_trips": 1000, "avg_rating": 4.8,
          "dispute_history": {"total_disputes": 3, "upheld_against": 1, "rejected": 2}, "fraud_flags": 0,
          "vehicle": {"make": "Toyota", "model": "Prius"}}


@pytest.fixture
def store(tmp_path):
    return Store(f"sqlite:///{(tmp_path / 'p.db').as_posix()}")


def _case(store, dispute_id, filed_by="rider", trip_id="T-1", ratings=None):
    people.register_case(store, dispute_id=dispute_id, filed_by_role=filed_by,
                         trip={"trip_id": trip_id, "rider_id": "R-1", "driver_id": "D-1", "actual_fare": 12.0},
                         rider_profile=RIDER, driver_profile=DRIVER, dispute_type="fare_dispute",
                         description="x", filed_at="2026-10-01T09:00:00+08:00", ratings=ratings)


def test_prior_history_only(store):
    _case(store, "FD-1")
    d = people.get_user_history(store, "D-1", exclude_dispute_id="FD-1")
    assert d["complaints_received"] == 3 and d["complaints_received_upheld"] == 1
    assert d["total_trips"] == 1001 and d["avg_rating"] == 4.8 and d["vehicle"] == "Toyota Prius"
    assert d["joined_on"] == "2024-07-23"  # 800 days before the filing date
    r = people.get_user_history(store, "R-1", exclude_dispute_id="FD-1")
    assert r["complaints_filed"] == 2 and r["complaints_filed_upheld"] == 1
    assert r["fraud_confirmed"] == 1 and r["fraud_confirmed_details"] == ["frequent_cancellations"]
    assert "age" not in d and "age" not in r


def test_current_case_never_counts_as_its_own_history(store):
    _case(store, "FD-1")
    store.record_ruling(dispute_id="FD-1", status="resolved", verdict="upheld")
    assert people.get_user_history(store, "D-1", exclude_dispute_id="FD-1")["complaints_received"] == 3
    assert people.get_user_history(store, "D-1")["complaints_received"] == 4


def test_outcomes_ai_then_human_override_then_pending(store):
    _case(store, "FD-1")
    _case(store, "FD-2", trip_id="T-2")
    _case(store, "NS-3", filed_by="driver", trip_id="T-3")
    store.record_ruling(dispute_id="FD-1", status="resolved", verdict="partially_upheld")  # AI, counts
    r2 = store.record_ruling(dispute_id="FD-2", status="resolved", verdict="upheld")
    store.submit_review(r2.id, "hy", "override", "fare was correct", final_verdict="dismissed", final_refund=0)
    store.record_ruling(dispute_id="NS-3", status="escalated_to_human", verdict=None)  # waiting
    d = people.get_user_history(store, "D-1")
    assert d["complaints_received"] == 3 + 2 and d["complaints_received_upheld"] == 1 + 1
    assert d["complaints_filed"] == 1 and d["complaints_filed_upheld"] == 0
    assert d["disputes_awaiting_outcome"] == 1
    by_id = {x["dispute_id"]: x for x in d["recent_disputes"]}
    assert by_id["FD-2"]["outcome"] == "dismissed" and by_id["FD-2"]["decided_by"] == "human"
    r = people.get_user_history(store, "R-1")
    assert r["complaints_received"] == 1  # the driver's no-show complaint


def test_only_confirmed_flags_count(store):
    _case(store, "CR-1")
    f1 = people.raise_flag(store, user_id="R-1", signal="repeat_fee_refund_claims", detail="3 in 30d", dispute_id="CR-1")
    f2 = people.raise_flag(store, user_id="R-1", signal="collusion_offer_in_chat", detail="quote", dispute_id="CR-0")
    r = people.get_user_history(store, "R-1")
    assert r["fraud_confirmed"] == 1 and r["flags_pending_review"] == 2  # prior 1, both new still pending
    people.review_flag(store, f2.id, "hy", "confirmed", "chat shows the offer")
    people.review_flag(store, f1.id, "hy", "rejected", "claims were genuine")
    r = people.get_user_history(store, "R-1")
    assert r["fraud_confirmed"] == 2 and r["flags_pending_review"] == 0
    assert "collusion_offer_in_chat: chat shows the offer" in r["fraud_confirmed_details"]
    with pytest.raises(ValueError):
        people.review_flag(store, f1.id, "hy", "confirmed", "changed mind")  # decided flags are final
    with pytest.raises(ValueError):
        people.review_flag(store, f2.id, "hy", "confirmed", " ")
    assert store.verify_audit_chain() == (True, None)


def test_flags_of_the_current_case_are_left_out(store):
    _case(store, "CR-1")
    f = people.raise_flag(store, user_id="R-1", signal="s", detail="d", dispute_id="CR-1")
    people.review_flag(store, f.id, "hy", "confirmed", "r")
    assert people.get_user_history(store, "R-1", exclude_dispute_id="CR-1")["fraud_confirmed"] == 1
    assert people.get_user_history(store, "R-1")["fraud_confirmed"] == 2


def test_ratings_from_new_trips_join_the_average(store):
    _case(store, "FD-1", ratings={"rider_rating_of_driver": 1.0, "driver_rating_of_rider": 5.0})
    d = people.get_user_history(store, "D-1")
    assert d["avg_rating"] == round((4.8 * 1000 + 1.0) / 1001, 2)


def test_register_case_keeps_first_profile(store):
    _case(store, "FD-1")
    people.register_case(store, dispute_id="FD-9", filed_by_role="rider", trip={"trip_id": "T-9"},
                         rider_profile={**RIDER, "total_trips": 999}, driver_profile=DRIVER,
                         dispute_type=None, description=None, filed_at=None)
    assert people.get_user_history(store, "R-1")["total_trips"] == 40 + 2


def test_unknown_person(store):
    assert people.get_user_history(store, "D-404") is None


def test_api_history_and_flag_review(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from src.api import main as api_main
    from src.store import db as store_db
    st = Store(f"sqlite:///{(tmp_path / 'api.db').as_posix()}")
    monkeypatch.setattr(store_db, "_store", st)
    _case(st, "FD-1")
    c = TestClient(api_main.app, headers={"Authorization": "Bearer offline-admin"})
    assert c.get("/api/people/D-1/history").json()["complaints_received"] == 4
    assert c.get("/api/people/D-404/history").status_code == 404
    f = c.post("/api/flags", json={"user_id": "R-1", "signal": "s", "detail": "d", "raised_by": "fraud_agent"}).json()
    assert f["status"] == "pending" and f["user_role"] == "rider"
    assert c.post(f"/api/flags/{f['id']}/review", json={"reviewer": "hy", "decision": "maybe", "reason": "r"}).status_code == 409
    assert c.post(f"/api/flags/{f['id']}/review", json={"reviewer": "hy", "decision": "confirmed", "reason": "r"}).json()["status"] == "confirmed"
    assert [x["id"] for x in c.get("/api/flags?status=confirmed").json()] == [f["id"]]
