# Technology Stack Research & Comparison

> Comprehensive analysis of all viable technology options for the RydeResolve-Agent project.
> Each category is grouped with pros/cons to help make informed decisions.

---

## 1. LLM Engine (Large Language Model)

The LLM powers all agent reasoning, debate, and verdict generation.

### Option A: Tencent Hunyuan (混元) — **Competition Native**

| Aspect | Details |
|--------|---------|
| Models | Hunyuan-a13b (reasoning), Hunyuan-role (roleplay), Hunyuan-turbos-vision (multimodal) |
| Pricing | Hunyuan-a13b: ¥0.5/M input, ¥2/M output (~$0.07/$0.28 USD) |
| Free Quota | 1M tokens free (valid 1 year) per model |
| API Format | OpenAI-compatible endpoint available |
| Embedding | Hunyuan-embedding: ¥0.7/M tokens (~$0.10 USD) |
| Multimodal | Vision models available (Hunyuan-turbos-vision) |

**Pros:**
- Competition is Tencent-sponsored — using their stack shows alignment
- Free token quota covers development + demo
- OpenAI-compatible API = easy swap with other providers
- Cheapest option (especially with free quota)
- Singapore region available (ap-singapore)

**Cons:**
- Model quality may lag behind GPT/Claude for complex multi-step reasoning
- Documentation is primarily in Chinese
- Less mature ecosystem (fewer community integrations vs OpenAI)
- No explicit function-calling documentation found

### Option B: OpenAI GPT Series

| Aspect | Details |
|--------|---------|
| Models | GPT-5.6 Luna ($0.20/$1.20), GPT-5.6 Terra ($2/$12), GPT-6 Astra ($10/$50) |
| Context | 1.05M tokens (all models) |
| Features | Function calling, JSON mode, vision, web search, reasoning effort control |
| Max Output | 128K tokens |

**Pros:**
- Best-in-class reasoning quality
- Mature API with function calling, JSON mode, structured output
- Massive ecosystem (LangChain, LlamaIndex, etc.)
- 1M+ token context window

