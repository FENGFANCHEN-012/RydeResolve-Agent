"""
Agent 1: Information Collection Agent

Gathers comprehensive dispute context from:
- User-submitted report text
- Ryde platform API (trip, payment, chat, GPS, profiles)
- Uploaded evidence (screenshots, photos, receipts)
"""
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum

from src.integrations.ryde_api import RydeAPIClient


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
    # Evidence
    evidence: list[EvidenceItem] = []
    # Additional metadata
    language: str = "en"  # en, zh, ms, ta
    submitted_at: Optional[str] = None


class CollectorAgent:
    """
    Collects and structures dispute information from multiple sources:
    1. User report text
    2. Ryde platform API (trip, payment, chat, GPS, profiles)
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
        reporter: str = "passenger",
        evidence: list[EvidenceItem] | None = None,
        language: str = "en",
    ) -> DisputeContext:
        """
        Collect comprehensive dispute context.

        Steps:
        1. Create base context from user report
        2. Fetch order data from Ryde platform API
        3. Attach any uploaded evidence
        4. Return enriched DisputeContext
        """
        from datetime import datetime

        # Step 1: Base context
        context = DisputeContext(
            
            # get the report id
            dispute_id=f"DRP-{order_id}",
            reporter=reporter,
            order_id=order_id,
            description=report_text,
            evidence=evidence or [],
            language=language,
            submitted_at=datetime.now().isoformat(),
        )

        # Step 2: Fetch data from Ryde platform API
        api = self._get_api()
        try:
            order_data = await api.get_full_order_context(order_id)

            if order_data:
                if order_data.get("trip"):
                    context.trip = order_data["trip"].model_dump() if hasattr(order_data["trip"], "model_dump") else dict(order_data["trip"])

                if order_data.get("payment"):
                    context.payment = order_data["payment"].model_dump() if hasattr(order_data["payment"], "model_dump") else dict(order_data["payment"])

                if order_data.get("chat_log"):
                    context.chat_log = [
                        msg.model_dump() if hasattr(msg, "model_dump") else dict(msg)
                        for msg in order_data["chat_log"]
                    ]

                if order_data.get("gps_trace"):
                    context.gps_trace = [
                        pt.model_dump() if hasattr(pt, "model_dump") else dict(pt)
                        for pt in order_data["gps_trace"]
                    ]

                if order_data.get("rider_profile"):
                    context.rider_profile = order_data["rider_profile"].model_dump() if hasattr(order_data["rider_profile"], "model_dump") else dict(order_data["rider_profile"])

                if order_data.get("driver_profile"):
                    context.driver_profile = order_data["driver_profile"].model_dump() if hasattr(order_data["driver_profile"], "model_dump") else dict(order_data["driver_profile"])

                # Merge API evidence with uploaded evidence
                api_evidence = order_data.get("evidence", [])
                for ev in api_evidence:
                    ev_dict = ev.model_dump() if hasattr(ev, "model_dump") else dict(ev)
                    context.evidence.append(EvidenceItem(**ev_dict))

        except Exception as exc:
            # If API fails, continue with basic context (user report only)
            # This ensures the system is resilient to API outages
            import logging
            logging.getLogger(__name__).warning(
                "Ryde API fetch failed for order %s: %s", order_id, exc
            )

        return context

    async def collect_with_evidence_upload(
        self,
        report_text: str,
        order_id: str,
        reporter: str = "passenger",
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
                    uploaded_by=ef.get("uploaded_by", reporter),
                ))

        return await self.collect(
            report_text=report_text,
            order_id=order_id,
            reporter=reporter,
            evidence=evidence_items,
            language=language,
        )
