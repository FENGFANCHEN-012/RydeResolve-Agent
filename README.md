# RydeResolve-Agent

> Multi-Agent System for Automated Dispute Resolution on the Ryde Platform
>
> **Competition**: Tencent Cloud AI CAN DO IT Hackathon Singapore 2026
> **Prize Pool**: 17,000 SGD
> **Date**: 2026-09-18

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

1. **Adversarial Multi-Agent Debate** — Passenger Agent vs Driver Agent through 3 rounds of evidence-based argument
2. **Confidence-graded Processing** — High confidence auto-execute, low confidence escalates to human
3. **RAG Policy Anchoring** — Every verdict must cite specific platform clauses
4. **Full Audit Trail** — Complete reasoning chain for every decision

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM Engine | Tencent Hunyuan |
| Agent Framework | LangChain / LangGraph |
| RAG | Tencent VectorDB + Embedding |
| Backend | Python + FastAPI |
| Frontend | React + TypeScript |
| Database | PostgreSQL |
| Queue | Redis |
| Deploy | Tencent Cloud CVM / TKE |

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
│   └── proposal.md          # Design proposal report
├── src/
│   ├── agents/              # Agent implementations
│   ├── core/                # Orchestrator, debate engine
│   ├── rag/                 # Policy knowledge base
│   ├── api/                 # FastAPI service
│   ├── models/              # Data models
│   └── config.py
├── tests/
├── frontend/
├── data/                    # Mock data & policy docs
├── requirements.txt
└── docker-compose.yml
```

## Development Plan

| Phase | Week | Focus |
|-------|------|-------|
| 1 | Week 1 | Architecture + policy docs + RAG setup |
| 2 | Week 2 | Core agents (classifier, passenger, driver, policy) |
| 3 | Week 3 | Arbitration engine + debate mechanism + confidence |
| 4 | Week 4 | API + frontend dashboard + integration |
| 5 | Week 5 | Mock data testing + optimization + submission |

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
