# Design Decisions Log

Each entry records what we changed, why, what the data showed, and what it cost.
Numbers come from `scripts/eval.py` (14 end-to-end cases, Cerebras gpt-oss-120b,
1 run each) and `scripts/retrieval_eval/` (32 retrieval questions). With 14 cases,
one case is 7 points, and LLM runs are not deterministic, so small moves are noise.

---

## D1. Replace the paraphrased policy library with Ryde's official text (2026-09-29)

**Problem.** `data/policies/*.md` were AI-written paraphrases. Only 2-34% of their
sentences appear in Ryde's help centre, and some rules were invented: "no fee if the
driver is more than 10 min late", a "S$50-150 vomit range", P0-P3 tiers.

**Change.** `scripts/fetch_official_policies.py` pulls the help centre (public Zendesk
API) and five rydesharing.com pages, word for word, into `data/policies/official/`
(22 files, 61 articles).

**Effect.** CR-002 was wrong because the Policy agent retrieved two invented rules
("fee only after the driver arrives", "full refund if the driver did not arrive") and
missed the deciding one. On the official index it retrieves "cancel more than 3 min
after matching is chargeable" and rules correctly (see D6 table).

---

## D2. Retrieval: benchmark before choosing, keep our own RAG for rulings (2026-09-29)

**Test.** 32 questions (22 short policy questions, 10 raw complaints written like real
dispute text), each labelled with the official sections that answer it. Same scoring
for every system. ADP's retrieved passages were read from its SSE `token_stat` event.

| System | Hit@1 | Hit@3 | MRR | Time / query |
|---|---|---|---|---|
| Live config: bge-small + BM25, RRF | 0.78 | 0.91 | 0.854 | 15 ms |
| **bge-base + BM25, RRF** | **0.88** | **0.97** | **0.923** | 34 ms |
| bge-small + jina-turbo rerank | 0.88 | 0.94 | 0.914 | 2.7 s (CPU) |
| bge-base + bge-reranker-base | 0.88 | 0.94 | 0.907 | 9.7 s (CPU) |
| bge-small + title prefix in chunk | 0.72 | 0.91 | 0.820 | 31 ms |
| Tencent ADP (all 32) | 0.81 | 0.84 | 0.828 | 5.4 s |
| Tencent ADP (27 it actually searched) | 0.96 | 1.00 | 0.981 | |

**Decisions.**
- **Adopt bge-base.** +10 points Hit@1 for +20 ms. Indexed into a new Qdrant
  collection `ryde_policies_official`; the old shared collection is untouched.
- **No reranker for now.** It helps bge-small but adds 3-10 s per query on CPU, and
  bge-base alone reaches the same quality. Rerank on top of bge-base did not help.
- **No title prefix.** It made ranking worse (0.78 to 0.72 Hit@1).
- **ADP is an auxiliary, not the ruling retriever.** Its retrieval is the best we
  measured, but its intent router sent 5 of 32 policy questions (16%) to plain chat
  with no knowledge-base search, and nothing in the answer shows it. It also exposes
  no relevance scores (so no "not in policy" threshold), takes ~5 s per call, and runs
  only in ap-jakarta. Rulings auto-execute refunds, so they need retrieval that always
  runs, scores we can threshold, and traces we can audit. ADP fits the reviewer's
  policy assistant and rider/driver self-service Q&A, where a weak answer costs little.
- **Weak spot found: raw complaint text.** bge-base scores 1.00 Hit@1 on short questions
  but 0.60 on complaints, and complaints are exactly what the pipeline receives.
  Query rewriting is the next experiment (pending).

---

## D3. Retrieve once per dispute; type hints in official wording (2026-09-30)

Passenger, Driver and Policy agents each ran the same search with the same query.
`retrieve_for_dispute` now caches per query, so one dispute costs one search. The
per-type hint words appended to the query were rewritten from the invented rules'
vocabulary ("P0", "surge pricing", "driver arrival grace period") to the official
articles' wording ("I'm Here", "3 minutes of matching", "fee waiver request").

---

## D4. A missing deciding fact forces human review (2026-09-30)

**Problem.** NS-003: rider and driver each say they were at the pickup. The Collector
found the driver's GPS stopped at 07:19, so nobody can check. The Policy agent still
took the rider's word as fact (confidence 0.96) and the case auto-executed: first a
S$5 refund, and on the next run the opposite ruling. The ruling was a coin flip.

**Change.** New deterministic Fairness check `decisive_evidence_gap` (high severity):
for dispute types decided by where the driver was (no-show, cancellation refund,
route deviation), lost or missing driver GPS sends the case to a human, whatever the
LLM confidence. Only a *gap* counts; a *conflict* such as NS-001's "no-show recorded
but the driver never arrived" is evidence for the rider and does not block.

**Trade-off.** More cases can go to humans when GPS drops out. That is the right
direction for a system that pays out automatically.

---

## D5. "Side not considered" vs "side has no evidence" (2026-09-30)

**Problem.** CF-001, DISP-002 and SQ-001 went to human review for "one side's
evidence was not considered at all". In each, that side's advocate *had* analysed
the case and honestly found nothing in its favour (DISP-002: GPS shows the driver
waited 8 minutes, so the rider advocate has no evidence). The check counted evidence
items, so a clear case against one party looked like an ignored party.

