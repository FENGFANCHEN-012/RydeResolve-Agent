# RydeResolve-Agent — Development Plan

> **Competition**: Tencent Cloud AI CAN DO IT Hackathon Singapore 2026
> **Track**: Digital Native — Ryde
> **Challenge**: Multi-Agent Autonomous Dispute Resolution System
> **Deadline**: 16 October 2026
> **Demo Day**: 3 November 2026

---

## 1. Current State Assessment

The repository currently contains **skeleton code only** — all agent classes, the orchestrator, debate engine, confidence module, and API endpoints exist as stubs with `TODO` markers. No actual LLM integration, no RAG implementation, no frontend, no mock data, and no tests have been written.

### What Exists
| Component | Status |
|---|---|
| `src/agents/collector.py` | Skeleton — creates basic `DisputeContext` from report text |
| `src/agents/classifier.py` | Skeleton — `classify()` returns `None` |
| `src/agents/passenger.py` | Skeleton — `analyze()` and `rebut()` return `None` |
| `src/agents/driver.py` | Skeleton — `analyze()` and `rebut()` return `None` |
| `src/agents/policy.py` | Skeleton — `retrieve_policies()` and `evaluate_compliance()` return `None` |
| `src/agents/arbitrator.py` | Skeleton — `arbitrate()` returns dummy `Decision` with `confidence=0.0` |
| `src/agents/executor.py` | Partial — constructs result dict but no real execution |
| `src/core/orchestrator.py` | Pipeline wired but calls stub methods |
| `src/core/debate.py` | Debate loop wired but calls stub methods |
| `src/core/confidence.py` | Implemented — confidence calculation logic works |
| `src/api/main.py` | Basic FastAPI with 3 endpoints |
| `src/rag/indexer.py` | Skeleton — chunking works, no embedding/storage |
| `src/rag/retriever.py` | Skeleton — returns empty list |
| `src/models/__init__.py` | Empty |
| `data/policies/` | Only a README listing policy sources to collect |
| `tests/` | Only `__init__.py` |
| `frontend/` | Does not exist |
| `docs/` | Does not exist |

### What's Missing
- LLM integration (Tencent Hunyuan or fallback OpenAI-compatible)
- RAG pipeline (embedding + vector store + retrieval)
- Mock dispute dataset (GPS traces, chat logs, payment data, rider/driver profiles)
- Policy documents (actual Ryde ToS, refund policy, etc.)
- Frontend dashboard (agent communication visualization)
- Tests
- `.env.example` needs updating
- `docker-compose.yml` needs PostgreSQL/Redis services

---

## 2. Architecture Overview

```
Dispute Filed
     │
     ▼
[Collector Agent] ── gathers ──▶ GPS, Chat, Payment, History, Ratings
     │
     ▼
[Classifier Agent] ── classifies ──▶ Dispute Type + Urgency (P0-P3)
     │                                   │
     │                              P0/Safety? ──yes──▶ Human Escalation
     │                                   │ no
     ▼
[Debate Engine] ── runs 3 rounds ──▶
     ├── [Rider Advocate Agent] ── analyzes + rebuts (cites policy)
     ├── [Driver Advocate Agent] ── analyzes + rebuts (cites policy)
     └── [Policy Agent (RAG)] ── retrieves relevant policy clauses
     │
     ▼
[Judge Agent] ── synthesizes ──▶ Verdict + Confidence + Rationale
     │                                   │
     │                          Confidence < 0.5? ──yes──▶ Human Review Queue
     │                                   │ no
     ▼
[Execution Agent] ── executes ──▶ Refund / Penalty / Notification
```

### Alignment with Competition Requirements

| Competition Requirement | Our Implementation |
|---|---|
| Rider Advocate Agent (MVP) | `src/agents/passenger.py` — analyze + rebut |
| Driver Advocate Agent (MVP) | `src/agents/driver.py` — analyze + rebut |
| Judge Agent (MVP) | `src/agents/arbitrator.py` — verdict + confidence + reasoning |
| GPS & Telemetry evidence | `src/agents/collector.py` — structured GPS data |
| Chat & Communication logs | `src/agents/collector.py` — chat log text |
| Payment & Fare data | `src/agents/collector.py` — fare breakdown |
| Historical Behavior Profiles | `src/agents/collector.py` — dispute history + ratings |
| Inter-agent communication observable | Frontend dashboard + API logging |
| At least 2 dispute categories | Route Deviation + No-Show Charge |
| Working end-to-end prototype | Full pipeline from filing to execution |
| Source code on GitHub | Complete repo |
| Architecture diagram | `docs/architecture.png` |
| Built with CodeBuddy | `proof of usage of codebuddy/` folder |

---

## 3. Technology Decisions

### LLM Engine
- **Primary**: Tencent Hunyuan (via OpenAI-compatible API)
- **Fallback**: Any OpenAI-compatible endpoint (for local development)
- **Framework**: LangChain for prompt management + tool calling

