"""
Code checks on uploaded photos (no LLM). A Collector standard tool.

What code can establish about a photo, each finding citing evidence[i]:
- when it was taken (EXIF DateTimeOriginal) against the trip: before pickup, or long after
  drop-off, is a conflict on that photo; no capture time is a gap;
- where it was taken (EXIF GPS) against the drop-off point;
- that it was uploaded before it was taken (impossible: one of the two times is false);
- an editing or image-generation program named in the file (EXIF Software);
- the same picture submitted twice in this case, or already submitted in another case.

What is in the picture is not code's to say: the image analyst (src/agents/image_analyst.py)
describes it, and its view can only send a case to a person.
"""
import hashlib
import os
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from src.agents.collector_tools import _SGT, Finding, _hhmm, _km, _latlng, _minutes, _ts

ROOT = Path(__file__).resolve().parents[2]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
# Folders scanned for the same picture in another case (uploads and the test library)
EVIDENCE_DIRS = (ROOT / "data" / "evidence", ROOT / "data" / "evidence_samples" / "cases")
# A photo taken this long after drop-off no longer shows the state the trip left the car in.
# A case's policy can set its own window (photo_window_after_dropoff_min).
DEFAULT_WINDOW_MIN = 60
GPS_TOLERANCE_KM = 1.0
EDITORS = ("photoshop", "lightroom", "snapseed", "gimp", "picsart", "canva", "facetune", "meitu",
           "stable diffusion", "midjourney", "dall-e", "dall·e", "firefly", "generative", "ai generated")

_EXIF_DATETIME_ORIGINAL, _EXIF_OFFSET_ORIGINAL, _EXIF_DATETIME, _EXIF_SOFTWARE = 36867, 36881, 306, 305
_EXIF_IFD, _GPS_IFD = 0x8769, 0x8825


def photo_path(file_url: str) -> Path | None:
    """Local file behind an evidence URL ("/data/evidence/..." or a repo-relative path)."""
    if not file_url or "://" in file_url:
        return None
    p = (ROOT / file_url.lstrip("/")).resolve()
    return p if ROOT in p.parents and p.is_file() else None


def is_photo(item) -> bool:
    item = item.model_dump() if hasattr(item, "model_dump") else dict(item)
    ext = os.path.splitext(item.get("file_url") or "")[1].lower()
    return ext in IMAGE_EXTS or item.get("evidence_type") in ("photo", "screenshot")


def read_photo(path: Path) -> dict:
    """Hash and the EXIF fields the checks use. Missing fields are simply absent."""
    from PIL import Image

    data = path.read_bytes()
    out = {"sha256": hashlib.sha256(data).hexdigest()}
    with Image.open(path) as img:
        exif = img.getexif()
        sub = exif.get_ifd(_EXIF_IFD) if exif else {}
        raw = sub.get(_EXIF_DATETIME_ORIGINAL) or exif.get(_EXIF_DATETIME)
        if raw:
            out["taken_raw"] = str(raw)
            out["offset"] = str(sub.get(_EXIF_OFFSET_ORIGINAL) or "") or None
        if exif.get(_EXIF_SOFTWARE):
            out["software"] = str(exif.get(_EXIF_SOFTWARE)).strip()
        gps = exif.get_ifd(_GPS_IFD) if exif else {}
        if gps and 2 in gps and 4 in gps:
            def deg(v):
                d, m, s = (float(x) for x in v)
                return d + m / 60 + s / 3600
            lat, lng = deg(gps[2]), deg(gps[4])
            out["gps"] = (-lat if gps.get(1) == "S" else lat, -lng if gps.get(3) == "W" else lng)
    return out


