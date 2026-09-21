# RydeResolve-Agent — Task Breakdown

> Detailed task list for implementation. Each task is sized for 1-3 hours of focused work.
> Tasks are grouped by phase and can be parallelized within a phase where dependencies allow.

---

## Phase 1: Foundation (Sep 21-25)

### 1.1 Data Models
- [ ] **1.1.1** Create `src/models/dispute.py` — `Dispute`, `DisputeType`, `UrgencyLevel`, `DisputeStatus`
- [ ] **1.1.2** Create `src/models/evidence.py` — `GPSTrace`, `ChatMessage`, `PaymentBreakdown`, `TripData`, `BehaviorProfile`
- [ ] **1.1.3** Create `src/models/agent_output.py` — `AdvocateAnalysis`, `PolicyEvaluation`, `DebateMessage`, `JudgeVerdict`
- [ ] **1.1.4** Create `src/models/api_models.py` — Request/Response models for API endpoints
- [ ] **1.1.5** Update `src/models/__init__.py` with all exports

### 1.2 Mock Dataset
- [ ] **1.2.1** Create `data/mock_disputes/route_deviation_01.json` — Driver takes 3km longer route, passenger overcharged
- [ ] **1.2.2** Create `data/mock_disputes/route_deviation_02.json` — Driver takes slightly longer route but due to traffic
- [ ] **1.2.3** Create `data/mock_disputes/no_show_01.json` — Driver doesn't show up, passenger charged cancellation fee
- [ ] **1.2.4** Create `data/mock_disputes/no_show_02.json` — Driver claims passenger wasn't at pickup, passenger disputes
- [ ] **1.2.5** Create `data/mock_disputes/safety_incident_01.json` — Driver behaved inappropriately (stretch goal data)
- [ ] **1.2.6** Create `data/mock_disputes/property_damage_01.json` — Rider spilled drinks, driver claims cleaning fee (stretch goal data)
- [ ] **1.2.7** Create `data/mock_disputes/rider_profiles.json` — Sample rider behavior profiles (5+ riders)
- [ ] **1.2.8** Create `data/mock_disputes/driver_profiles.json` — Sample driver behavior profiles (5+ drivers)

### 1.3 Policy Documents
- [ ] **1.3.1** Write `data/policies/terms_of_use.md` — Curated Ryde Terms of Use
- [ ] **1.3.2** Write `data/policies/cancellation_policy.md` — Cancellation and no-show policies
- [ ] **1.3.3** Write `data/policies/refund_policy.md` — Refund eligibility and processing
- [ ] **1.3.4** Write `data/policies/driver_guidelines.md` — Driver code of conduct and route standards
- [ ] **1.3.5** Write `data/policies/safety_standards.md` — Safety requirements and incident protocols
- [ ] **1.3.6** Write `data/policies/rider_code_of_conduct.md` — Rider responsibilities and expectations

### 1.4 LLM Client
- [ ] **1.4.1** Create `src/core/llm_client.py` — Unified LLM client with Hunyuan/OpenAI fallback
- [ ] **1.4.2** Create `src/core/prompts.py` — All prompt templates for each agent role
- [ ] **1.4.3** Add LLM client config to `src/config.py` — API keys, model names, temperature settings

### 1.5 Config & Environment
- [ ] **1.5.1** Update `.env.example` with all required environment variables
- [ ] **1.5.2** Update `src/config.py` with LLM, ChromaDB, and frontend settings
- [ ] **1.5.3** Update `requirements.txt` — add chromadb, langchain-community, etc.

### 1.6 Docker Setup
- [ ] **1.6.1** Update `docker-compose.yml` — add PostgreSQL, Redis, ChromaDB services
- [ ] **1.6.2** Update `Dockerfile` — ensure proper Python 3.12 base, install all deps
- [ ] **1.6.3** Create `docker-compose.dev.yml` — dev overrides for hot reload

---

## Phase 2: Core Agents MVP (Sep 26-Oct 2)

