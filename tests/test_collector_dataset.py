"""
Tests for CollectorAgent dataset input (data/Dispute_format/*.md).
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.collector import CollectorAgent, DisputeType

DATASET_DIR = Path(__file__).resolve().parent.parent / "data" / "Dispute_format"
DISP_002 = next(DATASET_DIR.glob("*DISP-002*.md"))


@pytest.mark.asyncio
async def test_disp002_markdown_maps_to_context():
    ctx = await CollectorAgent().collect_from_dataset(DISP_002)

    assert ctx.dispute_id == "DISP-002"
    assert ctx.order_id == "TRIP-2026-09945"
    assert ctx.type == DisputeType.NO_SHOW
    assert ctx.reporter == "passenger"  # dataset says "rider"
    assert ctx.submitted_at == "2026-09-13T09:20:00+08:00"
    assert "Tiong Bahru Plaza" in ctx.description

    assert ctx.trip["cancellation_reason"] == "rider_no_show"
    assert ctx.payment == {
        "cancellation_fee": 5.0,
        "total_fare": 5.0,
        "payment_method": "e-wallet",
    }
    assert ctx.rider_profile["rating"] == 3.9
    assert ctx.driver_profile["rating"] == 4.9
    assert ctx.platform_policy["free_wait_time_min"] == 5
    assert len(ctx.app_events) == 10


@pytest.mark.asyncio
async def test_disp002_chat_and_gps_normalized():
    ctx = await CollectorAgent().collect_from_dataset(DISP_002)

    assert len(ctx.chat_log) == 6
    call = ctx.chat_log[2]
    assert call["sender"] == "driver"
    assert call["message_type"] == "call"
    assert "not answered" in call["message"]

    assert len(ctx.gps_trace) == 8
    arrived = ctx.gps_trace[4]
    assert arrived["latitude"] == 1.2847 and arrived["longitude"] == 103.8382
    assert arrived["status"] == "arrived"


@pytest.mark.asyncio
async def test_answer_key_never_reaches_context():
    """The markdown's 'Expected ruling' prose and any expected_* JSON key must be dropped."""
    ctx = await CollectorAgent().collect_from_dataset(DISP_002)
    dumped = json.dumps(ctx.model_dump()).lower()
    assert "expected" not in dumped  # "Expected ruling: ... UPHELD"
    assert "evidence summary" not in dumped
    assert "pattern of disputed no-shows" not in dumped

    data = CollectorAgent.load_dispute_dataset(DISP_002)
    data["dispute_ticket"]["expected_outcome"] = "upheld"
    ctx2 = await CollectorAgent().collect_from_dataset(data)
    assert "expected_outcome" not in json.dumps(ctx2.model_dump())


@pytest.mark.asyncio
async def test_json_file_and_unknown_type(tmp_path):
    data = CollectorAgent.load_dispute_dataset(DISP_002)
    data["dispute_ticket"]["dispute_type"] = "something_new"
    data["dispute_ticket"]["filed_by"] = "driver"
    f = tmp_path / "d.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    ctx = await CollectorAgent().collect_from_dataset(str(f))
    assert ctx.type is None  # left for the Classifier to decide
    assert ctx.reporter == "driver"


def test_markdown_without_json_block_raises(tmp_path):
    f = tmp_path / "bad.md"
    f.write_text("# no json here", encoding="utf-8")
    with pytest.raises(ValueError):
        CollectorAgent.load_dispute_dataset(f)


# ---------------------------------------------------------------------- #
# collect(order_id): platform lookup must never invent data
# ---------------------------------------------------------------------- #

MOCK_DIR = Path(__file__).resolve().parent.parent / "data" / "mock_disputes"


