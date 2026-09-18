"""
FastAPI Entry Point
RydeResolve-Agent REST API service.
"""
from fastapi import FastAPI
from pydantic import BaseModel

from src.core.orchestrator import Orchestrator

app = FastAPI(
    title="RydeResolve-Agent",
    description="Multi-Agent Dispute Resolution System for Ryde Platform",
    version="0.1.0",
)


class DisputeRequest(BaseModel):
    report_text: str
    order_id: str


@app.get("/")
async def root():
    return {
        "service": "RydeResolve-Agent",
        "status": "running",
        "competition": "Tencent Cloud AI CAN DO IT Hackathon Singapore 2026",
    }


@app.post("/api/disputes/resolve")
async def resolve_dispute(request: DisputeRequest):
    """Submit a dispute for automated resolution."""
    orchestrator = Orchestrator()
    result = await orchestrator.resolve(
        report_text=request.report_text,
        order_id=request.order_id,
    )
    return result


@app.get("/api/health")
async def health():
    return {"status": "healthy"}
