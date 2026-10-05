# RydeResolve-Agent

> Multi-Agent System for Automated Dispute Resolution on the Ryde Platform
>
> **Competition**: Tencent Cloud AI CAN DO IT Hackathon Singapore 2026 — Digital Native Track (Ryde)
>
> **Prize Pool**: SGD $17,000 (1st: $10,000 / 2nd: $5,000 / 3rd: $2,000)
>
> **Challenge**: Multi-Agent Autonomous Dispute Resolution System
>
> **Deadline**: 16 October 2026 | **Demo Day**: 3 November 2026
>
> **Built with**: CodeBuddy (Tencent Cloud AI coding assistant)

## Overview

RydeResolve-Agent settles ride disputes on **Ryde**, Singapore's first real-time carpooling
platform, using a pipeline of cooperating agents. A Rider Advocate and a Driver Advocate each build
their side's case from platform evidence and official Ryde policy, then rebut each other. A Judge
rules on every ask, with a confidence score and reasons. Code checks and a Fairness review decide
whether the ruling is executed automatically or sent to a person. Every step is traced and
visible live.

**Status (2026-10-05):** the full pipeline runs end to end. On 33 labelled cases it rules
**31/33 correctly (93.9%)**, with 0 failed runs, in about 1.5 minutes and US$0.011 per case
(`docs/08_DESIGN_DECISIONS.md`, D19).

## Background

### About Ryde