@pytest.mark.asyncio
async def test_mock_no_show_is_not_turned_into_completed_trip():
    ctx = await CollectorAgent().collect("Driver never came.", "RYDE-DEMO-003")

    assert ctx.dispute_id == "NS-001"
    assert ctx.type == DisputeType.NO_SHOW
    assert ctx.description == "Driver never came."  # user's report wins
    assert ctx.trip["driver_arrival_time"] is None  # driver never arrived; not filled in
    assert "status" not in ctx.trip  # no invented "completed"
    assert ctx.payment == {  # derived from trip_data, no GST added
        "cancellation_fee": 8.0, "total_fare": 8.0, "payment_method": "credit_card",
    }
    assert ctx.gps_trace[0] == {
        "timestamp": "2026-09-21T08:53:00+08:00", "latitude": 1.3072, "longitude": 103.8630,
        "speed_kmh": 30, "status": "en_route",
    }  # no random heading / accuracy
    assert "phone" not in ctx.rider_profile  # no fake phones
    assert ctx.data_completeness["source"] == "mock_disputes/no_show_01.json"
    assert ctx.data_completeness["missing"] == []


@pytest.mark.asyncio
async def test_collect_is_deterministic():
    a = await CollectorAgent().collect("x", "RYDE-DEMO-001")
    b = await CollectorAgent().collect("x", "RYDE-DEMO-001")
    a.submitted_at = b.submitted_at = None
    assert a.model_dump() == b.model_dump()


@pytest.mark.asyncio
async def test_every_value_comes_from_the_file():
    """Every leaf value in the context's platform data must exist in the source file."""
    def leaves(o):
        if isinstance(o, dict):
            for v in o.values():
                yield from leaves(v)
        elif isinstance(o, list):
            for v in o:
                yield from leaves(v)
        else:
            yield o

    for f in MOCK_DIR.glob("*.json"):
        source = set(map(json.dumps, leaves(json.loads(f.read_text(encoding="utf-8")))))
        order_id = json.loads(f.read_text(encoding="utf-8"))["dispute_ticket"]["trip_id"]
        ctx = await CollectorAgent().collect("", order_id)
        platform = {k: getattr(ctx, k) for k in
                    ("trip", "payment", "chat_log", "gps_trace", "rider_profile", "driver_profile")}
        invented = set(map(json.dumps, leaves(platform))) - source
        assert invented == set(), f"{f.name}: {invented}"


_DISP002_SECTIONS = {"dispute_ticket", "rider_profile", "driver_profile", "trip_data",
                     "gps_telemetry", "chat_logs", "app_events"}
_VERDICTS = {"upheld", "partially_upheld", "dismissed", None}  # None = human review


@pytest.mark.parametrize("path", sorted(MOCK_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_mock_files_follow_disp002_format(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert _DISP002_SECTIONS <= set(data), _DISP002_SECTIONS - set(data)
    assert "cancellation_policy" in data or "platform_policy" in data
    ticket, trip = data["dispute_ticket"], data["trip_data"]
    for key in ("dispute_id", "trip_id", "filed_by", "dispute_type", "description",
                "filed_at", "status"):
        assert key in ticket, key
    assert trip["trip_id"] == ticket["trip_id"]
    assert trip["rider_id"] == data["rider_profile"]["rider_id"]
    assert trip["driver_id"] == data["driver_profile"]["driver_id"]
    for p in data["gps_telemetry"]:
        assert set(p) == {"timestamp", "lat", "lng", "speed_kmh", "status"}
    # Answer key for evaluation only
    expected = data["expected_outcome"]
    assert expected["verdict"] in _VERDICTS
    assert isinstance(expected["requires_human_review"], bool)
    assert (expected["verdict"] is None) == expected["requires_human_review"]


@pytest.mark.asyncio
async def test_answer_key_stripped_from_mock_files():
    ctx = await CollectorAgent().collect("", "RYDE-DEMO-003")
    assert "expected" not in json.dumps(ctx.model_dump()).lower()


@pytest.mark.asyncio
async def test_disp002_found_by_order_id():
    ctx = await CollectorAgent().collect("", "TRIP-2026-09945")
    assert ctx.dispute_id == "DISP-002"
    assert len(ctx.app_events) == 10
    assert ctx.data_completeness["missing"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("order_id", ["ORDER-999", "DRP-anything", "RYDE-DEMO-999"])
async def test_unknown_order_returns_no_fake_data(order_id):
    ctx = await CollectorAgent().collect("some complaint", order_id)
    assert ctx.trip is None and ctx.payment is None and ctx.gps_trace is None
    assert ctx.data_completeness["source"] is None
    assert "trip" in ctx.data_completeness["missing"]
