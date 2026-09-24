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
