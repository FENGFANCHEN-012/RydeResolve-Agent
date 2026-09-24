"""
Agent 5: Platform Policy Agent
RAG-based retrieval of real Ryde policies (Terms of Use, Code of Conduct,
Cancellation Policy, Refund Policy, Safety Standards, etc.) and compliance
evaluation via LLM.

All policies referenced by this agent are sourced from Ryde's official website
(rydesharing.com) and help center (help.rydesharing.com).
"""
import asyncio
import json
import logging

from src.core.trace import record_retrieval
from src.agents.collector import DisputeContext, DisputeType
from src.rag.retriever import DocumentRetriever
from src.core.llm_client import LLMClient

logger = logging.getLogger(__name__)


class PolicyAgent:
    """Retrieves and applies platform policies via RAG."""

    def __init__(self, retriever: DocumentRetriever | None = None, llm_client: LLMClient | None = None):
        """
        Initialise the agent with optional dependency injection.

        Args:
            retriever: A DocumentRetriever instance (or mock). If None, a real
                       DocumentRetriever is instantiated lazily on first use.
            llm_client: An LLMClient instance (or mock). If None, a real
                        LLMClient is instantiated lazily on first use.
        """
        self.name = "Policy"
        self._retriever = retriever
        self._llm_client = llm_client

    # ------------------------------------------------------------------
    # Lazy accessors – only create real instances when no mock was injected
    # ------------------------------------------------------------------

    def _get_retriever(self) -> DocumentRetriever:
        if self._retriever is None:
            try:
                self._retriever = DocumentRetriever()
            except Exception as exc:
                logger.warning("Could not initialise DocumentRetriever: %s", exc)
                self._retriever = None  # type: ignore[assignment]
        return self._retriever  # type: ignore[return-value]

    def _get_llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_dispute_type(context: DisputeContext) -> str:
        """
        Safely extract the dispute type string from a DisputeContext.

        Returns an empty string if the type is missing or cannot be resolved.
        """
        dt = context.type
        if dt is None:
            return ""
        if isinstance(dt, DisputeType):
            return dt.value
        if isinstance(dt, str):
            return dt
        return str(dt)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve_policies(self, context: DisputeContext) -> list[dict]:
        """
        Retrieve relevant policy clauses from the vector store (ChromaDB).

        Uses the dispute type to augment the query and the dispute description
        as the primary search text.  Returns a list of clause dicts with keys:
        ``clause``, ``source``, ``section``, ``file_type``, ``similarity``,
        ``chunk_index``.

        If ChromaDB is unavailable or the retriever cannot be initialised, an
        empty list is returned (never crashes).
        """
        dispute_type = self._extract_dispute_type(context)
        dispute_description = context.description or ""

        retriever = self._get_retriever()
        if retriever is None:
            logger.warning("No retriever available; returning empty policy list.")
            return []

        try:
            # Blocking (ChromaDB + embedding API): run off the event loop
            clauses = await asyncio.to_thread(
                retriever.retrieve_for_dispute,
                dispute_type=dispute_type,
                dispute_description=dispute_description,
            )
        except Exception as exc:
            logger.warning("Policy retrieval failed: %s", exc)
            return []

        record_retrieval(dispute_type, clauses or [])
        return clauses or []

    async def evaluate_compliance(self, context: DisputeContext) -> dict:
        """
        Evaluate whether each party's actions comply with platform policies.

        Workflow:
        1. Retrieve relevant policy clauses via RAG.
        2. If no clauses are retrieved, return a safe human-review result.
        3. Build a prompt with the dispute context and retrieved clauses.
        4. Call the LLM and parse JSON output.
        5. Validate that every policy reference exists in the retrieved clauses.
        6. If the LLM returns invalid JSON or raises, return a safe
           human-review result.

        Returns a dict with keys:
        - passenger_compliant (bool)
        - driver_compliant (bool)
        - violations (list[str])
        - policy_references (list[str])
        - reasoning (str)
        - confidence (float)
        - requires_human_review (bool)
        """
        policies = await self.retrieve_policies(context)

        if not policies:
            return self._safe_human_review_result(
                context, "No policy clauses were retrieved for this dispute."
            )

        # Build a compact representation of retrieved clauses for the prompt
        clause_summaries = []
        valid_policy_ids: set[str] = set()
        for idx, p in enumerate(policies):
            ref = f"{p.get('source', 'unknown')}#{p.get('chunk_index', idx)}"
            valid_policy_ids.add(ref)
            clause_summaries.append(
                {
                    "reference": ref,
                    "source": p.get("source", "Unknown"),
                    "section": p.get("section", ""),
                    "clause": p.get("clause", "")[:500],
                }
            )

        system_prompt = (
            "You are a platform policy compliance evaluator for a ride-hailing "
            "dispute resolution system. The policies provided are real Ryde "
            "policies sourced from rydesharing.com and help.rydesharing.com.\n\n"
            "Evaluate whether the passenger and the driver complied with the "
            "referenced policy clauses.\n\n"
            "Respond ONLY with a valid JSON object (no markdown, no extra text) "
            "with the following keys:\n"
            "  \"passenger_compliant\": boolean,\n"
            "  \"driver_compliant\": boolean,\n"
            "  \"violations\": list of strings (specific policy violations, may be empty),\n"
            "  \"policy_references\": list of strings (references from the provided clauses only),\n"
            "  \"reasoning\": string (concise, evidence-based explanation — no chain-of-thought),\n"
            "  \"confidence\": float (0.0–1.0),\n"
            "  \"requires_human_review\": boolean\n\n"
            "IMPORTANT: Only use policy references that appear in the provided "
            "clauses. Do not invent or fabricate policy references."
        )

        user_prompt = (
            f"Dispute ID: {context.dispute_id}\n"
            f"Dispute Type: {self._extract_dispute_type(context)}\n"
            f"Reporter: {context.reporter}\n"
            f"Order ID: {context.order_id}\n"
            f"Description: {context.description}\n"
            f"Trip details: {json.dumps(context.trip) if context.trip else 'N/A'}\n"
            f"Payment details: {json.dumps(context.payment) if context.payment else 'N/A'}\n"
            f"Chat log: {json.dumps(context.chat_log) if context.chat_log else 'N/A'}\n"
            f"GPS trace: {json.dumps(context.gps_trace) if context.gps_trace else 'N/A'}\n\n"
            f"Retrieved policy clauses (JSON):\n{json.dumps(clause_summaries, indent=2)}\n\n"
            "Evaluate compliance now. Remember: respond ONLY with valid JSON."
        )

        llm = self._get_llm_client()
        if llm is None:
            return self._safe_human_review_result(
                context, "LLM client is not available."
            )

        try:
            raw_response = await llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            return self._safe_human_review_result(
                context, f"LLM call failed: {exc}"
            )

        parsed = self._parse_llm_json(raw_response)
        if parsed is None:
            return self._safe_human_review_result(
                context, "LLM returned invalid JSON."
            )

        # Filter out any policy references not present in retrieved clauses
        parsed = self._sanitize_policy_references(parsed, valid_policy_ids)

        return parsed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_human_review_result(self, context: DisputeContext, reason: str) -> dict:
        """Return a conservative result that flags the dispute for human review."""
        return {
            "passenger_compliant": None,
            "driver_compliant": None,
            "violations": [],
            "policy_references": [],
            "reasoning": reason,
            "confidence": 0.0,
            "requires_human_review": True,
        }

    @staticmethod
    def _parse_llm_json(raw: str) -> dict | None:
        """
        Attempt to parse the LLM response as JSON.

        Strips common wrapping (markdown code fences, leading/trailing text)
        before parsing.  Returns None if parsing fails.
        """
        if not raw or not isinstance(raw, str):
            return None

        text = raw.strip()

        # Remove markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        # Try direct parse first
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract the first JSON object from the text
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                result = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None

        if not isinstance(result, dict):
            return None

        # Validate required keys are present (allow missing but fill defaults)
        defaults = {
            "passenger_compliant": None,
            "driver_compliant": None,
            "violations": [],
            "policy_references": [],
            "reasoning": "",
            "confidence": 0.0,
            "requires_human_review": True,
        }
        for key, default in defaults.items():
            if key not in result:
                result[key] = default

        # Type coercion for safety
        if not isinstance(result["violations"], list):
            result["violations"] = []
        if not isinstance(result["policy_references"], list):
            result["policy_references"] = []

        # Ensure confidence is a float
        try:
            result["confidence"] = float(result["confidence"])
        except (TypeError, ValueError):
            result["confidence"] = 0.0

        # Ensure requires_human_review is a bool
        if not isinstance(result["requires_human_review"], bool):
            result["requires_human_review"] = True

        return result

    @staticmethod
    def _sanitize_policy_references(parsed: dict, valid_refs: set[str]) -> dict:
        """
        Remove any policy references that do not appear in the retrieved clauses.

        If any references are dropped, set requires_human_review to True and
        append a note to the reasoning.
        """
        original_refs = parsed.get("policy_references", [])
        if not isinstance(original_refs, list):
            original_refs = []

        clean_refs = [ref for ref in original_refs if ref in valid_refs]

        if len(clean_refs) != len(original_refs):
            dropped = [r for r in original_refs if r not in valid_refs]
            note = (
                f" Removed {len(dropped)} unverified policy reference(s) that "
                "were not found in retrieved clauses."
            )
            parsed["reasoning"] = (parsed.get("reasoning", "") or "") + note
            parsed["requires_human_review"] = True

        parsed["policy_references"] = clean_refs
        return parsed
