"""
RydeResolve-Agent Configuration
Centralized settings loaded from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# LLM Configuration
# ============================================================
# Uses OpenAI-compatible API format.
# Primary: Tencent Hunyuan / Fallback: OpenAI, Deepseek, etc.
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))

# Tencent Hunyuan (if using directly)
TENCENT_SECRET_ID = os.getenv("TENCENT_SECRET_ID", "")
TENCENT_SECRET_KEY = os.getenv("TENCENT_SECRET_KEY", "")
TENCENT_REGION = os.getenv("TENCENT_REGION", "ap-singapore")
HUNYUAN_API_URL = os.getenv("HUNYUAN_API_URL", "")
HUNYUAN_MODEL = os.getenv("HUNYUAN_MODEL", "hunyuan-pro")

# ============================================================
# Vector Database (ChromaDB)
# ============================================================
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8200"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "ryde_policies")

# Tencent VectorDB (optional alternative)
VECTORDB_API_URL = os.getenv("VECTORDB_API_URL", "")
VECTORDB_COLLECTION = os.getenv("VECTORDB_COLLECTION", "ryde_policies")

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
MAX_DEBATE_ROUNDS = int(os.getenv("MAX_DEBATE_ROUNDS", "3"))
CONFIDENCE_THRESHOLD_HIGH = float(os.getenv("CONFIDENCE_THRESHOLD_HIGH", "0.8"))
CONFIDENCE_THRESHOLD_LOW = float(os.getenv("CONFIDENCE_THRESHOLD_LOW", "0.5"))

# ============================================================
# API Settings
# ============================================================
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
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
