"""
FastAPI Entry Point
RydeResolve-Agent REST API service with RAG endpoints.
"""
import os
import io
import tempfile
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import CORS_ORIGINS, CHROMA_COLLECTION, BASE_DIR
from src.core.orchestrator import Orchestrator
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


class DisputeRequest(BaseModel):
    report_text: str
    order_id: str


class QARequest(BaseModel):
    question: str
    top_k: int = 5
    collection_name: str | None = None


# ============================================================
# Health & Root
# ============================================================

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


# ============================================================
# Multi-Agent Dispute Resolution (existing)
# ============================================================

@app.post("/api/disputes/resolve")
async def resolve_dispute(request: DisputeRequest):
    """Submit a dispute for automated resolution."""
    orchestrator = Orchestrator()
    result = await orchestrator.resolve(
        report_text=request.report_text,
        order_id=request.order_id,
    )
    return result