### 2.1 Collector Agent
- [ ] **2.1.1** Implement `CollectorAgent.collect()` — load mock data by order_id, populate `DisputeContext`
- [ ] **2.1.2** Implement GPS trace analysis helper — compute route deviation, unexpected stops
- [ ] **2.1.3** Implement payment validation helper — verify fare breakdown math
- [ ] **2.1.4** Add unit test for CollectorAgent

### 2.2 Classifier Agent
- [ ] **2.2.1** Implement `ClassifierAgent.classify()` — LLM call to classify dispute type + urgency
- [ ] **2.2.2** Add safety/legal detection logic — auto-flag P0 for safety incidents
- [ ] **2.2.3** Add unit test for ClassifierAgent

### 2.3 Rider Advocate Agent
- [ ] **2.3.1** Implement `PassengerAgent.analyze()` — LLM-powered evidence analysis + case building
- [ ] **2.3.2** Implement `PassengerAgent.rebut()` — LLM-powered counter-argument generation
- [ ] **2.3.3** Wire policy citation — agent retrieves and cites relevant policy clauses
- [ ] **2.3.4** Add unit test for PassengerAgent

### 2.4 Driver Advocate Agent
- [ ] **2.4.1** Implement `DriverAgent.analyze()` — LLM-powered evidence analysis + case building
- [ ] **2.4.2** Implement `DriverAgent.rebut()` — LLM-powered counter-argument generation
- [ ] **2.4.3** Wire policy citation — agent retrieves and cites relevant policy clauses
- [ ] **2.4.4** Add unit test for DriverAgent

### 2.5 Policy Agent (RAG)
- [ ] **2.5.1** Implement `PolicyIndexer.index_policies()` — chunk + embed + store in ChromaDB
- [ ] **2.5.2** Implement `PolicyRetriever.retrieve()` — query embedding + vector search
- [ ] **2.5.3** Implement `PolicyAgent.retrieve_policies()` — use retriever to find relevant clauses
- [ ] **2.5.4** Implement `PolicyAgent.evaluate_compliance()` — LLM evaluates both parties against policy
- [ ] **2.5.5** Create indexing script `scripts/index_policies.py` — standalone script to build index
- [ ] **2.5.6** Add unit test for PolicyAgent

### 2.6 Judge Agent
- [ ] **2.6.1** Implement `ArbitrationAgent.arbitrate()` — LLM synthesizes all inputs into verdict
- [ ] **2.6.2** Implement confidence scoring — use `confidence.py` module with real inputs
- [ ] **2.6.3** Implement escalation logic — confidence < 0.5 → human review
- [ ] **2.6.4** Add unit test for ArbitrationAgent

### 2.7 Debate Engine
- [ ] **2.7.1** Update `DebateEngine.debate()` — wire real agent calls, structured message log
- [ ] **2.7.2** Add communication log formatting — each message has round, speaker, content, evidence, citations
- [ ] **2.7.3** Add unit test for DebateEngine

### 2.8 Orchestrator
- [ ] **2.8.1** Update `Orchestrator.resolve()` — wire all real agent calls
- [ ] **2.8.2** Add structured logging — log each step with timing and status
- [ ] **2.8.3** Add error handling — graceful failure at each step
- [ ] **2.8.4** Add unit test for Orchestrator

### 2.9 Execution Agent
- [ ] **2.9.1** Update `ExecutionAgent.execute()` — format notification messages for both parties
- [ ] **2.9.2** Add action logging — record all executed actions
- [ ] **2.9.3** Add unit test for ExecutionAgent

### 2.10 API Endpoints
- [ ] **2.10.1** `POST /api/disputes` — file a new dispute
- [ ] **2.10.2** `GET /api/disputes/{id}` — get dispute status + result
- [ ] **2.10.3** `GET /api/disputes/{id}/debate` — get full agent communication log
- [ ] **2.10.4** `GET /api/disputes` — list all disputes
- [ ] **2.10.5** `POST /api/disputes/resolve` — trigger resolution (existing, update return format)
- [ ] **2.10.6** Add CORS middleware for frontend
- [ ] **2.10.7** Add integration test for API