**Change.** A side is "not considered" only when its advocate produced no analysis
(no stance, no reasoning), or when neither side has any evidence. An advocate that ran
and found nothing is now a medium note: it does not block execution but triggers the
LLM semantic review, which checks the ruling is grounded in the case evidence.

---

## D6. End-to-end results so far

| Run | Change | Verdict | Refund | Escalation | Wrong and auto-executed |
|---|---|---|---|---|---|
| 09-28 15:11 | old paraphrased index | 64% | 70% | 71% | CR-002, NS-003 |
| 09-30 09:48 | + D1-D3 official index, bge-base | 64% | 80% | 71% | NS-003 |
| 09-30 11:01 | + D4-D5 fairness fixes | **86%** | **90%** | **100%** | SQ-001 (see below) |

Cost per 14-case run is about US$0.12. Retrieval Hit@3 reads 100% on the official
index, but it is lenient: several cases accept any of 4-6 sections.

**Still open.**
- **RD-001** flips between runs (upheld, partially upheld, dismissed). Its answer key
  assumes a detour raises the fare, but official Ryde fares are fixed by pickup and
  drop-off. The case premise needs fixing before its result means anything.
- **SQ-001** auto-executed a full S$27.40 refund. The official text has no refund rule
  for rude or unsafe driving, so the amount has no policy basis. Candidate rule:
  a refund with no cited policy basis goes to a human.
- ~~Answer keys rest on invented rules~~ Done 2026-09-30: an independent audit of all 14
  keys; RD-002 became a metered RydeTAXI trip, SQ-001 accepts upheld or partially upheld,
  reasons cite "this trip's policy" where a rule is case-only, and the labelling conventions
  are written in `data/mock_disputes/README.md`. 13 held-out variants were added
  (`scripts/make_heldout_cases.py`), audited separately; one wrong label (NS-002-M1) was fixed.

---

## D7. Proposed: a shared case dossier, and advocates that can look up more policy

**What we found.** The Collector already builds a deterministic case file (facts,
conflicts and gaps, each with its source), but only the Arbitrator and Fairness agents
see it. The Passenger, Driver and Policy agents never do: in NS-003 none of their
prompts mention that the driver's GPS was lost. Advocates also get one shared set of
policy clauses and cannot search for rules that matter to their side.

**What the brief asks.** The MVP says the advocates "autonomously gather their
respective evidence" and cite company policy. RAG appears in the stretch goal
"Policy & Precedent Agent" (policies *and past rulings*, recommendations to the Judge).
So advocates should be able to look things up themselves, and a shared policy agent
is a bonus, not a replacement for that.

**Why advocates should not write their own search keywords.** They do not know the
official vocabulary ("I'm Here", "3 minutes of matching", "fee waiver request"): raw
wording scored 0.60 Hit@1 against 1.00 for policy wording (D2). They also carry wrong
premises into the query: in the rewrite test an LLM wrote "within 5 minutes" for a
rule that says "more than 3 minutes", and an advocate has a side to argue.

**Proposal.**
1. Give every agent the same dossier: the Collector's findings plus both parties'
   statements and evidence. Deterministic, so no new LLM call and nothing invented.
2. A Policy & Precedent agent runs the first, generic search from the dispute type and
   the Collector's facts (not the raw complaint) and publishes a base clause pool.
3. An advocate that needs more asks through that agent rather than inventing keywords:
   either it picks sections from the policy table of contents (about 110 headings,
   short enough to put in the prompt, tagged rider/driver), or it asks a plain-language
   question that the policy agent turns into official wording. Up to one or two extra
   lookups per side.
4. Every clause any agent retrieves goes into the shared pool that the other side, the
   Judge and Fairness all see, and citations are checked against that pool.
5. Later, add past rulings (precedents) to the same agent, as the brief describes.

**Measure first.** Add advocate-style questions (partisan, some with wrong premises) to
the retrieval test set and compare: advocate-written keywords vs asking the policy agent
vs picking from the table of contents. No LLM cost for the table-of-contents arm.

**Expected upside.** Advocates argue from established facts rather than one party's
claim (the NS-003 failure); side-specific searches can find rules the shared query
misses (the CR-002 failure); both sides see the same record.

**Risks.** More LLM calls, latency and cost (Cerebras allows 5 requests/min);
advocates may "shop" for favourable clauses, which is why the pool must be shared and
visible; more nondeterminism.

**Plan.** Ship step 1 alone, re-run the eval, then step 2 alone, so each step's effect
is measured separately and recorded here.

---

## D8. Learning feedback loop: human corrections become precedents, released only through the eval gate (2026-09-30)

**What the brief asks.** Stretch goal "Learning Feedback Loop": when a human reviewer overrides the
Judge, the correction is fed back into the Policy & Precedent knowledge base.

**What "self-evolution" means here.** Four levels, lowest risk first: (1) precedent memory,
(2) rule and threshold proposals, (3) prompt tuning, (4) fine-tuning. We build (1) now and (2) next.
(3) needs far more labelled cases than we have; (4) is out of scope.

**Design.**
- `src/store/db.py`: SQLite through SQLAlchemy (`STORE_URL`; a URL change moves it to Postgres or
  TencentDB). Tables: rulings, reviews, precedents, and a hash-chained audit log.
- Every pipeline result is recorded and returns a `ruling_id`. A reviewer confirms or overrides it
  (`POST /api/rulings/{id}/review`, a reason is required). An override, or any human decision on an
  escalated case, becomes a **pending** precedent. Confirming a correct automatic ruling does not.
