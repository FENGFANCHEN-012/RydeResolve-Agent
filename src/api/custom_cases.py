"""Cases built in the dashboard's case editor (POST /api/custom-cases).

The editor sends a dataset in the same format as the case files in data/mock_disputes, plus its
photos. The server keeps only the known sections, assigns the ids itself, writes every photo again
(re-encoded JPEG, with the capture time and place the editor set, the photo's own tags, or none),
and saves the case as data/custom_cases/<id>.json. The case index rescans that folder on every
request, so the new case is listed and runs through the normal pipeline at once. Answer keys are
never accepted: a built case has no expected outcome.
"""
from __future__ import annotations

import io
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from src.agents.photo_checks import IMAGE_EXTS, photo_path
from src.agents.photo_stamp import stamped_jpeg
from src.api.uploads import read_upload, validate_count, validate_filename

ROOT = Path(__file__).resolve().parents[2]
CASE_DIR = ROOT / "data" / "custom_cases"
PHOTO_DIR = ROOT / "data" / "evidence" / "custom"
SGT = timezone(timedelta(hours=8))

MAX_CASE_BYTES = 256 * 1024     # the dataset JSON
MAX_CASES = 300                 # keeps a public demo from filling the disk
MAX_PHOTOS = 8                  # existing + new, per case
MAX_LIST = 200                  # chat lines, app events, GPS points
MAX_TEXT = 4000                 # any one string
UPLOAD_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SECTIONS = ("dispute_ticket", "rider_profile", "driver_profile", "trip_data", "gps_telemetry",
            "chat_logs", "app_events", "platform_policy", "cancellation_policy", "payment_data",
            "pair_history")
TIME_MODES = ("set", "own", "none", "copy")


def _bad(msg: str):
    raise HTTPException(400, msg)


def _check_values(v, where: str, depth: int = 0):
    """Plain JSON only, bounded in depth, list length and string length."""
    if depth > 6:
        _bad(f"{where} is nested too deeply.")
    if isinstance(v, str):
        if len(v) > MAX_TEXT:
            _bad(f"{where} is longer than {MAX_TEXT} characters.")
    elif isinstance(v, list):
        if len(v) > MAX_LIST:
            _bad(f"{where} has more than {MAX_LIST} items.")
        for i, x in enumerate(v):
            _check_values(x, f"{where}[{i}]", depth + 1)
    elif isinstance(v, dict):
        if len(v) > MAX_LIST:
            _bad(f"{where} has more than {MAX_LIST} fields.")
        for k, x in v.items():
            if not isinstance(k, str) or len(k) > 100:
                _bad(f"{where} has an invalid field name.")
            _check_values(x, f"{where}.{k}", depth + 1)
    elif not (v is None or isinstance(v, (bool, int, float))):
        _bad(f"{where} has an unsupported value.")


