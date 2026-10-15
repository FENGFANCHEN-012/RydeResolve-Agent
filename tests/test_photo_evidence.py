"""Photo evidence: code checks on capture time, place, editing and reuse (photo_checks), and the
vision model's view, which can only raise doubts (image_analyst)."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from src.agents import code_judge, image_analyst, photo_checks
from src.agents.collector import DisputeContext, EvidenceItem

TRIP = {"pickup_time": "2026-10-11T21:40:00+08:00", "dropoff_time": "2026-10-11T22:05:00+08:00",
        "dropoff_location": {"lat": 1.3240, "lng": 103.9300}}


def _deg(x):
    d = int(x); m = int((x - d) * 60); s = round(((x - d) * 60 - m) * 60, 2)
    return (d, m, s)


def make_photo(path, taken=None, offset=None, software=None, gps=None, colour=(120, 90, 60)):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (64, 48), colour)
    exif = Image.Exif()
    if software:
        exif[305] = software
    if taken or offset:
        sub = exif.get_ifd(0x8769)
        if taken:
            sub[36867] = taken
        if offset:
            sub[36881] = offset
    if gps:
        g = exif.get_ifd(0x8825)
        g[1], g[2], g[3], g[4] = "N", _deg(gps[0]), "E", _deg(gps[1])
    img.save(path, "JPEG", exif=exif)
    return path


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(photo_checks, "ROOT", tmp_path)
    monkeypatch.setattr(photo_checks, "EVIDENCE_DIRS", (tmp_path / "cases",))
    photo_checks._hash_index.cache_clear()
    return tmp_path


def ctx(*files, uploaded_at=None, policy=None):
    return DisputeContext(dispute_id="CF-T", reporter="driver", order_id="O-T", description="Rider spilled coffee",
                          trip=TRIP, platform_policy=policy,
                          evidence=[EvidenceItem(evidence_type="photo", description="spill", file_url=f,
                                                 uploaded_by="driver", uploaded_at=uploaded_at) for f in files])


def kinds(findings):
    return {f.id.split("[")[0]: f.kind for f in findings}


def test_photo_taken_after_dropoff_is_a_verified_fact(root):
    make_photo(root / "cases/CF-T/a.jpg", taken="2026:10:11 22:11:00")
    out = photo_checks.photo_checks(ctx("cases/CF-T/a.jpg"))
    assert kinds(out) == {"photo_checks.time": "fact"}
    assert "6 min after drop-off" in out[0].statement and out[0].sources[0] == "evidence[0]"


@pytest.mark.parametrize("taken,key", [
    ("2026:10:10 09:00:00", "photo_checks.before_trip"),   # a day before the trip
    ("2026:10:11 23:30:00", "photo_checks.late"),          # 85 min after drop-off, past 60
])
def test_photo_outside_the_trip_window_is_a_conflict_on_that_photo(root, taken, key):
    make_photo(root / "cases/CF-T/a.jpg", taken=taken)
    out = photo_checks.photo_checks(ctx("cases/CF-T/a.jpg"))
    assert kinds(out) == {key: "conflict"} and out[0].questioned == ["evidence[0]"]


def test_case_policy_sets_its_own_window(root):
    make_photo(root / "cases/CF-T/a.jpg", taken="2026:10:11 23:30:00")
    out = photo_checks.photo_checks(ctx("cases/CF-T/a.jpg", policy={"photo_window_after_dropoff_min": 120}))
    assert kinds(out) == {"photo_checks.time": "fact"}


def test_exif_offset_is_respected(root):
    # 14:11 UTC is 22:11 in Singapore
    make_photo(root / "cases/CF-T/a.jpg", taken="2026:10:11 14:11:00", offset="+00:00")
    assert kinds(photo_checks.photo_checks(ctx("cases/CF-T/a.jpg"))) == {"photo_checks.time": "fact"}


def test_no_capture_time_is_a_gap(root):
    make_photo(root / "cases/CF-T/a.jpg")
    assert kinds(photo_checks.photo_checks(ctx("cases/CF-T/a.jpg"))) == {"photo_checks.no_time": "gap"}


def test_missing_file_is_a_gap(root):
    assert kinds(photo_checks.photo_checks(ctx("cases/CF-T/nope.jpg"))) == {"photo_checks.unreadable": "gap"}


def test_editing_program_is_a_conflict(root):
    make_photo(root / "cases/CF-T/a.jpg", taken="2026:10:11 22:11:00", software="Adobe Photoshop 25.0")
    k = kinds(photo_checks.photo_checks(ctx("cases/CF-T/a.jpg")))
    assert k["photo_checks.edited"] == "conflict" and k["photo_checks.time"] == "fact"


def test_uploaded_before_taken_is_a_conflict(root):
    make_photo(root / "cases/CF-T/a.jpg", taken="2026:10:11 22:11:00")
    out = photo_checks.photo_checks(ctx("cases/CF-T/a.jpg", uploaded_at="2026-10-11T22:08:00+08:00"))
    assert kinds(out)["photo_checks.uploaded_before_taken"] == "conflict"


@pytest.mark.parametrize("gps,kind", [((1.3245, 103.9302), "fact"), ((1.3521, 103.8198), "conflict")])
def test_capture_place_against_dropoff(root, gps, kind):
    make_photo(root / "cases/CF-T/a.jpg", taken="2026:10:11 22:11:00", gps=gps)
    assert kinds(photo_checks.photo_checks(ctx("cases/CF-T/a.jpg")))["photo_checks.place"] == kind


def test_same_file_twice_in_one_case(root):
    make_photo(root / "cases/CF-T/a.jpg", taken="2026:10:11 22:11:00")
    (root / "cases/CF-T/b.jpg").write_bytes((root / "cases/CF-T/a.jpg").read_bytes())
    out = photo_checks.photo_checks(ctx("cases/CF-T/a.jpg", "cases/CF-T/b.jpg"))
    dup = [f for f in out if f.id.startswith("photo_checks.duplicate")]
    assert len(dup) == 1 and dup[0].questioned == ["evidence[1]"]


def test_photo_already_used_in_another_case(root):
    import os
    make_photo(root / "cases/OLD-1/x.jpg", taken="2026:10:11 22:11:00")
    (root / "cases/CF-T").mkdir(parents=True)
    (root / "cases/CF-T/a.jpg").write_bytes((root / "cases/OLD-1/x.jpg").read_bytes())
    os.utime(root / "cases/OLD-1/x.jpg", (1_000_000, 1_000_000))   # stored long before
    out = photo_checks.photo_checks(ctx("cases/CF-T/a.jpg"))
    reused = [f for f in out if f.id.startswith("photo_checks.reused")]
    assert reused and reused[0].value["other_cases"] == ["OLD-1"]


def test_the_first_case_to_hold_a_photo_is_not_doubted_by_a_later_copy(root):
    import os
    make_photo(root / "cases/CF-T/a.jpg", taken="2026:10:11 22:11:00")
    (root / "cases/LATER-1").mkdir(parents=True)
    (root / "cases/LATER-1/x.jpg").write_bytes((root / "cases/CF-T/a.jpg").read_bytes())
    os.utime(root / "cases/CF-T/a.jpg", (1_000_000, 1_000_000))   # ours came first
    out = photo_checks.photo_checks(ctx("cases/CF-T/a.jpg"))
    assert not [f for f in out if f.id.startswith("photo_checks.reused")]


def test_no_photos_no_findings(root):
    assert photo_checks.photo_checks(ctx()) == []


def test_path_outside_the_repo_is_refused(root):
    assert photo_checks.photo_path("../../etc/passwd") is None


# ---- the vision model's view
@pytest.mark.parametrize("report,expected", [
    ({"scene": "car_interior", "mess_visible": True, "severity": "heavy", "matches_claim": "yes",
      "generation_or_editing_signs": []}, set()),
    ({"scene": "car_interior", "mess_visible": False, "severity": "none", "matches_claim": "no",
      "generation_or_editing_signs": []}, {"image_analysis.no_mess", "image_analysis.mismatch"}),
    ({"scene": "not_a_car", "mess_visible": True, "severity": "moderate", "matches_claim": "no",
      "generation_or_editing_signs": []}, {"image_analysis.not_a_car", "image_analysis.mismatch"}),
    ({"scene": "car_interior", "mess_visible": True, "severity": "heavy", "matches_claim": "yes",
      "generation_or_editing_signs": ["warped seat stitching"]}, {"image_analysis.edited"}),
])
def test_model_view_only_ever_raises_doubts(report, expected):
    out = image_analyst.doubts(report, 0, "driver")
    assert {f.id.split("[")[0] for f in out} == expected
    assert all(f.kind == "conflict" and f.questioned == ["evidence[0]"] for f in out)


class FakeClient:
    def __init__(self, answer):
        async def create(**kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer))], usage=None)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def test_analyse_sends_the_image_and_keeps_the_report_unverified(root, monkeypatch):
    monkeypatch.setattr(image_analyst, "GROQ_API_KEY", "x")
    make_photo(root / "cases/CF-T/a.jpg", taken="2026:10:11 22:11:00")
    answer = json.dumps({"scene": "car_interior", "mess_visible": True, "severity": "heavy",
                         "matches_claim": "yes", "generation_or_editing_signs": [], "description": "coffee"})
    client = FakeClient("Here: " + answer)
    reports, findings = asyncio.run(image_analyst.analyse(ctx("cases/CF-T/a.jpg"), client=client))
    assert findings == [] and reports[0]["verified"] is False and reports[0]["severity"] == "heavy"
    parts = client.kwargs["messages"][0]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_analyse_without_a_key_marks_photos_unanalysed(root, monkeypatch):
    monkeypatch.setattr(image_analyst, "GROQ_API_KEY", "")
    make_photo(root / "cases/CF-T/a.jpg", taken="2026:10:11 22:11:00")
    reports, findings = asyncio.run(image_analyst.analyse(ctx("cases/CF-T/a.jpg")))
    assert reports == [] and [f.kind for f in findings] == ["gap"]


def test_unparseable_model_answer_is_a_gap(root, monkeypatch):
    monkeypatch.setattr(image_analyst, "GROQ_API_KEY", "x")
    make_photo(root / "cases/CF-T/a.jpg", taken="2026:10:11 22:11:00")
    reports, findings = asyncio.run(image_analyst.analyse(ctx("cases/CF-T/a.jpg"), client=FakeClient("no idea")))
    assert reports == [] and findings[0].id.startswith("image_analysis.failed")


# ---- the code Judge will not let a charge rest on a doubted photo
def test_code_judge_blocks_a_ruling_resting_on_a_doubted_photo():
    context = {"findings": [f.model_dump() for f in image_analyst.doubts(
        {"scene": "car_interior", "mess_visible": False, "severity": "none", "matches_claim": "no"}, 0, "driver")]}
    decision = SimpleNamespace(refund_amount=None, refund_calculation=None, decisive_facts=[
        {"fact": "photo shows a heavy coffee stain", "sources": ["evidence[0]"], "status": "verified"}])
    assert code_judge.check_facts(decision, context)