- `src/rag/precedents.py`: precedents live in their own Qdrant collection, found by a deterministic
  fact summary built from the Collector's findings, never from either party's argument. The Judge's
  prompt shows the closest ones only when there are some. With an empty index the call is unchanged.
- Lifecycle (`src/store/feedback.py`, `scripts/precedents.py`):
  pending -> (human approves) -> **staged** -> (evaluation gate) -> **active** or rejected; active -> retired.
  Staged precedents are visible only to the candidate eval run (`eval.py --with-staged-precedents`).

**Safeguards (Responsible AI).**
1. Only human-confirmed outcomes are learned. Unreviewed AI rulings never become precedents, so a
   mistake cannot be repeated as an authority.
2. Release gate: the candidate eval must not lower verdict accuracy overall or on the held-out set,
   and must not worsen any hard safety metric (P0 escalation, refund cap, missing-data escalation,
   failure rate). A precedent that buys accuracy with safety is rejected.
3. No self-answering: a case never sees precedents from its own family (the case and its eval
   variants), so the evaluation cannot be answered by its own answer key.
4. Rollback: retiring a precedent removes it from the index at once; the record stays.
5. Tamper evidence: every change is in an append-only audit log where each entry hashes the previous
   one; `GET /api/audit/verify` finds the first altered entry.
6. Party input cannot enter the knowledge base: only a reviewer's decision and reason do.

**Verified.** 12 unit tests (lifecycle, gate, family exclusion, audit tampering, prompt section) and
a smoke test on the real Qdrant cluster with a throwaway collection: override -> pending -> staged
(invisible to live rulings, visible to the eval, invisible to the case's own family) -> gate passed ->
active -> retired -> gone. Full suite: 269 passed; the 2 failures predate this work.

**Not yet.** Level (2) rule proposals from override patterns; a reviewer screen in the dashboard;
per-party override-rate monitoring for fairness drift.

## D9. Eval covers stability and robustness; citation "key = value" fix (2026-09-30)

**Problem.** `eval.py` measured accuracy, speed, tokens and cost, but not the stability and
robustness targets of 06_EVAL_PLAN.md: `--repeat` runs were scored as independent runs, and the
held-out variants were scored one by one, never against the case they were derived from. Results
also had no column for the 09-25 baseline (07_EVAL_BASELINE.md).

**Change (`scripts/eval.py`, no LLM calls involved).**
- `paired_metrics()` compares runs with each other. A run's outcome is "escalated" or (verdict, refund).
  - `consistency` (target 90%): every run of a repeated case has the same outcome.
  - `paraphrase_invariance` (90%): a P-variant has the same outcome as its base case.
  - `counterfactual_sensitivity` (90%): a C-variant's outcome differs from the base AND is correct.
  - `injection_resistance` (100%): an I-variant is correct and its refund stays within the cap.
  - M (missing data) and B (boundary) variants stay scored by their answer key only.
- Each metric carries `baseline_0925`; the report adds a "By set" table (only dev is comparable with
  the baseline: different provider, policy library and case count) and a table of every pair.
- `--report-only` now picks up every saved repeat (`_r2`, `_r3`...), not only `--repeat`'s count.
- Tests: 6 offline tests in `tests/test_eval_scoring.py`. The case-count test now checks the 14
  dev cases only; the held-out count depended on test order.

**Bug found by the partial run 20260930-132225 (6/27 cases).** CR-002-P3 (Chinese complaint) had the
right verdict but was escalated: the Judge cited `free_cancellation_within_min_of_match = 3`, the
normaliser did not strip `= value`, so a real case-policy key was removed as unverified, which forces
human review. The language was not the cause. Fixed in `src/core/policy_refs.py`
(`tests/test_policy_refs.py`, 5 tests).

**Open.** CR-002-M2 (GPS removed, timing decides) was also right but escalated by
`decisive_evidence_gap` (D4): for cancellation disputes the rule fires on any missing GPS, even when
no arrival is claimed and the timing alone decides. Proposed narrowing, not yet applied: for
`cancellation_refund`, a GPS gap is decisive only when the platform records a driver arrival.

**Measured so far** (report rebuilt from the 6 saved traces): paraphrase invariance 0/1 (the
CR-002-P3 bug above), counterfactual sensitivity 1/1. Consistency needs a `--repeat` run.
Full suite: 282 passed.

**Full run 20260930-132225 (27 cases, Cerebras gpt-oss-120b, 1 run each).** A first resume went to
Groq by mistake (`.env` defaults to groq; Cerebras is chosen per command). Those 23 traces are kept
in `groq_invalid/` and were re-run. `eval.py` now stores the provider/model in every trace and
refuses to resume a folder made with another provider.

| Metric | Target | 09-25 baseline | Now (all 27) | Dev (14) | Held-out (13) |
|---|---|---|---|---|---|
| Verdict accuracy | 85% | 23% | 74% | **86%** | 62% |
| Refund accuracy | 85% | 11% | 68% | 80% | 58% |
| Classification / P0 / missing-data / refund cap / Hit@3 / citations / failures | | | all pass | | |
| Paraphrase invariance | 90% | — | 3/4 | | |
| Counterfactual sensitivity | 90% | — | 1/3 | | |
| Injection resistance | 100% | — | 2/3 | | |
| p50 end to end / compute | | 170 s / — | 91 s / 12 s | | |
| Tokens, cost per case | | ~21k | ~20k, $0.0088 | | |

The 7 wrong cases:
- RD-002, RD-002-I3: right verdict, escalated because citations written as `key: value (note)` were
  stripped. Fixed by extending the normaliser to `:` (2 more tests); replaying the 6 raw citations
  through the fix keeps all of them.
- CR-002-M2: `decisive_evidence_gap` too wide (open question above).
- FD-002-C3: right refund (S$9.60) but escalated: Fairness saw the Judge contradict the Policy
  agent, which had reported no violation. The Policy agent missed the case rule
  `surge_must_be_displayed_before_confirmation`.
- NS-002-B1 (7 min wait, 8 min threshold): the Judge used the 5-min free wait as the threshold.
- NS-002-C1 (driver not at pickup): the Collector found the conflict (`consistency.arrival_gps_far`,
  0.96 km) but the Judge ruled on the app's "arrived" event. The advocates never see findings; the
  Judge gets them buried in the raw context JSON. This is the case for D7 / experiment E.
- RD-001: the Judge cited "fares are fixed" and still refused the refund above the fixed fare, while
  its paraphrase RD-001-P4 ruled correctly: a reasoning error, and a sign of instability.

## D10. Case Brief: one shared dossier after classification; narrower GPS-gap rule (2026-09-30)

**Problem (from run 20260930-132225).** The advocates and the Policy agent never saw the Collector's
findings, the app event timeline or this trip's own rules (`platform_policy`, e.g.
`no_show_threshold_min`). Only the Judge got them, inside one raw JSON dump. Results: the Policy agent
missed `surge_must_be_displayed_before_confirmation` (FD-002-C3); the Judge ruled on an "arrived"
event the Collector had flagged as contradicted by GPS (NS-002-C1) and used the 5-min free wait as
the 8-min no-show threshold (NS-002-B1).

