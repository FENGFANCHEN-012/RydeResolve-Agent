# RydeResolve-Agent Session Summary

**Date**: 2026-09-21
**Session**: RAG Pipeline Development & Optimization

---

## 1. Architecture Overview

```
Frontend (index.html)  <--HTTP-->  FastAPI Backend (main.py)
                                        |
                    +-------------------+-------------------+
                    |                   |                   |
              RAG Pipeline      Dispute Resolution    Health/Stats
                    |
    +---------------+---------------+---------------+
    |               |               |               |
Document      Embedding       Retriever         QA Engine
Parser        (Gemini)        (Advanced)        (Gemini)
    |               |               |               |
  PDF/DOCX    3072-dim      Query Rewrite     LLM Generation
  TXT/MD      vectors       Hybrid Search
                            Re-ranking
                            Confidence Scoring
```

---

## 2. Completed Work

### 2.1 Core RAG Pipeline (Initial)
- **Document Parser**: PDF, DOCX, TXT, MD, HTML support
- **Vector DB**: ChromaDB (local persistent / HTTP client)
- **Embedding**: Google Gemini `gemini-embedding-2` (3072 dims)
- **LLM**: Google Gemini `gemini-3.6-flash`
- **API Endpoints**:
  - `POST /api/rag/upload` - Single file upload
  - `POST /api/rag/upload-multiple` - Batch upload
  - `GET /api/rag/search` - Vector search
  - `POST /api/rag/ask` - RAG Q&A
  - `GET /api/rag/stats` - Knowledge base stats
  - `DELETE /api/rag/collection` - Clear collection

### 2.2 Advanced Retrieval Pipeline (5 Optimizations)

| # | Technique | File | Description |
|---|-----------|------|-------------|
| 1 | Query Rewriting | `query_rewriter.py` | LLM expands 1 query -> 3-4 variants |
| 2 | Hybrid Search | `hybrid_search.py` | Vector + BM25 with RRF fusion |
| 3 | Re-ranking | `reranker.py` | Keyword overlap scoring + optional LLM rerank |
| 4 | Smart Chunking | `smart_chunker.py` | Semantic boundary splitting + context prefix |
| 5 | Confidence Scoring | `confidence_scorer.py` | Quality assessment + graceful fallback |

**Pipeline Flow**:
```
User Query -> Query Rewrite (3-4 variants)
    -> Multi-query Retrieval (each variant)
    -> Hybrid Fusion (Vector + BM25 via RRF)
    -> Deduplication
    -> Re-ranking
    -> Confidence Scoring
    -> LLM Answer Generation (or Fallback)
```

### 2.3 Frontend
- Single-page app with 4 tabs: Upload, Search, Chat & QA, Accuracy Test
- Drag-and-drop file upload
- Real-time stats display
- Source citation with expand/collapse
- Accuracy testing with manual scoring

---

## 3. Configuration

### Environment Variables (`.env`)
```bash
# LLM (Google Gemini)
LLM_API_KEY=<your_gemini_api_key_here>
LLM_MODEL=gemini-3.6-flash
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=4096

# Embedding
EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSION=3072

# Vector DB
CHROMA_HOST=localhost
CHROMA_PORT=8200
CHROMA_COLLECTION=ryde_policies

# API
API_HOST=0.0.0.0
API_PORT=8000
```

### API Key Sources
- **Gemini**: https://aistudio.google.com/app/apikey (free tier)
- **Tencent Cloud** (deprecated): SecretId/SecretKey in `SecretKey_tecent_cloud.csv`

---

## 4. Key Files & Their Roles