[Ryde Technologies Pte. Ltd.](https://www.rydesharing.com) is a Singapore-based mobility platform offering:

| Service | Description |
|--------|-------------|
| Ride-hailing | Private car services with instant & advance booking |
| Delivery | Point-to-point on-demand delivery (RydeSEND) |
| Carpooling | Shared rides, eco-friendly travel — Ryde's flagship differentiator |

**Key business differentiators**:
- **0% commission for drivers** (vs Grab/Gojek)
- **Ryde+ subscription** for passengers (unlimited cashback, priority matching)
- Corporate & merchant solutions

### Problem

As a multi-sided platform connecting passengers, drivers, merchants, and corporate clients, Ryde faces significant dispute volume across fare, cancellation, service quality, delivery, driver rights, and accident liability categories. Current manual customer service is slow, inconsistent, and costly.

## Architecture

![RydeResolve architecture](docs/architecture.png)

Vector source: [`docs/architecture.svg`](docs/architecture.svg).

### Core Agents

| Agent | Role |
|-------|------|
| **Collector** | Deterministic tools over platform data (GPS, fare, chat, app events, profiles) produce facts, conflicts and data gaps, each with its source |
| **Classifier** | Dispute type and urgency (P0-P3); safety and unclear cases go straight to a person |
| **Case Brief** | One shared dossier (no LLM): facts, conflicts, the trip's rules, timeline and retrieved policy clauses |
| **Rider / Driver advocates** | Each builds its side's case from the brief and cites policy, then rebuts the other |
| **Policy** | Compliance check of both cases against the retrieved official Ryde policy (RAG) |
| **Judge** | Splits the filing into asks, rules on each with amounts from specific rules, gives confidence and reasons; sees approved precedents |
| **Fairness** | Code checks (real citations, GPS gaps, fee basis, refund basis) plus an LLM grounding/bias review; any high-severity finding sends the case to a person |
| **Executor** | Simulated refund / penalty and a notice to each party with its own outcome (EN/ZH/MS/TA) |

### Key Innovations

1. **Adversarial debate on shared facts.** Both advocates argue from the same Case Brief (facts,
   conflicts and data gaps found by deterministic tools), then rebut each other. `MAX_DEBATE_ROUNDS`
   sets the number of rounds (default 1).
2. **Rulings per ask, amounts from rules.** The Judge splits a filing into its separate asks and
   takes every amount from a specific policy rule applied to a specific figure.
3. **Policy anchoring with verified citations.** Rulings may only cite clauses that retrieval
   actually returned from the official Ryde policy texts. Invalid citations are caught in code.
4. **Safe by default.** Safety cases, missing data, contradicted payouts, discretionary refunds and
   high-severity fairness findings go to a person instead of being executed.
5. **Learning with a human in the loop.** Reviewers approve or correct rulings, and only approved
   rulings become precedents the Judge can see. Risk flags count only after a person confirms them.
6. **Full audit trail.** A live trace of every agent step and LLM call, rulings stored in a database,
   and an append-only, hash-chained audit log (`GET /api/audit/verify`).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | LangGraph state graph (`src/core/workflow.py`) |
| LLM | `LLM_PROVIDER`: Groq or Cerebras (`gpt-oss-120b`), Google Gemini, or Tencent Hunyuan (TokenHub). `LLM_FALLBACK_PROVIDERS` tries backups in order |
| Policy retrieval | Qdrant Cloud hybrid search (dense `bge-base-en-v1.5` + BM25 via fastembed, RRF fusion; collection `ryde_policies_official`); local ChromaDB as an alternative |
| Tencent Cloud | ADP (Agent Development Platform) policy assistant on Hunyuan hy3, built over the same official policy files (`scripts/adp/`) |
| Records | SQLAlchemy store: SQLite locally, Postgres (Supabase) via `STORE_URL` / `DATABASE_URL` |
| Backend | Python + FastAPI, live trace streamed over server-sent events |
| Frontend | Single-page dashboard (`frontend/index.html`, plain JS): file a dispute, watch the agents, read the ruling and both notices |
| Tests | pytest (offline, no real model calls) |
| Containers | Dockerfile + docker-compose |

## Dispute Categories

Covered end to end with labelled test cases: **fare disputes**, **route deviation**, **no-show
charges**, **cancellation and refunds**, **cleaning fees**, **service quality** (conduct
complaints) and **driver rights**. Safety incidents are classified P0 and always go to a person.

## Quick Start

```bash
pip install -r requirements.txt
# create .env with the variables below
uvicorn src.api.main:app --port 8000
# open frontend/index.html in a browser (add ?api=<url> to use another backend)
```

Main `.env` variables:

| Variable | Purpose |
|----------|---------|
| `LLM_PROVIDER` | `groq`, `cerebras`, `gemini` or `hunyuan` |
| `LLM_FALLBACK_PROVIDERS` | Backup providers tried in order, e.g. `cerebras,gemini` |
| `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `LLM_API_KEY` (Gemini), `HUNYUAN_API_KEY` | Provider keys |
| `LLM_SPEND_CAP_USD` | Per-process spend cap for the paid Cerebras credit (default 1.00) |
| `VECTOR_BACKEND`, `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, `QDRANT_DENSE_MODEL`, `POLICIES_DIR` | Policy index (`qdrant` or `chroma`); the team uses `ryde_policies_official`, `BAAI/bge-base-en-v1.5`, `data/policies/official` |
| `STORE_URL` / `DATABASE_URL` | Records database (default: local SQLite) |
| `MAX_DEBATE_ROUNDS` | Debate rounds (default 1) |

## Evaluation

```bash
LLM_PROVIDER=cerebras python scripts/eval.py --yes        # all labelled cases
python scripts/eval.py --cases FD-002,NS-001 --repeat 3     # chosen cases, stability check
python scripts/eval.py --resume data/eval/<run>             # continue a stopped run
python -m pytest -q                                         # offline unit tests
```

Each run writes `data/eval/<timestamp>/report.html`, `results.csv` and one trace per case. Evals
never use fallback providers, so a run never mixes models. Latest full run (20261005-131434):

| Metric | Result |
|--------|--------|
| Verdict accuracy | 31/33 (93.9%): dev 13/14, held-out 18/19 |
| Refund amount accuracy | 25/27 |
| Classification accuracy | 28/28 |
| Refund cap respected, citation validity, retrieval Hit@3 | 100% |
| Failed runs | 0 |
| Cost and time per case | US$0.011, about 91 s (model time about 12 s; the rest is free-tier rate limiting) |

A sealed case set (`data/eval_cases/sealed`) is run once, just before submission. It checks that
the prompt changes made on these 33 cases generalise. The evaluation design, every change and its
measured effect are in `docs/06_EVAL_PLAN.md` and `docs/08_DESIGN_DECISIONS.md`.

## Project Structure

```
RydeResolve-Agent/
├── src/
│   ├── agents/        # collector (+ collector_tools), classifier, case_brief, passenger, driver,
│   │                  # policy, arbitrator (Judge), fairness, executor
│   ├── core/          # workflow (LangGraph), debate, llm_client, trace, policy_refs, confidence
│   ├── rag/           # indexer, retriever, Qdrant hybrid search, policy topics, precedents
│   ├── store/         # records DB, audit chain, feedback/precedents, rider/driver history
│   ├── integrations/  # simulated Ryde platform API (integration contract)
│   ├── api/           # FastAPI service
│   └── config.py
├── frontend/          # dashboard: index.html, dispute.js, dispute.css
├── data/
│   ├── policies/official/   # verbatim official Ryde policy texts (retrieval source)
│   ├── mock_disputes/       # demo disputes with platform data
│   ├── eval_cases/          # held-out, sealed and fraud case sets
│   └── eval_answer_keys.json
├── scripts/           # eval, index_policies, adp/ (Tencent ADP), migrate_store, seed_people, ...
├── tests/             # pytest suite
├── docs/              # requirements, development log, eval plan, design decisions, architecture
└── proof of usage of codebuddy/   # CodeBuddy development screenshots
```

## Documentation

| Document | Contents |
|----------|----------|
| [docs/01_PROJECT_REQUIREMENTS.md](docs/01_PROJECT_REQUIREMENTS.md) | Competition brief and what it requires |
| [docs/03_DEVELOPMENT_LOG.md](docs/03_DEVELOPMENT_LOG.md) | Dated development log and current handoff |
| [docs/05_NEXT_STEPS.md](docs/05_NEXT_STEPS.md) | Remaining work before submission |
| [docs/06_EVAL_PLAN.md](docs/06_EVAL_PLAN.md) | How the architecture is evaluated |
| [docs/08_DESIGN_DECISIONS.md](docs/08_DESIGN_DECISIONS.md) | Every design change with its measured effect (D1–D19) |
| [docs/09_FRAUD_AGENT_DESIGN.md](docs/09_FRAUD_AGENT_DESIGN.md) | Fraud and bad-faith detection design |

## License

MIT
