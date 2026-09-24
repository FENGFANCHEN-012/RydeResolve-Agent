"""
Agent 1: Information Collection Agent

Gathers dispute context from:
- User-submitted report text
- Ryde platform order data (dispute datasets in the DISP-002 format)
- Uploaded evidence (screenshots, photos, receipts)

Rule: the collector never invents data. Anything the source does not contain
stays None, and `data_completeness` records what is missing.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from enum import Enum

from src.integrations.ryde_api import (
    RydeAPIClient,
    dataset_order_id,
    load_dispute_dataset,
    strip_answer_keys,
)

logger = logging.getLogger(__name__)


class DisputeType(str, Enum):
    ROUTE_DEVIATION = "route_deviation"
    NO_SHOW = "no_show"
    FARE = "fare_dispute"
    CANCELLATION = "cancellation_refund"
    SERVICE_QUALITY = "service_quality"
    DELIVERY = "delivery_dispute"
    DRIVER_RIGHTS = "driver_rights"
    ACCIDENT = "accident_liability"


class EvidenceItem(BaseModel):
    """Evidence uploaded by either party."""
    evidence_type: str  # screenshot, photo, receipt, video, audio, document
    description: str
    file_url: str
    uploaded_by: str  # rider, driver


# get the dispute context from ryde app as proof to support judgement

class DisputeContext(BaseModel):
    dispute_id: str
    type: Optional[DisputeType] = None
    reporter: str  # "passenger" or "driver"
    order_id: str
    description: str
    # Platform data from Ryde API
    trip: Optional[dict] = None
    payment: Optional[dict] = None
    ratings: Optional[dict] = None
    chat_log: Optional[list[dict]] = None
    gps_trace: Optional[list[dict]] = None
    rider_profile: Optional[dict] = None
    driver_profile: Optional[dict] = None
    # App-side event log (driver_arrived, wait_timer_expired, ...) and the
    # policy parameters that applied to this trip, when the input provides them
    app_events: Optional[list[dict]] = None
    platform_policy: Optional[dict] = None
    # Evidence
    evidence: list[EvidenceItem] = []
    # Which data was found and where it came from, e.g.
    # {"source": "mock_disputes/no_show_01.json", "trip": True, "gps_trace": False, ...}
    data_completeness: dict = {}
    # Additional metadata
    language: str = "en"  # en, zh, ms, ta
    submitted_at: Optional[str] = None


# Platform data fields tracked in data_completeness
_PLATFORM_FIELDS = (
    "trip", "payment", "chat_log", "gps_trace",
    "rider_profile", "driver_profile", "app_events", "platform_policy",
)


class CollectorAgent:
    """
    Collects and structures dispute information from multiple sources:
    1. User report text
    2. Ryde platform order data
    3. Uploaded evidence files
    """

    def __init__(self, ryde_api: RydeAPIClient | None = None):
        self.name = "Collector"
        self._api = ryde_api

    def _get_api(self) -> RydeAPIClient:
        if self._api is None:
            self._api = RydeAPIClient()
        return self._api

    async def collect(
        self,
        report_text: str,
        order_id: str,
        reporter: str | None = None,
        evidence: list[EvidenceItem] | None = None,
        language: str = "en",
    ) -> DisputeContext:
        """
        Collect dispute context for an order.

        1. Look the order up on the platform (dataset files for the demo).
        2. Map it to a DisputeContext without inventing any values.
        3. The user's report text and reporter override the dataset's, and
           uploaded evidence is attached.
        """
        dataset = None
        error = None
        try:
            dataset = await self._get_api().get_order_dataset(order_id)
        except Exception as exc:
            # Keep going with the report only, but record why data is missing
            error = str(exc)
            logger.warning("Ryde data fetch failed for order %s: %s", order_id, exc)

        if dataset:
            context = self._context_from_dataset(dataset, language)
        else:
            context = DisputeContext(
                dispute_id=f"DRP-{order_id}",
                reporter="passenger",
                order_id=order_id,
                description="",
                language=language,
            )
            context.data_completeness = self._completeness(context, source=None)
            if error:
                context.data_completeness["error"] = error
            else:
                logger.warning("Order %s not found; context has the report only", order_id)

        if report_text:
            context.description = report_text
        if reporter:
            context.reporter = reporter
        context.evidence.extend(evidence or [])
        if not context.submitted_at:
            context.submitted_at = datetime.now().isoformat()
        return context

    async def collect_with_evidence_upload(
        self,
        report_text: str,
        order_id: str,
        reporter: str | None = None,
        evidence_files: list[dict] | None = None,
        language: str = "en",
    ) -> DisputeContext:
        """
        Collect dispute context with evidence file uploads.

        evidence_files: list of dicts with keys:
            - evidence_type: str (screenshot, photo, receipt, etc.)
            - description: str
            - file_url: str
            - uploaded_by: str (rider/driver)
        """
        evidence_items = []
        if evidence_files:
            for ef in evidence_files:
                evidence_items.append(EvidenceItem(
                    evidence_type=ef.get("evidence_type", "document"),
                    description=ef.get("description", ""),
                    file_url=ef.get("file_url", ""),
                    uploaded_by=ef.get("uploaded_by", reporter or "passenger"),
                ))

        return await self.collect(
            report_text=report_text,
            order_id=order_id,
            reporter=reporter,
            evidence=evidence_items,
            language=language,
        )

    # ------------------------------------------------------------------
    # Dispute dataset input (data/Dispute_format/*.md or *.json)
    # ------------------------------------------------------------------

    @staticmethod
    def load_dispute_dataset(path: str | Path) -> dict:
        """Load a .json or .md dataset file (see ryde_api.load_dispute_dataset)."""
        return load_dispute_dataset(path)

    async def collect_from_dataset(
        self, data: dict | str | Path, language: str = "en"
    ) -> DisputeContext:
        """
        Build a DisputeContext directly from a dataset file or dict, without
        looking anything up on the platform.
        """
        source = None
        if not isinstance(data, dict):
            source = Path(data).name
            data = load_dispute_dataset(data)
        data = strip_answer_keys(data)
        data.setdefault("_source", source)
        context = self._context_from_dataset(data, language)
        if not context.submitted_at:
            context.submitted_at = datetime.now().isoformat()
        return context

    def _context_from_dataset(self, data: dict, language: str) -> DisputeContext:
        """Single mapping from the dataset format to DisputeContext."""
        ticket = data.get("dispute_ticket") or {}
        trip = data.get("trip_data")
        rider = data.get("rider_profile")
        order_id = dataset_order_id(data) or "UNKNOWN"

        context = DisputeContext(
            dispute_id=ticket.get("dispute_id") or f"DRP-{order_id}",
            type=_map_dispute_type(ticket.get("dispute_type")),
            reporter=_map_reporter(ticket.get("filed_by")),
            order_id=order_id,
            description=ticket.get("description", ""),
            trip=trip,
            payment=_build_payment(data.get("payment_data"), trip, rider),
            chat_log=[_normalize_chat(m) for m in data.get("chat_logs") or []] or None,
            gps_trace=[_normalize_gps(p) for p in data.get("gps_telemetry") or []] or None,
            rider_profile=_normalize_profile(rider),
            driver_profile=_normalize_profile(data.get("driver_profile")),
            app_events=data.get("app_events") or None,
            platform_policy=data.get("cancellation_policy") or data.get("platform_policy"),
            language=language,
            submitted_at=ticket.get("filed_at"),
        )
        context.data_completeness = self._completeness(context, data.get("_source"))
        return context

    @staticmethod
    def _completeness(context: DisputeContext, source: str | None) -> dict:
        result = {"source": source}
        result.update({f: getattr(context, f) is not None for f in _PLATFORM_FIELDS})
        result["missing"] = [f for f in _PLATFORM_FIELDS if not result[f]]
        return result


# ---------------------------------------------------------------------- #
# Dataset -> DisputeContext mapping helpers
# ---------------------------------------------------------------------- #

# Dataset dispute_type strings -> internal DisputeType
_DATASET_TYPE_MAP: dict[str, DisputeType] = {
    "no_show": DisputeType.NO_SHOW,
    "no_show_charge": DisputeType.NO_SHOW,
    "route_deviation": DisputeType.ROUTE_DEVIATION,
    "fare": DisputeType.FARE,
    "fare_dispute": DisputeType.FARE,
    "overcharge": DisputeType.FARE,
    "cancellation": DisputeType.CANCELLATION,
    "cancellation_refund": DisputeType.CANCELLATION,
    "service_quality": DisputeType.SERVICE_QUALITY,
    "delivery": DisputeType.DELIVERY,
    "delivery_dispute": DisputeType.DELIVERY,
    "driver_rights": DisputeType.DRIVER_RIGHTS,
    "accident": DisputeType.ACCIDENT,
    "accident_liability": DisputeType.ACCIDENT,
}


def _map_dispute_type(raw: str | None) -> DisputeType | None:
    # Unknown types return None so the Classifier decides instead
    return _DATASET_TYPE_MAP.get((raw or "").strip().lower())


def _map_reporter(filed_by: str | None) -> str:
    # The pipeline uses "passenger"/"driver"; datasets say "rider"
    return "driver" if (filed_by or "").lower() == "driver" else "passenger"


def _normalize_chat(msg: dict) -> dict:
    """Dataset chat uses content/type; the pipeline uses message/message_type."""
    return {
        "timestamp": msg.get("timestamp"),
        "sender": msg.get("sender"),
        "message": msg.get("message", msg.get("content", "")),
        "message_type": msg.get("message_type", msg.get("type", "message")),
    }


def _normalize_gps(point: dict) -> dict:
    """Dataset GPS uses lat/lng; the pipeline uses latitude/longitude.
    Optional fields (speed, status) are copied only when present."""
    out = {
        "timestamp": point.get("timestamp"),
        "latitude": point.get("latitude", point.get("lat")),
        "longitude": point.get("longitude", point.get("lng")),
    }
    for key in ("speed_kmh", "status"):
        if key in point:
            out[key] = point[key]
    return out


def _normalize_profile(profile: dict | None) -> dict | None:
    """Keep every dataset field and add the `rating` key the orchestrator reads."""
    if not profile:
        return None
    out = dict(profile)
    if "rating" not in out and "avg_rating" in out:
        out["rating"] = out["avg_rating"]
    return out


def _build_payment(
    payment_data: dict | None, trip: dict | None, rider: dict | None
) -> dict | None:
    """
    Use payment_data when the dataset has it. Otherwise derive the charge in
    dispute from trip_data (e.g. a cancellation fee). Returns None if neither
    has any payment information.
    """
    if payment_data:
        payment = dict(payment_data)
        # charged_fare is what the rider paid; the orchestrator reads total_fare
        if "total_fare" not in payment and "charged_fare" in payment:
            payment["total_fare"] = payment["charged_fare"]
        return payment

    trip = trip or {}
    fee = trip.get("cancellation_fee")
    if fee is None and trip.get("total_fare") is None:
        return None
    payment = {}
    if fee is not None:
        payment["cancellation_fee"] = fee
        payment["total_fare"] = fee
    for key in ("total_fare", "estimated_fare"):
        if key in trip:
            payment[key] = trip[key]
    if rider and rider.get("payment_method"):
        payment["payment_method"] = rider["payment_method"]
    return payment
