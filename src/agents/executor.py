"""
Agent 7: Execution Agent
Executes arbitration decisions and notifies all parties.

This implementation is a **simulated** executor suitable for hackathon demos.
It does NOT call any real Ryde production API. Every operation is labelled
``simulated_*`` so the demo never falsely claims that a real refund, driver
penalty, or platform notification actually happened.
"""
from __future__ import annotations

import logging
from typing import Any

from src.agents.arbitrator import Decision
from src.config import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

# Singapore's official languages. We default to English when the caller does
# not supply a language code, and we fall back to English for any unsupported
# code so the executor never crashes on unexpected input.
DEFAULT_LANGUAGE = "en"
DEFAULT_CURRENCY = "SGD"

# Status values emitted by the simulated executor.
STATUS_EXECUTED = "executed"
STATUS_ESCALATED = "escalated_to_human"
STATUS_FAILED = "failed"

# Simulation markers — every transaction and notification is clearly tagged
# so the demo cannot be confused with a real platform action.
SIMULATED_TRANSACTION_STATUS = "simulated_success"
SIMULATED_NOTIFICATION_STATUS = "simulated_sent"
SIMULATED_OPERATION_NOTE = (
    "Simulated operation — no real Ryde platform API call was made."
)


# ---------------------------------------------------------------------------
# Multilingual notification templates
# ---------------------------------------------------------------------------
# Templates are intentionally simple, short, and self-contained so they work
# in a demo without an external translation service. If a language is not
# supported we silently fall back to English (the official default).

_NOTIFICATION_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "subject": "Update on your Ryde dispute {dispute_id}",
        "message": (
            "Hello {recipient_label}, your dispute {dispute_id} has been reviewed. "
            "Reason: {rationale_summary}. "
            "If you have further questions, please contact Ryde support."
        ),
        "escalation_subject": "Your dispute {dispute_id} is being escalated",
        "escalation_message": (
            "Hello {recipient_label}, your dispute {dispute_id} requires human "
            "review. Our team will follow up shortly. "
            "No financial action will be taken until a specialist reviews the case."
        ),
    },
    "zh": {
        "subject": "您的 Ryde 纠纷 {dispute_id} 有最新进展",
        "message": (
            "{recipient_label} 您好,您的纠纷 {dispute_id} 已由系统审核完毕。"
            "处理原因:{rationale_summary}。如有疑问请联系 Ryde 客服。"
        ),
        "escalation_subject": "您的纠纷 {dispute_id} 已转交人工处理",
        "escalation_message": (
            "{recipient_label} 您好,您的纠纷 {dispute_id} 需要人工复核,"
            "专员会尽快与您联系。在此之前不会执行任何财务或处罚操作。"
        ),
    },
    "ms": {
        "subject": "Maklumat terkini pertikaian Ryde anda {dispute_id}",
        "message": (
            "Hai {recipient_label}, pertikaian anda {dispute_id} telah "
            "disemak. Sebab: {rationale_summary}. Sila hubungi sokongan Ryde "
            "untuk sebarang pertanyaan lanjut."
        ),
        "escalation_subject": "Pertikaian anda {dispute_id} telah dinaikkan taraf",
        "escalation_message": (
            "Hai {recipient_label}, pertikaian anda {dispute_id} memerlukan "
            "semakan manusia. Pasukan kami akan menghubungi anda tidak lama "
            "lagi. Tiada tindakan kewangan akan diambil sehingga seorang "
            "pakar menyemak kes ini."
        ),
    },
    "ta": {
        "subject": "Ryde புகார் {dispute_id} குறித்த புதுப்பிப்பு",
        "message": (
            "{recipient_label}, உங்கள் புகார் {dispute_id} மதிப்பாய்வு "
            "செய்யப்பட்டது. காரணம்: {rationale_summary}. கூடுதல் "
            "கேள்விகளுக்கு Ryde ஆதரவை தொடர்பு கொள்ளவும்."
        ),
        "escalation_subject": "உங்கள் புகார் {dispute_id} மனித மதிப்பாய்வுக்கு அனுப்பப்பட்டது",
        "escalation_message": (
            "{recipient_label}, உங்கள் புகார் {dispute_id} மனித மதிப்பாய்வு "
            "தேவைப்படுகிறது. எங்கள் குழு விரைவில் தொடர்பு கொள்ளும். "
            "ஒரு நிபுணர் இந்த வழக்கை மதிப்பாய்வு செய்யும் வரை நிதி "
            "நடவடிக்கை எடுக்கப்படாது."
        ),
    },
}