**Change.**
- New workflow node `case_brief` between the Classifier and the debate (`src/agents/case_brief.py`).
  No LLM: it cannot invent a fact and costs no tokens itself. It holds type and urgency, the
  Collector's facts / conflicts / gaps with sources, the case rules (citable as
  `platform_policy.<key>`), the app event timeline and the clause list from one RAG search (same
  query as the agents, so their lookups hit the retriever cache).
- A fact computed from a record that a conflict disputes (e.g. a wait timed from a contradicted
  arrival) is listed separately as "computed from a disputed record", not as verified.
- The rendered brief goes into the Passenger / Driver opening and rebuttal prompts, the Policy
  prompt and the top of the Judge prompt; the raw JSON sent to the Judge no longer repeats it.
  Prompts gained short rules: a conflict is not proof; cite case rules by key; apply each rule by its
  own value. The Policy agent must check every case rule against the facts.
- Advocates and the Policy agent accept case-rule citations (normalised like the Judge's).
- Fairness `decisive_evidence_gap`: for `cancellation_refund`, a GPS gap is decisive only when the
  platform records a driver arrival (trip field or `driver_arrived` event). With no arrival, timing
  decides (CR-002-M2). No-show and route cases are unchanged.
- Dashboard: a "Case Brief" node between the Classifier and the three agents.

**Cost.** About 750-850 tokens per brief, sent to about 6 prompts per case: roughly +5k tokens per
case (about 20k -> 25k), so about 40 cases per day on Cerebras instead of 50.

**Verified offline.** 7 tests in `tests/test_case_brief.py` (sorting, disputed facts, retrieval
failure, rendering, citations), 2 workflow tests (the debate receives the brief; a classifier
escalation skips it), 2 fairness tests. Full suite: 294 passed. Rendered briefs for NS-002-C1 and
NS-002-B1 checked by hand. Not yet measured end to end: needs a Cerebras run (quota exhausted today).

## D11. Policy sections tagged with dispute type and audience (2026-10-01)

**Why.** Step 1 of the agreed RAG plan: the Classifier will fetch the base clauses for the classified
type, and each agent may search for more. Tags let a search be ranked toward the right type and side.
Agreed limits: tags rank, they do not hard-filter (a misclassified case must still find its rule);
`general` sections match any type; the shared base clauses go to both sides, so audience only ranks an
agent's own extra searches and never hides a clause from either side.

**What.** `data/policies/official/policy_tags.json`: 153 sections (131 headings + 22 empty Overviews).
Proposed by a subagent, reviewed by hand. Changed after review: the cancellation-fee waiver also covers
no-show fees; the fixed-fare sections also cover route deviation; 6 waiting/cancellation-fee sections
are `both` (they bind the driver too); 4 legal sections no longer `general` (they would surface in
every search as noise). Final counts: driver_rights 32, fare_dispute 31, cancellation_refund 23,
no_show 20, service_quality 17, accident_liability 14, delivery_dispute 13, route_deviation 8,
general 7, none 63.

**Checks.** All 101 expected sections in the eval answer keys carry their case's type (before review,
8 no-show cases would have lost the waiver section). The indexer stores `dispute_types`, `audience`
and `dt_<type>` flags on each chunk (`src/rag/indexer.py`); `tests/test_policy_tags.py` (4 tests).

**Re-indexed 2026-10-01.** `ryde_policies_official` rebuilt: 165 chunks, all 165 carry tags (long
sections give several chunks, so chunk counts exceed section counts). Retrieval unchanged by design:
offline Hit@3 still 27/27. Retrieval does not use the tags yet (step 2).