### RAG
- **Vector Store**: ChromaDB (local, easy to demo) with option to swap to Tencent VectorDB
- **Embeddings**: Tencent Embedding API (fallback: OpenAI embeddings)
- **Policy docs**: Scrape + manually curate Ryde public policy pages

### Backend
- **Framework**: FastAPI (already set up)
- **Agent orchestration**: Custom async pipeline (LangGraph optional enhancement)
- **Data validation**: Pydantic v2

### Frontend
- **Framework**: React + TypeScript + Vite
- **UI Library**: Tailwind CSS + shadcn/ui
- **Visualization**: Real-time agent communication log + dispute timeline
- **Key screens**: Dispute filing form, Live agent debate view, Verdict display

### Infrastructure
- **Containerization**: Docker + docker-compose (PostgreSQL + Redis + API + Frontend)
- **Demo deployment**: Cloud Studio or Tencent Cloud CVM

---

## 4. Development Phases

### Phase 1: Foundation (Days 1-5) — Sep 21-25

**Goal**: Data models, mock data, LLM client, and policy documents ready.

| Task | Details | Files |
|---|---|---|
| 1.1 Data models | Define all Pydantic models for dispute, evidence, trip, payment, agent outputs | `src/models/` |
| 1.2 Mock dataset | Create 10+ realistic dispute scenarios with full evidence (GPS, chat, payment, history) | `data/mock_disputes/` |
| 1.3 Policy documents | Write/curate Ryde policy docs (ToS, refund, cancellation, driver guidelines, safety) | `data/policies/` |
| 1.4 LLM client | Build unified LLM client with Hunyuan/OpenAI fallback, prompt templates | `src/core/llm_client.py` |
| 1.5 Config update | Update `.env.example`, `config.py` with all needed settings | `.env.example`, `src/config.py` |
| 1.6 Docker setup | Working `docker-compose.yml` with PostgreSQL + Redis + API | `docker-compose.yml` |

### Phase 2: Core Agents MVP (Days 6-12) — Sep 26-Oct 2

**Goal**: Three core agents fully functional with LLM integration, debate engine working end-to-end.

| Task | Details | Files |
|---|---|---|
| 2.1 Collector Agent | Implement evidence gathering from mock data, structure into `DisputeContext` | `src/agents/collector.py` |
| 2.2 Classifier Agent | LLM-based classification: dispute type + urgency + human-required flag | `src/agents/classifier.py` |
| 2.3 Rider Advocate Agent | LLM-powered: analyze evidence, build case, cite policy, rebut driver arguments | `src/agents/passenger.py` |
| 2.4 Driver Advocate Agent | LLM-powered: analyze evidence, build case, cite policy, rebut passenger arguments | `src/agents/driver.py` |
| 2.5 Policy Agent (RAG) | Index policy docs into ChromaDB, retrieve relevant clauses for each dispute | `src/agents/policy.py`, `src/rag/` |
| 2.6 Judge Agent | LLM-powered: synthesize both sides + policy, issue verdict + confidence + reasoning | `src/agents/arbitrator.py` |
| 2.7 Debate Engine | Wire 3-round adversarial debate with observable communication log | `src/core/debate.py` |
| 2.8 Orchestrator | Wire full pipeline end-to-end | `src/core/orchestrator.py` |
| 2.9 Execution Agent | Execute verdict actions, generate notifications | `src/agents/executor.py` |
| 2.10 API endpoints | Dispute filing, status, result, agent communication log endpoints | `src/api/main.py` |

### Phase 3: Frontend Dashboard (Days 13-17) — Oct 3-7

**Goal**: Interactive dashboard showing dispute filing, live agent debate, and verdict display.

| Task | Details | Files |
|---|---|---|
| 3.1 Project setup | Vite + React + TypeScript + Tailwind + shadcn/ui | `frontend/` |
| 3.2 Dispute filing form | Input form for dispute description + order ID + category selection | `frontend/src/components/` |
| 3.3 Live agent debate view | Real-time display of agent messages, evidence, rebuttals | `frontend/src/components/` |
| 3.4 Verdict display | Show verdict, confidence, rationale, policy references, recommended action | `frontend/src/components/` |
| 3.5 Dispute history | List of past disputes with status and outcomes | `frontend/src/components/` |
| 3.6 Architecture diagram | Create visual architecture diagram | `docs/architecture.png` |

### Phase 4: Testing & Polish (Days 18-22) — Oct 8-12

**Goal**: All MVP dispute types working, tests pass, demo-ready.

| Task | Details | Files |
|---|---|---|
| 4.1 Unit tests | Test each agent's output format and logic | `tests/` |
| 4.2 Integration tests | End-to-end pipeline test for Route Deviation dispute | `tests/` |
| 4.3 Integration tests | End-to-end pipeline test for No-Show Charge dispute | `tests/` |
| 4.4 Agent communication log | Ensure all inter-agent messages are logged and visible | `src/core/` |
| 4.5 Error handling | Graceful handling of LLM failures, missing data, timeouts | All files |
| 4.6 Demo script | Write step-by-step demo walkthrough script | `docs/demo_script.md` |