---

## Phase 3: Frontend Dashboard (Oct 3-7)

### 3.1 Project Setup
- [ ] **3.1.1** Initialize Vite + React + TypeScript project in `frontend/`
- [ ] **3.1.2** Install Tailwind CSS + shadcn/ui + axios
- [ ] **3.1.3** Create API client module (`frontend/src/api/`)
- [ ] **3.1.4** Create base layout + routing

### 3.2 Dispute Filing
- [ ] **3.2.1** Create dispute filing form component
- [ ] **3.2.2** Add dispute type selector (Route Deviation / No-Show Charge / etc.)
- [ ] **3.2.3** Add order ID input + description textarea
- [ ] **3.2.4** Wire form to `POST /api/disputes` endpoint

### 3.3 Live Agent Debate View
- [ ] **3.3.1** Create agent message card component — shows speaker, round, content, evidence, citations
- [ ] **3.3.2** Create debate timeline component — chronological view of all agent messages
- [ ] **3.3.3** Add real-time polling — fetch debate log every 2s while dispute is processing
- [ ] **3.3.4** Add color coding — rider advocate (blue), driver advocate (orange), policy (green), judge (purple)

### 3.4 Verdict Display
- [ ] **3.4.1** Create verdict card component — shows verdict, confidence meter, rationale
- [ ] **3.4.2** Create policy reference list — clickable references to policy clauses
- [ ] **3.4.3** Create recommended action display — refund amount, penalties, notifications
- [ ] **3.4.4** Create confidence gauge visualization

### 3.5 Dispute History
- [ ] **3.5.1** Create dispute list component — table of past disputes with status badges
- [ ] **3.5.2** Add dispute detail view — click to see full dispute + debate + verdict
- [ ] **3.5.3** Add filtering by dispute type and status

### 3.6 Architecture Diagram
- [ ] **3.6.1** Create architecture diagram (use draw.io or mermaid export to PNG)
- [ ] **3.6.2** Save to `docs/architecture.png`

---

## Phase 4: Testing & Polish (Oct 8-12)

### 4.1 Unit Tests
- [ ] **4.1.1** Test all data model validation
- [ ] **4.1.2** Test confidence calculation edge cases
- [ ] **4.1.3** Test collector GPS analysis logic
- [ ] **4.1.4** Test payment validation logic

### 4.2 Integration Tests
- [ ] **4.2.1** End-to-end test: Route Deviation dispute full pipeline
- [ ] **4.2.2** End-to-end test: No-Show Charge dispute full pipeline
- [ ] **4.2.3** Test safety incident escalation to human review
- [ ] **4.2.4** Test low-confidence escalation

### 4.3 Communication Log
- [ ] **4.3.1** Verify all agent messages are logged with full metadata
- [ ] **4.3.2** Verify log is retrievable via API
- [ ] **4.3.3** Verify log displays correctly in frontend

### 4.4 Error Handling
- [ ] **4.4.1** Handle LLM API failures gracefully
- [ ] **4.4.2** Handle missing mock data gracefully
- [ ] **4.4.3** Handle malformed input gracefully
- [ ] **4.4.4** Add request timeout handling

### 4.5 Demo Preparation
- [ ] **4.5.1** Write demo script (`docs/demo_script.md`)
- [ ] **4.5.2** Pre-run 2 demo cases and save results
- [ ] **4.5.3** Test demo on clean environment (docker-compose up from scratch)

---

## Phase 5: Stretch Goals (Oct 13-15)

### 5.1 Escalation Protocol
- [ ] **5.1.1** Implement human review queue — store escalated disputes
- [ ] **5.1.2** Generate case summary for human reviewer
- [ ] **5.1.3** Add API endpoint for human review queue