## D12. Base clauses from the Case Brief, ranked by section tags; fact-built query rejected (2026-10-01)

**Plan agreed.** The Classifier's type picks the base clauses (one search, handed to every agent);
section tags rank results without filtering; the query might be built from verified facts instead of
the complaint (no LLM: a rewrite had invented a rule, D2).

**A/B** (`scripts/retrieval_eval/fact_query_eval.py`, 27 eval cases, live collection read-only, no LLM;
score = RRF rank score + w x tag; tag +1 for the case type or `general`, -1 for `none`):

| Variant | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| Complaint + type hint (before) | 0.815 | 1.00 | 0.895 |
| Fact-built query | 0.556 | 0.926 | 0.710 |
| Complaint + facts merged (RRF) | 0.815 | 0.963 | 0.892 |
| **Complaint, tags w=0.001 (adopted)** | **0.963** | 1.00 | 0.981 |
| Complaint, tags w=0.001, deliberately wrong type | 0.741 | 1.00 | 0.846 |
| Complaint, tags w=0.004, wrong type | 0.148 | 0.593 | 0.411 |

- The fact-built query lost: the findings are mostly measurements (km, speed, message counts), not
  policy wording. `src/rag/query_builder.py` is kept (marked unused) for the A/B; its `TYPE_HINTS`
  now feed the retriever.
- Tags help a lot, but weight matters: from w=0.004 they act like a hard filter and a misclassified
  case loses its rule (Hit@3 0.59). w=0.001 keeps the gain with the right type and keeps the right
  section in the top 3 with a wrong one. Worst case (every runner-up tagged with the wrong type) the
  plain top hit falls to 4th, still inside the 5 clauses agents receive (tested).
- A "keep the plain top 2" safeguard added nothing at w=0.001 and was not adopted.
- Caveat: the tag review used these answer keys once (the waiver section gained `no_show`), so the
  no-show part of the gain is optimistic; 27 cases written by us.

**Change.**
- `retrieve_for_dispute` searches a 20-chunk pool and returns the top 5 after `rank_by_tags`.
  Both stores now return each chunk's `dispute_types`.
- The Case Brief keeps the full text of its clauses; Passenger, Driver and Policy use them
  (`brief_clauses`) instead of searching, and the Judge may cite them. Outside the workflow (no brief)
  agents still search themselves.
- Tests: shared clauses (agent must not search), ranking keeps everything and the worst-case bound.
  Full suite 301 passed. Offline Hit@3 27/27. End-to-end effect still needs a Cerebras run.

## D13. Guarded LLM query rewrite (2026-10-01, rejected by the A/B)

**Why.** The complaint is a weak query (D2: Hit@1 0.60 for complaint-style questions). The earlier
rewrite prompt asked for "key facts (times, amounts)" and invented one: a policy question with no number
came back as "within 5 minutes" (cached Q04). Re-checking the cache: 1 of 24 rewrites invented a number;
a second suspect (Q02 "5 min") restated "about five minutes" and was faithful.

**What.** `src/rag/guarded_rewrite.py` (new; the older `src/rag/query_rewriter.py` used by
`advanced_retriever.py` is unchanged): the prompt allows rewording only, no new fact, number, time,
amount or rule, and treats the message as data. A deterministic check then rejects any rewrite with a
number not in the complaint (number words count: "five" = 5), or empty / over 30 words; a rejected
rewrite falls back to the complaint. Tests: `tests/test_guarded_rewrite.py` (the real Q04 is rejected,
Q02 accepted). A/B script: `scripts/retrieval_eval/rewrite_guarded_eval.py` (59 short Cerebras calls,
cached). Not wired into the pipeline until it beats complaint + tags.

**Result** (run 2026-10-01, Cerebras, `data/eval/retrieval/rewrite_guarded.json`):

| Set | Raw Hit@1 | Rewrite Hit@1 | Both (RRF) Hit@1 |
|---|---|---|---|
| 27 cases, tag-ranked | 0.963 | 0.963 | 0.963 |
| 10 complaint-style questions | 0.60 | 0.50 | 0.60 |
| 22 short questions | 1.00 | 0.727 | 0.818 |

The guard rejected 0 of 59: the strict prompt stopped invented numbers. But rewrites drift in meaning,
which no number check can catch (NS-002, a rider charged a no-show fee while the driver was there,
became "driver cancellation fee waiver request for late arrival"). 8 of 59 outputs were also doubled
("...waiting feerating removal waiting fee"), an extraction bug; fixing it cannot close the 0.27 drop
on short questions. Decision: not adopted. The complaint stays the query; the gap from short
complaints is closed by topics instead (D14: recall 0.744 -> 0.92). Module and tests are kept.

## D14. Base clauses: complaint + type core topics + data-triggered topics; advocates may request topics (2026-10-01)

**Why.** A complaint is often one sentence, so a search with it misses rules the case turns on.

**Topic catalogue** (`src/rag/policy_topics.py`, 14 topics, no LLM): each topic is fixed official
wording plus the section tags it may come from (filtered search; Qdrant needs bool payload indexes on
`dt_*`, created by `QdrantStore.ensure_tag_indexes`). The Case Brief's base clauses = complaint search
(tag-ranked) + the classified type's core topics + topics the platform data triggers (cancellation fee
charged, no-show cancellation, waiting timer, surge, ERP/toll in the fare, route alerts, cleaning claim,
safety alerts, RydeSEND). Triggers read platform records only, never the complaint. Each clause records
`found_by`. Cap 10 clauses (each cut to 500 characters in prompts).

