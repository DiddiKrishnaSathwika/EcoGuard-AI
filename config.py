import os
from pathlib import Path
from dotenv import load_dotenv

# Project root
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")


def _bool(name, default="false"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# Application details
APP_NAME = "EcoGuard AI"
APP_DESCRIPTION = (
    "AI-powered Environmental Compliance Checker "
    "for Small and Medium Enterprises across India."
)

# OpenRouter configuration for text generation.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip() or None
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "").strip() or "openai/gpt-4.1-mini"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# OIDC settings are public identifiers, not credentials. The frontend client ID
# is configured separately with VITE_OIDC_CLIENT_ID.
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "").strip()
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "").strip()
OIDC_JWKS_URL = os.getenv("OIDC_JWKS_URL", "").strip()
AUTH_ADMIN_SUBJECTS = {
    subject.strip()
    for subject in os.getenv("AUTH_ADMIN_SUBJECTS", "").split(",")
    if subject.strip()
}

# Optional Google key used only by the optional Chroma embedding backend.
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or None
GEMINI_API_VERSION = "v1beta"

# LangSmith configuration (supports modern and older variable names)
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
LANGSMITH_TRACING = _bool("LANGSMITH_TRACING", os.getenv("LANGCHAIN_TRACING_V2", "false"))
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", os.getenv("LANGCHAIN_PROJECT", "EcoGuard-AI"))

# Backward compatibility
LANGCHAIN_API_KEY = LANGSMITH_API_KEY
LANGCHAIN_TRACING_V2 = str(LANGSMITH_TRACING)
LANGCHAIN_PROJECT = LANGSMITH_PROJECT

# Only enable tracing when a key is really present (avoids noisy 401 errors)
if LANGSMITH_TRACING and LANGSMITH_API_KEY:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = LANGSMITH_PROJECT
else:
    LANGSMITH_TRACING = False

# Retrieval backend: local BM25 (default) or ChromaDB + Google embeddings
USE_VECTOR_DB = _bool("USE_VECTOR_DB")
IS_VERCEL_RUNTIME = _bool("VERCEL")
FILE_STORAGE_BACKEND = os.getenv("FILE_STORAGE_BACKEND", "local").strip().lower()
if FILE_STORAGE_BACKEND not in ("local", "vercel_blob"):
    raise ValueError("FILE_STORAGE_BACKEND must be 'local' or 'vercel_blob'.")
if IS_VERCEL_RUNTIME and FILE_STORAGE_BACKEND != "vercel_blob":
    raise ValueError(
        "Vercel requires FILE_STORAGE_BACKEND=vercel_blob; local disk is not persistent."
    )
if IS_VERCEL_RUNTIME and USE_VECTOR_DB:
    raise ValueError(
        "USE_VECTOR_DB cannot use local Chroma persistence on Vercel; set USE_VECTOR_DB=false."
    )

# Server settings
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "15"))
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

# Project directories / files
DATA_DIR = BASE_DIR / "data"
REGULATIONS_DIR = DATA_DIR / "cached_regulations"
UPLOADS_DIR = DATA_DIR / "uploads"
SAMPLE_DIR = DATA_DIR / "sample_documents"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or None
DB_PATH = Path(os.getenv("ECOGUARD_DB_PATH", DATA_DIR / "ecoguard.db"))
KNOWLEDGE_BASE_FILE = DATA_DIR / "regulatory_knowledge_base.json"
VECTOR_DB_DIR = BASE_DIR / "vector_db"
REPORTS_DIR = BASE_DIR / "reports"


def validate_configuration():
    if not OPENROUTER_API_KEY:
        raise ValueError(
            "OpenRouter API key is missing. Add OPENROUTER_API_KEY to your .env file."
        )
    return True
