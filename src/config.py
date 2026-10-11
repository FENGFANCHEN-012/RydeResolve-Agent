"""
RydeResolve-Agent Configuration
Centralized settings loaded from environment variables.
"""
import os
from dotenv import load_dotenv

# Per-machine overrides precede the shared .env; explicit process variables still win.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env.local"))
load_dotenv()


# ============================================================
# LLM Configuration (Google Gemini)
# ============================================================
# Gemini API Key: https://aistudio.google.com/app/apikey
# Free-tier request limits vary by model and project; see AI Studio.
# Chat model: gemini-3.6-flash (fast, cheap)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.6-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
# gpt-oss reasoning effort for the Passenger / Driver advocates only ("low", "medium", "high").
# Empty = provider default. Their reasoning was ~1.3k output tokens per opening (D15); the Judge
# and Fairness are never lowered. Keep empty until an eval shows no accuracy loss.
ADVOCATE_REASONING_EFFORT = os.getenv("ADVOCATE_REASONING_EFFORT", "").strip().lower()
# Output budget of one rebuttal. gpt-oss counts its hidden reasoning in max_tokens: at 300, 18 of
# 108 rebuttals in run 20261001-203206 spent all 300 on reasoning and came back empty. The prompt
# still caps the text at 180 words; only tokens actually used are billed.
REBUTTAL_MAX_TOKENS = int(os.getenv("REBUTTAL_MAX_TOKENS", "1500"))

# Chat provider: "gemini" (default), "groq", "cerebras" or "hunyuan" (the last three use the
# OpenAI-compatible API). Embeddings never use this setting.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
CEREBRAS_BASE_URL = os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1")
# Tencent Hunyuan (hy3) through TokenHub's OpenAI-compatible API. The key is a TokenHub
# API key, not the TENCENTCLOUD_SECRET_ID/KEY pair used by the ADP scripts.
HUNYUAN_API_KEY = os.getenv("HUNYUAN_API_KEY", "")
HUNYUAN_MODEL = os.getenv("HUNYUAN_MODEL", "hy3")
HUNYUAN_BASE_URL = os.getenv("HUNYUAN_BASE_URL", "https://tokenhub-intl.tencentcloudmaas.com/v1")
# Backup providers, tried in order when a call to LLM_PROVIDER fails (e.g. "groq,cerebras").
# Empty = no fallback. Evals turn fallback off so one run never mixes models.
LLM_FALLBACK_PROVIDERS = [p.strip().lower() for p in os.getenv("LLM_FALLBACK_PROVIDERS", "").split(",")
                          if p.strip()]
# Paid-credit guard: the client refuses new calls once estimated spend in this
# process reaches the cap. Prices are USD per million tokens.
LLM_SPEND_CAP_USD = float(os.getenv("LLM_SPEND_CAP_USD", "1.00"))
LLM_PRICE_IN_PER_M = float(os.getenv("LLM_PRICE_IN_PER_M", "0.35"))
LLM_PRICE_OUT_PER_M = float(os.getenv("LLM_PRICE_OUT_PER_M", "0.75"))

# ============================================================
# Embedding Configuration (Google Gemini)
# ============================================================
# Embedding model: gemini-embedding-2 (3072 dimensions)
# Keep the embedding provider identical for indexing and retrieval. The local
# hash provider works even when LLM_API_KEY is set for dispute generation.
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "hash").strip().lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "3072"))

# ============================================================
# Vector Database (ChromaDB)
# ============================================================
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8200"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "ryde_policies")

# ============================================================
# Vector backend: "chroma" (local, default) or "qdrant" (Qdrant Cloud, shared)
# ============================================================
# Qdrant runs hybrid search (dense + BM25 sparse, fused with RRF). Both vectors
# are made locally by fastembed, so indexing and search use no API quota and
# give every teammate the same results.
VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "chroma").strip().lower()
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "ryde_policies")
QDRANT_DENSE_MODEL = os.getenv("QDRANT_DENSE_MODEL", "BAAI/bge-small-en-v1.5")
QDRANT_SPARSE_MODEL = os.getenv("QDRANT_SPARSE_MODEL", "Qdrant/bm25")

# ============================================================
# PostgreSQL
# ============================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ryde_resolve"
)

# ============================================================
# Redis
# ============================================================
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ============================================================
# Agent Settings
# ============================================================
# A single rebuttal round keeps one full dispute within a small daily quota.
# Set MAX_DEBATE_ROUNDS=3 explicitly when a larger request budget is available.
MAX_DEBATE_ROUNDS = int(os.getenv("MAX_DEBATE_ROUNDS", "1"))
# Triage (src/core/triage.py) may give complex cases more rounds: COMPLEX_MAX_ROUNDS, default 1.
# Reasoning effort for the Safety agent's LLM call (D24); the more careful the better here
SAFETY_REASONING_EFFORT = os.getenv("SAFETY_REASONING_EFFORT", "high").strip().lower()
# D33: the filer, when a draft ruling goes against them, may object once (rule + record, checked by code) and
# the Judge reconsiders. Off by default until measured; OBJECTION_ROUND=1 turns it on.
OBJECTION_ROUND = os.getenv("OBJECTION_ROUND", "0").strip().lower() in ("1", "true", "yes", "on")
CONFIDENCE_THRESHOLD_HIGH = float(os.getenv("CONFIDENCE_THRESHOLD_HIGH", "0.8"))
CONFIDENCE_THRESHOLD_LOW = float(os.getenv("CONFIDENCE_THRESHOLD_LOW", "0.5"))

# ============================================================
# API Settings
# ============================================================
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000"
).split(",")
# Wildcard access is unsuitable for a service that spends quota and edits records.
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS if origin.strip() and origin.strip() != "*"]

# ============================================================
# Supported Languages (Singapore Official Languages)
# ============================================================
SUPPORTED_LANGUAGES = os.getenv("SUPPORTED_LANGUAGES", "en,zh,ms,ta").split(",")

# ============================================================
# Paths
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
# POLICIES_DIR=data/policies/official indexes the verbatim official text instead
POLICIES_DIR = os.path.join(BASE_DIR, os.getenv("POLICIES_DIR") or os.path.join("data", "policies"))
MOCK_DISPUTES_DIR = os.path.join(DATA_DIR, "mock_disputes")
