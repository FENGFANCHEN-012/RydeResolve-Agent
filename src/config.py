"""
RydeResolve-Agent Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Tencent Cloud
TENCENT_SECRET_ID = os.getenv("TENCENT_SECRET_ID", "")
TENCENT_SECRET_KEY = os.getenv("TENCENT_SECRET_KEY", "")
TENCENT_REGION = os.getenv("TENCENT_REGION", "ap-singapore")

# Hunyuan LLM
HUNYUAN_API_URL = os.getenv("HUNYUAN_API_URL", "")
HUNYUAN_MODEL = os.getenv("HUNYUAN_MODEL", "hunyuan-pro")

# Vector Database (Tencent VectorDB)
VECTORDB_API_URL = os.getenv("VECTORDB_API_URL", "")
VECTORDB_COLLECTION = os.getenv("VECTORDB_COLLECTION", "ryde_policies")

# PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/ryde_resolve")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Agent Settings
MAX_DEBATE_ROUNDS = 3
CONFIDENCE_THRESHOLD_HIGH = 0.8
CONFIDENCE_THRESHOLD_LOW = 0.5

# Supported Languages (Singapore Official Languages)
SUPPORTED_LANGUAGES = ["en", "zh", "ms", "ta"]
