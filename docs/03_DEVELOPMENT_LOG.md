# Development Log — Key Milestones

> **Last updated**: 2026-10-15
>
> This log records the key milestones, decisions, problems and next steps of every session.
> Every change, with how it was measured, is in `08_DESIGN_DECISIONS.md` (D1-D52b); this log is the
> session-level summary. Latest update adds Session 7 (2026-10-06 – 10-09: fraud agent, experiments,
> adaptive triage) and Session 8 (2026-10-10 – 10-15: code Judge, rule checks, blind and sealed sets,
> photos, Policy v2.1, live server, precedent selection, notices, chat tone).

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

## Current Pipeline State (LangGraph, `src/core/workflow.py`, updated 2026-10-15)

```
Report -> [Collector] deterministic tools: facts / conflicts / gaps / rule checks / photo file checks
             |  [ImageAnalyst] vision model describes photos (can only raise doubts)
             |  [ChatTone] code labels each chat message; a model re-checks doubtful ones
             |             (reviewers and notice wording only, never an agent input)
          [Classifier] type + urgency P0-P3 ---- safety / legal (P0) ----> [Safety] -> a person
             |
          [Case Brief] no LLM: facts, the trip's rules, timeline, Policy v2.1 sections and its
             |          official precedents 7.1-7.3 for this dispute type
          [Fraud] risk signals and pair history (Judge and Fairness only)
             |
   [Rider advocate]  [Driver advocate]  [Policy]      one round; more for complex cases
             |
          [Judge] per-ask ruling, amount arithmetic, confidence, decisive facts, followed precedents
             |
          [Code Judge] facts on uncontradicted records, amount adds up; one remand, then a person
             |
          [Policy v2.1 gate] sections that must go to a person
             |
          [Fairness] deterministic checks + LLM review; high = escalate, medium = note
             |
          [Executor] simulated actions; one notice per party, four languages
```

Every ruling, review and precedent change is written to the record store (SQLite or Postgres) with
a hash-chained audit log. Escalated cases go to the review desk (`frontend/review.html`).

---

## Open Issues (updated 2026-10-16)

| # | Issue | Priority | Status |
|---|-------|----------|--------|
| 0 | **Data-problem records slip past the Code Judge** when the Judge does not list the questioned record: F2-12, F2-16, F2-17 executed in the 16 Oct re-run; F2-12 and F2-17 also once in two on pre-D55 code | 🔴 P0 | Next fix: check the questioned record in code (D59) |
| 1 | Demo video | 🔴 P0 | Recording 16 Oct (`DEMO_RECORDING_GUIDE.md`, about 7 min 50 s of a 5-8 min limit) |
| 2 | Submission form | 🔴 P0 | Due 16 Oct, with the demo access code |
| 3 | Saved demo runs predate D51/D52 (no ChatTone step, no notice opening line) | 🟠 P1 | A new saved run needs a small paid run |
| 4 | No precedent is active; the Judge now reports the ones it follows (D55), gain not measured | 🟠 P1 | Needs the release-gate eval (paid) |
| 4b | Money the Judge writes in `compensation` text is executed but not code-checked; a driver's claimed fee has no amount field (D58-02) | 🟠 P1 | Found 16 Oct, not fixed |
| 4c | Rules counting "every started minute" (no ceil()) and "N%" caps (0.3 not a figure) still go to a person | 🟡 P2 | D58 |
| 5 | Chat tone not scored on a labelled blind set of real chats | 🟡 P2 | D52b scores are on our own sentences |
| 6 | Older eval sets (fresh_sonnet, images, photo_side, cancel_scope, discretion, fraud, stress) not re-run on the final code | 🟡 P2 | Their published scores are pre-v2.1 |
| 7 | Route baseline check (OSRM) | 🟡 P2 | Parked: mock routes are shorter than real roads |
| 8 | Git history scrub (an e-mail address and co-author lines) | 🟢 | Parked; needs team coordination and a force-push |
| 9 | ~~Live demo deployment~~ | | ✅ Tencent Lighthouse, Caddy, systemd (D44) |
| 10 | ~~Sealed set run once~~ | | ✅ 16/23 (D41) |
| 11 | ~~Fraud agent, image analysis, learning loop~~ | | ✅ D20-D22, D46-D47, D45 (gated) |
| 12 | ~~`calculate_confidence()` unused~~ | | Kept in `src/core/confidence.py`; the Judge states its confidence and the code Judge and gates check the ruling |