| File | Role |
|------|------|
| `src/api/main.py` | FastAPI entry point, all HTTP endpoints |
| `src/config.py` | Centralized configuration from env vars |
| `src/core/llm_client.py` | Gemini LLM client wrapper |
| `src/rag/document_parser.py` | PDF/DOCX/TXT/MD parser |
| `src/rag/embedding.py` | Gemini embedding client + hash fallback |
| `src/rag/indexer.py` | Document chunking + ChromaDB indexing |
| `src/rag/retriever.py` | Basic vector similarity retrieval |
| `src/rag/qa_engine.py` | Basic RAG Q&A (retrieval + LLM) |
| `src/rag/query_rewriter.py` | **NEW**: LLM query expansion |
| `src/rag/hybrid_search.py` | **NEW**: Vector + BM25 hybrid search |
| `src/rag/reranker.py` | **NEW**: Result re-ranking |
| `src/rag/confidence_scorer.py` | **NEW**: Retrieval quality scoring |
| `src/rag/smart_chunker.py` | **NEW**: Semantic chunking |
| `src/rag/advanced_retriever.py` | **NEW**: Orchestrates all 5 optimizations |
| `src/rag/advanced_qa_engine.py` | **NEW**: Advanced Q&A with full pipeline |
| `frontend/index.html` | Single-page frontend UI |

---

## 5. Git History

| Commit | Description |
|--------|-------------|
| `b787fbb` | Initial RAG pipeline + frontend + accuracy testing |
| `233a01f` | Migrate LLM/Embedding from Hunyuan to Google Gemini |
| `7922d15` | Add advanced RAG retrieval pipeline (5 optimizations) |

**Remote**: `https://github.com/FENGFANCHEN-012/RydeResolve-Agent.git`
**Branch**: `main`

---

## 6. Known Issues & TODOs

### Current Limitations
1. **Chunking**: Still uses simple word-count splitting (500 words). Smart chunker exists but not integrated into indexer yet.
2. **BM25 Index**: Rebuilt on every search call (no caching). Should be rebuilt only on document changes.
3. **LLM Rerank**: Disabled by default (slow). Simple reranker is active.
4. **Query Rewrite**: Sometimes generates off-topic variants (e.g., "Amazon refund" for Ryde policy).

### Next Session Priorities
1. **Integrate Smart Chunker** into `indexer.py` - replace word-count with semantic boundary splitting
2. **Optimize BM25** - persist index, rebuild only on upload/delete
3. **Add query filtering** - detect and remove off-topic query variants
4. **Add re-ranking cache** - cache rerank scores for repeated queries
5. **Multi-language support** - test with Chinese/Malay queries
6. **Agent integration** - expose RAG as tool for dispute resolution agent
7. **Performance monitoring** - add latency metrics per pipeline stage

### Test Commands
```bash
# Start server
cd RydeResolve-Agent
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# Quick tests
curl http://localhost:8000/api/health
curl "http://localhost:8000/api/rag/search?query=refund&advanced=true"
curl -X POST http://localhost:8000/api/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the refund policy?"}'
```

---

## 7. Data & State

### ChromaDB Collection
- **Name**: `ryde_policies`
- **Location**: `./chroma_data/` (local persistent)
- **Chunks**: ~16 (depends on uploads)
- **Embedding**: 3072-dim Gemini vectors

### Uploaded Files
- `data/uploads/test_upload.txt` - test file
- `data/uploads/CHEN_FENG_FAN_Resume_AI_V8_Clean_Layout.pdf` - resume PDF
- `data/policies/*.md` - policy documents (auto-indexed on startup)

---

## 8. Dependencies

```
fastapi + uvicorn       # Web framework
chromadb                # Vector database
google-generativeai     # Gemini SDK
python-dotenv           # Env config
PyPDF2 + python-docx    # Document parsing
numpy                   # Vector math
```

---

## 9. Session Context for Next Session

**What was just done**: Completed advanced RAG pipeline with 5 optimization techniques. All tested and pushed to GitHub.

**Current state**: Server running on `localhost:8000`, Gemini API configured, 16 chunks indexed.

**Immediate next steps**:
1. Integrate smart chunker into indexer
2. Optimize BM25 index caching
3. Connect RAG as tool for dispute resolution agent

**Key decisions made**:
- Switched from Tencent Hunyuan to Google Gemini (better availability)
- ChromaDB local mode (no Docker needed)
- Advanced retrieval enabled by default on `/api/rag/ask`
