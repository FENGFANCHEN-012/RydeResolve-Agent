"""Write a photo's capture time, GPS position and software tag into its EXIF.

Used by scripts/stamp_case_photos.py (test-set photos) and by the case editor upload
(src/api/custom_cases.py), where the person building a case sets when and where each photo was
taken. The image is always re-encoded as JPEG, so nothing but the pixels and these tags survives.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from PIL import Image


def _dms(x: float):
    x = abs(x)
    d = int(x); m = int((x - d) * 60); s = round(((x - d) * 60 - m) * 60, 2)
    return (d, m, s)


def stamped_jpeg(img: Image.Image, taken_at: str | None, gps, software: str | None,
                 base_exif: Image.Exif | None = None) -> bytes:
    """JPEG bytes of img with the given tags. base_exif (the photo's own tags) is kept and only
    the given fields are overwritten; without it the photo carries only what is given here."""
    exif = base_exif if base_exif is not None else Image.Exif()
    if base_exif is None:
        exif[0x0110] = "Phone camera"  # Model
    if software:
        exif[305] = software
    if taken_at:
        t = datetime.fromisoformat(taken_at)
        sub = exif.get_ifd(0x8769)
        sub[36867] = t.strftime("%Y:%m:%d %H:%M:%S")
        if t.utcoffset() is not None:
            off = int(t.utcoffset().total_seconds() // 60)
            sub[36881] = f"{'+' if off >= 0 else '-'}{abs(off) // 60:02d}:{abs(off) % 60:02d}"
    if gps:
        g = exif.get_ifd(0x8825)
        g[1], g[2] = ("N" if gps[0] >= 0 else "S"), _dms(gps[0])
        g[3], g[4] = ("E" if gps[1] >= 0 else "W"), _dms(gps[1])
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=88, exif=exif)
    return out.getvalue()


def stamp(src: Path, dst: Path, taken_at: str | None, gps, software: str | None) -> None:
    """Library photo src -> dst with only the given tags."""
    with Image.open(src) as img:
        data = stamped_jpeg(img, taken_at, gps, software)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