**Measured** (`scripts/retrieval_eval/base_pool_eval.py`, 27 cases, share of expected sections that
reach the agents):

| | Recall | Every expected section present |
|---|---|---|
| Complaint search only (before) | 0.744 | 0.185 |
| + topics, cap 8 (first try) | 0.793 / 0.84 (varied by run) | 0.296 / 0.481 |
| + topics, cap 10, deterministic ties, distinct sections, transaction-fee topic | **0.92** (stable) | **0.667** |

The run-to-run variation came from score ties between near-identical sections (cancellation vs waiting
fee waiver): Qdrant broke them differently each run and the cap cut the second. Results are now sorted
by score then chunk id. Caveat: the transaction-fee topic was added after seeing that all fare cases
missed that section. Left as is: "Will I be charged for cancelling a ride?" (restates a rule already
present) is still missed in the cancellation cases.

**Advocate requests.** Passenger and Driver may list up to 2 catalogue topics in `policy_requests`
(anything else is ignored). The debate fetches them after the openings into the SHARED brief: the
rebuttals of both sides and the Judge read the full text, so no side argues from a rule only it saw.
`DebateEngine.debate_with_context` returns the updated context; the workflow keeps it.

**Tests.** 16 in `tests/test_case_brief.py` (merge without duplicates, cap, triggers ignore the complaint,
request validation, shared requested clauses). Full suite 312 passed (before the 3 request tests).
End-to-end effect needs a Cerebras eval.

## D15. Eval 20261001-114026, its fixes, fewer tokens per prompt (2026-10-01)

**Run** (27 cases, Cerebras, with D10-D14): verdict accuracy 63% (17/27), down from 74%. Not a
reasoning regression: the Judge ruled correctly in 6 of the 10 misses.

| Cause | Cases | Fix |
|---|---|---|
| Fairness did not accept clauses from the Case Brief (topic fetches), so correct citations looked hallucinated (my miss: the Judge side was updated in D12, Fairness was not) | FD-002, FD-002-I2, FD-002-P2, NS-002, NS-002-I1 | Brief clause refs count as retrieved in `FairnessAgent._build_valid_refs` |
| Fairness' LLM check read "upheld" as "the fee is upheld" | NS-001 | The prompt states what each verdict label means and the refund |
| Right refund, label `partially_upheld` instead of `upheld` | FD-002-C3 (S$9.60), RD-001-P4 (S$3.70) | `align_verdict_label`: a refund equal to the full disputed amount (fee charged, or excess over the quoted fare, from platform data) is `upheld` |
| Judge kept a no-show fee on a contradicted arrival / with a 7-min wait under an 8-min threshold, despite the D10 prompt rules | NS-002-C1, NS-002-B1 | New deterministic Fairness check `fee_basis_not_met` (high -> human review) |

Replayed on all 27 recorded rulings (no LLM): the label rule changes exactly the 2 cases above; the
fee-basis check flags exactly NS-002-B1 and C1 and no correct ruling. Projection if the re-run Judge
rules as recorded: 25/27 (B1 and C1 go to a person rather than being decided).

**Tokens.** Per case 29.0k (up from 20k: brief + clauses). By agent: Judge 26%, openings 36%, Policy 15%,
rebuttals 17%, Fairness 7%. The same data was sent twice per prompt (raw GPS/JSON and the brief's
facts computed from it), and clauses were indented JSON. Changes (only when a brief exists):
- raw GPS points replaced by a one-line pointer; the Judge's raw dump drops what the brief states
  (`SUMMARISED_FIELDS`: gps_trace, findings, app_events, platform_policy);
- clauses rendered as compact text (`render_clauses`); the brief's clause list omitted where the full
  clause text follows.
Measured offline (`scripts/retrieval_eval/prompt_size.py`, 27 cases, user prompt ~chars/4):
Passenger 2909 -> 2256 (-22%), Driver 3082 -> 2429 (-21%), Judge 5717 -> 4516 (-21%). Policy gets the
same changes. Also added, off by default: `ADVOCATE_REASONING_EFFORT` (gpt-oss reasoning effort for the
two advocates only; their openings average ~1.3k output tokens). Turn on only if an eval shows no loss.

Tests: `tests/test_ruling_guards.py` (9), 1 Fairness test for brief clauses. Full suite 325 passed.
**Confirming run 20261001-203206** (all 27 cases, Cerebras, final code): verdict accuracy **92.6%
(25/27)**, refund accuracy **90.9% (20/22)**, matching the replay projection exactly. Dev 14/14,
held-out 11/13. All 8 cases fixed above now resolve correctly; the only misses are NS-002-B1 and
NS-002-C1, which the `fee_basis_not_met` check sends to a person as intended (the Judge's reasoning
error is caught, not fixed). Classification 100%, escalation accuracy 92.6%, P0 recall, refund cap,
missing-data escalation and Hit@3 all 100%. Paired checks 9/10 (the NS-002-C1 counterfactual is the
one failure). Tokens 678.5k in total, 25.1k per case (-13% vs 29.0k), 0 LLM errors.

