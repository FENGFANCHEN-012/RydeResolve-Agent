"""Build the photo files a test case refers to, from the photo library.

    python scripts/stamp_case_photos.py data/eval_cases/images

Each case's "_photo_stamps" says, per photo file, which library photo to use and what capture
time, GPS position and software tag to write into its EXIF (or "copy_of" another case's photo,
byte for byte). The files land in data/evidence_samples/cases/<case id>/. Cases are processed in
id order so a copy_of target already exists.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.agents.photo_stamp import stamp  # noqa: E402

LIBRARY = ROOT / "data" / "evidence_samples" / "library"
CASES = ROOT / "data" / "evidence_samples" / "cases"


def main(folder: str) -> None:
    for case in sorted(Path(folder).glob("*.json")):
        data = json.loads(case.read_text(encoding="utf-8"))
        cid = (data.get("dispute_ticket") or {}).get("dispute_id") or case.stem
        for name, spec in (data.get("_photo_stamps") or {}).items():
            dst = CASES / cid / name
            if spec.get("copy_of"):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(CASES / spec["copy_of"], dst)
                print(f"{cid}/{name}: copy of {spec['copy_of']}")
                continue
            src = LIBRARY / f"{str(spec['library']).removesuffix('.jpg')}.jpg"   # with or without the extension
            stamp(src, dst, spec.get("taken_at"), spec.get("gps"), spec.get("software"))
            print(f"{cid}/{name}: {spec['library']} taken {spec.get('taken_at')} gps {spec.get('gps')} "
                  f"software {spec.get('software')}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data" / "eval_cases" / "images"))