### 5.2 Policy & Precedent Agent
- [ ] **5.2.1** Store past rulings in a precedent database
- [ ] **5.2.2** Retrieve similar past cases for Judge Agent
- [ ] **5.2.3** Feed precedent-based recommendations to Judge

### 5.3 Fraud Detection Agent
- [ ] **5.3.1** Implement behavioral pattern analysis
- [ ] **5.3.2** Calculate dispute abuse risk score
- [ ] **5.3.3** Feed risk signals to Judge Agent

### 5.4 SLA & Routing
- [ ] **5.4.1** Implement priority queue with urgency-based routing
- [ ] **5.4.2** Fast-track safety-related disputes

### 5.5 Image Analysis
- [ ] **5.5.1** Integrate multi-modal LLM for photo validation
- [ ] **5.5.2** Check photo timestamp matches trip
- [ ] **5.5.3** Validate photo authenticity

---

## Phase 6: Submission (Oct 16)

- [ ] **6.1** Final code review and cleanup
- [ ] **6.2** Collect 3+ CodeBuddy usage screenshots
- [ ] **6.3** Create 16:9 cover image (380x216px)
- [ ] **6.4** Final README polish with setup instructions
- [ ] **6.5** Submit project via submission link
- [ ] **6.6** Prepare Demo Day presentation (if selected as finalist)

---

## Task Dependencies

```
Phase 1 (Foundation) — all must complete before Phase 2
  1.1 Data Models ──────────┐
  1.2 Mock Dataset ─────────┤
  1.3 Policy Documents ────┤── Phase 2 depends on all of these
  1.4 LLM Client ──────────┤
  1.5 Config ──────────────┤
  1.6 Docker ──────────────┘

Phase 2 (Core Agents) — critical path
  2.1 Collector ────┐
  2.2 Classifier ───┤
  2.5 Policy/RAG ───┤── 2.3 + 2.4 depend on 2.5 for policy citations
  2.3 Rider Agent ──┤── 2.3 depends on 2.1 (context) + 2.5 (policy)
  2.4 Driver Agent ──┤── 2.4 depends on 2.1 (context) + 2.5 (policy)
  2.6 Judge Agent ───┤── 2.6 depends on 2.3 + 2.4 + 2.5
  2.7 Debate Engine ─┘── 2.7 depends on 2.3 + 2.4 + 2.5
  2.8 Orchestrator ──── 2.8 depends on ALL agents (2.1-2.6)
  2.9 Executor ──────── 2.9 depends on 2.6 (Decision model)
  2.10 API ──────────── 2.10 depends on 2.8

Phase 3 (Frontend) — depends on Phase 2 API
  All frontend tasks depend on 2.10 API being functional

Phase 4 (Testing) — depends on Phase 2 + 3
Phase 5 (Stretch) — depends on Phase 4 (MVP solid)
Phase 6 (Submission) — depends on all above
```

---

## Parallelization Strategy

Within each phase, these tasks can be done in parallel:

### Phase 1 Parallel Groups
- **Group A**: 1.1 (Data Models) + 1.4 (LLM Client) + 1.5 (Config)
- **Group B**: 1.2 (Mock Dataset) + 1.3 (Policy Documents)
- **Group C**: 1.6 (Docker) — independent

### Phase 2 Parallel Groups
- **Group A**: 2.1 (Collector) + 2.2 (Classifier) + 2.5 (Policy/RAG) — do first
- **Group B**: 2.3 (Rider Agent) + 2.4 (Driver Agent) — after Group A
- **Group C**: 2.6 (Judge) + 2.7 (Debate) — after Group B
- **Group D**: 2.8 (Orchestrator) + 2.9 (Executor) + 2.10 (API) — after Group C

### Phase 3 Parallel Groups
- **Group A**: 3.1 (Setup) — do first
- **Group B**: 3.2 (Filing) + 3.5 (History) — independent
- **Group C**: 3.3 (Debate View) + 3.4 (Verdict) — independent
- **Group D**: 3.6 (Architecture) — independent
