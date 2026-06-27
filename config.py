"""
config.py — loads environment variables via python-dotenv and exposes
config values for the rest of the app.  All Azure vars are optional;
the app boots and matches without them.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ───────────────────────────────────────────────────────────────
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "course_reco.db")

# ── Flask ──────────────────────────────────────────────────────────────────
SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")

# ── Azure OpenAI (all optional — blank = use deterministic fallback) ───────
AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")


def azure_creds_available() -> bool:
    """Return True only when all four Azure variables are non-empty."""
    return all([
        AZURE_OPENAI_ENDPOINT,
        AZURE_OPENAI_API_KEY,
        AZURE_OPENAI_DEPLOYMENT,
        AZURE_OPENAI_API_VERSION,
    ])