---

## Code Statistics (updated 2026-10-16, branch post-submission)

| Metric | Value |
|--------|-------|
| Python files (src + scripts) | 98 |
| Test files | 41 (Python and frontend) |
| Local tests | 660 Python + 28 frontend, all pass offline |
| Total lines of code (py/js/html/css) | ~31,400 |
| Git commits (main) | 215 |
| Agents and checks | Collector, ImageAnalyst, ChatTone, Classifier, Safety, Case Brief, Fraud, Rider, Driver, Policy, Judge, Code Judge, Policy gate, Fairness, Executor |
| Results (README) | organisers' samples 3/3; blind set in their format 25/30; regression 44/52 with no wrong payout (15 Oct), 45/52 with 5 wrong automatic rulings on the submitted code (16 Oct, D59); sealed 16/23 (D41) |
| Official policy documents | 24 files in `data/policies/official/`; Policy v2.1 governing |
| Frontend | dashboard (`index.html`, `dispute.js`), case editor, review desk (`review.html`) |

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

## Session Handoff (for the next session, updated 2026-10-16)

State: submitted version tagged `submission-2026-10-16` (fc6b422, deployed). Later work on branch
`post-submission` (D59 onward); during judging nothing goes to `main` or the server without the owner's OK.

### 🚨 P0 — before submission
1. Record the demo video from `DEMO_NARRATION.md` / `DEMO_SCRIPT.md` (saved runs demo-1 to demo-7)
2. Submit the form (`SUBMISSION_FORM.md`) with the demo access code, not the admin code

### 🟠 If time allows
3. One new saved run that shows the ChatTone step and the review-desk tags (small paid run)
4. Release-gate eval of the precedent selection (D51), paid; ask before running

### Key files
- `src/core/workflow.py` — LangGraph pipeline; `src/core/llm_client.py` — providers and fallback
- `src/agents/arbitrator.py` — Judge; `code_judge.py` — code checks; `policy_gates.py` — v2.1 gate
- `src/agents/fairness.py` — audit; `chat_signals.py` — chat tone; `executor.py` — notices
- `src/agents/case_brief.py`, `src/agents/collector_tools.py` — shared dossier and evidence tools
- `src/rag/precedents.py` — precedent selection; `src/store/` — records, audit chain, precedents
- `scripts/eval.py` — evaluation; `docs/08_DESIGN_DECISIONS.md` — every change (D1–D52b)

## 2026-10-07 — Local demo repairs (uncommitted, fix/demo-reliability)

Fixed stale case selection, failed/truncated streams, successful retry display, dataset/reporter
labels, text escaping, source text/scores, readiness, bounded uploads, loopback/role access,
server-assigned audit actors, provider-key checks and terminal fallback errors. The API now
serves the dashboard. Secret files are excluded from images; compose runtime settings and
writable mounts are updated. Official policies are read-only through upload/delete by default.

Validation: 418 backend tests; 21 frontend tests; pip check and diff checks passed. API read
checks for the dashboard, cases, traces, precedents and flags returned 200. Secret-file paths
returned 404. Installed missing psycopg 3.3.4. Shared Postgres still times out, so this machine
uses a separate SQLite store in .env.local, plus the existing official Qdrant collection
(165 chunks / bge-base 768 dimensions). No shared history was imported or index rebuilt.

Live Groq smoke: FD-002 resolved (3 rounds, 11 calls, 0 failures, 230.1s) and saved/replayed.
NS-001 escalated after a 413 size refusal (8,927 vs 8,000 tokens; 244.6s), also saved/replayed.
The local profile now uses the project default 1 round. Its NS-001 retest hit the 200k daily
quota and failed safely (85.0s); capacity with 1 round remains unverified. Gemini model metadata
query returned Unauthenticated; Cerebras key is not configured. No fallback was enabled.
No new full accuracy claim, sealed-set run, public deployment or browser layout validation.
The next priorities are working provider quota, shared-store connectivity, review UI and final
submission evidence. See the repair report exported in the 2026-10-07 Codex chat outputs.


