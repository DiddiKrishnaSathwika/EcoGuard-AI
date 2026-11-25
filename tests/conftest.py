import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Tests must never touch the real database.
os.environ["DATABASE_URL"] = ""
os.environ["ECOGUARD_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ.setdefault("TEST_DATABASE_URL", "")
os.environ.setdefault("ENABLE_DISPOSABLE_POSTGRES_TESTS", "")
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_API_KEY"] = ""
os.environ["LANGCHAIN_API_KEY"] = ""
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("OPENROUTER_API_KEY", None)
