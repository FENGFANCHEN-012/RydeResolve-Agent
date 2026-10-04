"""
FastAPI Entry Point
RydeResolve-Agent REST API service with RAG endpoints.
"""
import os
import io
import re
import json
import asyncio
import tempfile
import shutil
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.config import CORS_ORIGINS, CHROMA_COLLECTION, BASE_DIR, DATA_DIR
from src.core.orchestrator import Orchestrator
from src.core.trace import Tracer, set_tracer
from src.rag.document_parser import document_parser
from src.rag.indexer import DocumentIndexer
from src.rag.retriever import DocumentRetriever
from src.rag.qa_engine import rag_qa_engine
from src.rag.advanced_qa_engine import advanced_rag_qa_engine
from src.rag.advanced_retriever import advanced_retriever
from src.rag.embedding import embedding_manager

app = FastAPI(
    title="RydeResolve-Agent",
    description="Multi-Agent Dispute Resolution System for Ryde Platform with RAG",
    version="0.2.0",
)

# CORS — allow all origins for local dev (includes file:// protocol)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Saved pipeline runs for replay (see /api/disputes/traces)
_running_tasks: set = set()


class EvidenceItem(BaseModel):
    evidence_type: str  # screenshot, photo, receipt, video, audio, document
    description: str
    file_url: str
    uploaded_by: str  # rider, driver


class DisputeRequest(BaseModel):
    report_text: str = ""  # "" = use the complaint from the order's dataset
    order_id: str
    reporter: str | None = None  # passenger or driver; None = use the dataset's
    evidence: list[EvidenceItem] = []
    language: str = "en"  # en, zh, ms, ta


class QARequest(BaseModel):
    question: str
    top_k: int = 5
    collection_name: str | None = None


# ============================================================
# Health & Root
# ============================================================

@app.on_event("startup")
async def warm_up_vector_store():
    """Open the ChromaDB client in the background so the first dispute doesn't
    freeze the server while the client is created."""
    from src.rag.indexer import _get_chroma_client

    task = asyncio.create_task(asyncio.to_thread(_get_chroma_client))
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)



@app.get("/")
async def root():
    return {
        "service": "RydeResolve-Agent",
        "status": "running",
        "competition": "Tencent Cloud AI CAN DO IT Hackathon Singapore 2026",
        "track": "Digital Native — Ryde",
        "features": ["multi-agent", "rag", "file-upload"],
    }


@app.get("/api/health")
async def health():
    return {"status": "healthy"}


# ============================================================
# RAG: File Upload & Document Management
# ============================================================

