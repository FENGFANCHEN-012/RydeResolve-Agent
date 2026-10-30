"""
Ryde Platform API Client

Simulates Ryde's platform API. For the hackathon there is no live API, so order
data is read from dispute dataset files in the DISP-002 format:

    data/mock_disputes/*.json   synthetic demo disputes
    data/Dispute_format/*.md    sample datasets (JSON inside a ```json block)

Rule: this client only returns what a dataset file actually contains. It never
generates, randomises or fills in missing values. Missing data stays missing so
the agents (and the human reviewer) can see that it is missing.
"""
import os
import json
import logging
import re
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIRS = [
    Path(DATA_DIR) / "mock_disputes",
    Path(DATA_DIR) / "Dispute_format",
    Path(DATA_DIR) / "custom_cases",      # built in the dashboard's case editor
    # Extra folders the evaluation adds (e.g. held-out cases), kept out of the demo by default
    *[Path(DATA_DIR).parent / d for d in os.getenv("EXTRA_DISPUTE_DIRS", "").split(os.pathsep) if d],
]

# Keys that hold the expected verdict. Only evaluation may read them.
ANSWER_KEYS = {"expected_outcome", "expected_ruling", "expected_verdict", "ground_truth"}


def load_dispute_dataset(path: str | Path) -> dict:
    """
    Load one dispute dataset file.

    .json -> parsed directly.
    .md   -> only the first ```json fenced block is parsed. The prose around it
             ("Expected ruling", "Evidence Summary") is the answer key and is
             deliberately never read.
    """
    text = Path(path).read_text(encoding="utf-8")
    if str(path).lower().endswith(".md"):
        match = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
        if not match:
            raise ValueError(f"No ```json block found in {path}")
        text = match.group(1)
    return json.loads(text)


# The organisers' sample format (DISP-001, DISP-003) also carries someone's analysis next to the
# records: a recommended ruling, which side each item supports, "reroute justified". Those are
# conclusions, not evidence: the agents must reach them from the records, so they are removed
# with the answer keys. The records themselves (fare breakdown, surge log, recommended route,
# traffic incidents) are kept and mapped into the trip by the Collector.
ANALYSIS_SECTIONS = {"case_metadata", "recommended_ruling", "evidence_summary", "traffic_analysis",
                     "chat_log_analysis"}
# Free-text reasoning inside record sections: (section, key)
ANALYSIS_FIELDS = {("fare_breakdown", "notes"), ("fare_breakdown", "comparison"), ("optimal_route", "notes")}


def strip_answer_keys(obj):
    """Recursively drop answer-key fields so no agent can see the expected result; at the top
    level also drop the analysis sections and fields above."""
    if isinstance(obj, dict) and ("dispute_ticket" in obj or "trip_data" in obj):
        obj = {k: v for k, v in obj.items() if k not in ANALYSIS_SECTIONS}
        for section, key in ANALYSIS_FIELDS:
            if isinstance(obj.get(section), dict) and key in obj[section]:
                obj[section] = {k: v for k, v in obj[section].items() if k != key}
        # An incident feed's structured fields are records; its free-text description can carry
        # a judgment ("the driver's reroute ... was a reasonable alternative")
        if isinstance(obj.get("traffic_conditions"), list):
            obj["traffic_conditions"] = [{k: v for k, v in t.items() if k != "description"}
                                         if isinstance(t, dict) else t for t in obj["traffic_conditions"]]
    return _strip_keys(obj)


def _strip_keys(obj):
    if isinstance(obj, dict):
        return {k: _strip_keys(v) for k, v in obj.items() if k not in ANSWER_KEYS}
    if isinstance(obj, list):
        return [_strip_keys(v) for v in obj]
    return obj


def dataset_order_id(data: dict) -> Optional[str]:
    """The order (trip) id a dataset belongs to."""
    return (data.get("dispute_ticket") or {}).get("trip_id") or (
        data.get("trip_data") or {}
    ).get("trip_id")


# ---------------------------------------------------------------------------
# Real data: Ryde's API (D70)
# ---------------------------------------------------------------------------
# RYDE_API_MODE=dataset (default) reads the files above. RYDE_API_MODE=http reads one dispute from
# GET {RYDE_API_BASE_URL}{RYDE_API_DISPUTE_PATH} and the open-dispute list from RYDE_API_LIST_PATH,
# with "Authorization: Bearer {RYDE_API_KEY}". The payload is mapped to the DISP-002 shape every
# agent reads (map_ryde_payload), so nothing downstream changes; answer keys and analysis sections
# are stripped exactly as for files. Ryde has not published a dispute API: the base URL is a
# placeholder and RYDE_FIELD_MAP is the contract a real integration fills in. See the README,
# "Connecting real data".
RYDE_API_MODE = os.getenv("RYDE_API_MODE", "dataset").strip().lower()
RYDE_API_BASE_URL = os.getenv("RYDE_API_BASE_URL", "https://api.rydesharing.com/v1").rstrip("/")
RYDE_API_KEY = os.getenv("RYDE_API_KEY", "")
RYDE_API_DISPUTE_PATH = os.getenv("RYDE_API_DISPUTE_PATH", "/disputes/{order_id}")
RYDE_API_LIST_PATH = os.getenv("RYDE_API_LIST_PATH", "/disputes?status=open")
RYDE_API_TIMEOUT = float(os.getenv("RYDE_API_TIMEOUT", "15"))

