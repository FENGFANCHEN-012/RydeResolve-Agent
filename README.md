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

RydeResolve-Agent is an intelligent multi-agent system designed to automatically adjudicate and mediate disputes on **Ryde** — Singapore's first real-time carpooling platform. The system leverages Tencent Cloud AI capabilities (Hunyuan LLM, VectorDB, NLP) to simulate real-world dispute mediation through adversarial multi-agent debate.

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

```
Report -> [Collector Agent] -> [Classifier Agent] -> Parallel Investigation:
                                                    ├── [Passenger Agent]
                                                    ├── [Driver Agent]
                                                    └── [Policy Agent (RAG)]
                                                          |
                                                 [Arbitration Agent]
                                                          |
                                              Confidence > threshold?
                                              ├── Yes -> [Execution Agent]
                                              └── No  -> Human Review Queue
```

### Core Agents

| Agent | Role |
|-------|------|
| **Collector** | Gathers dispute context from platform data (GPS, payment, ratings, chat) |
| **Classifier** | Auto-classifies dispute type & urgency (P0-P3) |
| **Passenger** | Advocates passenger perspective, cites passenger rights |
| **Driver** | Advocates driver perspective, cites driver rights |
| **Policy** | RAG-based retrieval of Ryde ToS, Code of Conduct, refund policies |
| **Arbitration** | Synthesizes all perspectives, generates verdict & remediation |
| **Execution** | Executes decisions, notifies parties (EN/CN/MS/Tamil) |

### Key Innovations

1. **Adversarial Multi-Agent Debate** — Passenger Agent vs Driver Agent with one rebuttal round by default; set `MAX_DEBATE_ROUNDS=3` for a larger request budget. The default requires up to five model requests for the debate, plus any classifier, arbitration, and fairness requests.
2. **Confidence-graded Processing** — High confidence auto-execute, low confidence escalates to human
3. **RAG Policy Anchoring** — Every verdict must cite specific platform clauses
4. **Full Audit Trail** — Complete reasoning chain for every decision

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM Engine | Tencent Hunyuan (OpenAI-compatible API, fallback supported) |
| Agent Framework | LangChain + custom async pipeline |
| RAG | ChromaDB + Tencent Embedding API |
| Backend | Python 3.12 + FastAPI |
| Frontend | React + TypeScript + Vite + Tailwind CSS |
| Data Validation | Pydantic v2 |
| Containerization | Docker + docker-compose |

## Dispute Categories

1. **Fare Disputes** — overcharging, surge pricing, carpool splitting
2. **Cancellation & Refund** — driver/passenger cancellation, refund timing
3. **Service Quality** — rudeness, detours, rating retaliation
4. **Delivery** — damaged goods, delays, RydeSEND disputes
5. **Driver Rights** — account bans, payout issues, 0% commission disputes
6. **Accident Liability** — traffic accidents, insurance claims

## Project Structure

```
RydeResolve-Agent/
├── docs/
│   ├── PLAN.md              # Detailed development plan
│   └── TASKS.md             # Task breakdown with checkboxes
├── src/
│   ├── agents/              # Agent implementations (collector, classifier, passenger, driver, policy, arbitrator, executor)
│   ├── core/                # Orchestrator, debate engine, confidence, LLM client
│   ├── rag/                 # Policy indexer + retriever (ChromaDB)
│   ├── api/                 # FastAPI service
│   ├── models/              # Pydantic data models
│   └── config.py            # Configuration
├── tests/                   # Unit + integration tests
├── frontend/                # React + TypeScript dashboard (planned)
├── data/
│   ├── policies/            # Ryde policy documents for RAG
│   └── mock_disputes/       # Mock dispute scenarios with evidence (planned)
├── proof of usage of codebuddy/  # CodeBuddy development screenshots
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Development Plan

> Detailed plan and task breakdown: see [docs/PLAN.md](docs/PLAN.md) and [docs/TASKS.md](docs/TASKS.md)

### Current Status: Phase 1 — Foundation

| Phase | Dates | Focus | Status |
|-------|-------|-------|--------|
| 1. Foundation | Sep 21-25 | Data models, mock dataset, policy docs, LLM client, Docker | In Progress |
| 2. Core Agents MVP | Sep 26-Oct 2 | All 3 core agents + debate engine + orchestrator + API | Pending |
| 3. Frontend Dashboard | Oct 3-7 | React UI: dispute filing, live debate view, verdict display | Pending |
| 4. Testing & Polish | Oct 8-12 | Unit tests, integration tests, error handling, demo prep | Pending |
| 5. Stretch Goals | Oct 13-15 | Escalation protocol, precedent RAG, fraud detection | Pending |
| 6. Submission | Oct 16 | Final review, CodeBuddy proof, cover image, submit | Pending |

### MVP Scope
- **3 Core Agents**: Rider Advocate, Driver Advocate, Judge Agent
- **2 Dispute Types**: Route Deviation + No-Show Charge
- **Evidence Sources**: GPS traces, chat logs, payment data, behavior profiles
- **Observable Communication**: All inter-agent messages logged and visible in UI

## Target Metrics

| Metric | Goal |
|--------|------|
| Auto-resolution rate | >= 70% |
| Avg processing time | < 5 min (vs 2-3 days manual) |
| Verdict accuracy | >= 85% |
| User satisfaction | >= 4.0/5.0 |
| Cost reduction | >= 60% |

## License

MIT
