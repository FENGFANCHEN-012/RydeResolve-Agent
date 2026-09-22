"""
Ryde Platform API Client

Simulates integration with Ryde's platform API for fetching order data,
trip details, payment records, chat logs, GPS traces, and user profiles.

In a production environment, this would make HTTP requests to Ryde's
internal API endpoints. For the hackathon demo, we use realistic mock data
based on the actual Ryde platform structure.
"""
import json
import random
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel


class TripDetails(BaseModel):
    """Trip information from Ryde platform."""
    order_id: str
    service_type: str  # RydeX, RydeXL, RydePOOL, RydeTAXI, RydeSEND, etc.
    status: str  # completed, cancelled, no_show
    pickup_name: str
    pickup_address: str
    pickup_lat: float
    pickup_lng: float
    dropoff_name: str
    dropoff_address: str
    dropoff_lat: float
    dropoff_lng: float
    requested_at: str  # ISO 8601
    driver_assigned_at: Optional[str] = None
    driver_arrived_at: Optional[str] = None
    trip_started_at: Optional[str] = None
    trip_ended_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    cancellation_reason: Optional[str] = None
    cancelled_by: Optional[str] = None  # rider, driver, system
    estimated_distance_km: float
    estimated_duration_min: int
    actual_distance_km: Optional[float] = None
    actual_duration_min: Optional[int] = None
    route_deviation_percent: Optional[float] = None
    driver_reported_reason: Optional[str] = None


class PaymentDetails(BaseModel):
    """Payment and fare information from Ryde platform."""
    order_id: str
    currency: str  # SGD
    base_fare: float
    distance_fare: float
    time_fare: float
    surge_multiplier: float
    surge_amount: float
    platform_fee: float  # up to 20% service fee
    tolls: float
    promo_discount: float
    rydecoins_used: float
    subtotal: float
    gst: float
    total_fare: float
    estimated_fare: float
    payment_method: str  # cash, credit_card, apple_pay, rydecoins
    paid_at: Optional[str] = None
    refund_amount: Optional[float] = None
    refund_status: Optional[str] = None  # pending, approved, rejected
    refund_reason: Optional[str] = None


class ChatMessage(BaseModel):
    """In-app chat message between rider and driver."""
    timestamp: str
    sender: str  # rider, driver
    message: str
    message_type: str  # text, image, system


class GPSPoint(BaseModel):
    """GPS location point from trip trace."""
    timestamp: str
    latitude: float
    longitude: float
    speed_kmh: Optional[float] = None
    heading: Optional[float] = None
    accuracy_m: Optional[float] = None


class UserProfile(BaseModel):
    """User profile information from Ryde platform."""
    user_id: str
    user_type: str  # rider, driver
    name: str
    phone: str
    email: str
    account_created_at: str
    account_age_months: int
    rating: float
    total_trips: int
    total_disputes_filed: int
    total_disputes_received: int
    previous_violations: list[str] = []
    account_status: str  # active, suspended, under_review
    verification_status: str  # verified, pending, unverified


class EvidenceItem(BaseModel):
    """Evidence submitted by either party."""
    evidence_id: str
    evidence_type: str  # screenshot, photo, receipt, video, audio, document
    uploaded_by: str  # rider, driver
    uploaded_at: str
    description: str
    file_url: str
    file_size_mb: float
    mime_type: str