## Session 7: 2026-10-06 – 2026-10-09 (billy; fraud agent, experiments, adaptive triage)

- **Fraud & Bad-Faith agent** (D20-D22): deterministic risk signals and an evidence-grounded chat
  labeller; a contradiction must name the claim words it contradicts; threats go to safety review,
  not fraud. Seen by the Judge and Fairness only, never by the advocates.
- **Local demo repairs** (10-07, entry above): stream, escaping, access and storage fixes.
- **Experimental architecture, not adopted** (D23-D31): advocate-chosen lookups with evidence pools,
  adaptive orchestration and a structured Judge scored 31-32/37 against 35/37 at +42-47% tokens, so
  `main` kept the simpler pipeline; the branches keep the records.
- **Adaptive triage** (D32): complexity x risk decides debate rounds and audit depth; Fairness adds
  up the disputed total. Regression 35/38, 0 wrong payouts executed, median 92 s per case.

## Session 8: 2026-10-10 – 2026-10-15 (billy; branch `feature/rule-engine`, merged to `main`)

- **10-11 — Judge discipline.** One debate round by default; an objection round tested and left off
  (D33-D34); a Clerk agent rejected, every case rule given a scope text instead (D35-D36); Fairness
  sends a discretionary partial refund to a person (D37). **Code Judge** (D38): each decisive fact must
  sit on an uncontradicted record and a refund must be arithmetic on record figures; one remand, then
  a person. Wrong payouts executed on its test set: 4 -> 1.
- **10-12 — Rule checks and fresh tests.** Code evaluates the trip's time rules (D39: 8/10, was
  5/10). A fresh blind set (D40, 16/20, no wrong payout) and the sealed set, run once (D41, 16/23).
  The one sealed wrong payout led to D42: a remand cannot pass by deleting the blocked record.
- **10-13 — Live server and the learning loop.** Deployment faults the laptop did not show (D44).
  First precedent test: no measurable gain, nothing released (D45). Precedent design (D43).
- **10-14 — Photos and the organisers' format.** Code checks each photo's time, place, editing tag and
  reuse; a vision model describes it and can only raise doubts (D46-D47). Case editor in the
  dashboard (D49). The organisers' sample format and **Ryde Dispute Resolution Policy v2.1** become
  governing (D50): samples 3/3, blind set in their format 25/30, regression 44/52 with no wrong payout.
- **10-15 — Submission polish.** Secret scan of the full history (clean); historical plans and
  unused files removed; Figure 1 redrawn. D51: precedents chosen by type, policy version and
  principle, the Judge lists the ones it followed (checked by code), a Judge-only model switch and a
  self-hosted provider, notices in four languages, data protection and cost in the docs. D52/D52b:
  chat tone by code, doubtful messages re-checked by a model, shown on the review desk and used for
  notice wording only; Fairness notes a ruling whose reasons lean on a party's manner.

## Session 9: 2026-10-16 (billy; submission day, then branch `post-submission`)

- **Precedents** (D55): the Judge never returned `precedent_ids` because the system prompt's fixed key
  list lacked it; added. Isolated test (local store, separate Qdrant collection): 0/14 replies had the
  key before, 7/7 after; one correct citation; no measured accuracy gain.
- **Keys** (D56): photo analysis reads its own `VISION_API_KEY`; the server moved to new Cerebras and
  Groq keys. Cover figures matched to the README (~89 s, 78%); a recording guide added.
- **Rate-based refunds** (D57-D58): derived numbers written as arithmetic, rule wording counts as
  record figures, trip pause lengths, floor()/min(), and rate credits not held as discretion. F2-06,
  F2-09, F2-11, D57-01, D57-04 now decided automatically and right; two new blind sets (D57 5/8, D58
  3/8) found two older gaps (money in `compensation` text, a driver's fee).
- **Full regression on the submitted code** (D59): 45/52, but five wrong automatic rulings. A prompt
  line from D58 made the Judge leave out the questioned record; removed. The deeper gap predates the
  day: the Code Judge sees a questioned record only if the Judge lists it. Next fix: check the record
  in code.
