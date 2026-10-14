"""Case editor upload (POST /api/custom-cases): what is kept, the ids, the photo tags, the limits."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.agents.photo_checks import read_photo
from src.api import custom_cases, main
from src.integrations import ryde_api

SAMPLE = "data/evidence_samples/cases/IM-04/photo1.jpg"


def demo():
    return TestClient(main.app, headers={"Authorization": "Bearer offline-demo"})


@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(custom_cases, "CASE_DIR", tmp_path / "custom_cases")
    monkeypatch.setattr(custom_cases, "PHOTO_DIR", tmp_path / "evidence" / "custom")
    monkeypatch.setattr(ryde_api, "DEFAULT_DATA_DIRS", [tmp_path / "custom_cases"])
    return tmp_path


def case(**over):
    data = {
        "dispute_ticket": {"filed_by": "rider", "dispute_type": "no_show", "description": "Driver never came.",
                           "dispute_id": "IM-01", "filed_at": "2026-10-11T10:00:00+08:00"},
        "trip_data": {"trip_id": "RYDE-IM-001", "pickup_time": "2026-10-11T09:30:00+08:00"},
        "chat_logs": [{"timestamp": "2026-10-11T09:31:00+08:00", "sender": "rider", "type": "message", "content": "where?"}],
        "cancellation_policy": {"no_show_threshold_min": {"value": 5, "text": "Minutes ..."}},
        "expected_outcome": {"verdict": "upheld"}, "evidence": [{"file_url": "x.jpg"}], "_source": "x", "junk": 1,
    }
    data.update(over)
    return json.dumps(data)


def jpeg(color=(200, 50, 50)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(out, "JPEG")
    return out.getvalue()


def post(client, data, photos=(), files=()):
    return client.post("/api/custom-cases", data={"case": data, "photos": json.dumps(list(photos))},
                       files=[("files", f) for f in files])


def test_saved_case_gets_server_ids_and_only_known_sections(tmp_dirs):
    r = post(demo(), case())
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["dispute_id"].startswith("CU-") and out["order_id"] == "RYDE-" + out["dispute_id"]
    saved = json.loads((tmp_dirs / "custom_cases" / f"{out['dispute_id']}.json").read_text(encoding="utf-8"))
    assert saved["dispute_ticket"]["dispute_id"] == out["dispute_id"]
    assert saved["trip_data"]["trip_id"] == out["order_id"]
    assert "expected_outcome" not in saved and "junk" not in saved and "_source" not in saved
    assert saved["evidence"] == [] and saved["_custom"]["created_by"] == "demo"
    assert saved["cancellation_policy"]["no_show_threshold_min"]["value"] == 5
    # listed and loadable at once, like any case file
    listed = demo().get("/api/disputes/cases").json()["cases"]
    assert [c["order_id"] for c in listed] == [out["order_id"]]
    assert demo().get(f"/api/disputes/cases/{out['order_id']}").json()["expected_outcome"] is None


def test_photo_time_modes(tmp_dirs):
    photos = [
        {"source": "upload:0", "uploaded_by": "driver", "time_mode": "set", "taken_at": "2026-10-11T09:55:00+08:00",
         "gps": [1.3504, 103.8485], "software": "Adobe Photoshop", "description": "mud"},
        {"source": "upload:1", "time_mode": "none"},
        {"source": f"existing:{SAMPLE}", "time_mode": "own"},
        {"source": f"existing:{SAMPLE}", "time_mode": "copy"},
    ]
    r = post(demo(), case(), photos, [("a.jpg", jpeg()), ("b.png", jpeg())])
    assert r.status_code == 200, r.text
    cid = r.json()["dispute_id"]
    folder = tmp_dirs / "evidence" / "custom" / cid
    set_, none, own, copy = (read_photo(folder / f"photo{n}.jpg") for n in range(1, 5))
    assert set_["taken_raw"] == "2026:10:11 09:55:00" and set_["offset"] == "+08:00"
    assert abs(set_["gps"][0] - 1.3504) < 1e-4 and set_["software"] == "Adobe Photoshop"
    assert "taken_raw" not in none and "gps" not in none
    sample = read_photo(main.Path(main.BASE_DIR) / SAMPLE)
    assert own["taken_raw"] == sample["taken_raw"] and own["sha256"] != sample["sha256"]
    assert copy["sha256"] == sample["sha256"]
    saved = json.loads((tmp_dirs / "custom_cases" / f"{cid}.json").read_text(encoding="utf-8"))
    assert [e["file_url"] for e in saved["evidence"]] == [f"data/evidence/custom/{cid}/photo{n}.jpg" for n in range(1, 5)]
    assert saved["evidence"][0]["uploaded_by"] == "driver" and saved["evidence"][1]["uploaded_by"] == "rider"


@pytest.mark.parametrize("data,photos,files,status", [
    ("{not json", [], [], 400),
    (case(dispute_ticket={"filed_by": "rider", "dispute_type": "no_show", "description": " "}), [], [], 400),
    (case(dispute_ticket={"filed_by": "boss", "dispute_type": "no_show", "description": "x"}), [], [], 400),
    (case(trip_data=None), [], [], 400),
    (case(chat_logs="hi"), [], [], 400),
    (case(), [{"source": "existing:.env", "time_mode": "own"}], [], 400),
    (case(), [{"source": "existing:src/config.py", "time_mode": "copy"}], [], 400),
    (case(), [{"source": "existing:../outside.jpg", "time_mode": "own"}], [], 400),
    (case(), [{"source": "upload:0", "time_mode": "copy"}], [("a.jpg", jpeg())], 400),
    (case(), [{"source": "upload:3", "time_mode": "set"}], [("a.jpg", jpeg())], 400),
    (case(), [{"source": "upload:0", "time_mode": "set"}], [("a.jpg", b"not an image")], 400),
    (case(), [{"source": "upload:0", "time_mode": "set"}], [("a.gif", jpeg())], 400),
    (case(), [{"source": "upload:0", "time_mode": "set", "taken_at": "yesterday"}], [("a.jpg", jpeg())], 400),
    (case(), [{"source": "upload:0", "time_mode": "set", "gps": [95, 10]}], [("a.jpg", jpeg())], 400),
    (case(), [{"source": f"existing:{SAMPLE}", "time_mode": "own"}] * 9, [], 400),
    (case(chat_logs=[{"content": "x" * 5000}]), [], [], 400),
    (case(app_events=[{}] * 201), [], [], 400),
])
def test_bad_input_is_refused_and_nothing_is_kept(tmp_dirs, data, photos, files, status):
    assert post(demo(), data, photos, files).status_code == status
    assert not list((tmp_dirs / "custom_cases").glob("*.json")) if (tmp_dirs / "custom_cases").exists() else True
    assert not any((tmp_dirs / "evidence" / "custom").glob("*/*")) if (tmp_dirs / "evidence" / "custom").exists() else True


def test_case_limit(tmp_dirs, monkeypatch):
    monkeypatch.setattr(custom_cases, "MAX_CASES", 1)
    assert post(demo(), case()).status_code == 200
    assert post(demo(), case()).status_code == 409


def test_needs_an_access_code_and_serves_rule_texts():
    assert TestClient(main.app).post("/api/custom-cases", data={"case": case()}).status_code == 401
    texts = demo().get("/api/case-rule-texts").json()["texts"]
    assert "driver presses" in texts["cancellation_fee_after_wait"]
