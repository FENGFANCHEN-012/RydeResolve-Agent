"""Case brief: the shared dossier every agent sees after classification (no LLM)."""
import pytest

from src.agents.case_brief import CaseBriefAgent, case_rule_refs, render_case_brief
from src.agents.collector import DisputeContext
from src.agents.passenger import PassengerAgent


class FakeRetriever:
    """Complaint search returns `clauses`; a topic search returns `topic_hits` (any topic)."""
    def __init__(self, clauses=None, fail=False, topic_hits=None):
        self.clauses, self.fail, self.topic_hits = clauses or [], fail, topic_hits or []

    def retrieve_for_dispute(self, dispute_type, dispute_description):
        if self.fail:
            raise RuntimeError("index down")
        return self.clauses

    def retrieve(self, query, top_k=5, collection_name=None, any_tags=None):
        if self.fail:
            raise RuntimeError("index down")
        return self.topic_hits[:top_k]


@pytest.fixture(autouse=True)
def _fresh_retrieval_cache():
    from src.rag import retriever
    retriever._DISPUTE_CACHE.clear()
    yield
    retriever._DISPUTE_CACHE.clear()


def _context(**over):
    base = dict(
        dispute_id="NS-002-C1", type="no_show", reporter="passenger", order_id="RYDE-HELD-010",
        description="I was charged a no-show fee but the driver never came.",
        platform_policy={"no_show_threshold_min": 8, "free_wait_time_min": 5},
        app_events=[{"timestamp": "17:59", "event_type": "driver_arrived"}],
        findings=[
            {"id": "wait_time.total", "tool": "wait_time", "kind": "fact",
             "statement": "Driver waited 8.0 min.", "sources": ["app_events[0]"]},
            {"id": "consistency.arrival_gps_far", "tool": "consistency_check", "kind": "conflict",
             "statement": "driver_arrived was logged but GPS was 0.96 km away.", "sources": ["gps_trace[3]"]},
            {"id": "data_gaps.missing_sources", "tool": "data_gaps", "kind": "gap",
             "statement": "Missing platform data: payment."},
        ],
    )
    base.update(over)
    return DisputeContext(**base)


@pytest.mark.asyncio
async def test_brief_sorts_findings_rules_timeline_and_clauses():
    clauses = [{"source": "Ryde Help Rider Booking A Ryde", "chunk_index": 3, "section": "Grace period"}]
    brief = await CaseBriefAgent(retriever=FakeRetriever(clauses)).build(_context())
    assert [f["id"] for f in brief["facts"]] == ["wait_time.total"]
    assert [f["id"] for f in brief["conflicts"]] == ["consistency.arrival_gps_far"]
    assert [f["id"] for f in brief["gaps"]] == ["data_gaps.missing_sources"]
    assert brief["case_rules"] == {"platform_policy.no_show_threshold_min": 8,
                                   "platform_policy.free_wait_time_min": 5}
    assert brief["timeline"][0]["event"] == "driver_arrived"
    assert brief["clauses"] == [{"reference": "Ryde Help Rider Booking A Ryde#3", "section": "Grace period",
                                 "found_by": ["complaint"]}]


@pytest.mark.asyncio
async def test_retrieval_failure_still_gives_a_brief():
    brief = await CaseBriefAgent(retriever=FakeRetriever(fail=True)).build(_context())
    assert brief["clauses"] == [] and brief["conflicts"]


@pytest.mark.asyncio
async def test_rendered_brief_shows_conflicts_and_citable_rules():
    ctx = _context()
    ctx = ctx.model_copy(update={"case_brief": await CaseBriefAgent(retriever=FakeRetriever()).build(ctx)})
    text = render_case_brief(ctx)
    assert "CONFLICTS" in text and "0.96 km" in text
    assert "platform_policy.no_show_threshold_min = 8" in text
    # the same text is produced from the dict form the Judge receives
    assert render_case_brief(ctx.model_dump()) == text


def test_no_brief_renders_nothing():
    assert render_case_brief(_context()) == ""
    assert case_rule_refs(_context()) == set()