**Cons:**
- More expensive than Hunyuan (even Luna is 2x Hunyuan's price)
- Not competition-native (doesn't show Tencent alignment)
- API access may require VPN in Singapore/China

### Option C: DeepSeek

| Aspect | Details |
|--------|---------|
| Models | DeepSeek V4.1 Flash ($0.12/$0.48 per M tokens) |
| Context | 1.05M tokens |
| Features | Sparse MoE (552B backbone, 8B active), agentic-optimized |

**Pros:**
- Cheapest strong reasoning model on the market
- Excellent for long-horizon agentic tasks
- Compressed KV caching reduces cost on multi-step workloads
- OpenAI-compatible API

**Cons:**
- Not competition-native
- May have rate limits / availability issues
- Less mature than OpenAI for function calling

### Option D: OpenRouter (Multi-Model Router)

| Aspect | Details |
|--------|---------|
| Models | 100+ models (GPT, Claude, DeepSeek, Llama, Fugu, etc.) |
| Pricing | Aggregated; often discounted vs direct API |
| Features | Single API key, swap models instantly |

**Pros:**
- One API key, access to all models
- Can route different agents to different models (e.g., cheap model for classifier, strong model for judge)
- Built-in fallback and load balancing
- Fugu models are purpose-built for multi-agent orchestration

**Cons:**
- Extra latency (routing layer)
- Additional cost layer on top of provider pricing
- Not competition-native

### Recommendation: **Hunyuan (Primary) + OpenAI-compatible fallback**

| Agent | Model | Rationale |
|-------|-------|-----------|
| Classifier (simple routing) | Hunyuan-a13b | Cheap, fast, sufficient for classification |
| Rider/Driver Advocate | Hunyuan-a13b | Good reasoning, cost-effective for debate rounds |
| Judge Agent | Hunyuan-a13b (or DeepSeek fallback) | Needs strongest reasoning; use DeepSeek if Hunyuan insufficient |
| Embedding | Hunyuan-embedding | Native Tencent embedding, cheap |

> **Strategy**: Use Hunyuan for all agents (competition alignment + free quota). Configure LLM client with OpenAI-compatible base URL so we can swap to DeepSeek or OpenAI instantly if quality is insufficient. This is already how our `src/core/llm_client.py` is built.

---

## 2. Multi-Agent Orchestration Framework

Controls how agents communicate, debate, and reach consensus.

### Option A: LangGraph (by LangChain)

| Aspect | Details |
|--------|---------|
| License | MIT (open source) |
| Architecture | Graph-based state machine with low-level primitives |
| Memory | Built-in state management across agent turns |
| HITL | Human-in-the-loop controls built in |
| Streaming | First-class token-by-token streaming |

**Pros:**
- Most mature multi-agent framework
- Graph-based = precise control over agent communication flow
- Built-in state management (critical for debate rounds)
- Human-in-the-loop (for escalation protocol)
- Streaming support (for real-time UI)
- Huge ecosystem (LangChain tools, retrievers, etc.)
- No performance overhead

**Cons:**
- Steeper learning curve (low-level primitives)
- More manual setup than high-level frameworks
- Documentation can be fragmented

### Option B: Microsoft AutoGen (v0.4+)

| Aspect | Details |
|--------|---------|
| License | Open source (Microsoft) |
| Architecture | Event-driven, multi-layer (Core, AgentChat, Studio, Extensions) |
| Communication | gRPC-based distributed runtime |
| Code Execution | Docker-isolated safe execution |

**Pros:**
- Microsoft-backed, actively developed
- Event-driven = great for async agent communication
- AutoGen Studio = no-code prototyping UI
- Distributed runtime (gRPC) for scalable deployments
- Docker code execution (safe for agent tools)

**Cons:**
- Python 3.10+ required
- Multi-layer architecture = learning curve
- Multiple packages to understand
- Migration complexity from earlier versions
- Documentation fragmented across packages

### Option C: CrewAI

| Aspect | Details |
|--------|---------|
| License | Open source |
| Architecture | Two-tier: Flows (control) + Crews (agent teams) |
| Orchestration | Event-driven Flows + role-based Crews |
| Community | 100,000+ certified developers |

**Pros:**
- Most intuitive API for role-based agent design (perfect for Rider/Driver/Judge)
- Flows provide production-grade state management
- Cost-optimized (minimizes token usage)
- Extensible ecosystem (observability, databases, web scraping)
- MCP (Model Context Protocol) support

**Cons:**
- Less granular control than LangGraph
- Newer ecosystem (fewer integrations than LangChain)
- May abstract away too much for our custom debate protocol

### Option D: Custom Async Pipeline (No Framework)

| Aspect | Details |
|--------|---------|
| Architecture | Pure Python asyncio + custom message bus |
| Dependencies | Zero (just `asyncio` + LLM client) |

**Pros:**
- Zero learning curve (we control everything)
- Zero dependencies (no framework version conflicts)
- Maximum flexibility for custom debate protocol
- Easiest to debug (no framework magic)
- Smallest code footprint

**Cons:**
- Must build state management, message passing, and retry logic from scratch
- No built-in streaming/HITL — must implement
- No community support for edge cases
- More code to maintain

### Recommendation: **Custom Async Pipeline (with LangGraph-inspired patterns)**

For a hackathon with 25 days, the custom pipeline is best because:
1. **Our debate protocol is highly custom** — 3 agents debating in rounds with confidence scoring is simpler to build directly than to force into a framework
2. **Zero framework overhead** — no learning curve, no version conflicts
3. **Full control** — our `orchestrator.py` + `debate.py` pattern already matches this
4. **If we need framework features later** — we can adopt LangGraph patterns without full migration

> **Fallback**: If we find the custom pipeline lacks features (streaming, HITL), we can adopt LangGraph selectively for specific components.

---

## 3. Vector Database (for Policy RAG)

Stores and retrieves Ryde policy documents via vector similarity.

### Option A: ChromaDB — **Current Choice**

| Aspect | Details |
|--------|---------|
| License | Apache 2.0 (open source) |
| Setup | `pip install chromadb` — zero config |
| Scale | Designed for LLM apps, not billion-scale |
| SDK | Native Python, first-class LangChain integration |
| Deployment | In-memory (dev) or Docker (production) |

**Pros:**
- **Zero setup** — runs locally in 3 lines of Python
- Already integrated in our project (indexer + retriever working)
- Native Python, no external service needed for dev
- LangChain integration if needed
- Free and open source

**Cons:**
- Not built for massive scale (fine for our ~20 policy chunks)
- No hybrid search (keyword + vector) out of the box
- Less feature-rich than Qdrant/Weaviate

### Option B: Tencent VectorDB

| Aspect | Details |
|--------|---------|
| Type | Fully managed enterprise vector database |
| Scale | 1 billion vectors, million-level QPS |
| SDK | Python, Java, Go, HTTP API |
| Features | Embedding management, hybrid search |

**Pros:**
- Competition-native (Tencent stack alignment)
- Fully managed (no infrastructure)
- Billion-scale (massive overkill for us, but shows ambition)
- Built-in embedding management

**Cons:**
- Requires Tencent Cloud account setup
- More complex than ChromaDB for a hackathon
- May incur costs after free tier
- Overkill for ~20 policy document chunks

### Option C: Qdrant

| Aspect | Details |
|--------|---------|
| License | Apache 2.0 |
| Language | Rust (fast, memory-efficient) |
| Deployment | Docker (1 command) or Qdrant Cloud (free tier) |
| Features | Payload filtering, hybrid search |

**Pros:**
- Extremely fast (Rust)
- Excellent metadata filtering (good for filtering by policy type)
- Easy Docker setup
- Generous free cloud tier

**Cons:**
- Newer ecosystem than ChromaDB
- Requires running a separate service (vs ChromaDB in-process)

### Option D: pgvector (PostgreSQL extension)

| Aspect | Details |
|--------|---------|
| License | Open source PostgreSQL extension |
| Setup | `CREATE EXTENSION vector` on existing Postgres |
| Features | SQL-based vector search, ACID compliance |

**Pros:**
- One database for everything (disputes + vectors)
- ACID compliance for transactional data
- SQL JOINs with vector search
- We already need PostgreSQL for dispute records

**Cons:**
- Fewer ANN index options than dedicated vector DBs
- Not as optimized for pure vector search
- Requires Postgres setup

### Recommendation: **ChromaDB (dev) → Tencent VectorDB (production/demo)**

- **Phase 1-3**: ChromaDB (already working, zero setup, fast iteration)
- **Phase 4 (demo)**: Migrate to Tencent VectorDB for competition alignment
- **Why not pgvector**: We need Postgres for dispute records anyway, but keeping vector search separate is cleaner

---

## 4. Backend Framework

### Option A: FastAPI (Python) — **Current Choice**

| Aspect | Details |
|--------|---------|
| Language | Python 3.12+ |
| Async | Native async/await support |
| Type Safety | Pydantic v2 integration |
| Performance | Starlette-based, high performance |
| Docs | Auto-generated OpenAPI/Swagger |

**Pros:**
- Already integrated and working
- Same language as LLM agents (no serialization overhead)
- Native WebSocket support (for real-time agent communication UI)
- Pydantic models = type-safe API
- Auto API docs (good for demo)

**Cons:**
- Python GIL (not an issue for I/O-bound LLM calls)
- Less performant than Go/Rust for CPU-bound tasks (not our case)

### Option B: Flask + Socket.IO

**Pros:**
- Simpler than FastAPI
- Socket.IO for real-time

**Cons:**
- No native async (bad for concurrent LLM calls)
- Less type safety
- Slower than FastAPI

### Option C: Go (Gin/Fiber) + gRPC

**Pros:**
- Extremely fast
- gRPC for agent-to-agent communication

**Cons:**
- Different language from LLM ecosystem (Python)
- Serialization overhead between Python agents and Go backend
- Overkill for hackathon

### Recommendation: **FastAPI (no change)**

Already the best choice. Python + FastAPI + Pydantic is the standard for LLM applications.

---

## 5. Frontend Framework

### Option A: React + Vite + Tailwind + shadcn/ui — **Recommended**

| Aspect | Details |
|--------|---------|
| Framework | React 19 + Vite |
| Styling | Tailwind CSS 4 |
| Components | shadcn/ui (copy-paste, fully customizable) |
| State | Zustand (lightweight) or React Query |
| Real-time | Native WebSocket or EventSource |
| Charts | Recharts or Tremor |

**Pros:**
- Most mature ecosystem for AI/streaming UIs
- shadcn/ui = full control over component DOM (perfect for custom agent UIs)
- Vite = instant dev server, fast HMR
- Huge community (solutions for every problem)
- Vercel AI SDK for streaming LLM responses

**Cons:**
- React re-render management needed for real-time data
- More boilerplate than Vue/Svelte

### Option B: Next.js (React) + shadcn/ui

**Pros:**
- Server Components for initial load
- API routes in same project
- Vercel AI SDK integration
- Better SEO (not needed for dashboard)

**Cons:**
- Server Components add complexity
- WebSocket + Server Components can be tricky
- Overkill for a single-page dashboard

### Option C: Vue 3 + Vite

**Pros:**
- Best out-of-box reactivity (no manual memoization)
- Clean Composition API
- Fast prototyping

**Cons:**
- Smaller AI tooling ecosystem vs React
- Fewer dashboard templates

### Option D: Svelte/SvelteKit

**Pros:**
- Best raw performance (no Virtual DOM)
- Lowest memory footprint
- Great for high-frequency data

**Cons:**
- Smallest ecosystem
- Fewer charting/AI libraries

### Recommendation: **React + Vite + Tailwind + shadcn/ui**

- Best ecosystem for real-time AI dashboards
- shadcn/ui gives us custom agent chat windows, streaming text, collapsible logs
- Vite for fast development
- Zustand for lightweight state management
- Recharts for analytics charts

---

## 6. Database (for Dispute Records + State)

### Option A: PostgreSQL — **Current Choice**

| Aspect | Details |
|--------|---------|
| Type | Relational |
| ORM | SQLAlchemy 2.0 + Alembic |
| Features | ACID, JSONB, full-text search |

**Pros:**
- Already in docker-compose
- ACID for dispute records (legal compliance)
- JSONB for flexible evidence storage
- Can add pgvector extension if needed

**Cons:**
- Requires migration management (Alembic)
- More setup than NoSQL

### Option B: MongoDB

**Pros:**
- Flexible schema (good for varied evidence types)
- No migrations needed

**Cons:**
- No ACID by default
- Less suitable for legal/financial records
- Not in Tencent ecosystem

### Option C: Tencent Cloud TDSQL-C

**Pros:**
- Competition-native
- MySQL/PostgreSQL compatible
- Fully managed

**Cons:**
- Overkill for hackathon
- Requires cloud setup

### Recommendation: **PostgreSQL (no change)**

Perfect for dispute records with ACID guarantees. Already configured.

---

## 7. Message Queue / State Store

### Option A: Redis — **Current Choice**

| Aspect | Details |
|--------|---------|
| Type | In-memory key-value |
| Use | Agent state, message queue, caching |
| Features | Pub/Sub, Streams, TTL |

**Pros:**
- Already in docker-compose
- Perfect for agent state management (debate rounds, confidence scores)
- Pub/Sub for real-time UI updates
- Streams for agent message log

**Cons:**
- In-memory (data lost on restart — fine for hackathon)

### Option B: Tencent Cloud TDMQ (Message Queue)

**Pros:**
- Competition-native
- Managed Kafka/Pulsar

**Cons:**
- Overkill for 3-agent communication
- Complex setup

### Recommendation: **Redis (no change)**

---

## 8. Deployment / Containerization

### Option A: Docker + docker-compose — **Current Choice**

**Pros:**
- Already configured
- One command to start everything
- Reproducible environment
- Standard for hackathons

### Option B: Tencent Cloud TKE (Kubernetes)

**Pros:**
- Competition-native
- Production-grade orchestration

**Cons:**
- Overkill for hackathon
- Complex setup

### Option C: Cloud Studio (Tencent Cloud Sandbox)

**Pros:**
- Competition-native (Tencent)
- Free preview environment
- Can show live demo URL

**Cons:**
- Limited resources
- May not persist

### Recommendation: **Docker (dev) → Cloud Studio (demo)**

- Use docker-compose for development
- Deploy to Cloud Studio for live demo URL (shows Tencent alignment)

---

## 9. Observability / Logging

### Option A: Structured Logging (Python `logging` + JSON)

**Pros:**
- Zero dependencies
- Full control
- Good enough for hackathon

### Option B: Langfuse (Open Source LLM Observability)

**Pros:**
- Purpose-built for LLM tracing
- Shows agent reasoning chains
- Self-hosted or cloud
- Great for demo (visualizes agent communication)

**Cons:**
- Additional service to run
- May be overkill

### Option C: Tencent Cloud CLS (Cloud Log Service)

**Pros:**
- Competition-native
- Fully managed

**Cons:**
- Overkill for hackathon
- Requires cloud setup

### Recommendation: **Structured Logging (primary) + Langfuse (if time permits)**

- Start with structured JSON logging (all agent messages logged)
- If time permits in Phase 4, add Langfuse for visual agent tracing (great for demo)

---

## Summary: Final Tech Stack Recommendation

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **LLM** | Tencent Hunyuan (primary) + OpenAI-compatible fallback | Competition-native, free quota, cheap |
| **Agent Framework** | Custom async pipeline | Zero overhead, full control, matches our debate protocol |
| **Vector DB** | ChromaDB (dev) → Tencent VectorDB (demo) | Fast iteration now, competition alignment later |
| **Backend** | FastAPI + Pydantic v2 | Already working, native async, auto docs |
| **Frontend** | React + Vite + Tailwind + shadcn/ui | Best ecosystem for real-time AI dashboards |
| **Database** | PostgreSQL + SQLAlchemy | ACID for dispute records, already configured |
| **Cache/Queue** | Redis | Agent state, pub/sub for UI, already configured |
| **Deployment** | Docker (dev) → Cloud Studio (demo) | Reproducible dev, Tencent-native demo |
| **Observability** | Structured logging + Langfuse (optional) | Zero-cost start, visual tracing if time permits |

### Competition Alignment Score

| Tencent-native components | Score |
|--------------------------|-------|
| Hunyuan LLM | ★★★★★ |
| Hunyuan Embedding | ★★★★★ |
| Tencent VectorDB (demo) | ★★★★☆ |
| Cloud Studio (demo deploy) | ★★★★☆ |
| **Overall Tencent alignment** | **★★★★☆** (4/5) |

> The remaining 1 star is reserved for if we also use Tencent CLS (logging) and TKE (deployment), but those are overkill for a hackathon.
