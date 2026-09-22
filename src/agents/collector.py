"""
Agent 1: Information Collection Agent
Gathers dispute context from platform data (GPS, payment, ratings, chat logs).
"""
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class DisputeType(str, Enum):
    ROUTE_DEVIATION = "route_deviation"
    NO_SHOW = "no_show"
    FARE = "fare_dispute"
    CANCELLATION = "cancellation_refund"
    SERVICE_QUALITY = "service_quality"
    DELIVERY = "delivery_dispute"
    DRIVER_RIGHTS = "driver_rights"
    ACCIDENT = "accident_liability"


class DisputeContext(BaseModel):
    dispute_id: str
    type: Optional[DisputeType] = None
    reporter: str  # "passenger" or "driver"
    order_id: str
    description: str
    trip: Optional[dict] = None
    payment: Optional[dict] = None
    ratings: Optional[dict] = None
    chat_log: Optional[list[str]] = None
    gps_trace: Optional[list[dict]] = None


class CollectorAgent:
    """Collects and structures dispute information from multiple sources."""

    def __init__(self):
        self.name = "Collector"

    async def collect(self, report_text: str, order_id: str) -> DisputeContext:
        """
        Collect dispute context from:
        - User-submitted report text
        - Ryde platform order data (trip, payment, ratings, GPS)
        - In-app chat logs
        - Rating records
        """
        # TODO: Integrate with Ryde platform API
        # For now, create basic context from report
        context = DisputeContext(
            dispute_id=f"DRP-{order_id}",
            reporter="passenger",  # to be determined from report
            order_id=order_id,
            description=report_text,
        )
        return context