@pytest.mark.asyncio
async def test_advocate_keeps_case_rule_citation_from_the_brief():
    ctx = _context()
    ctx = ctx.model_copy(update={"case_brief": await CaseBriefAgent(retriever=FakeRetriever()).build(ctx)})
    valid = {"Ryde Help Rider Booking A Ryde#3"} | case_rule_refs(ctx)
    parsed = PassengerAgent._sanitize_policy_references(
        {"policy_references": ["no_show_threshold_min = 8", "Invented Policy#9"], "reasoning": ""}, valid)
    assert parsed["policy_references"] == ["platform_policy.no_show_threshold_min"]


@pytest.mark.asyncio
async def test_fact_from_a_disputed_arrival_is_flagged():
    wait = {"id": "wait_time.waited_before_cancel", "tool": "wait_time", "kind": "fact",
            "statement": "Driver waited 8.0 min.", "sources": ["trip.driver_arrival_time", "trip.cancellation_time"]}
    contact = {"id": "contact_attempts.driver", "tool": "contact_attempts", "kind": "fact",
               "statement": "The driver sent 3 messages.", "sources": ["chat_log[0]"]}
    conflict = {"id": "consistency.arrival_gps_far", "tool": "consistency_check", "kind": "conflict",
                "statement": "driver_arrived was logged but GPS was 0.96 km away.",
                "sources": ["app_events[0]", "gps_trace[2]", "trip.pickup_location"]}
    agent = CaseBriefAgent(retriever=FakeRetriever())
    brief = await agent.build(_context(findings=[wait, contact, conflict]))
    flags = {f["id"]: f["disputed"] for f in brief["facts"]}
    assert flags == {"wait_time.waited_before_cancel": True, "contact_attempts.driver": False}
    # without the conflict the same wait is an ordinary verified fact (NS-002-B1)
    brief = await agent.build(_context(findings=[wait, contact]))
    assert not any(f["disputed"] for f in brief["facts"])


# ---------------------------------------------------------------- shared base clauses + tag ranking

@pytest.mark.asyncio
async def test_agents_use_the_brief_clauses_instead_of_searching():
    clause = {"source": "Ryde Help Rider Booking A Ryde", "chunk_index": 3, "section": "Grace period",
              "clause": "Riders are guaranteed 3 minutes of grace period."}
    ctx = _context()
    ctx = ctx.model_copy(update={"case_brief": await CaseBriefAgent(retriever=FakeRetriever([clause])).build(ctx)})

    class MustNotSearch:
        def retrieve_for_dispute(self, **_):
            raise AssertionError("agent searched although the brief has clauses")

    got = await PassengerAgent(retriever=MustNotSearch())._retrieve_policies(ctx)
    assert got == [{**clause, "found_by": ["complaint"]}]


def test_tag_ranking_moves_matching_sections_up_but_removes_nothing():
    from src.rag.retriever import rank_by_tags
    chunks = [{"section": "privacy", "dispute_types": "none"},
              {"section": "fees", "dispute_types": "fare_dispute"},
              {"section": "waiting", "dispute_types": "no_show,cancellation_refund"},
              {"section": "appeals", "dispute_types": "general"}]
    ranked = [c["section"] for c in rank_by_tags(chunks, "no_show")]
    assert ranked[0] == "waiting" and ranked[-1] == "privacy"
    assert sorted(ranked) == sorted(c["section"] for c in chunks)


def test_tag_weight_is_too_small_to_bury_the_best_match():
    # Worst case for a misclassified case: every runner-up matches the (wrong) type and the
    # plain top hit does not. It drops to 4th but stays inside the 5 clauses agents receive (D12)
    from src.rag.retriever import rank_by_tags
    chunks = [{"section": f"s{i}", "dispute_types": "fare_dispute"} for i in range(20)]
    chunks[0]["dispute_types"] = "no_show"
    ranked = [c["section"] for c in rank_by_tags(chunks, "fare_dispute")]
    assert ranked.index("s0") < 5


# ---------------------------------------------------------------- topics (D14)