@app.post("/api/rag/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection_name: str | None = None,
):
    """
    Upload a single document file, parse it, chunk it, and index into vector DB.
    Supported formats: PDF, Word (.docx/.doc), PowerPoint (.pptx),
    Excel (.xlsx), TXT, Markdown, HTML.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in document_parser.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {ext}. "
                   f"Supported: {', '.join(sorted(document_parser.SUPPORTED_EXTENSIONS))}",
        )

    # Read file content in a thread to avoid blocking
    try:
        content_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    if not content_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    file_size_mb = len(content_bytes) / (1024 * 1024)

    # Parse document
    file_obj = io.BytesIO(content_bytes)
    try:
        text = document_parser.parse(file.filename, file_obj)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse {file.filename}: {str(e)}",
        )

    if not text or not text.strip():
        raise HTTPException(
            status_code=422,
            detail=f"No text content extracted from {file.filename}",
        )

    # Index into vector DB
    indexer = DocumentIndexer()
    try:
        chunk_count = indexer.index_file(
            filename=file.filename,
            content=text,
            file_type=ext,
            collection_name=collection_name,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Indexing failed for {file.filename}: {str(e)}",
        )

    # Also save original file to data/uploads for reference
    upload_dir = os.path.join(BASE_DIR, "data", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, file.filename)
    with open(save_path, "wb") as f:
        f.write(content_bytes)

    return {
        "status": "success",
        "filename": file.filename,
        "file_type": ext,
        "file_size_mb": round(file_size_mb, 2),
        "chunks_indexed": chunk_count,
        "text_length": len(text),
        "collection": collection_name or CHROMA_COLLECTION,
        "embedding_mode": embedding_manager.mode,
    }


@app.post("/api/rag/upload-multiple")
async def upload_multiple_documents(
    files: list[UploadFile] = File(...),
    collection_name: str | None = None,
):
    """Upload multiple documents at once."""
    results = []
    indexer = DocumentIndexer()

    for file in files:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in document_parser.SUPPORTED_EXTENSIONS:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": f"Unsupported format: {ext}",
            })
            continue

        try:
            content_bytes = await file.read()
        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": f"Read failed: {str(e)}",
            })
            continue

        if not content_bytes:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": "Empty file",
            })
            continue

        file_size_mb = len(content_bytes) / (1024 * 1024)
        file_obj = io.BytesIO(content_bytes)
        try:
            text = document_parser.parse(file.filename, file_obj)
            if not text or not text.strip():
                results.append({
                    "filename": file.filename,
                    "status": "error",
                    "error": "No text content extracted",
                })
                continue

            chunk_count = indexer.index_file(
                filename=file.filename,
                content=text,
                file_type=ext,
                collection_name=collection_name,
            )
            # Invalidate hybrid search index after new documents
            from src.rag.advanced_retriever import advanced_retriever
            advanced_retriever.invalidate_indexes()
            results.append({
                "filename": file.filename,
                "status": "success",
                "file_size_mb": round(file_size_mb, 2),
                "chunks_indexed": chunk_count,
                "text_length": len(text),
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": str(e),
            })

    total_chunks = sum(r.get("chunks_indexed", 0) for r in results)
    return {
        "total_files": len(files),
        "successful": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "total_chunks": total_chunks,
        "results": results,
    }


@app.get("/api/rag/stats")
async def rag_stats(collection_name: str | None = None):
    """Get knowledge base statistics."""
    indexer = DocumentIndexer()
    stats = indexer.get_collection_stats(collection_name)
    stats["embedding_mode"] = embedding_manager.mode
    return stats


@app.get("/api/rag/collections")
async def list_collections():
    """List all vector DB collections."""
    indexer = DocumentIndexer()
    return {"collections": indexer.list_collections()}


@app.delete("/api/rag/collection")
async def delete_collection(collection_name: str | None = None):
    """Delete a collection (clear all documents)."""
    indexer = DocumentIndexer()
    indexer.clear_collection(collection_name)
    return {"status": "deleted", "collection": collection_name or CHROMA_COLLECTION}


@app.get("/api/rag/search")
async def search_documents(
    query: str,
    top_k: int = 5,
    collection_name: str | None = None,
    advanced: bool = True,
):
    """Search the knowledge base and return matching chunks (no LLM generation)."""
    if advanced:
        retrieval = await advanced_retriever.retrieve(
            query=query,
            top_k=top_k,
            collection_name=collection_name,
        )
        return {
            "query": query,
            "top_k": top_k,
            "results": retrieval["results"],
            "total": len(retrieval["results"]),
            "confidence": retrieval["confidence"],
            "should_answer": retrieval["should_answer"],
            "metrics": retrieval["metrics"],
            "query_variants": retrieval["query_variants"],
        }
    else:
        retriever = DocumentRetriever()
        results = retriever.retrieve(
            query=query,
            top_k=top_k,
            collection_name=collection_name,
        )
        return {
            "query": query,
            "top_k": top_k,
            "results": results,
            "total": len(results),
        }


# ============================================================
# RAG: Question-Answering
# ============================================================

@app.post("/api/rag/ask")
async def rag_ask(request: QARequest, advanced: bool = True):
    """
    Ask a question and get a RAG-grounded answer.

    Flow: question → vector search → context assembly → LLM answer
    Set advanced=false to use basic retrieval (faster, less accurate).
    """
    try:
        if advanced:
            result = await advanced_rag_qa_engine.answer(
                question=request.question,
                top_k=request.top_k,
                collection_name=request.collection_name,
            )
        else:
            result = await rag_qa_engine.answer(
                question=request.question,
                top_k=request.top_k,
                collection_name=request.collection_name,
            )
        return result
    except Exception as e:
        # Catch any LLM / Gemini / internal error and return a graceful error
        # so the frontend gets a proper HTTP response (instead of an aborted connection).
        import traceback as _tb
        print(f"[rag_ask] EXCEPTION: {type(e).__name__}: {e}", flush=True)
        print(_tb.format_exc(), flush=True)
        err_type = type(e).__name__
        err_msg = str(e) or repr(e)
        # Detect Gemini quota errors specifically
        is_quota = (
            "quota" in err_msg.lower()
            or "ResourceExhausted" in err_type
            or "429" in err_msg
        )
        if is_quota:
            user_msg = (
                "LLM API quota exceeded (Gemini free tier is 20 requests/day). "
                "Please wait until tomorrow or switch to a paid API key in your .env (LLM_API_KEY)."
            )
        else:
            user_msg = f"{err_type}: {err_msg[:300]}"
        return JSONResponse(
            status_code=500,
            content={
                "answer": user_msg,
                "sources": [],
                "question": request.question,
                "confidence": 0.0,
                "should_answer": False,
                "error": user_msg,
                "error_type": err_type,
            },
        )


# ============================================================
# Multi-Agent Dispute Resolution
# ============================================================

@app.post("/api/disputes/resolve")
async def resolve_dispute(request: DisputeRequest):
    """
    Submit a dispute for automated resolution with full platform context.

    Fetches real order data from Ryde platform API including:
    - Trip details (pickup, dropoff, route, timing)
    - Payment/fare breakdown
    - In-app chat logs
    - GPS trace
    - Rider and driver profiles
    - Uploaded evidence (screenshots, photos, receipts)
    """
    orchestrator = Orchestrator()
    result = await orchestrator.resolve(
        report_text=request.report_text,
        order_id=request.order_id,
        reporter=request.reporter,
        evidence=request.evidence,
        language=request.language,
    )
    return result


@app.get("/api/disputes/cases")
async def list_dispute_cases():
    """Demo cases available on the (simulated) platform, for the dashboard picker."""
    from src.integrations.ryde_api import RydeAPIClient

    return {"cases": RydeAPIClient().list_orders()}


@app.get("/api/disputes/cases/{order_id}")
async def get_dispute_case(order_id: str):
    """
    One case for the dashboard: `dataset` is exactly what the agents receive
    (answer keys stripped); `expected_outcome` is the answer key, shown only
    for comparison after a run and never passed to any agent.
    """
    from src.integrations.ryde_api import RydeAPIClient, load_dispute_dataset

    api = RydeAPIClient()
    dataset = await api.get_order_dataset(order_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    raw = load_dispute_dataset(api._index[order_id])
    return {"order_id": order_id, "dataset": dataset,
            "expected_outcome": raw.get("expected_outcome")}


@app.post("/api/disputes/resolve-stream")
async def resolve_dispute_stream(request: DisputeRequest):
    """
    Same pipeline as /api/disputes/resolve, streamed as Server-Sent Events.

    Each agent step emits step_start / llm_call / step_end events (see
    src/core/trace.py), then a final `result` (or `error`) and `done`.
    The full trace is also saved to the record store so it can be replayed
    without spending LLM quota.
    """
    tracer = Tracer()

    async def run():
        set_tracer(tracer)  # only affects this task's context
        tracer.emit({"type": "run_start", "request": request.model_dump()})
        try:
            result = await Orchestrator().resolve(
                report_text=request.report_text,
                order_id=request.order_id,
                reporter=request.reporter,
                evidence=request.evidence,
                language=request.language,
            )
            tracer.emit({"type": "result", "result": result})
        except Exception as exc:
            tracer.emit({"type": "error", "message": str(exc)})
        finally:
            name = await asyncio.to_thread(_save_trace, request.order_id, tracer.events)
            tracer.emit({"type": "done", "trace_name": name})
            tracer.close()

    # Keep a reference so the task isn't garbage-collected mid-run
    task = asyncio.create_task(run())
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)

    async def event_stream():
        while True:
            event = await tracer.queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _save_trace(order_id: str, events: list[dict]) -> str | None:
    from src.store.db import get_store
    try:
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", order_id)
        name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{safe}.json"
        # Events can hold datetimes etc.; store them exactly as the stream sent them
        get_store().save_trace(name, order_id, json.loads(json.dumps(events, default=str)))
        return name
    except Exception:
        return None


@app.get("/api/disputes/traces")
async def list_traces():
    """Saved pipeline runs, newest first."""
    from src.store.db import get_store
    return {"traces": await asyncio.to_thread(get_store().list_trace_names, 50)}


@app.get("/api/disputes/traces/{name}")
async def get_trace(name: str):
    """One saved run's events, for replay in the dashboard."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.json", name):
        raise HTTPException(status_code=400, detail="Invalid trace name")
    from src.store.db import get_store
    events = await asyncio.to_thread(get_store().get_trace, name)
    if events is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {"name": name, "events": events}