class ExecutionAgent:
    """Simulated arbitration executor and notifier.

    The executor is **deliberately simulated**: it never touches any external
    Ryde platform API. All side-effects are recorded in the returned dict
    so the orchestrator and frontend can render a clear demo experience
    without ever claiming that a real refund or driver penalty occurred.
    """

    def __init__(self):
        self.name = "Executor"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def execute(
        self,
        decision: Decision,
        dispute_id: str,
        language: str = DEFAULT_LANGUAGE,
    ) -> dict:
        """Execute a ``Decision`` and return a structured result dict.

        Args:
            decision: The arbitration decision produced upstream.
            dispute_id: Unique dispute identifier from the collector.
            language: Preferred notification language (defaults to English).

        Returns:
            A dict containing at least the following keys:
                - ``dispute_id``
                - ``executed`` (bool)
                - ``status`` (str)
                - ``notifications_sent`` (bool)
                - ``actions_taken`` (list[str])
                - ``transaction_records`` (list[dict])
                - ``notifications`` (list[dict])
        """
        safe_language = self._resolve_language(language)

        result: dict[str, Any] = {
            "dispute_id": dispute_id,
            "executed": False,
            "status": STATUS_FAILED,
            "notifications_sent": False,
            "actions_taken": [],
            "transaction_records": [],
            "notifications": [],
            "error": None,
        }

        try:
            if self._needs_human_review(decision):
                result["status"] = STATUS_ESCALATED
                result["executed"] = False
                self._record_escalation(result)
                self._generate_notifications(
                    decision=decision,
                    dispute_id=dispute_id,
                    language=safe_language,
                    result=result,
                    escalated=True,
                )
                return result

            # Normal execution path.
            result["status"] = STATUS_EXECUTED
            result["executed"] = True

            self._apply_refund(decision, result)
            self._apply_compensation(decision, result)
            self._apply_driver_penalty(decision, result)
            self._generate_notifications(
                decision=decision,
                dispute_id=dispute_id,
                language=safe_language,
                result=result,
                escalated=False,
            )
            return result
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Simulated execution failed for %s", dispute_id)
            result["status"] = STATUS_FAILED
            result["executed"] = False
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["actions_taken"].append(
                f"Execution failed: {type(exc).__name__}: {exc}"
            )
            return result

    # ------------------------------------------------------------------
    # Decision helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _needs_human_review(decision: Decision) -> bool:
        """Return True when the decision must be escalated."""
        return bool(getattr(decision, "human_review_needed", False))

    @staticmethod
    def _resolve_language(language: str | None) -> str:
        """Pick a supported language, falling back to English."""
        if not language:
            return DEFAULT_LANGUAGE
        candidate = language.lower().strip()
        if candidate in _NOTIFICATION_TEMPLATES:
            return candidate
        if candidate in SUPPORTED_LANGUAGES:
            # Supported by config but missing templates — fall back gracefully.
            return DEFAULT_LANGUAGE
        return DEFAULT_LANGUAGE

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _apply_refund(self, decision: Decision, result: dict) -> None:
        """Record a simulated refund transaction if requested."""
        amount = getattr(decision, "refund_amount", None)
        if amount is None:
            return
        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid refund_amount %r on dispute %s; not executing refund.",
                amount,
                result.get("dispute_id"),
            )
            result["actions_taken"].append(
                f"Skipped refund: invalid refund_amount {amount!r}"
            )
            return
        if amount_value <= 0:
            return

        record = {
            "type": "refund",
            "status": SIMULATED_TRANSACTION_STATUS,
            "amount": round(amount_value, 2),
            "currency": DEFAULT_CURRENCY,
            "note": SIMULATED_OPERATION_NOTE,
        }
        result["transaction_records"].append(record)
        result["actions_taken"].append(
            f"Refund {DEFAULT_CURRENCY} {amount_value:.2f} to passenger (simulated)"
        )

    def _apply_compensation(self, decision: Decision, result: dict) -> None:
        """Record a compensation action while preserving the original value."""
        compensation = getattr(decision, "compensation", None)
        if compensation is None:
            return
        if isinstance(compensation, str) and not compensation.strip():
            return

        record = {
            "type": "compensation",
            "status": SIMULATED_TRANSACTION_STATUS,
            "value": compensation,
            "note": SIMULATED_OPERATION_NOTE,
        }
        result["transaction_records"].append(record)
        result["actions_taken"].append(
            f"Issue compensation: {compensation} (simulated)"
        )

    def _apply_driver_penalty(self, decision: Decision, result: dict) -> None:
        """Record a structured driver-penalty action."""
        penalty = getattr(decision, "driver_penalty", None)
        if penalty is None:
            return
        if isinstance(penalty, str) and not penalty.strip():
            return

        record = {
            "type": "driver_penalty",
            "status": SIMULATED_TRANSACTION_STATUS,
            "value": penalty,
            "note": SIMULATED_OPERATION_NOTE,
        }
        result["transaction_records"].append(record)
        result["actions_taken"].append(
            f"Apply driver penalty: {penalty} (simulated)"
        )

    def _record_escalation(self, result: dict) -> None:
        """Record that the case was escalated to a human reviewer."""
        result["actions_taken"].append("Escalated to human review queue")

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def _generate_notifications(
        self,
        decision: Decision,
        dispute_id: str,
        language: str,
        result: dict,
        escalated: bool,
    ) -> None:
        """Produce simulated notifications for passenger and driver."""
        template = _NOTIFICATION_TEMPLATES.get(language, _NOTIFICATION_TEMPLATES[DEFAULT_LANGUAGE])
        rationale_summary = self._summarise_rationale(decision)

        for recipient, recipient_label in (
            ("passenger", "Passenger"),
            ("driver", "Driver"),
        ):
            try:
                if escalated:
                    subject = template["escalation_subject"].format(
                        dispute_id=dispute_id
                    )
                    message = template["escalation_message"].format(
                        dispute_id=dispute_id,
                        recipient_label=recipient_label,
                    )
                else:
                    subject = template["subject"].format(dispute_id=dispute_id)
                    message = template["message"].format(
                        dispute_id=dispute_id,
                        recipient_label=recipient_label,
                        rationale_summary=rationale_summary,
                    )
            except (KeyError, IndexError) as exc:
                logger.warning(
                    "Notification template rendering failed (%s); falling back to English.",
                    exc,
                )
                fallback = _NOTIFICATION_TEMPLATES[DEFAULT_LANGUAGE]
                if escalated:
                    subject = fallback["escalation_subject"].format(dispute_id=dispute_id)
                    message = fallback["escalation_message"].format(
                        dispute_id=dispute_id,
                        recipient_label=recipient_label,
                    )
                else:
                    subject = fallback["subject"].format(dispute_id=dispute_id)
                    message = fallback["message"].format(
                        dispute_id=dispute_id,
                        recipient_label=recipient_label,
                        rationale_summary=rationale_summary,
                    )

            notification = {
                "recipient": recipient,
                "language": language,
                "subject": subject,
                "message": message,
                "status": SIMULATED_NOTIFICATION_STATUS,
            }
            result["notifications"].append(notification)

        result["notifications_sent"] = bool(result["notifications"])

    @staticmethod
    def _summarise_rationale(decision: Decision) -> str:
        """Produce a short human-readable rationale summary for messages."""
        rationale = getattr(decision, "rationale", "") or ""
        verdict = getattr(decision, "verdict", None)
        verdict_value = getattr(verdict, "value", verdict) if verdict else "decision"
        summary = rationale.strip().replace("\n", " ")
        if not summary:
            summary = f"Decision: {verdict_value}."
        else:
            summary = f"Decision: {verdict_value}. {summary}"
        # Keep notifications short for the demo.
        if len(summary) > 240:
            summary = summary[:237].rstrip() + "..."
        return summary