@pytest.mark.asyncio
async def test_topic_clauses_join_the_complaint_hits_without_duplicates():
    grace = {"source": "Ryde Help Rider Booking A Ryde", "chunk_index": 3, "section": "Grace period", "clause": "g"}
    waiver = {"source": "Ryde Help Rider Fares And Charges", "chunk_index": 2, "section": "Waiver", "clause": "w"}
    brief = await CaseBriefAgent(retriever=FakeRetriever([grace], topic_hits=[waiver, grace])).build(_context())
    refs = [c["reference"] for c in brief["clauses"]]
    assert refs == ["Ryde Help Rider Booking A Ryde#3", "Ryde Help Rider Fares And Charges#2"]
    # the grace clause was found by the complaint AND by topics; the reasons are kept
    assert brief["clauses"][0]["found_by"][0] == "complaint" and len(brief["clauses"][0]["found_by"]) > 1
    assert "no_show" in brief["topics"]          # core topic of the type
    assert "found by:" in render_case_brief(ctx := _context().model_copy(update={"case_brief": brief}))


@pytest.mark.asyncio
async def test_base_clauses_are_capped():
    from src.agents.case_brief import MAX_BASE_CLAUSES
    many = iter({"source": "S", "chunk_index": i, "section": f"s{i}", "clause": "x"} for i in range(100))

    class Plenty(FakeRetriever):
        def retrieve(self, query, top_k=5, collection_name=None, any_tags=None):
            return [next(many) for _ in range(top_k)]   # new clauses for every topic

    brief = await CaseBriefAgent(retriever=Plenty([next(many) for _ in range(5)])).build(_context())
    assert len(brief["clauses"]) == MAX_BASE_CLAUSES


def test_platform_data_triggers_topics_but_the_complaint_does_not():
    from src.rag.policy_topics import triggered_topics
    ctx = _context(description="I want a refund for the surge and the cleaning fee!",
                   trip={"cancellation_fee": 4.0, "cancellation_reason": "rider_no_show"},
                   app_events=[{"event_type": "speeding_alert"}])
    topics = triggered_topics(ctx)
    assert {"cancellation_fee", "refund", "no_show", "waiting_fee", "safety_conduct"} <= set(topics)
    assert "fare_surge" not in topics and "cleaning_fee" not in topics   # only said in the complaint


def test_every_type_topic_is_in_the_catalogue():
    from src.rag.policy_topics import TOPICS, TYPE_TOPICS
    assert all(t in TOPICS for ts in TYPE_TOPICS.values() for t in ts)


# ---------------------------------------------------------------- advocates' topic requests (D14)

def test_only_catalogue_topics_are_accepted_and_at_most_two():
    from src.agents.case_brief import valid_requests
    analysis = {"policy_requests": ["Refund", "give me $100", "no_show", "waiting_fee", "refund"]}
    assert valid_requests(analysis) == ["refund", "no_show"]
    assert valid_requests({"policy_requests": "refund"}) == []      # not a list
    assert valid_requests("not a dict") == []


@pytest.mark.asyncio
async def test_requested_clauses_join_the_shared_brief_for_both_sides():
    from src.agents.case_brief import add_requested_clauses
    base = {"source": "A", "chunk_index": 1, "section": "base", "clause": "b"}
    new = {"source": "B", "chunk_index": 2, "section": "Waiver", "clause": "waiver text"}
    ctx = _context()
    ctx = ctx.model_copy(update={"case_brief": await CaseBriefAgent(retriever=FakeRetriever([base])).build(ctx)})
    from src.rag import retriever as r
    r._DISPUTE_CACHE.clear()
    updated, added = await add_requested_clauses(ctx, {"passenger": ["refund"], "driver": []},
                                                 FakeRetriever(topic_hits=[new, base]))
    assert [c["section"] for c in added] == ["Waiver"]                  # base clause not repeated
    texts = updated.case_brief["clause_texts"]
    assert texts[-1]["found_by"] == ["requested by passenger: refund"]
    assert "waiver text" in render_case_brief(updated)                    # both sides read the text
    assert ctx.case_brief["clause_texts"] != texts                       # original context untouched


@pytest.mark.asyncio
async def test_no_requests_leaves_the_context_unchanged():
    from src.agents.case_brief import add_requested_clauses
    ctx = _context()
    same, added = await add_requested_clauses(ctx, {"passenger": [], "driver": []}, FakeRetriever())
    assert same is ctx and added == []
