"""
D73: a party adds new evidence to a borderline auto-resolved ruling, and the AI settles it first.

    safety wording in the text        -> a person (no AI reconsideration)
    nothing the case does not show    -> decision kept, the party is told why
    a new fact                        -> the whole pipeline runs again with the text as evidence
        second ruling confident       -> it stands (same outcome = kept, else changed)
        second ruling unsure/escalated-> a person
    any error                         -> a person (escalate rather than misjudge)

Just disagreeing is not new evidence, so an unhappy party alone never reaches a person: the AI
keeps deciding, and a person sees only new facts the AI cannot settle.
"""
from __future__ import annotations

import json
import logging

from src import config
from src.agents.safety import safety_words
from src.store.db import (APPEAL_CHANGED, APPEAL_KEPT, APPEAL_RECONSIDERING, APPEAL_WITH_PERSON,
                          Store, get_store)

logger = logging.getLogger(__name__)

_SYSTEM = """You check whether a ride-hailing party's appeal adds NEW FACTS to a decided dispute.
A new fact is something about the trip that the case record below does not already contain or that
contradicts it: a receipt, an amount, a time, a place, something that happened, a document.
NOT new facts: disagreeing, repeating the complaint, opinions, insults, asking for more money,
saying the decision is unfair. Answer only JSON:
{"new_fact": true|false, "facts": ["<each new fact, short>"], "why": "<one sentence the party can read>"}"""

NOTE_KEPT_NO_FACT = ("We read your message. It does not add information the case did not already have, so "
                     "the decision stays the same. {why}")
NOTE_KEPT_SAME = "We checked the case again with your new information. The decision stays the same."
NOTE_CHANGED = "We checked the case again with your new information and changed the decision."
NOTE_PERSON = "A person from Ryde will review your case. No money moves while they look at it."


async def new_facts(ruling, evidence: str, llm=None) -> dict:
    """The model's view of whether the text adds facts the ruling did not have."""
    if llm is None:
        from src.core.llm_client import llm_client as llm
    case = (f"Case record: {ruling.case_summary or 'not recorded'}\n"
            f"Decision: {ruling.verdict}, refund {ruling.refund_amount}\n"
            f"Reasons given: {ruling.rationale or ''}")
    raw = str(await llm.chat_json(
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": f"{case}\n\nThe party's appeal:\n{evidence}"}],
        temperature=0.0))
    data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    return {"new_fact": data.get("new_fact") is True, "facts": list(data.get("facts") or []),
            "why": str(data.get("why") or "").strip()}


async def _rerun(ruling, appeal) -> dict:
    from src.agents.collector import EvidenceItem
    from src.core.orchestrator import Orchestrator
    item = EvidenceItem(evidence_type="document", file_url="", uploaded_by=appeal.party,
                        description=f"Added by the {appeal.party} after the first decision: {appeal.evidence}")
    return await Orchestrator().resolve(report_text="", order_id=ruling.order_id, evidence=[item])


def _to_person(store: Store, ruling_id: int, appeal, why: str, new_ruling_id: int | None = None):
    """Into the human review queue (review.html). A ruling the pipeline escalated is there already."""
    ruling = store.get_ruling(ruling_id)
    if ruling.status == "resolved":
        store.request_appeal(ruling_id, appeal.party, f"{why} New evidence: {appeal.evidence}", actor="appeal")
    return store.update_appeal(appeal.id, APPEAL_WITH_PERSON, NOTE_PERSON, new_ruling_id)


async def settle(appeal_id: int, store: Store | None = None, llm=None, rerun=None):
    """Run once per appeal, after open_appeal. Never raises: a failure hands the case to a person."""
    store = store or get_store()
    appeal = store.get_appeal(appeal_id)
    ruling = store.get_ruling(appeal.ruling_id)
    try:
        hits = safety_words(appeal.evidence)
        if hits:
            return _to_person(store, ruling.id, appeal, f"Safety wording in the new evidence ({', '.join(hits[:5])}).")

        check = await new_facts(ruling, appeal.evidence, llm)
        if not check["new_fact"]:
            return store.update_appeal(appeal.id, APPEAL_KEPT, NOTE_KEPT_NO_FACT.format(why=check["why"]).strip())

        store.update_appeal(appeal.id, APPEAL_RECONSIDERING)
        result = await (rerun or _rerun)(ruling, appeal)
        new_id = result.get("ruling_id")
        verdict = result.get("verdict") or {}
        if new_id is None:
            return _to_person(store, ruling.id, appeal, "The second decision could not be recorded.")
        if result.get("status") != "resolved":
            return _to_person(store, new_id, appeal, "The second decision went to a person.", new_id)
        confidence = verdict.get("confidence")
        if confidence is None or confidence < config.APPEAL_BELOW_CONFIDENCE:
            return _to_person(store, new_id, appeal,
                              f"With the new evidence the AI is still unsure (confidence {confidence}).", new_id)
        same = verdict.get("verdict") == ruling.verdict and \
            abs(float(verdict.get("refund_amount") or 0) - float(ruling.refund_amount or 0)) < 0.01
        return store.update_appeal(appeal.id, APPEAL_KEPT if same else APPEAL_CHANGED,
                                   NOTE_KEPT_SAME if same else NOTE_CHANGED, new_id)
    except Exception as exc:  # escalate rather than misjudge
        logger.warning("Appeal %s could not be settled by the AI: %s", appeal_id, exc)
        try:
            return _to_person(store, ruling.id, appeal, f"The AI could not check the new evidence ({exc}).")
        except Exception as exc2:
            logger.error("Appeal %s could not be handed to a person either: %s", appeal_id, exc2)
            return None
