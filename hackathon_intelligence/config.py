import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory (Repo Relative)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# Centralized LLM Provider Config
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL

DEFAULT_OPENROUTER_MODEL = "openrouter/free"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL).strip() or DEFAULT_OPENROUTER_MODEL

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL

# Storage & Log Paths
LOG_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "research_cache.db"
LOG_FILE = LOG_DIR / "run_logs.jsonl"

# Hard Execution & Efficiency Limits
MAX_LLM_CALLS = 4
MAX_SEARCH_CALLS = 6
MAX_RESULTS_PER_SEARCH = 4
MAX_SELECTED_SOURCES = 15
MAX_SNIPPET_LENGTH = 350
