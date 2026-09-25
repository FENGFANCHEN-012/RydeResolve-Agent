"""
RydeResolve-Agent Configuration
Centralized settings loaded from environment variables.
"""
import os
from dotenv import load_dotenv

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

# Chat provider: "gemini" (default) or "groq" (OpenAI-compatible API, free tier:
# https://console.groq.com/keys). Embeddings always use Gemini; Groq has none.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

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
CONFIDENCE_THRESHOLD_HIGH = float(os.getenv("CONFIDENCE_THRESHOLD_HIGH", "0.8"))
CONFIDENCE_THRESHOLD_LOW = float(os.getenv("CONFIDENCE_THRESHOLD_LOW", "0.5"))

# ============================================================
# API Settings
# ============================================================
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "*"
).split(",")

# ============================================================
# Supported Languages (Singapore Official Languages)
# ============================================================
SUPPORTED_LANGUAGES = os.getenv("SUPPORTED_LANGUAGES", "en,zh,ms,ta").split(",")

# ============================================================
# Paths
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
POLICIES_DIR = os.path.join(DATA_DIR, "policies")
MOCK_DISPUTES_DIR = os.path.join(DATA_DIR, "mock_disputes")