**What the traces credit to which fix.** The label rule fired in RD-001-P4 (the `[Label: …]` marker
is in its rationale); `fee_basis_not_met` fired in both NS-002-B1 and C1. But in the five
previously-blocked FD-002/NS-002 cases the Judge this time cited only `platform_policy.*` fields or
Policy-retrieved clauses, which the old whitelist already accepted — and FD-002-C3's Judge wrote
`upheld` itself. So this run does not exercise the brief-clause whitelist fix (its evidence remains
the replay of run 114026 plus the unit test), and 4 of the 8 recovered cases passed because the LLM
output differed, not because a fix fired. The 93% therefore still needs the stability measurement
(`--repeat 3`) before it is quoted as a stable number.

**Stability run 20261002-100226** (the 8 previously flaky cases x 3 repeats, Cerebras): 24/24
verdicts and 24/24 refunds correct, consistency 1.0 (the earlier runs had no repeats, n=0). Cost
US$0.26. The 92.6% is stable on the cases that used to flip.

**New held-out cases, baseline 20261002-105854.** Six cases written after the fixes above, so the
code was never tuned on them (SQ-002, FD-003, CF-002, NS-004, DR-002, CR-003; loader now sees 33
cases, retrieval Hit@3 6/6). Verdict 3/6: CF-002, NS-004, DR-002 correct. The two label misses had the **right refund
amount**; FD-003 should have gone to a person and was paid S$7.20 instead (a routing error that
executed money, the more serious kind):

| Case | Expected | Got | Cause |
|---|---|---|---|
| SQ-002 (detour S$4.20 + rude driver) | partially_upheld | upheld | `align_verdict_label` forced `upheld` (`[Label:]` in the trace): the refund equals the detour excess, but the conduct ask got no money. The rule is blind to filings with more than one ask |
| CR-003 (fee S$5 + promo already returned) | partially_upheld | upheld | Judge labelled it; one of two asks was denied |
| FD-003 (12.5-min GPS gap on the contested stretch) | escalate | upheld S$7.20 | The GPS-gap check covers no_show / cancellation / route types only, not metered fare disputes (predicted when the cases were written) |

Fixes are deferred until the answer keys are blind-judged by a person (a disagreement means the key
may be wrong): a multi-ask guard on `align_verdict_label`, a Judge prompt line on multi-ask labels,
and the GPS-gap check extended to metered fare disputes. Four fraud cases (`data/eval_cases/fraud/`)
are excluded from the default eval until the Fraud Agent (docs/09) exists.

## D16. Label from the asks; GPS gap blocks metered fare disputes; overfitting protocol (2026-10-02)

**Fixes** for the three baseline misses in D15 (two had the right money but the wrong label; FD-003 paid out a case that should have gone to a person):
- **Label computed from the asks.** The Judge now lists each thing the filer asked for with an
  outcome (`granted` / `partly` / `denied` / `already_resolved`) and `label_from_asks` computes the
  label: all satisfied -> upheld, all denied -> dismissed, otherwise partially_upheld. The Judge's own
  label stands only when the list is missing or malformed. `already_resolved` (e.g. a promo the platform
  returned automatically) counts as satisfied: a definition decided by the user before any re-run, which
  changes CR-003's key to `upheld`. `align_verdict_label` (D15) now skips filings with more than one ask
  (SQ-002: the refund equalled the detour excess but the conduct ask got no money).
- **GPS gap on metered fares.** `_location_evidence_gaps` also blocks a `fare_dispute` when the fare is
  metered (`platform_policy.fare_basis` or the booking event): a metered fare depends on the route driven.
  An upfront fare is fixed by the quote and stays unblocked (FD-003).

**Checks before any LLM run.** 10 new unit tests in `tests/test_ruling_guards.py`, each rule tested in
both directions (fires where it should, silent where it should not: upfront fare + GPS gap, metered fare
without a gap, one-ask filing still promoted). Replay of the GPS rule over all 57 recorded traces (runs
203206, 100226, 105854): it changes FD-003 only. The label change needs a new Judge field, so it can only
be measured by a re-run.

**Overfitting protocol** (from now on):
1. Fix the rule, not the case: no case IDs, amounts or wording in code; each fix states the general
   principle (here: the label definition; "a metered fare depends on the route").
2. Test both directions: every new rule gets a test where it must NOT fire.
3. Replay before re-run: a rule that changes only the case it was written for, across all recorded
   traces, is expected; one that changes correct rulings is rejected.
4. Once a case has motivated a fix it no longer counts as held-out evidence. The six cases of run
   105854 are reported separately as "used for fixes"; the generalisation number must come from a new
   sealed set, written without access to the code, run once before submission.
5. Answer-key changes are decided from the definition, before the re-run, and recorded with the date
   (CR-003 above), never to match an output.

**Empty rebuttals (found 2026-10-02).** Rebuttals were capped at `max_tokens=300`. gpt-oss counts its
hidden reasoning in that budget, so 18 of 108 rebuttals in run 203206 (17%) used all 300 tokens on
reasoning and returned nothing; the debate then carried a "could not be generated" placeholder. Every
empty reply in the run had exactly 300 completion tokens. Now `REBUTTAL_MAX_TOKENS` (default 1500; the
180-word limit stays in the prompt), and the client logs a warning when a reply is empty because the
budget ran out. All earlier numbers, including the 92.6%, were measured with these gaps in the debate;
the next run measures full debates.

## D17. Full-debate run 20261002-211912; two payout guards (2026-10-04)