### Phase 5: Stretch Goals (Days 23-25) — Oct 13-15

**Goal**: Implement bonus features if MVP is solid.

| Task | Details | Priority |
|---|---|---|
| 5.1 Escalation Protocol | Confidence < threshold → human review queue with case summary | High |
| 5.2 Policy & Precedent Agent | Store past rulings, retrieve similar precedents for Judge Agent | Medium |
| 5.3 Fraud Detection Agent | Detect patterns of dispute abuse, feed risk scores to Judge | Medium |
| 5.4 SLA & Routing Manager | Prioritize disputes by urgency, fast-track safety issues | Low |
| 5.5 Image Analysis | Multi-modal photo validation for property damage disputes | Low |

### Phase 6: Submission (Day 26) — Oct 16

| Task | Details |
|---|---|
| 6.1 Final code review | Ensure code is clean, documented, runs without errors |
| 6.2 CodeBuddy proof | Collect 3+ screenshots of CodeBuddy development conversations |
| 6.3 Cover image | Create 16:9 project cover image (380x216px) |
| 6.4 README polish | Final README with setup instructions, architecture, screenshots |
| 6.5 Submit | Submit via https://tinyurl.com/TCHackathonSGProjectSubmission |

---

## 5. MVP Scope — Exactly What We Build

### Dispute Categories (Minimum 2 Required)
1. **Route Deviation** — "Driver took a longer route and I was overcharged."
2. **No-Show Charge** — "Driver didn't show up but I was charged a cancellation fee."

### Evidence Per Dispute (Mock Data)
Each mock dispute includes:
- **GPS trace**: Array of `{lat, lng, timestamp, speed}` waypoints
- **Optimal route**: Pre-computed optimal path for comparison
- **Chat log**: Array of `{sender, message, timestamp}` messages
- **Payment breakdown**: `{base_fare, distance_fare, time_fare, surge_multiplier, promo_discount, total charged}`
- **Trip metadata**: `{pickup, dropoff, requested_time, actual_start, actual_end, estimated_duration, actual_duration}`
- **Rider profile**: `{account_age, total_trips, avg_rating, dispute_count, last_5_ratings}`
- **Driver profile**: `{account_age, total_trips, avg_rating, dispute_count, acceptance_rate, last_5_ratings}`

### Agent Output Requirements

**Rider Advocate Agent** outputs:
- `stance`: Passenger's position on the dispute
- `evidence`: List of evidence items supporting passenger's claim
- `policy_citations`: Specific policy clauses cited
- `remedy_requested`: What the passenger is asking for
- `argument`: Natural language argument text

**Driver Advocate Agent** outputs:
- `stance`: Driver's position on the dispute
- `evidence`: List of evidence items supporting driver's defense
- `policy_citations`: Specific policy clauses cited
- `remedy_requested`: What the driver is asking for
- `argument`: Natural language argument text

**Judge Agent** outputs:
- `verdict`: `upheld` | `partially_upheld` | `dismissed`
- `confidence`: 0.0-1.0
- `refund_amount`: Dollar amount if refund ordered
- `compensation`: Description of any compensation
- `driver_penalty`: Description of any driver penalty
- `rationale`: Natural language reasoning summary
- `policy_references`: List of cited policy clauses
- `escalation_recommended`: Boolean
- `human_review_needed`: Boolean

### Inter-Agent Communication Log
Every message between agents is logged:
```json
{
  "round": 0,
  "speaker": "rider_advocate",
  "content": "The GPS data shows the driver deviated...",
  "evidence": ["gps_trace_3km_longer", "estimated_vs_actual_duration"],
  "policy_citations": ["Section 4.2 - Route Optimization"],
  "timestamp": "2026-09-21T10:30:00Z"
}
```

---

## 6. Risk Mitigation

| Risk | Mitigation |
|---|---|
| Tencent Hunyuan API not available during dev | Fallback to OpenAI-compatible API; use `.env` to switch |
| VectorDB setup complexity | Use ChromaDB (local, zero-config) as primary; VectorDB as enhancement |
| LLM response latency in demo | Pre-generate results for 2 demo cases; live demo uses cached mode |
| Frontend time constraint | Prioritize backend + API; use minimal but polished UI |
| Mock data realism | Base scenarios on real Ryde policy edge cases; include edge cases |

---

## 7. Success Criteria

| Criterion | Target | How We Measure |
|---|---|---|
| Working prototype | End-to-end pipeline for 2 dispute types | Manual demo |
| Agent communication observable | All agent messages logged + visible in UI | Frontend log view |
| LLM integration | All agents use LLM for reasoning | Code review |
| RAG policy retrieval | Judge cites specific policy clauses | Verdict output |
| Confidence scoring | Verdict includes confidence + escalation logic | Decision model |
| Source code complete | Full repo on GitHub | Repository |
| CodeBuddy proof | 3+ development screenshots | `proof of usage of codebuddy/` |
| Architecture diagram | Visual diagram in repo | `docs/architecture.png` |
| Demo walkthrough | Step-by-step script + working demo | `docs/demo_script.md` |
