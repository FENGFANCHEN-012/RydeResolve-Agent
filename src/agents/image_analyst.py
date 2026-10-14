"""
Image analyst: a vision model describes each uploaded photo (multi-modal stretch goal).

The model says what the picture shows: is it a car, is there a mess, how bad, does it match the
claim, any sign of editing or generation. Code (src/agents/photo_checks.py) has already checked
when and where the photo was taken.

The model's view is never a verified fact. It is kept as a report the advocates and the Judge
can read, and it becomes a finding only when it doubts the photo (not a car, no mess, does not
match the claim, looks edited or generated). Such a finding is a conflict on that photo, so the
code Judge will not let a ruling rest on it: the model can send a case to a person, never
approve a charge or a refund on its own. If the model cannot be reached, the photo is a gap.
"""
import base64
import io
import json
import logging
import os
import re
import time

from src.agents.collector_tools import Finding
from src.agents.photo_checks import is_photo, photo_path  # noqa: F401  (is_photo used by the workflow)
from src.config import GROQ_API_KEY, GROQ_BASE_URL
from src.core.trace import record_llm_call

logger = logging.getLogger(__name__)

VISION_MODEL = os.getenv("VISION_MODEL", "qwen/qwen3.8-27b")
MAX_SIDE = 1024

PROMPT = """You review one photo uploaded as evidence in a ride-hailing dispute in Singapore.
The claim it was uploaded for: {claim}
Uploaded by: {who}. Their caption: {caption}

Describe only what is visible. Do not guess what is outside the picture. Answer with JSON only:
{{"scene": "car_interior" | "car_boot" | "car_exterior" | "not_a_car" | "unclear",
  "mess_visible": true | false,
  "mess_type": "short words, or none",
  "severity": "none" | "light" | "moderate" | "heavy",
  "where": "which part of the car, or n/a",
  "matches_claim": "yes" | "partly" | "no" | "unclear",
  "generation_or_editing_signs": ["each visible sign the image was edited or AI-generated, empty if none"],
  "description": "one or two plain sentences"}}
"light" means wipeable in a minute (a few drops, crumbs); "moderate" needs proper cleaning;
"heavy" soaks into fabric or covers a large area."""


def _enabled() -> bool:
    return os.getenv("VISION_ENABLED", "1") != "0" and bool(GROQ_API_KEY)


def _jpeg_b64(path) -> str:
    from PIL import Image

    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _claim_text(context) -> str:
    parts = [(context.description or "").strip()]
    for e in context.app_events or []:
        if isinstance(e, dict) and "claim" in str(e.get("event_type", "")):
            parts.append(str(e.get("details") or ""))
    return " | ".join(p for p in parts if p)[:600] or "not stated"


def _parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError("no JSON in the model's answer")
    return json.loads(match.group(0))


async def _ask(client, prompt: str, b64: str, label: str) -> dict:
    t0 = time.perf_counter()
    try:
        resp = await client.chat.completions.create(
            model=VISION_MODEL, temperature=0, max_tokens=900,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}])
    except Exception as exc:
        record_llm_call(f"{prompt}\n[image: {label}]", None, int((time.perf_counter() - t0) * 1000),
                        error=str(exc), provider="groq", model=VISION_MODEL)
        raise
    text = resp.choices[0].message.content or ""
    usage = ({"prompt_tokens": resp.usage.prompt_tokens, "completion_tokens": resp.usage.completion_tokens}
             if getattr(resp, "usage", None) else None)
    record_llm_call(f"{prompt}\n[image: {label}]", text, int((time.perf_counter() - t0) * 1000),
                    usage=usage, provider="groq", model=VISION_MODEL)
    return _parse(text)


def doubts(report: dict, i: int, who: str) -> list[Finding]:
    """The model's doubts about photo i as conflicts on that photo. Agreement adds nothing."""
    src, n = f"evidence[{i}]", i + 1
    out = []

    def conflict(key: str, text: str):
        out.append(Finding(id=f"image_analysis.{key}[{i}]", tool="image_analysis", kind="conflict",
                           statement=f"Image analysis (model's view, not verified): photo {n} ({who}) {text}",
                           value={k: report.get(k) for k in ("scene", "mess_visible", "severity", "matches_claim")},
                           sources=[src], questioned=[src]))

    if report.get("scene") in ("not_a_car", "unclear"):
        conflict("not_a_car", f"does not clearly show a car: {report.get('description', '')}")
    elif report.get("mess_visible") is False or report.get("severity") == "none":
        conflict("no_mess", f"shows no visible mess: {report.get('description', '')}")
    if report.get("matches_claim") == "no":
        conflict("mismatch", f"does not match the claim: {report.get('description', '')}")
    signs = [s for s in report.get("generation_or_editing_signs") or [] if str(s).strip()]
    if signs:
        conflict("edited", f"shows signs of editing or generation: {'; '.join(map(str, signs))[:300]}")
    return out


async def analyse(context, client=None) -> tuple[list[dict], list[Finding]]:
    """One report per readable photo, and the findings its doubts raise."""
    photos = [(i, e) for i, e in enumerate(context.evidence or []) if is_photo(e) and photo_path(e.file_url)]
    if not photos:
        return [], []
    reports, findings = [], []
    if not _enabled():
        for i, e in photos:
            findings.append(Finding(id=f"image_analysis.unavailable[{i}]", tool="image_analysis", kind="gap",
                                    statement=f"Photo {i + 1} ({e.uploaded_by}) was not analysed: image analysis "
                                              f"is switched off or has no key.", sources=[f"evidence[{i}]"]))
        return reports, findings
    if client is None:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL, max_retries=3, timeout=90)
    claim = _claim_text(context)
    for i, e in photos:
        prompt = PROMPT.format(claim=claim, who=e.uploaded_by, caption=e.description or "none")
        try:
            report = await _ask(client, prompt, _jpeg_b64(photo_path(e.file_url)), f"evidence[{i}]")
        except Exception as exc:
            logger.warning("Image analysis failed for evidence[%s]: %s", i, exc)
            findings.append(Finding(id=f"image_analysis.failed[{i}]", tool="image_analysis", kind="gap",
                                    statement=f"Photo {i + 1} ({e.uploaded_by}) could not be analysed: {exc}"[:300],
                                    sources=[f"evidence[{i}]"]))
            continue
        reports.append({"evidence": f"evidence[{i}]", "uploaded_by": e.uploaded_by, "model": VISION_MODEL,
                        "verified": False, **report})
        findings.extend(doubts(report, i, e.uploaded_by))
    return reports, findings