@app.post("/api/disputes/resolve-with-files")
async def resolve_dispute_with_files(
    report_text: str,
    order_id: str,
    reporter: str = "passenger",
    language: str = "en",
    evidence_files: list[UploadFile] = File(default=[]),
):
    """
    Submit a dispute with evidence file uploads.

    Evidence files (screenshots, photos, receipts) are saved and their
    URLs are passed to the dispute resolution pipeline.
    """
    from src.agents.collector import EvidenceItem

    # Save uploaded evidence files
    evidence_items = []
    upload_dir = os.path.join(BASE_DIR, "data", "evidence", order_id)
    os.makedirs(upload_dir, exist_ok=True)

    for file in evidence_files:
        if not file.filename:
            continue
        content = await file.read()
        save_path = os.path.join(upload_dir, file.filename)
        with open(save_path, "wb") as f:
            f.write(content)

        evidence_items.append(EvidenceItem(
            evidence_type=_detect_evidence_type(file.filename),
            description=f"Uploaded evidence: {file.filename}",
            file_url=f"/data/evidence/{order_id}/{file.filename}",
            uploaded_by=reporter,
        ))

    orchestrator = Orchestrator()
    result = await orchestrator.resolve(
        report_text=report_text,
        order_id=order_id,
        reporter=reporter,
        evidence=evidence_items,
        language=language,
    )
    return result


