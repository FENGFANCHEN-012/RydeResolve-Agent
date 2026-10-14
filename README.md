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
rules on every ask, with a confidence score and reasons. Photos are checked by code (capture time,
place, editing, reuse) and by a vision model. Code checks and a Fairness review decide
whether the ruling is executed automatically or sent to a person. Every step is traced and
visible live.

**Status (2026-10-14):** submission candidate with the code Judge (D38), rule checks (D39), photo
evidence (D46-D47) and a case editor (D49). Evaluated on Cerebras `gpt-oss-120b`, one run per case:

- 38 labelled dev and held-out cases: **33/38**, 0 wrong payouts (every miss went to a person).
- 20 fresh cases written blind by another model: **16/20**, 0 wrong payouts.
- Sealed set, run once and never used for a fix: **16/23**, with one wrong payout (S$8.00).
  The remand loophole behind it was then closed (D42).
- 20 more fresh cases written blind after that fix: **13/20**, with one wrong payout (S$8.00,
  a rule's wording misread; D42). The fix itself stopped one payout live (F2-17). That wording was
  rewritten in D48; the three cases that misread it are now right.
- Two blind photo sets (cleaning fees with stamped photos): **8/12**, with one wrong payout (a
  S$100 fee refunded because the driver's photo predated the trip, though a doubted photo needs a
  person; D46), then **9/10** after the fix that sends every doubted photo to a person (D47), with
  no fee confirmed or removed on a doubted photo.
- A blind set for the cancellation-fee wording: **7/10**, with two wrong payouts on other points
  (a held fee, and a driver's own chat admission set aside; D48, open).

This is evaluation accuracy, not an automatic resolution rate: a case sent to a person counts as a
miss whenever the answer key says the system could have decided it. Across the first four sets, 67
of 82 standard disputes (82%) were closed with no human, in about 98 seconds each.

**Live demo (2026-10-14):** http://43.134.17.192 on a Tencent Lighthouse server in Singapore. An
access code is required (given to judges); five recorded runs can be replayed under "Saved runs",
and "+ New case" / "Copy & edit" build a new case (trip, profiles, chat, rules, photos) to run.
Walkthrough: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). Deployment: [deploy/README.md](deploy/README.md).

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
| **Collector** | Deterministic tools over platform data (GPS, fare, chat, app events, profiles) produce facts, conflicts and data gaps, each with its source; rule checks measure the trip's time rules and report MET / NOT MET; photo checks read each photo's capture time and GPS against the trip, editing software, and the same file in another case |
| **ImageAnalyst** | A vision model (`qwen/qwen3.8-27b` on Groq) says what each photo shows: a car, a mess, whether it matches the claim, signs of editing or generation. It can only raise doubts, never approve money |
| **Classifier** | Dispute type and urgency (P0-P3); safety and unclear cases go straight to a person |
| **Case Brief** | One shared dossier (no LLM): facts, conflicts, the trip's rules, timeline and retrieved policy clauses |
| **Rider / Driver advocates** | Each builds its side's case from the brief and cites policy, then rebuts the other |
| **Fraud** | Deterministic risk signals and evidence-grounded chat labels; threats route separately to safety review |
| **Policy** | Compliance check of both cases against the retrieved official Ryde policy (RAG) |
| **Judge** | Splits the filing into asks, rules on each with amounts from specific rules, gives confidence and reasons; names the facts its ruling turns on and the refund arithmetic; sees approved precedents |
| **Code Judge** | Code, not a model: every decisive fact must be verified on a record nothing contradicts, and a refund must be plain arithmetic on record figures; a case with a doubted photo goes to a person whichever side the ruling favours; a failing draft goes back to the Judge once, then to a person |
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
5. **Code checks the Judge.** The model does not check itself: code verifies the facts a ruling
   turns on and the refund arithmetic, and measures time rules itself. On the 38-case and fresh sets
   no run paid out on a wrong ruling after this check; the sealed set found one (D41).
6. **Photos checked twice.** Code reads what a photo's file says (when, where, edited, reused);
   a vision model reads what it shows. Either can only raise a doubt, and a doubted photo is
   always a person's decision.
7. **Learning with a human in the loop.** Reviewers approve or correct rulings, and only approved
   rulings become precedents the Judge can see. Risk flags count only after a person confirms them.
8. **Full audit trail.** A live trace of every agent step and LLM call, rulings stored in a database,
   and an append-only, hash-chained audit log (`GET /api/audit/verify`).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | LangGraph state graph (`src/core/workflow.py`) |
| LLM | `LLM_PROVIDER`: Groq or Cerebras (`gpt-oss-120b`), Google Gemini, or Tencent Hunyuan (TokenHub). `LLM_FALLBACK_PROVIDERS` tries backups in order |
| Vision | `qwen/qwen3.8-27b` on Groq for photo descriptions; Pillow reads and writes photo EXIF |
| Policy retrieval | Qdrant Cloud hybrid search (dense `bge-base-en-v1.5` + BM25 via fastembed, RRF fusion; collection `ryde_policies_official`); local ChromaDB as an alternative |
| Tencent Cloud | ADP (Agent Development Platform) policy assistant on Hunyuan hy3, built over the same official policy files (`scripts/adp/`) |
| Records | SQLAlchemy store: SQLite locally, Postgres (Supabase) via `STORE_URL` / `DATABASE_URL` |
| Backend | Python + FastAPI, live trace streamed over server-sent events |
| Frontend | Single-page dashboard (`frontend/index.html`, plain JS): pick or build a case (`case_editor.js`), watch the agents, read the ruling and both notices; review desk (`review.html`) |
| Tests | pytest (offline, no real model calls) |
| Containers | Dockerfile + docker-compose |

## Dispute Categories

Covered end to end with labelled test cases: **fare disputes**, **route deviation**, **no-show
charges**, **cancellation and refunds**, **cleaning fees**, **service quality** (conduct
complaints) and **driver rights**. Safety incidents are classified P0 and always go to a person.

## Quick Start

```bash
python -m pip install -r requirements.txt
# create .env with the variables below
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
# Open http://127.0.0.1:8000 in your browser
```

On Windows, run `./Start-Ryde.ps1` in PowerShell to check dependencies, open the dashboard,
and start the API. Use `./Start-Ryde.ps1 -Port 8001` if the old server occupies port 8000.
The terminal must remain open. Do not use CMD's `start "" ...` syntax in PowerShell.

The dashboard and API share an origin. `/api/health` reports process liveness;
`/api/readiness` separately checks model-key configuration, record connectivity and policy
collection/model dimensions. It does not verify live quota or model quality.

An optional untracked `.env.local` overrides `.env` for this machine (explicit process
variables take precedence). For an isolated local demo with the existing official Qdrant index:

```dotenv
STORE_URL=sqlite:///data/ryde_resolve.local.db
QDRANT_COLLECTION=ryde_policies_official
QDRANT_DENSE_MODEL=BAAI/bge-base-en-v1.5
POLICIES_DIR=data/policies/official
MAX_DEBATE_ROUNDS=1
```

This local record database is separate from the shared store; it does not import shared
history. Set STORE_URL explicitly to reconnect to the shared store after connectivity is fixed.
The local Groq smoke run exceeded this account's 8,000-token single-request capacity with
three debate rounds (8,927 requested). The local profile uses the project default of one
round; this is a demo configuration change, not a new full-evaluation accuracy claim.
Only select an existing Qdrant collection indexed with the same embedding model; do not rebuild
any shared collection to start the demo.

Before remote access, configure distinct `API_DEMO_KEY` and `API_ADMIN_KEY` secrets and HTTPS.
With keys configured, the dashboard asks for an access code and keeps it only in memory.
Demo access can run cases; uploads, deletions, reviews, precedents, flags and audit/history
administration require the admin key. Audit actor names come from the authenticated role.
Without keys, API access is limited to loopback clients and hosts, with origin checks.
The API permits one dispute run at a time and cancels further work after a stream disconnect;
an already-sent provider request can still complete and be billed.

The shared `ryde_policies_official` collection is read-only through the upload/delete API
unless `ALLOW_POLICY_MUTATIONS=1` is explicitly set. Use a separate collection for uploaded
documents; evidence files never enter the policy index. Uploads accept at most 5 files,
10 MB per file, with generated storage names and bounded multipart request bodies.
The container keeps policy/case files in the image and mounts only writable data directories.
If using SQLite in Docker, set `STORE_URL=sqlite:///data/records/ryde_resolve.db` to use its
record volume. The default compose store is Postgres; a clean container build is still required.

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
never use fallback providers, so a run never mixes models. Latest results (D38-D48):

| Set | Cases | Correct | Wrong payouts | Run |
|-----|-------|---------|---------------|-----|
| Dev + held-out (answer keys written before the fixes) | 38 | 33 | 0 | 20261012-115556 |
| Fresh set written blind by a Claude Sonnet subagent | 20 | 16 | 0 | 20261012-155745-fresh |
| Sealed set (Gemini + qwen cases, run once, never used for a fix) | 23 | 16 | 1 (S$8.00) | 20261012-174317-sealed |
| Fresh set 2, written blind after the D42 fix | 20 | 13 | 1 (S$8.00) | 20261012-213702-fresh2 |
| Photo set IM (cleaning fees, stamped photos), blind | 12 | 8 | 1 (S$100 refund on a doubted photo; fixed in D47) | 20261014-113148-images |
| Photo set PS (mostly rider disputes of a fee charged on a photo), blind, after D47 | 10 | 9 | 0 (one award amount left empty) | 20261014-132901-photo-side |
| Cancellation-scope set CS, blind, after D48 | 10 | 7 | 2 (S$5.50, S$8.00) | 20261014-140420-cancel-scope |

On the sealed set two runs hit provider errors (HTTP 429) and were re-run once; the raw first pass
was 14/23. The misses, including the wrong payout and why it got through, are in
`docs/08_DESIGN_DECISIONS.md` (D41, D42). All results are without precedents: the precedent
store was empty in every evaluated run; when precedents should reach the Judge is designed in D43.
Every change, its measured effect and the rejected
alternatives are in `docs/06_EVAL_PLAN.md` and `docs/08_DESIGN_DECISIONS.md`.

## Project Structure

```
RydeResolve-Agent/
├── src/
│   ├── agents/        # collector (+ collector_tools, photo_checks), image_analyst, classifier,
│   │                  # case_brief, passenger, driver, policy, arbitrator (Judge), code_judge,
│   │                  # fraud, fairness, executor
│   ├── core/          # workflow (LangGraph), debate, llm_client, trace, policy_refs, confidence
│   ├── rag/           # indexer, retriever, Qdrant hybrid search, policy topics, precedents
│   ├── store/         # records DB, audit chain, feedback/precedents, rider/driver history
│   ├── integrations/  # simulated Ryde platform API (integration contract)
│   ├── api/           # FastAPI service, case editor upload (custom_cases)
│   └── config.py
├── frontend/          # dashboard: index.html, dispute.js, case_editor.js, review desk
├── data/
│   ├── policies/official/   # verbatim official Ryde policy texts (retrieval source)
│   ├── mock_disputes/       # demo disputes with platform data
│   ├── eval_cases/          # held-out, sealed, fresh, photo and fraud case sets
│   ├── evidence_samples/    # photo library (SOURCES.json) and the stamped case photos
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
| [docs/08_DESIGN_DECISIONS.md](docs/08_DESIGN_DECISIONS.md) | Every design change with its measured effect, and the rejected ones (D1–D49) |
| [docs/09_FRAUD_AGENT_DESIGN.md](docs/09_FRAUD_AGENT_DESIGN.md) | Fraud and bad-faith detection design |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | 8-minute demo walkthrough: five recorded runs and a live case-editor run |
| [deploy/README.md](deploy/README.md) | Running the service on a Linux server (systemd + Caddy) |

## License

MIT