# Ryde payload key -> DISP-002 key. Keys already in DISP-002 form pass unchanged.
RYDE_FIELD_MAP = {
    "dispute": "dispute_ticket", "ticket": "dispute_ticket",
    "rider": "rider_profile", "passenger": "rider_profile",
    "driver": "driver_profile",
    "trip": "trip_data", "order": "trip_data",
    "gps": "gps_telemetry", "telemetry": "gps_telemetry",
    "events": "app_events",
    "chat": "chat_logs", "messages": "chat_logs",
    "policy": "platform_policy",
    "payments": "payment_records",
}


class RydeAPIError(RuntimeError):
    """Ryde's API answered with an error or with something that is not a dispute."""


def map_ryde_payload(payload) -> dict:
    """Map one API payload to the DISP-002 shape. A payload wrapped in {"data": {...}} is unwrapped.
    Only keys are renamed: values are passed through, never filled in (the rule at the top of this
    file). Raises RydeAPIError when no trip id can be found, because every agent keys on it."""
    if not isinstance(payload, dict):
        raise RydeAPIError("Ryde API returned no dispute object")
    body = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    out = {RYDE_FIELD_MAP.get(k, k): v for k, v in body.items()}
    if not dataset_order_id(out):
        raise RydeAPIError("Ryde API dispute has no trip_id")
    return out


def _list_items(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("disputes", "data", "items", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise RydeAPIError("Ryde API dispute list has no list of disputes")


class RydeAPIClient:
    """
    Client for fetching order data from the Ryde platform.

    For the hackathon demo: looks the order up in the dataset folders.
    For production: would make authenticated HTTP requests to Ryde's API.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        data_dirs: list[str | Path] | None = None,
        mode: str | None = None,
        transport=None,
    ):
        self.api_key = api_key or RYDE_API_KEY or "demo-api-key"
        self.base_url = (base_url or RYDE_API_BASE_URL).rstrip("/")
        self.data_dirs = [Path(d) for d in (data_dirs or DEFAULT_DATA_DIRS)]
        self.mode = (mode or RYDE_API_MODE).strip().lower()   # "dataset" or "http"
        self._transport = transport                           # tests pass an httpx.MockTransport
        self._index: dict[str, Path] | None = None

    # -- Ryde's API (mode "http") -----------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    @staticmethod
    def _check(response, path: str):
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise RydeAPIError(f"Ryde API {path}: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise RydeAPIError(f"Ryde API {path}: not JSON") from exc

    async def _http_get(self, path: str):
        import httpx
        async with httpx.AsyncClient(base_url=self.base_url, timeout=RYDE_API_TIMEOUT,
                                     transport=self._transport) as client:
            return self._check(await client.get(path, headers=self._headers()), path)

    def _http_get_sync(self, path: str):
        import httpx
        with httpx.Client(base_url=self.base_url, timeout=RYDE_API_TIMEOUT, transport=self._transport) as client:
            return self._check(client.get(path, headers=self._headers()), path)

    @staticmethod
    def _summary(data: dict, source: str) -> dict:
        ticket = data.get("dispute_ticket") or {}
        return {
            "order_id": dataset_order_id(data),
            "dispute_id": ticket.get("dispute_id"),
            "dispute_type": ticket.get("dispute_type"),
            "filed_by": ticket.get("filed_by"),
            "description": ticket.get("description", ""),
            "source": source,
        }

    def _build_index(self) -> dict[str, Path]:
        """Map order id -> dataset file. Built once per client."""
        index: dict[str, Path] = {}
        for folder in self.data_dirs:
            if not folder.exists():
                continue
            for f in sorted([*folder.glob("*.json"), *folder.glob("*.md")]):
                if f.name.lower() == "readme.md":
                    continue
                try:
                    order_id = dataset_order_id(load_dispute_dataset(f))
                except Exception as exc:
                    logger.warning("Skipping unreadable dataset %s: %s", f, exc)
                    continue
                if not order_id:
                    logger.warning("Dataset %s has no trip_id; skipped", f)
                elif order_id in index:
                    logger.warning("Duplicate order %s in %s and %s", order_id, index[order_id], f)
                else:
                    index[order_id] = f
        return index

    async def get_order_dataset(self, order_id: str) -> Optional[dict]:
        """
        Return the dataset for an order, with answer keys removed, or None if
        the order is unknown. `_source` records which file it came from.
        """
        if self.mode == "http":
            payload = await self._http_get(RYDE_API_DISPUTE_PATH.format(order_id=order_id))
            if payload is None:
                return None
            data = strip_answer_keys(map_ryde_payload(payload))
            data["_source"] = f"ryde_api:{order_id}"
            return data
        if self._index is None:
            self._index = self._build_index()
        path = self._index.get(order_id)
        if path is None:
            return None
        data = strip_answer_keys(load_dispute_dataset(path))
        data["_source"] = f"{path.parent.name}/{path.name}"
        return data

    def list_orders(self) -> list[dict]:
        """Summary of every known order (for the dashboard's case picker). No answer keys."""
        if self.mode == "http":
            items = _list_items(self._http_get_sync(RYDE_API_LIST_PATH) or [])
            orders = []
            for item in items:
                try:
                    data = strip_answer_keys(map_ryde_payload(item))
                except RydeAPIError as exc:
                    logger.warning("Skipping a dispute from Ryde's API: %s", exc)
                    continue
                orders.append(self._summary(data, f"ryde_api:{dataset_order_id(data)}"))
            return orders
        if self._index is None:
            self._index = self._build_index()
        return [self._summary(load_dispute_dataset(path), f"{path.parent.name}/{path.name}")
                for path in self._index.values()]

    async def get_full_order_context(self, order_id: str) -> dict:
        """Order data for the preview endpoint; {} if the order is unknown."""
        return await self.get_order_dataset(order_id) or {}