def _detect_evidence_type(filename: str) -> str:
    """Detect evidence type from file extension."""
    ext = os.path.splitext(filename)[1].lower()
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    video_exts = {".mp4", ".mov", ".avi", ".mkv"}
    audio_exts = {".mp3", ".wav", ".m4a", ".ogg"}
    doc_exts = {".pdf", ".doc", ".docx", ".txt", ".md"}

    if ext in image_exts:
        return "photo" if "screenshot" not in filename.lower() else "screenshot"
    if ext in video_exts:
        return "video"
    if ext in audio_exts:
        return "audio"
    if ext in doc_exts:
        return "receipt" if "receipt" in filename.lower() or "invoice" in filename.lower() else "document"
    return "document"


@app.get("/api/disputes/order-context/{order_id}")
async def get_order_context(order_id: str):
    """
    Fetch full order context from Ryde platform API.

    Returns trip, payment, chat, GPS, profiles, and evidence for a given order.
    This is useful for previewing the data before submitting a dispute.
    """
    from src.integrations.ryde_api import RydeAPIClient

    api = RydeAPIClient()
    context = await api.get_full_order_context(order_id)

    if not context:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    # Convert Pydantic models to dicts for JSON serialization
    result = {}
    for key, value in context.items():
        if hasattr(value, "model_dump"):
            result[key] = value.model_dump()
        elif isinstance(value, list):
            result[key] = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in value
            ]
        else:
            result[key] = value

    return {"order_id": order_id, "context": result}



# ---------------------------------------------------------------------------
# Learning feedback loop: human review of rulings and the precedent lifecycle
# (src/store/feedback.py). Releasing staged precedents needs an evaluation run,
# so that step lives in scripts/precedents.py, not here.
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    reviewer: str
    action: str  # "confirm" or "override"
    reason: str
    final_verdict: str | None = None
    final_refund: float | None = None


class PrecedentAction(BaseModel):
    actor: str
    reason: str = ""


def _precedent_json(p) -> dict:
    return {k: getattr(p, k) for k in ("id", "dispute_id", "dispute_type", "verdict", "refund_amount", "principle",
                                      "ai_verdict", "status", "version", "approved_by", "gate_result",
                                      "created_at", "updated_at")}


@app.post("/api/rulings/{ruling_id}/review")
async def review_ruling(ruling_id: int, request: ReviewRequest):
    """A reviewer confirms or overrides a ruling. Overrides (and decisions on escalated
    cases) become pending precedents."""
    from src.store.db import get_store
    try:
        review, precedent = await asyncio.to_thread(
            get_store().submit_review, ruling_id, request.reviewer, request.action, request.reason,
            request.final_verdict, request.final_refund)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"review_id": review.id, "precedent": _precedent_json(precedent) if precedent else None}


@app.get("/api/precedents")
async def list_precedents(status: str | None = None):
    from src.store.db import get_store
    return [_precedent_json(p) for p in await asyncio.to_thread(get_store().list_precedents, status)]


@app.post("/api/precedents/{precedent_id}/approve")
async def approve_precedent(precedent_id: int, request: PrecedentAction):
    """Human approval: pending -> staged. It goes live only after the evaluation gate."""
    from src.rag.precedents import PrecedentIndex
    from src.store import feedback
    from src.store.db import get_store
    try:
        p = await asyncio.to_thread(feedback.approve, get_store(), PrecedentIndex(), precedent_id, request.actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _precedent_json(p)


@app.post("/api/precedents/{precedent_id}/retire")
async def retire_precedent(precedent_id: int, request: PrecedentAction):
    """Roll back a precedent: removed from the index, kept in the record."""
    from src.rag.precedents import PrecedentIndex
    from src.store import feedback
    from src.store.db import get_store
    if not request.reason.strip():
        raise HTTPException(status_code=400, detail="say why the precedent is retired")
    try:
        p = await asyncio.to_thread(feedback.retire, get_store(), PrecedentIndex(), precedent_id,
                                    request.actor, request.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _precedent_json(p)


@app.get("/api/audit/verify")
async def verify_audit():
    """Check the hash chain of the audit log (tamper evidence)."""
    from src.store.db import get_store
    ok, bad = await asyncio.to_thread(get_store().verify_audit_chain)
    return {"intact": ok, "first_bad_entry": bad}