class RydeAPIClient:
    """
    Client for fetching data from the Ryde platform.

    For hackathon demo: returns realistic mock data.
    For production: would make authenticated HTTP requests to Ryde API.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or "demo-api-key"
        self.base_url = base_url or "https://api.rydesharing.com/v1"
        self._mock_data_loaded = False
        self._mock_orders: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public API Methods
    # ------------------------------------------------------------------

    async def get_trip_details(self, order_id: str) -> Optional[TripDetails]:
        """Fetch trip details for a given order ID."""
        mock = self._get_mock_order(order_id)
        if not mock:
            return None
        return TripDetails(**mock["trip"])

    async def get_payment_details(self, order_id: str) -> Optional[PaymentDetails]:
        """Fetch payment/fare details for a given order ID."""
        mock = self._get_mock_order(order_id)
        if not mock:
            return None
        return PaymentDetails(**mock["payment"])

    async def get_chat_log(self, order_id: str) -> list[ChatMessage]:
        """Fetch in-app chat log between rider and driver."""
        mock = self._get_mock_order(order_id)
        if not mock:
            return []
        return [ChatMessage(**msg) for msg in mock.get("chat_log", [])]

    async def get_gps_trace(self, order_id: str) -> list[GPSPoint]:
        """Fetch GPS trace for the trip."""
        mock = self._get_mock_order(order_id)
        if not mock:
            return []
        return [GPSPoint(**pt) for pt in mock.get("gps_trace", [])]

    async def get_rider_profile(self, order_id: str) -> Optional[UserProfile]:
        """Fetch rider profile for the order."""
        mock = self._get_mock_order(order_id)
        if not mock:
            return None
        return UserProfile(**mock["rider_profile"])

    async def get_driver_profile(self, order_id: str) -> Optional[UserProfile]:
        """Fetch driver profile for the order."""
        mock = self._get_mock_order(order_id)
        if not mock:
            return None
        return UserProfile(**mock["driver_profile"])

    async def get_evidence(self, order_id: str) -> list[EvidenceItem]:
        """Fetch evidence submitted for the dispute."""
        mock = self._get_mock_order(order_id)
        if not mock:
            return []
        return [EvidenceItem(**ev) for ev in mock.get("evidence", [])]

    async def get_full_order_context(self, order_id: str) -> dict:
        """
        Fetch complete order context in one call.
        Returns all data needed for dispute resolution.
        """
        mock = self._get_mock_order(order_id)
        if not mock:
            return {}

        return {
            "trip": await self.get_trip_details(order_id),
            "payment": await self.get_payment_details(order_id),
            "chat_log": await self.get_chat_log(order_id),
            "gps_trace": await self.get_gps_trace(order_id),
            "rider_profile": await self.get_rider_profile(order_id),
            "driver_profile": await self.get_driver_profile(order_id),
            "evidence": await self.get_evidence(order_id),
        }

    # ------------------------------------------------------------------
    # Mock Data Store
    # ------------------------------------------------------------------

    def _get_mock_order(self, order_id: str) -> Optional[dict]:
        """Load mock order data. In production, this would query Ryde's database."""
        # First check if we have pre-loaded mock disputes
        from pathlib import Path
        import os

        mock_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "data" / "mock_disputes"
        if mock_dir.exists():
            for json_file in mock_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if data.get("order_id") == order_id:
                            return self._transform_mock_dispute(data)
                except Exception:
                    continue

        # Return default mock data for demo order IDs
        if order_id.startswith("RYDE-DEMO") or order_id.startswith("DRP-"):
            return self._get_default_mock_order(order_id)

        return None

    def _transform_mock_dispute(self, data: dict) -> dict:
        """Transform mock dispute JSON into Ryde API format."""
        trip = data.get("trip", {})
        payment = data.get("payment", {})
        chat = data.get("chat_log", [])
        gps = data.get("gps_trace", [])
        behavior = data.get("behavior_profiles", {})

        return {
            "trip": {
                "order_id": data.get("order_id", ""),
                "service_type": "RydeX",
                "status": "completed",
                "pickup_name": trip.get("pickup_name", "Unknown"),
                "pickup_address": trip.get("pickup_name", "Unknown"),
                "pickup_lat": 1.3098,
                "pickup_lng": 103.7775,
                "dropoff_name": trip.get("dropoff_name", "Unknown"),
                "dropoff_address": trip.get("dropoff_name", "Unknown"),
                "dropoff_lat": 1.3048,
                "dropoff_lng": 103.8318,
                "requested_at": "2026-09-21T10:00:00+08:00",
                "driver_assigned_at": "2026-09-21T10:01:00+08:00",
                "driver_arrived_at": "2026-09-21T10:05:00+08:00",
                "trip_started_at": "2026-09-21T10:06:00+08:00",
                "trip_ended_at": "2026-09-21T10:33:00+08:00",
                "estimated_distance_km": trip.get("estimated_distance_km", 8.0),
                "estimated_duration_min": trip.get("estimated_duration_min", 18),
                "actual_distance_km": trip.get("actual_distance_km", 8.0),
                "actual_duration_min": trip.get("actual_duration_min", 27),
                "route_deviation_percent": trip.get("route_deviation_percent", 0.0),
                "driver_reported_reason": trip.get("driver_reported_reason", ""),
            },
            "payment": {
                "order_id": data.get("order_id", ""),
                "currency": payment.get("currency", "SGD"),
                "base_fare": 3.0,
                "distance_fare": payment.get("estimated_fare", 14.5) * 0.6,
                "time_fare": payment.get("estimated_fare", 14.5) * 0.2,
                "surge_multiplier": 1.0,
                "surge_amount": 0.0,
                "platform_fee": payment.get("estimated_fare", 14.5) * 0.15,
                "tolls": 0.0,
                "promo_discount": 0.0,
                "rydecoins_used": 0.0,
                "subtotal": payment.get("charged_fare", 14.5),
                "gst": payment.get("charged_fare", 14.5) * 0.09,
                "total_fare": payment.get("charged_fare", 14.5) * 1.09,
                "estimated_fare": payment.get("estimated_fare", 14.5),
                "payment_method": "credit_card",
                "paid_at": "2026-09-21T10:33:00+08:00",
            },
            "chat_log": [
                {
                    "timestamp": msg.get("timestamp", ""),
                    "sender": msg.get("sender", ""),
                    "message": msg.get("message", ""),
                    "message_type": "text",
                }
                for msg in chat
            ],
            "gps_trace": [
                {
                    "timestamp": pt.get("timestamp", ""),
                    "latitude": pt.get("latitude", 0.0),
                    "longitude": pt.get("longitude", 0.0),
                    "speed_kmh": random.uniform(20, 60),
                    "heading": random.uniform(0, 360),
                    "accuracy_m": random.uniform(3, 15),
                }
                for pt in gps
            ],
            "rider_profile": {
                "user_id": f"RIDER-{random.randint(10000, 99999)}",
                "user_type": "rider",
                "name": "Demo Rider",
                "phone": "+65 9123 4567",
                "email": "rider@example.com",
                "account_created_at": "2025-01-15T00:00:00+08:00",
                "account_age_months": behavior.get("rider", {}).get("account_age_months", 12),
                "rating": behavior.get("rider", {}).get("rating", 4.8),
                "total_trips": 150,
                "total_disputes_filed": behavior.get("rider", {}).get("previous_disputes", 0),
                "total_disputes_received": 0,
                "previous_violations": [],
                "account_status": "active",
                "verification_status": "verified",
            },
            "driver_profile": {
                "user_id": f"DRIVER-{random.randint(10000, 99999)}",
                "user_type": "driver",
                "name": "Demo Driver",
                "phone": "+65 9876 5432",
                "email": "driver@example.com",
                "account_created_at": "2024-06-01T00:00:00+08:00",
                "account_age_months": behavior.get("driver", {}).get("account_age_months", 24),
                "rating": behavior.get("driver", {}).get("rating", 4.7),
                "total_trips": 800,
                "total_disputes_filed": 0,
                "total_disputes_received": behavior.get("driver", {}).get("previous_route_disputes", 0),
                "previous_violations": [],
                "account_status": "active",
                "verification_status": "verified",
            },
            "evidence": data.get("evidence", []),
        }

    def _get_default_mock_order(self, order_id: str) -> dict:
        """Generate a default mock order for demo purposes."""
        now = datetime.now()
        return {
            "trip": {
                "order_id": order_id,
                "service_type": "RydeX",
                "status": "completed",
                "pickup_name": "Singapore Polytechnic",
                "pickup_address": "500 Dover Road, Singapore 139651",
                "pickup_lat": 1.3098,
                "pickup_lng": 103.7775,
                "dropoff_name": "Orchard Road",
                "dropoff_address": "Orchard Road, Singapore 238863",
                "dropoff_lat": 1.3048,
                "dropoff_lng": 103.8318,
                "requested_at": (now - timedelta(minutes=45)).isoformat(),
                "driver_assigned_at": (now - timedelta(minutes=44)).isoformat(),
                "driver_arrived_at": (now - timedelta(minutes=38)).isoformat(),
                "trip_started_at": (now - timedelta(minutes=37)).isoformat(),
                "trip_ended_at": (now - timedelta(minutes=18)).isoformat(),
                "estimated_distance_km": 8.2,
                "estimated_duration_min": 18,
                "actual_distance_km": 10.4,
                "actual_duration_min": 27,
                "route_deviation_percent": 26.8,
                "driver_reported_reason": "Missed the correct exit",
            },
            "payment": {
                "order_id": order_id,
                "currency": "SGD",
                "base_fare": 3.0,
                "distance_fare": 8.7,
                "time_fare": 2.9,
                "surge_multiplier": 1.0,
                "surge_amount": 0.0,
                "platform_fee": 2.18,
                "tolls": 0.0,
                "promo_discount": 0.0,
                "rydecoins_used": 0.0,
                "subtotal": 14.5,
                "gst": 1.31,
                "total_fare": 15.81,
                "estimated_fare": 14.5,
                "payment_method": "credit_card",
                "paid_at": (now - timedelta(minutes=18)).isoformat(),
            },
            "chat_log": [
                {
                    "timestamp": (now - timedelta(minutes=30)).isoformat(),
                    "sender": "rider",
                    "message": "Why are we going in the opposite direction?",
                    "message_type": "text",
                },
                {
                    "timestamp": (now - timedelta(minutes=29)).isoformat(),
                    "sender": "driver",
                    "message": "Sorry, I missed the exit. I will turn back.",
                    "message_type": "text",
                },
            ],
            "gps_trace": [
                {
                    "timestamp": (now - timedelta(minutes=37)).isoformat(),
                    "latitude": 1.3098,
                    "longitude": 103.7775,
                    "speed_kmh": 0,
                    "heading": 90,
                    "accuracy_m": 5,
                },
                {
                    "timestamp": (now - timedelta(minutes=27)).isoformat(),
                    "latitude": 1.3188,
                    "longitude": 103.8057,
                    "speed_kmh": 45,
                    "heading": 45,
                    "accuracy_m": 8,
                },
                {
                    "timestamp": (now - timedelta(minutes=18)).isoformat(),
                    "latitude": 1.3048,
                    "longitude": 103.8318,
                    "speed_kmh": 30,
                    "heading": 180,
                    "accuracy_m": 6,
                },
            ],
            "rider_profile": {
                "user_id": "RIDER-12345",
                "user_type": "rider",
                "name": "Tan Wei Ming",
                "phone": "+65 9123 4567",
                "email": "weiming.tan@example.com",
                "account_created_at": "2025-01-15T00:00:00+08:00",
                "account_age_months": 18,
                "rating": 4.8,
                "total_trips": 150,
                "total_disputes_filed": 0,
                "total_disputes_received": 0,
                "previous_violations": [],
                "account_status": "active",
                "verification_status": "verified",
            },
            "driver_profile": {
                "user_id": "DRIVER-67890",
                "user_type": "driver",
                "name": "Kumar Rajesh",
                "phone": "+65 9876 5432",
                "email": "rajesh.kumar@example.com",
                "account_created_at": "2024-06-01T00:00:00+08:00",
                "account_age_months": 26,
                "rating": 4.7,
                "total_trips": 800,
                "total_disputes_filed": 0,
                "total_disputes_received": 1,
                "previous_violations": [],
                "account_status": "active",
                "verification_status": "verified",
            },
            "evidence": [],
        }