def _taken_at(meta: dict) -> datetime | None:
    """EXIF capture time. EXIF has no time zone unless OffsetTimeOriginal is set; without it the
    phone's clock is taken to be Singapore time."""
    raw = meta.get("taken_raw")
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw.strip()[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    if meta.get("offset"):
        try:
            return datetime.fromisoformat(dt.strftime("%Y-%m-%dT%H:%M:%S") + meta["offset"])
        except ValueError:
            pass
    return dt.replace(tzinfo=_SGT)


@lru_cache(maxsize=1)
def _hash_index(stamp: int) -> dict[str, list[tuple[str, float]]]:
    """sha256 -> (case folder, file time) for every stored picture. `stamp` refreshes the cache."""
    index: dict[str, list[tuple[str, float]]] = {}
    for base in EVIDENCE_DIRS:
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                index.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), []).append(
                    (p.parent.name, p.stat().st_mtime))
    return index


def _other_cases_with(sha: str, path: Path) -> list[str]:
    """Other cases that already held this picture before this file was stored. Only the later
    submission is the reuse: the first case to receive a photo is not doubted because of a copy."""
    stamp = sum(int(b.stat().st_mtime) for b in EVIDENCE_DIRS if b.is_dir())
    own_time = path.stat().st_mtime
    return sorted({folder for folder, t in _hash_index(stamp).get(sha, [])
                   if folder != path.parent.name and t < own_time})


def _window(ctx) -> float:
    try:
        return float((ctx.platform_policy or {}).get("photo_window_after_dropoff_min", DEFAULT_WINDOW_MIN))
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_MIN


def _trip_times(ctx) -> tuple[tuple[datetime, str] | None, tuple[datetime, str] | None]:
    trip = ctx.trip or {}
    start = end = None
    for key in ("pickup_time", "trip_start_time"):
        if _ts(trip.get(key)):
            start = (_ts(trip.get(key)), f"trip.{key}")
            break
    if _ts(trip.get("dropoff_time")):
        end = (_ts(trip.get("dropoff_time")), "trip.dropoff_time")
    for i, e in enumerate(ctx.app_events or []):
        t = _ts(e.get("timestamp"))
        if t and start is None and e.get("event_type") in ("trip_started", "rider_picked_up"):
            start = (t, f"app_events[{i}]")
        if t and end is None and e.get("event_type") == "trip_completed":
            end = (t, f"app_events[{i}]")
    return start, end