def clean_dataset(raw: str) -> dict:
    """The submitted dataset, reduced to the known sections and checked."""
    if len(raw.encode("utf-8")) > MAX_CASE_BYTES:
        raise HTTPException(413, "The case data is too large.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _bad("The case data is not valid JSON.")
    if not isinstance(data, dict):
        _bad("The case data must be an object.")
    case = {k: data[k] for k in SECTIONS if data.get(k) is not None}
    for k, v in case.items():
        _check_values(v, k)
    ticket, trip = case.get("dispute_ticket"), case.get("trip_data")
    if not isinstance(ticket, dict) or not isinstance(trip, dict):
        _bad("A case needs a complaint (dispute_ticket) and a trip (trip_data).")
    for k in ("rider_profile", "driver_profile", "platform_policy", "cancellation_policy", "payment_data"):
        if k in case and not isinstance(case[k], dict):
            _bad(f"{k} must be an object.")
    for k in ("gps_telemetry", "chat_logs", "app_events"):
        if k in case and not isinstance(case[k], list):
            _bad(f"{k} must be a list.")
    if ticket.get("filed_by") not in ("rider", "driver"):
        _bad("Filed by must be rider or driver.")
    if not str(ticket.get("description") or "").strip():
        _bad("The complaint text is empty.")
    if not str(ticket.get("dispute_type") or "").strip():
        _bad("Choose a dispute type.")
    return case


def _time(value, where: str) -> str | None:
    if value in (None, ""):
        return None
    try:
        t = datetime.fromisoformat(str(value))
    except ValueError:
        _bad(f"{where} is not a valid time.")
    return (t if t.tzinfo else t.replace(tzinfo=SGT)).isoformat()


def _gps(value, where: str):
    if value in (None, "", []):
        return None
    try:
        lat, lng = float(value[0]), float(value[1])
    except (TypeError, ValueError, IndexError):
        _bad(f"{where} needs a latitude and a longitude.")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        _bad(f"{where} is outside the map.")
    return [lat, lng]


def _existing_photo(url: str) -> Path:
    path = photo_path(url)
    allowed = (ROOT / "data" / "evidence", ROOT / "data" / "evidence_samples")
    if (path is None or path.suffix.lower() not in IMAGE_EXTS or not path.is_file()
            or not any(a in path.parents for a in allowed)):
        _bad("A kept photo is not one of the case photos on the server.")
    return path


def _write_photo(src: bytes | Path, dst: Path, meta: dict, n: int) -> None:
    mode = meta.get("time_mode") or "set"
    if mode not in TIME_MODES:
        _bad(f"Photo {n}: unknown time mode.")
    if mode == "copy":
        if not isinstance(src, Path):
            _bad(f"Photo {n}: only a kept photo can be copied byte for byte.")
        shutil.copyfile(src, dst)
        return
    try:
        img = Image.open(src if isinstance(src, Path) else io.BytesIO(src))
        img.load()
    except (UnidentifiedImageError, OSError):
        _bad(f"Photo {n} is not a readable image.")
    if img.width * img.height > 40_000_000:
        _bad(f"Photo {n} is too large.")
    own = img.getexif() if mode == "own" else None
    taken_at = _time(meta.get("taken_at"), f"Photo {n} capture time") if mode == "set" else None
    gps = _gps(meta.get("gps"), f"Photo {n} GPS") if mode == "set" else None
    software = (str(meta.get("software") or "")[:100] or None) if mode == "set" else None
    dst.write_bytes(stamped_jpeg(img, taken_at, gps, software, base_exif=own))


async def save_case(raw_case: str, raw_photos: str, files: list[UploadFile], created_by: str) -> dict:
    """Check and store one built case; returns its ids."""
    case = clean_dataset(raw_case)
    try:
        photos = json.loads(raw_photos or "[]")
    except json.JSONDecodeError:
        _bad("The photo list is not valid JSON.")
    if not isinstance(photos, list) or len(photos) > MAX_PHOTOS:
        _bad(f"A case can have at most {MAX_PHOTOS} photos.")
    validate_count(files)
    for f in files:
        validate_filename(f.filename, UPLOAD_EXTS)
    uploads = [await read_upload(f) for f in files]
    if CASE_DIR.exists() and len(list(CASE_DIR.glob("*.json"))) >= MAX_CASES:
        raise HTTPException(409, "The demo has reached its limit of built cases.")

    short = uuid4().hex[:6].upper()
    case_id, trip_id = f"CU-{short}", f"RYDE-CU-{short}"
    ticket, trip = case["dispute_ticket"], case["trip_data"]
    ticket.update(dispute_id=case_id, trip_id=trip_id)
    ticket["filed_at"] = _time(ticket.get("filed_at"), "Filed at") or datetime.now(SGT).isoformat(timespec="seconds")
    ticket.setdefault("status", "open")
    trip["trip_id"] = trip_id
    if isinstance(case.get("payment_data"), dict) and "trip_id" in case["payment_data"]:
        case["payment_data"]["trip_id"] = trip_id

    photo_dir = PHOTO_DIR / case_id
    photo_dir.mkdir(parents=True, exist_ok=True)
    evidence = []
    try:
        for n, meta in enumerate(photos, 1):
            if not isinstance(meta, dict):
                _bad(f"Photo {n}: invalid entry.")
            source = str(meta.get("source") or "")
            if source.startswith("upload:"):
                try:
                    src = uploads[int(source[7:])]
                except (ValueError, IndexError):
                    _bad(f"Photo {n}: its file was not uploaded.")
            elif source.startswith("existing:"):
                src = _existing_photo(source[9:])
            else:
                _bad(f"Photo {n}: unknown source.")
            dst = photo_dir / f"photo{n}.jpg"
            _write_photo(src, dst, meta, n)
            by = meta.get("uploaded_by") if meta.get("uploaded_by") in ("rider", "driver") else ticket["filed_by"]
            evidence.append({
                "evidence_type": "photo",
                "file_url": f"data/evidence/custom/{case_id}/{dst.name}",
                "uploaded_by": by,
                "uploaded_at": _time(meta.get("uploaded_at"), f"Photo {n} upload time") or ticket["filed_at"],
                "description": str(meta.get("description") or "")[:500],
            })
    except Exception:
        shutil.rmtree(photo_dir, ignore_errors=True)
        raise
    if not evidence:
        shutil.rmtree(photo_dir, ignore_errors=True)
    case["evidence"] = evidence
    case["_custom"] = {"created_by": created_by, "created_at": datetime.now(SGT).isoformat(timespec="seconds")}

    CASE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CASE_DIR / f".{case_id}.tmp"
    tmp.write_text(json.dumps(case, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, CASE_DIR / f"{case_id}.json")
    return {"order_id": trip_id, "dispute_id": case_id, "photos": len(evidence)}


def rule_texts() -> dict:
    """Scope text for each known case rule key, for the editor's rule rows."""
    path = ROOT / "data" / "policies" / "case_rule_texts.json"
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
