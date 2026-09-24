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


def strip_answer_keys(obj):
    """Recursively drop answer-key fields so no agent can see the expected result."""
    if isinstance(obj, dict):
        return {k: strip_answer_keys(v) for k, v in obj.items() if k not in ANSWER_KEYS}
    if isinstance(obj, list):
        return [strip_answer_keys(v) for v in obj]
    return obj


def dataset_order_id(data: dict) -> Optional[str]:
    """The order (trip) id a dataset belongs to."""
    return (data.get("dispute_ticket") or {}).get("trip_id") or (
        data.get("trip_data") or {}
    ).get("trip_id")


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
    ):
        self.api_key = api_key or "demo-api-key"
        self.base_url = base_url or "https://api.rydesharing.com/v1"
        self.data_dirs = [Path(d) for d in (data_dirs or DEFAULT_DATA_DIRS)]
        self._index: dict[str, Path] | None = None

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
        if self._index is None:
            self._index = self._build_index()
        orders = []
        for order_id, path in self._index.items():
            ticket = load_dispute_dataset(path).get("dispute_ticket") or {}
            orders.append({
                "order_id": order_id,
                "dispute_id": ticket.get("dispute_id"),
                "dispute_type": ticket.get("dispute_type"),
                "filed_by": ticket.get("filed_by"),
                "description": ticket.get("description", ""),
                "source": f"{path.parent.name}/{path.name}",
            })
        return orders

    async def get_full_order_context(self, order_id: str) -> dict:
        """Order data for the preview endpoint; {} if the order is unknown."""
        return await self.get_order_dataset(order_id) or {}
