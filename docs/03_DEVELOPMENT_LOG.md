# Development Log — Key Milestones

> **Last updated**: 2026-10-05
>
> This log records the key milestones, decisions, problems and next steps of every session.
> Latest update adds Session 6 (2026-10-02 – 10-05): ask-based labels, payout guards, Judge reasoning principles, Supabase record store, rider/driver history, LLM provider fallback, regression run 31/33 and the merge into `main` (PR #18).

---

## Session 1: 2026-09-21 (billy, solo session)

### Node 1: Project initialisation
- **Time**: morning
- **Work**: created the project structure and initialised the Git repository
- **Files**: `src/`, `frontend/`, `data/`, `.env.example`
- **Commit**: initial commit

### Node 2: Basic RAG pipeline
- **Time**: morning
- **Work**: document parsing, vector retrieval, question answering
- **New files**:
  - `src/rag/document_parser.py` — PDF/DOCX/TXT/MD parsing
  - `src/rag/embedding.py` — Hunyuan embedding + hash fallback
  - `src/rag/indexer.py` — ChromaDB indexing
  - `src/rag/retriever.py` — vector retrieval
  - `src/rag/qa_engine.py` — RAG question answering
  - `src/core/llm_client.py` — OpenAI-compatible LLM client
  - `src/api/main.py` — FastAPI endpoints
  - `frontend/index.html` — frontend UI
- **Commit**: `b787fbb` — feat: add RAG pipeline, frontend UI, and accuracy testing

### Node 3: End-to-end test
- **Time**: midday
- **Work**: tested the full upload → retrieve → answer flow
- **Result**: ✅ all passed (but embeddings were in hash mode, so similarity was 0)

### Node 4: Migration to Google Gemini
- **Time**: afternoon
- **Reason**: Tencent Hunyuan API keys were hard to obtain and the model had been taken offline
- **Changes**:
  - `src/config.py` — switched to Gemini configuration
  - `src/core/llm_client.py` — switched to the Gemini SDK
  - `src/rag/embedding.py` — switched to Gemini embeddings
  - `.env` — updated API key
- **Problem**: ChromaDB dimension mismatch (1024 -> 3072)
- **Fix**: deleted the old collection and re-indexed
- **Commit**: `233a01f` — feat: migrate LLM and embedding from Hunyuan to Google Gemini

### Node 5: Advanced retrieval pipeline (5 optimisations)
- **Time**: afternoon
- **Work**: implemented 5 RAG retrieval optimisation techniques
- **New files**:
  - `src/rag/query_rewriter.py` — Query Rewriting
  - `src/rag/hybrid_search.py` — Hybrid Search (Vector + BM25)
  - `src/rag/reranker.py` — Re-ranking
  - `src/rag/smart_chunker.py` — Smart Chunking
  - `src/rag/confidence_scorer.py` — Confidence Scoring
  - `src/rag/advanced_retriever.py` — Advanced Retriever orchestrator
  - `src/rag/advanced_qa_engine.py` — Advanced QA Engine
- **API changes**:
  - `/api/rag/search?advanced=true` — advanced retrieval
  - `/api/rag/ask?advanced=true` — advanced QA (on by default)
- **Test results**:
  - "What is the refund policy?" → Confidence: 0.81, Should answer: True
  - "What is the weather today?" → Confidence: 0.18, Should answer: False
- **Commit**: `7922d15` — feat: add advanced RAG retrieval pipeline

### Node 6: Real Ryde policy documents ingested
- **Time**: evening
- **Work**: replaced the earlier fictional policies with real official Ryde policies
- **Changes**:
  - Rewrote 6 existing policies (cancellation / dispute_refund / driver_guidelines / rider_code / safety / terms_of_use)
  - Added 5 policies (privacy_policy, driver_performance_standards, ratings_moderation_policy, dispute_appeals_policy, dispute_resolution_guide)
  - `dispute_resolution_guide.md` maps the 7 hackathon scenarios to official clauses
  - Fixed a bug in the indexing script (`index_policies` -> `index_documents`)
  - 12 documents indexed into ChromaDB, 41 chunks; RAG retrieval verified
- **Policy sources**:
  - Terms of Use: https://rydesharing.com/terms-of-use/
  - Privacy Policy: https://rydesharing.com/privacy-policy/
  - Code of Conduct: https://rydesharing.com/code-of-conduct/
  - Help Center: https://help.rydesharing.com/hc/en-us
- **Commit**: `1d5afed` — feat: replace fictional policies with real Ryde policies from official sources

### Node 7: Mock dispute dataset
- **Time**: evening
- **Commit**: `b39980a` — feat: cherry-pick agent implementations and mock data from feature branches
- **Includes**:
  - `data/mock_disputes/no_show_01.json`
  - `data/mock_disputes/no_show_02.json`
  - `data/mock_disputes/route_deviation_01.json`
  - `data/mock_disputes/route_deviation_02.json`
  - `data/mock_disputes/README.md` (clearly labelled as synthetic hackathon demo data)

### Node 8: Session summary & handoff docs
- **Time**: late afternoon
- **Work**: created handoff documentation
- **New files**:
  - `SESSION_SUMMARY.md` — technical session summary
  - `docs/01_PROJECT_REQUIREMENTS.md` — project requirements
  - `docs/02_TECH_RESEARCH.md` — technical research
  - `docs/03_DEVELOPMENT_LOG.md` — development log (this file)
  - `docs/04_SCORING_GUIDE.md` — scoring guide
  - `docs/05_NEXT_STEPS.md` — next-steps list
- **Commit**: `bc43021` — docs: add session summary for transfer

---

## Session 2: 2026-09-22 (billy + Zhilin-sp, multi-person session)

#### 🚨 **Key decision: drop Tencent Hunyuan, standardise on Google Gemini**
Reason: Hunyuan API access is hard to get + the endpoint is unstable + Gemini already has a free tier.

### Node 9: Classifier Agent upgrade — keywords → LLM
- **Author**: billy
- **Commit**: `1de51e7` — feat: upgrade classifier from keyword-based to LLM-based with P0 safety fallback
- **Changes**:
  - Two-layer strategy: fast P0 safety-keyword scan (offline, instant) + Gemini LLM classification
  - Rich input: trip / payment / chat log / GPS / ratings are all fed to the LLM
  - Safe fallback when the LLM fails (returns requires_human=true)
  - Fuzzy-match validation of the LLM output
- **Effect**: noticeably more accurate than the keyword-only approach

### Node 10: Ryde platform API integration (contract layer)
- **Author**: billy
- **Commit**: `3a4fd51` — feat: integrate Ryde platform API for rich dispute context
- **New**: `src/integrations/ryde_api.py` — RydeAPIClient
  - ⚠️ **Important**: **this is a contract layer**, **not a real API call**. Every `_get_mock_order()` / `_get_default_mock_order()` reads from `data/mock_disputes/*.json` or hard-coded mock data; `base_url="https://api.rydesharing.com/v1"` **is never actually called**. Ryde Technologies has no public API / MCP server (confirmed: https://www.rydesharing.com/ has no developer portal).
  - Why keep it: a single interface contract — if Ryde ever grants API access, only `_get_mock_order` needs to become an HTTP call; **all upper layers (Collector / Orchestrator / API) stay unchanged**.
- **Pydantic models**:
  - `TripDetails`, `PaymentDetails`, `ChatMessage`, `GPSPoint`, `UserProfile`, `EvidenceItem`
- **CollectorAgent upgrade**:
  - Now pulls platform data through RydeAPIClient
  - DisputeContext enriched with trip / payment / chat / GPS / profiles
  - Supports evidence upload and language selection
  - Fault tolerance: falls back to a basic context if the API fails

### Node 11: Rider Advocate Agent — real LLM implementation
- **Author**: Zhilin-sp (teammate)
- **Commit**: `b95a406` — feat: implement evidence-grounded rider advocate agent
- **Changes**: `src/agents/passenger.py` went from stub to a full LLM call
  - RAG retrieval of policy clauses
  - Strict system prompt (with a "never assume passenger correct" rule + JSON output format)
  - `_parse_llm_json()` handles markdown code fences + fallback
  - `_sanitize_policy_references()` removes references not in the retrieved set (anti-hallucination)
  - `_evidence_only_result()` returns a safe fallback when no policies are retrieved
  - `rebut()` treats opponent_argument as untrusted content (prompt-injection defence)
- **Tests**: new `tests/test_passenger_agent.py` (516 lines)

### Node 12: Driver Advocate Agent — real LLM implementation
- **Author**: Zhilin-sp (teammate)
- **Commit**: `bfde2a6` — feat: implement evidence-grounded driver advocate agent
- **Changes**: `src/agents/driver.py`, symmetric to the Passenger Agent
  - Same evidence-grounding + policy-sanitising mechanism
  - Same prompt-injection defence
  - Tests: `tests/test_driver_agent.py` (644 lines)

### Node 13: Merge + test fixes
- **Commit**: `5e807a4` — fix: merge remote test suites and fix compatibility issues
- **Commit**: `849d94a` — feat: merge enhanced evidence-grounded agents from feature/rider-advocate-agent
- **PRs**: `#4` (feature/rider-advocate-agent) and `#5` (feature/driver-advocate-agent)

### Node 14: Style alignment with remote main
- **Author**: billy
- **Commits**: `22fe25d`, `d389a04`, `62f95e7`, `ca72712`, `1b4c7db`, `5dee6e9`, `f4e5c32`, `4df47ec`
- **Work**: aligned the docstrings / prompts of arbitrator / debate / driver / collector / passenger with remote main

---

## Session 3: 2026-09-23 (morning)

### Node 15: Status audit
- **Author**: billy (current user)
- **Trigger**: user asked "what is done and what is not"
- **Audit**:
  - ✅ Full LLM integration: Collector / Classifier / Passenger / Driver / Policy / Debate / Orchestrator / Confidence
  - ✅ 5 RAG optimisations
  - ✅ Real Ryde policies (12 documents)
  - ✅ Mock disputes (4 cases)
  - ✅ Tests (passenger / driver / policy / classifier / rag)
  - 🔴 **Not done**: Arbitrator (`src/agents/arbitrator.py`) still a stub — `confidence=0.0`, `rationale=""`, always triggers escalation
  - 🟠 **Partly done**: Executor (`src/agents/executor.py`) only has an actions_taken list, no real platform API call
  - 🔴 **Not done**: full frontend dashboard (at the time `frontend/index.html` only had 4 RAG tabs — no dispute filing / live debate / verdict display)
  - 🟡 **Not done**: demo script, architecture diagram, multilingual notifications

### Node 16: Teammate's uncommitted changes — DESIGN.md + frontend redesign
- **Author**: another teammate (uncommitted changes)
- **Changes**:
  - `frontend/index.html` CSS fully rewritten (1502-line diff)
    - Title: `RydeResolve-Agent — RAG Knowledge Base` → `RydeResolve-Agent — Dispute Resolution Dashboard`
    - Added Rubik / Space Grotesk Google Fonts
    - New `:root` token system (Brand & Accent / Surface / Hairline / Text / Rounded / Spacing / Shadows)
    - Colour scheme changed to deep purple-violet (`--primary: #150f23`) + electric lime (`--accent-lime: #c2ef4e`) + hot pink (`--accent-pink: #fa7faa`)
    - Added a `body::before` starfield decoration layer
    - Top bar changed to 56px high + lime status dot
    - Tabs changed from `<div>` to `<button>` (accessibility)
    - Commented-out old theme kept in the diff
  - New `DESIGN.md` (387 lines) — design-token documentation, Sentri-inspired design language
- **Status (at the time)**: ⚠️ **uncommitted** (not on any branch, not pushed) — later committed in `722e3b9` (see Session 4)

### Node 17: Key judgement (raised by user)
- **Topic**: does linking to a "Ryde API" make sense?
- **Conclusion**:
  - Ryde Technologies **does not publish an API / MCP server** (confirmed)
  - The `RydeAPIClient` in the code is **100% mock**; the URL is never really called
  - Still worth keeping: a unified contract layer / clear interface / easy to swap later
  - **Do not** call it "Ryde API integration" in the demo text — call it a "simulated integration contract"
- **Recommendation**: reword the `ryde_api.py` docstring + README + demo script

---

## Session 4: 2026-09-23 afternoon – 2026-09-24 (billy + Yang Shuo + Zhilin-sp, integration day)

### Node 18: Merge PR #2 / #3 + DISP-002 sample
- **Author**: billy
- **Commits**: `7da1e6f`, `5b00430`, `139d871` — merged PR #2 (policy agent) and PR #3 (classifier), keeping main's newer versions and porting PR #3's unique test (a P0 safety keyword overrides a pre-supplied dispute type)
- **Commit**: `f75c21e` — added the DISP-002 no-show sample dataset
- **Commit**: `722e3b9` — Arbitrator now does real LLM reasoning (only the `_safe_decision()` fallback remains), API / frontend updates, debate rebuttal fix

### Node 19: Execution Agent upgrade
- **Author**: Yang Shuo (yangggshuo)
- **Commit**: `a0bab8f` — simulated actions + multilingual notifications

### Node 20: Fairness Agent
- **Author**: Yang Shuo
- **PR**: `#7` (`0b97f71`) — `src/agents/fairness.py`, an independent audit of the Arbitrator's decision that can BLOCK it

### Node 21: LangGraph workflow
- **Authors**: Yang Shuo (`#8`, `8ea8597`) + Zhilin-sp (`#9`, `99f145c`)
- **Change**: `src/core/workflow.py` + `workflow_state.py` — a real LangGraph graph with fairness and human-review routing; #9 makes the workflow honour human-review and executor outcomes
- **Significance**: the orchestrator moved from "planned" to a real LangGraph graph

### Node 22: Mock disputes rewritten in DISP-002 format, expanded to 13
- **Author**: billy
- **Commit**: `bfaa7b3`
- **Change**:
  - The 4 existing cases rewritten with full DISP-002 fields (ticket, profiles, trip timeline, GPS speed/status, app_events, policies)
  - 9 new cases: fare ×2, cancellation_refund ×2, service_quality (P1), safety_incident (P0), driver_rights, cleaning_fee (deliberately unmapped type), no_show_03 (no GPS → should go to human review)
  - Every case carries an `expected_outcome` answer key; the Collector strips it before any agent sees it
  - `tests/test_collector_dataset.py` checks the format of every case

### Node 23: Dispute dashboard + live agent trace
- **Author**: billy
- **Commit**: `2ed78dc`
- **Change**: `frontend/dispute.js` + `dispute.css` (loaded by `index.html`) + `src/core/trace.py`; the trace is hooked into each LangGraph node, the Fairness node was added to the frontend graph; traces are saved to `data/traces/` and can be replayed (`rrReplay(name)`)

### Node 24: Section-based RAG chunking
- **Author**: billy
- **Commit**: `6769b11`
- **Problem**: whole policy documents mixed several topics, so the top chunk often did not match the dispute type
- **Fix**: chunk by markdown section, so retrieval returns the section for that dispute type

### Node 25: Gemini free-tier hardening
- **Author**: Zhilin-sp
- **PRs**: `#10` call pacing + one retry on per-minute quota errors; `#11` keep the policy embedding provider stable when an LLM key is set; `#12` readable debate turns + quota-limited runs marked incomplete; `#13` default debate reduced to one round

### Node 26: Groq as a second LLM provider
- **Author**: billy
- **Trigger**: Gemini chat free-tier quota exhausted (429); Gemini embeddings use a separate quota and still work
- **Change**: `config.py` adds `LLM_PROVIDER` / `GROQ_*`; `llm_client.py` adds `_chat_groq` (openai `AsyncOpenAI`, `max_retries=4`, JSON mode in `chat_json`); `tests/test_llm_provider.py`; `tests/conftest.py` pins tests to the gemini path (otherwise unit tests would hit real Groq)
- **Model**: `openai/gpt-oss-120b` (llama-3.3-70b retired); Groq free tier: 1000 req/day, 8000 TPM per model
- **Real run**: NS-001 (RYDE-DEMO-003) — 11 LLM calls, 136 s (including rate-limit waits), result upheld / S$8 / no human review = matches the answer key. Trace: `data/traces/20260924-165252_RYDE-DEMO-003.json`

### Node 27: Fix "every real policy citation stripped"
- **Author**: billy
- **Problem**: `_build_valid_refs()` in `arbitrator.py` and `fairness.py` only accepted references found in the advocate arguments, not the PolicyAgent's verified `policy_references` → every real citation was stripped → every run was forced to human review / Fairness BLOCK
- **Fix**: both now also accept the PolicyAgent's verified references; regression tests added in `test_arbitrator_agent.py` and `test_fairness_agent.py`
- **Note**: `fairness.py` belongs to Yang Shuo — he needs to review the change

### Node 28: Collector tools (committed 2026-10-01)
- **Author**: billy
- **Change**: `src/agents/collector_tools.py` — 9 standard tools + 2 query tools, **fully deterministic, zero LLM calls**; findings are typed fact / conflict / gap, each with its source; `trace.py` adds a `tool_call` event; the dashboard shows a findings + tools panel; `tests/test_collector_tools.py`
- **Agreed design**: raw data is read-only; no "challenge" loop; other agents query via query tools (not an LLM); routing belongs to the graph, agents can only request

### Node 29: Evaluation plan (parked)
- **Author**: billy
- **File**: `docs/06_EVAL_PLAN.md` — accuracy, safety, Hit@3, speed (rate-limit wait measured separately), tokens, stability, robustness, fairness, ablations against a single-LLM-call baseline

### Node 30: Cloud vector DB — Qdrant Cloud
- **Background**: move the RAG vector store from local ChromaDB to the cloud so the whole team and the demo share one index
- **Finding**: Tencent Cloud VectorDB (international site) only offers "Contact us" — no self-serve sign-up
- **Done (2026-09-25, billy)**: Qdrant Cloud free cluster (GCP australia-southeast1). New `src/rag/qdrant_store.py`: every chunk stores a dense vector (fastembed `BAAI/bge-small-en-v1.5`, 384-d) and a BM25 sparse vector; search fuses both with RRF. Embeddings are computed locally, so no API quota is used and every teammate gets identical results. `VECTOR_BACKEND=chroma|qdrant` switch in `indexer.py` / `retriever.py`; agents unchanged. gRPC client (≈0.8 s per lookup vs ≈2 s over REST from Singapore). 108 chunks from the 11 policy documents indexed.
- **Check** (`scripts/verify_vector_store.py`, one query per dispute type): Qdrant hybrid put the matching scenario section first for 6 of 7 types (7th at rank 2); Chroma + Gemini dense ≈ 4 of 7; Chroma with the current `.env` default (hash embedding) 0 of 7 — local retrieval had silently stopped working
- **Later**: before Demo Day, optionally self-host Qdrant on Tencent Lighthouse with the whole demo (same API, only the URL changes)

**Tests**: 221 local tests pass offline (`--deselect tests/test_arbitrator_agent.py::TestArbitrationAgent::test_llm_client_none_fallback`, which calls a real LLM)

---

## Session 5: 2026-09-29 – 2026-10-01 (billy, branch `policy-official-rebuild`)

Every change and its measured effect is in [08_DESIGN_DECISIONS.md](08_DESIGN_DECISIONS.md) (D1–D15).
This section is the short version.

### Node 31: Official policy text + retrieval benchmark (D1–D3)
- `data/policies/official/`: 22 verbatim Ryde help-centre / site pages (`scripts/fetch_official_policies.py`);
  the old paraphrased library had invented rules. Separate Qdrant collection `ryde_policies_official`
  (bge-base, hybrid BM25), selected by 3 lines in `.env`; the old `ryde_policies` is untouched.
- Retrieval A/B (`scripts/retrieval_eval/`, 32 questions): bge-base hybrid Hit@1 0.88 vs bge-small 0.78.
  ADP stays auxiliary; rulings use our own RAG. One search per dispute (cache).

### Node 32: Answer-key audit, held-out set, evaluation upgrade (D4–D6, D9)
- Answer keys audited and fixed; 13 held-out variants (`scripts/make_heldout_cases.py`): paraphrase,
  language, counterfactual, injection, missing data, boundary.
- `scripts/eval.py`: dev/held-out split, cost, compute vs rate-limit time, and new paired metrics:
  consistency (repeats), paraphrase invariance, counterfactual sensitivity, injection resistance;
  baseline column; provider/model stored per trace (a resume refuses to mix providers).
- Fairness: `decisive_evidence_gap` (lost driver GPS where location decides -> human); narrowed for
  cancellations with no recorded arrival.

### Node 33: Feedback loop, level 1 (D8)
- `src/store/` (SQLite via `STORE_URL`: rulings, reviews, precedents, hash-chained audit log),
  `src/rag/precedents.py`, API review/precedent/audit endpoints, `scripts/precedents.py`.
  Human overrides become precedents only after an eval gate.

### Node 34: Case Brief — one shared dossier after classification (D10, D12, D14)
- New workflow node `case_brief` (`src/agents/case_brief.py`, no LLM): Collector facts / conflicts /
  gaps with sources (facts built on a disputed record are marked), this trip's platform rules
  (citable as `platform_policy.<key>`), app-event timeline, and the base policy clauses.
- Base clauses = complaint search ranked by section tags + the dispute type's core topics + topics
  triggered by platform data (fee charged, surge, route alert, cleaning claim, ...), from a fixed
  14-topic catalogue (`src/rag/policy_topics.py`). Advocates may request up to 2 catalogue topics;
  requested clauses go to the shared pool that both sides and the Judge read.
- Expected-section recall in the clauses agents receive: 0.744 -> 0.92 (27 cases).

### Node 35: Section tags on the knowledge base (D11, D12)
- `data/policies/official/policy_tags.json`: every section tagged with dispute types and audience
  (model-proposed, hand-reviewed, checked against the answer keys). Stored on each chunk; bool
  payload indexes for Qdrant filtering.
- Tag ranking weight 0.001: Hit@1 0.815 -> 0.963; with a deliberately wrong type the right section
  still stays in the top 3 (larger weights hid rules).

### Node 36: Query experiments that were rejected (D12, D13)
- Query built from Collector facts: Hit@1 0.56 vs 0.82 for the complaint — rejected.
- Guarded LLM rewrite (strict no-invention prompt + number check, `src/rag/guarded_rewrite.py`):
  no invented numbers, but meaning drift; short-question Hit@1 1.00 -> 0.73 — rejected.

### Node 37: Eval 20261001-114026 and fixes (D15)
- 27 cases: verdict 63% (17/27); the Judge was right in 6 of the 10 misses. Fixes: Fairness accepts
  Case Brief clauses; Fairness prompt defines verdict labels; label follows the refund
  (`align_verdict_label`); new deterministic check `fee_basis_not_met` (a fee kept on a contradicted
  arrival or under the no-show threshold goes to a person). Replayed on the recorded rulings:
  projected 25/27, the 2 Judge errors routed to a person. Re-run pending (Cerebras daily quota).
- Prompts ~21% smaller (raw GPS replaced by the brief's facts, compact clause text);
  `ADVOCATE_REASONING_EFFORT` switch added, off by default.
- Tests: 325 passed.

## Session 6: 2026-10-02 – 2026-10-05 (billy, branch `policy-official-rebuild`, merged as PR #18)

Short version; details and measured effects in [08_DESIGN_DECISIONS.md](08_DESIGN_DECISIONS.md) (D16–D19).

### Node 38: Labels from the asks, metered-fare GPS gap, overfitting protocol (D16)
- The Judge lists every ask with an outcome; `label_from_asks` computes upheld / partially_upheld / dismissed.
- A GPS gap blocks a metered `fare_dispute` (upfront fares stay automatic).
- Overfitting protocol: fix the rule not the case, test both directions, replay before re-run,
  sealed set run once before submission.
- Rebuttal budget 300 -> 1500 tokens: gpt-oss spent the whole 300 on hidden reasoning in 17% of rebuttals.

### Node 39: Full-debate run 29/33 and payout guards (D17)
- `fee_basis_not_met` also covers a kept fee when the trip's delay waiver is exceeded;
  new `refund_beyond_disputed_amount`. Both only route to a person.

### Node 40: Judge reasoning principles, discretionary refunds (D18)
- Four general principles in the Judge prompt (literal rule conditions, amounts from specific rules,
  arguments are not evidence, separate asks); conduct complaints count as asks. Run: 30/33.
- User decision: a service-quality refund with no fare overcharge is a person's call.
- Party notices: each side's notice states its own outcome from the ruling's fields; both in the UI.

### Node 41: Records on Supabase, rider/driver history
- Record store runs on Postgres (Supabase) via `STORE_URL` / `DATABASE_URL`; traces stored there.
- People-history store (trips, disputes, outcomes, fraud flags) for agents, reviewers and training export.
- Architecture diagram `docs/architecture.svg` / `.png` matching the current pipeline.

### Node 42: LLM provider fallback, regression run (D19)
- `LLM_FALLBACK_PROVIDERS`: backup chat providers tried in order. Evals turn it off.
- `hunyuan` provider (TokenHub, OpenAI-compatible) added and tested. The key authenticates, but every
  model returns 402 until a paid inference service is activated, so it is not used.
- Gemini free tier allows 20 requests/day per model (about 3 cases); Groq free tier rejects any single
  request over 8,000 tokens, which some Judge prompts exceed. Cerebras stays the eval provider.
- Regression run 20261005-131434: **31/33 (93.9%)**, US$0.37; all post-D18 fixes verified.
- Merged into `main` as PR #18 (2026-10-05). Tests: 368 passed.

---

## Key Decisions (updated)

### Decision 1: Why Gemini instead of Tencent Hunyuan?
- **Date**: 2026-09-21 afternoon
- **Options**: Tencent Hunyuan vs Google Gemini
- **Choice**: Google Gemini
- **Reasons**:
  1. Hunyuan's OpenAI-compatible endpoint had been taken offline
  2. TokenHub required a new application with a complicated process
  3. Gemini's free tier is generous and API keys are easy to get
  4. Stable access from the international site
- **Impact**: llm_client.py and embedding.py had to be rewritten

### Decision 2: Why local ChromaDB?
- **Date**: 2026-09-21 morning
- **Options**: ChromaDB in Docker vs local persistent mode
- **Choice**: local persistent mode
- **Reasons**:
  1. No Docker needed, simple deployment
  2. Data stored in local files, nothing lost
  3. Performance is sufficient (small dataset)
- **Impact**: cannot be shared across instances, but fine for the competition

### Decision 3: Why 5 RAG optimisations?
- **Date**: 2026-09-21 afternoon
- **Choice**: Query Rewrite + Hybrid Search + Re-ranking + Smart Chunking + Confidence Scoring
- **Reason**: the scoring values technical depth, and a multi-agent system needs high-quality retrieval

### Decision 4: Why "advocate perspective" agents instead of a neutral judge?
- **Date**: 2026-09-22
- **Choice**: Passenger Agent and Driver Agent **each advocate their own side** + the Arbitrator weighs both
- **Reasons**:
  1. Multi-agent debate surfaces contradictory evidence and is fairer
  2. Shows the reasoning chain better than a single LLM ruling directly
  3. Each advocate must list `contradictory_evidence`, preventing one-sided arguments
- **Impact**: required a dedicated `_sanitize_policy_references()` to block hallucinated policy references

### Decision 5: Why keep the mock Ryde API as a contract layer?
- **Date**: 2026-09-22
- **Choice**: keep `src/integrations/ryde_api.py` as a contract layer, and **do not** call it "Ryde API integration"
- **Reasons**:
  1. Ryde has no public API / MCP (confirmed)
  2. The code reads 100% from `data/mock_disputes/*.json`; the URL is never really called
  3. But the Pydantic models (TripDetails / PaymentDetails etc.) mirror the real Ryde platform structure and are easy to swap later
  4. Judges will check — it must be honestly labelled "simulated"

### Decision 6: Why add Groq as a second LLM provider?
- **Date**: 2026-09-24
- **Context**: Gemini chat free-tier quota exhausted (429); real dispute runs could not complete
- **Choice**: an `LLM_PROVIDER` switch — Groq (`openai/gpt-oss-120b`) for chat; embeddings stay on Gemini (separate quota, existing index needs no rebuild)
- **Impact**: `conftest.py` pins unit tests to the gemini path so they never hit real Groq

### Decision 7: Why deterministic Collector tools instead of an LLM?
- **Date**: 2026-09-24
- **Choice**: 9 standard + 2 query tools, zero LLM calls; raw data read-only; no "challenge" loop
- **Reasons**:
  1. The same dispute always yields the same findings — reproducible and testable
  2. Every finding (fact / conflict / gap) points back to raw evidence, so judges can trace it
  3. Saves LLM quota
- **Principle**: routing belongs to the LangGraph graph; agents can only request

### Decision 8: Qdrant Cloud for the cloud vector DB (adopted)
- **Date**: 2026-09-24
- **Options**: Tencent Cloud VectorDB vs Qdrant Cloud vs staying on local ChromaDB
- **Status**: Tencent VectorDB is not self-serve on the international site ("Contact us" only)
- **Proposal**: Qdrant Cloud free tier + fastembed local embeddings (dense + sparse hybrid, no API quota) now; self-host Qdrant on Tencent Lighthouse before Demo Day
- **Outcome**: adopted (Node 30); the official-policy collection is on Qdrant Cloud with hybrid search.

### Decision 9: Which LLM runs the agents? (2026-10-05)
- **Options tried**: Tencent Hunyuan via TokenHub (needs a paid inference service), Gemini free tier
  (20 requests/day per model), Groq free tier (8,000 tokens per request limit), Cerebras (paid, $5 credit)
- **Decision**: one model, `gpt-oss-120b`, for both evals and the demo. Evals run on Cerebras;
  day-to-day runs can use Groq with `LLM_FALLBACK_PROVIDERS=cerebras,gemini`
- **Why**: the eval score then describes the model the demo actually uses

---

## Current Pipeline State (LangGraph, `src/core/workflow.py`, updated 2026-10-05)

```
Report -> [Collector] (deterministic tools: facts / conflicts / gaps) -> [Classifier]
                    |
             [Case Brief]  <- no LLM: facts, case rules, timeline, base clauses
                    |         (complaint search + type topics + data-triggered topics, tag-ranked)
   ┌────────────────┼────────────────┐
   |                |                |
[Passenger Agent]  [Driver Agent]  [Policy Agent]   <- all read the same brief + clauses
   |  policy_requests (catalogue topics) -> shared pool
   └────────────────┼────────────────┘
                    |
            [Debate Engine]
                    |
            [Arbitrator]  <- brief first; rules per ask, label from the asks
                    |
            [Fairness Agent]  <- deterministic checks (decisive_evidence_gap, fee_basis_not_met,
                    |            refund_beyond_disputed_amount, refund basis) + LLM review; can BLOCK
          Confidence / human-review routing
                    |
            [Executor]  <- simulated actions, one notice per party; rulings, traces and
                           audit chain in the record store (SQLite or Supabase Postgres)
```

---

## Open Issues (updated)

| # | Issue | Priority | Status |
|---|-------|----------|--------|
| 1 | ~~Arbitrator is still a stub~~ | 🔴 P0 | ✅ Done (`722e3b9`) |
| 2 | ~~Frontend has no dispute dashboard~~ | 🔴 P0 | ✅ Done (`2ed78dc`, with live trace) |
| 3 | ~~Executor has no multilingual notification~~ | 🟠 P1 | ✅ Done (`a0bab8f`, actions still simulated) |
| 4 | ~~Smart Chunker not integrated into Indexer~~ | 🟡 P2 | ✅ Replaced by section chunking (`6769b11`) |
| 5 | BM25 index not cached | 🟡 P2 | Not started |
| 6 | Demo script not written | 🟡 P2 | Not started |
| 7 | ~~Architecture diagram not done~~ | 🟡 P2 | ✅ Done (`docs/architecture.svg`) |
| 8 | Reword Ryde API as "simulated" | 🟢 Easy | To do |
| 9 | ~~Teammate's `DESIGN.md` + frontend CSS uncommitted~~ | 🟡 | ✅ Committed (`722e3b9`) |
| 10 | ~~Groq provider + citation bug fix uncommitted~~ | 🔴 P0 | ✅ Committed |
| 11 | ~~Collector tools uncommitted~~ | 🟠 P1 | ✅ Committed and merged |
| 12 | ~~Local changes overlap origin PRs #10–#13~~ | 🔴 P0 | ✅ Synced and merged cleanly |
| 13 | ~~Cloud vector DB~~ | 🟠 P1 | ✅ Qdrant Cloud, hybrid search (Node 30) |
| 14 | ~~Evaluation plan phase 1~~ | 🟠 P1 | ✅ Done; full runs D15–D19 |
| 15 | `fairness.py` change needs Yang Shuo's review | 🟡 | To notify (now merged in PR #18) |
| 16 | `calculate_confidence()` exists but is never called; the journal describes it as used | 🟡 | Wire in or reword |
| 17 | Sealed set run once before submission | 🔴 P0 | Before 16 Oct |
| 18 | Live demo deployment (bonus) | 🟠 P1 | Not started |

---

## Code Statistics (updated 2026-10-05, origin/main)

| Metric | Value |
|--------|-------|
| Python files (src + scripts) | 73 |
| Test files | 25 |
| Local tests | 368 (all pass offline) |
| Total lines of code (py/js/html/css) | ~22,900 |
| Git commits (main) | 115 |
| Agents implemented | 9 (Collector, Classifier, Case Brief, Rider, Driver, Policy, Judge, Fairness, Executor) |
| Labelled eval cases | 33 (14 dev + 19 held-out) + 9 sealed + 4 fraud |
| Mock disputes | 13 (DISP-002 format) |
| Official policy documents | 23 files in `data/policies/official/` |
| Frontend | `index.html` + `dispute.js` / `dispute.css` (dispute dashboard + live trace) |

---

## References

| Resource | Link | Purpose |
|----------|------|---------|
| Gemini API | https://aistudio.google.com/app/apikey | API key |
| Gemini Docs | https://ai.google.dev/gemini-api/docs | Docs |
| ChromaDB | https://docs.trychroma.com | Vector DB |
| FastAPI | https://fastapi.tiangolo.com | Web framework |
| Ryde Policies | https://rydesharing.com/policies/ | Real policy source |
| TRTC Agent Skills | https://github.com/Tencent-RTC/agent-skills | Tencent Cloud skills |

---

## Session Handoff (for the next session, updated 2026-10-05)

State: `main` holds everything (PR #18). Latest eval 31/33 (D19). Deadline 16 Oct 2026.

### 🚨 P0 — before submission
1. README and docs match the code (done 2026-10-05: README, this log, next steps, eval plan)
2. Submission draft: business value numbers (31/33, ~91 s, US$0.011 per case), open items
3. CodeBuddy proof: add 1–2 screenshots of actual coding to `proof of usage of codebuddy/`
4. Sealed set: run once, last (`data/eval_cases/sealed`), report it as the generalisation number

### 🟠 Bonus
5. Live demo URL (Tencent Lighthouse + Docker + Postgres)
6. Policy agent queries the Tencent ADP assistant; compare with our retriever
7. Cover image 16:9, blurb under 10 words, optional 5–8 min demo video

### 🟢 Cleanup
8. `calculate_confidence()`: wire in or reword the journal
9. Reword `ryde_api.py` as a "simulated integration contract"
10. Git history scrub (parked; needs team coordination and a force-push)

### Key files
- `src/core/workflow.py` — LangGraph pipeline; `src/core/llm_client.py` — providers and fallback
- `src/agents/arbitrator.py` — Judge; `src/agents/fairness.py` — guards and review
- `src/agents/case_brief.py`, `src/agents/collector_tools.py` — shared dossier and evidence tools
- `src/store/` — record store, audit chain, precedents, people history
- `scripts/eval.py` — evaluation; `data/eval_answer_keys.json` — answer keys
- `docs/08_DESIGN_DECISIONS.md` — every change with its measured effect (D1–D19)