**Run** (33 cases, Cerebras, with D16 and full rebuttals): verdict **29/33 (87.9%)**, 0 LLM errors,
864k tokens, US$0.37. Paraphrase 4/4, injection 3/3, counterfactual 2/3 (NS-002-C1 as before).
The D16 fixes worked where they were aimed: FD-003 now goes to a person, CR-003 is `upheld` S$5.00.

| Case | Expected | Got | Cause |
|---|---|---|---|
| NS-002-B1, NS-002-C1 | upheld S$8 | to a person | Judge no-show reasoning, caught by `fee_basis_not_met` (unchanged since D15) |
| SQ-002 | partially_upheld S$4.20 | upheld **S$22.60** | Judge merged the two asks into "full fare refund", granted it citing `refund_at_ryde_discretion`. The previous run gave S$4.20: run-to-run variation, not the D16 code |
| CR-001 (dev) | upheld S$4 | dismissed | Judge read the trip's `no_fee_if_driver_delayed_beyond_eta_min = 10` as applying only if the driver arrives; the driver was 12.5 min past the ETA |

**Finding: missing rebuttals had been helping.** In runs 114026 and 203206 one of CR-001's two
rebuttals was empty (the D16 token-budget bug). With the driver's rebuttal present ("the driver was
still en route"), the Judge was persuaded. Part of the earlier 92.6% rested on one side being silent;
full debates expose the Judge's weakness on fee waivers.

**Guards, not answer fixes** (D16 protocol: general rule, both directions tested, replayed first):
- `fee_basis_not_met` also fires when the fee is kept although the trip's own
  `no_fee_if_driver_delayed_beyond_eta_min` is exceeded by the data (`wait_time.no_arrival` /
  `wait_time.arrival_vs_scheduled`).
- New high-severity check `refund_beyond_disputed_amount`: a refund larger than the disputed amount
  the platform data computes (fee charged, or excess over the quote) goes to a person.
Both only route to human review; they never change a ruling. Replay over all 140 recorded rulings
(runs since 20260930-132225): each fires once, on the wrong ruling it was written for, and on no
correct ruling. Projected: still 29/33 decided correctly, but every one of the four misses now goes to
a person, so **no wrong ruling would be executed automatically**. 6 tests; suite 341 passed.

Not changed: the Judge prompt. A fee-waiver prompt line would be written for CR-001 alone; the guard
catches the error class without tuning the prompt to one case. Revisit if the sealed set shows it.

## D18. Judge reasoning principles: run 20261004-083956 (2026-10-04)

**Prompt change.** Four general principles in the Judge's system prompt (no case ids or amounts): a rule
applies exactly when its written condition is met; every amount comes from a specific rule applied to
a specific figure (a discretion clause allows a refund but sets no amount); an advocate's argument is
not evidence; split a filing into its separate asks.

**Run** (33 cases, Cerebras, full debates): verdict **30/33 (90.9%)**, up from 29/33 in D17; 875k
tokens, US$0.38, 0 LLM errors. Newly correct: CR-001 (the delay waiver) and NS-002-B1, which no earlier
run had right: the Judge itself now applies the no-show threshold, without the D15 guard. Misses:
- NS-002-C1: sent to a person by `fee_basis_not_met` (unchanged).
- SQ-002: the Judge ruled S$4.20 with its single merged ask marked `partly` (correct), and our D15
  label rule relabelled it `upheld` because the refund equalled the S$4.20 disputed excess. Second
  time this rule caused an error. **Fix:** the amount rule now applies only when the Judge gives no
  asks list; the asks know what was asked for (S$22.60), the disputed amount does not. Replay over
  the two runs with asks lists: the rule fired once, on this case, wrongly.
- SQ-001 (dev, newly wrong): unsafe driving, rider asks for the fare. The Judge warned the driver,
  refunded nothing and labelled it dismissed; the key accepts partially_upheld / upheld. Both SQ keys
  (written 2026-09-30 and 10-02, before these changes) treat a complaint about conduct as an ask that
  a warning grants. **Fix:** the prompt states that definition: a conduct complaint is an ask, granted
  when the ruling acts on it. Not a key change.

**Overfitting note.** The Judge prompt has now been changed three times in response to these 33
cases (D16 asks, D18 principles, D18 conduct line). Each change is general, but the 33 cases can no
longer show whether the changes generalise; only the sealed set (run once, before submission) can.

**Discretionary refunds go to a person (user decision 2026-10-04).** Repeat run 20261004-145849
(SQ-001, SQ-002 x3): SQ-002 3/3 correct and stable (S$4.20, partially_upheld). SQ-001 got an accepted
label 3/3 but refunded the whole S$27.40 fare each time on "compensation at Ryde's discretion",
although the Judge prompt says a discretion clause sets no amount. Ryde's policy has no refund schedule
for rude or unsafe driving, so the user decided a refund there is a person's call. `_refund_basis_problems`
now also flags a service-quality refund that is not a fare overcharge (no disputed amount). A broader
first version (any refund without a computed disputed amount) was rejected on replay: it also caught
correct rule-based amounts (CF-001 S$150 fee, DR-001 S$120, DR-002 S$200 cap). The narrow version fires
only on SQ-001 (and the S$22.60 SQ-002 overpayment) across all recorded rulings. A warning-only ruling
stays automatic. New key option `escalation_acceptable` (SQ-001): deciding or escalating both count.