def photo_checks(ctx) -> list[Finding]:
    """Capture time, place, editing and reuse of each uploaded photo."""
    findings: list[Finding] = []
    start, end = _trip_times(ctx)
    dropoff = _latlng((ctx.trip or {}).get("dropoff_location"))
    window = _window(ctx)
    seen: dict[str, int] = {}
    for i, item in enumerate(ctx.evidence or []):
        if not is_photo(item):
            continue
        src, who, n = f"evidence[{i}]", item.uploaded_by, i + 1
        path = photo_path(item.file_url)
        if path is None:
            findings.append(Finding(id=f"photo_checks.unreadable[{i}]", tool="photo_checks", kind="gap",
                                    statement=f"Photo {n} ({who}) could not be opened; nothing about it can be checked.",
                                    sources=[src]))
            continue
        try:
            meta = read_photo(path)
        except Exception as exc:
            findings.append(Finding(id=f"photo_checks.unreadable[{i}]", tool="photo_checks", kind="gap",
                                    statement=f"Photo {n} ({who}) is not a readable image: {exc}", sources=[src]))
            continue

        # Same picture twice in this case, or already used in another case
        if meta["sha256"] in seen:
            j = seen[meta["sha256"]]
            findings.append(Finding(
                id=f"photo_checks.duplicate[{i}]", tool="photo_checks", kind="conflict",
                statement=f"Photo {n} is the same file as photo {j + 1}; it is one photo, not two.",
                value={"sha256": meta["sha256"][:16]}, sources=[src, f"evidence[{j}]"], questioned=[src]))
        seen.setdefault(meta["sha256"], i)
        others = _other_cases_with(meta["sha256"], path)
        if others:
            findings.append(Finding(
                id=f"photo_checks.reused[{i}]", tool="photo_checks", kind="conflict",
                statement=f"Photo {n} ({who}) is the same file as a photo submitted in another case "
                          f"({', '.join(others[:3])}); it cannot show this trip.",
                value={"other_cases": others}, sources=[src], questioned=[src]))

        # Editing or generation program named in the file
        software = meta.get("software") or ""
        if any(e in software.lower() for e in EDITORS):
            findings.append(Finding(
                id=f"photo_checks.edited[{i}]", tool="photo_checks", kind="conflict",
                statement=f"Photo {n} ({who}) names the program \"{software}\" in its file data: it was "
                          f"edited or generated, so it may not show the car as it was.",
                value={"software": software}, sources=[src], questioned=[src]))

        # Capture time against the trip
        taken = _taken_at(meta)
        if taken is None:
            findings.append(Finding(
                id=f"photo_checks.no_time[{i}]", tool="photo_checks", kind="gap",
                statement=f"Photo {n} ({who}) carries no capture time, so when it was taken cannot be checked.",
                sources=[src]))
        else:
            value = {"taken_at": taken.isoformat()}
            if start and taken < start[0] - timedelta(minutes=1):
                findings.append(Finding(
                    id=f"photo_checks.before_trip[{i}]", tool="photo_checks", kind="conflict",
                    statement=f"Photo {n} ({who}) was taken {taken.astimezone(_SGT):%Y-%m-%d %H:%M}, "
                              f"{_minutes(taken, start[0]):g} min before the trip began ({_hhmm(start[0])}); "
                              f"it cannot show the state this trip left the car in.",
                    value=value, sources=[src, start[1]], questioned=[src]))
            elif end and _minutes(end[0], taken) > window:
                findings.append(Finding(
                    id=f"photo_checks.late[{i}]", tool="photo_checks", kind="conflict",
                    statement=f"Photo {n} ({who}) was taken {_minutes(end[0], taken):g} min after drop-off "
                              f"({_hhmm(end[0])}), past the {window:g}-min window; another rider or the driver "
                              f"may have used the car in between.",
                    value=value, sources=[src, end[1]], questioned=[src]))
            elif end:
                rel = _minutes(end[0], taken)
                when = f"{rel:g} min after drop-off" if rel >= 0 else f"during the trip, {-rel:g} min before drop-off"
                findings.append(Finding(
                    id=f"photo_checks.time[{i}]", tool="photo_checks", kind="fact",
                    statement=f"Photo {n} ({who}) was taken at {_hhmm(taken)}, {when} ({_hhmm(end[0])}), "
                              f"within the {window:g}-min window.",
                    value=value, sources=[src, end[1]]))
            uploaded = _ts(getattr(item, "uploaded_at", None))
            if uploaded and uploaded < taken - timedelta(minutes=1):
                findings.append(Finding(
                    id=f"photo_checks.uploaded_before_taken[{i}]", tool="photo_checks", kind="conflict",
                    statement=f"Photo {n} ({who}) was uploaded at {_hhmm(uploaded)}, before its recorded capture "
                              f"time {_hhmm(taken)}; one of the two times is false.",
                    value={**value, "uploaded_at": uploaded.isoformat()}, sources=[src], questioned=[src]))

        # Capture place against the drop-off point
        if meta.get("gps") and dropoff:
            km = _km(*meta["gps"], *dropoff)
            kind = "fact" if km <= GPS_TOLERANCE_KM else "conflict"
            findings.append(Finding(
                id=f"photo_checks.place[{i}]", tool="photo_checks", kind=kind,
                statement=(f"Photo {n} ({who}) was taken {km:g} km from the drop-off point."
                           + ("" if kind == "fact" else
                              f" That is more than {GPS_TOLERANCE_KM:g} km away; it may not show this car.")),
                value={"km_from_dropoff": km}, sources=[src, "trip.dropoff_location"],
                questioned=[] if kind == "fact" else [src]))
    return findings
