"""Application constants and thresholds."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

_SECRET_KEYS = (
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "AI_BATCH_SIZE",
    "PREVIEW_ROW_LIMIT",
    "DB_DEV_CONNECTION_STRING",
    "DB_QA_CONNECTION_STRING",
)

_secrets_loaded = False

DIRECT_MATCH_THRESHOLD = 0.85
LOW_CONFIDENCE_THRESHOLD = 0.70
CONCAT_COLUMN_THRESHOLD = 0.60
DEFAULT_ROW_LIMIT = 1000
MAX_ROW_LIMIT = 10000
TOKEN_WEIGHT = 0.55
BIGRAM_WEIGHT = 0.45
CATEGORIES = ("direct", "derived", "hardcode", "conditional", "lookup", "missing")
REQUIRED_TRUE_VALUES = frozenset({"yes", "y", "true", "1", "required", "mandatory", "x"})


def _apply_streamlit_secrets() -> None:
    """Streamlit Community Cloud injects secrets via st.secrets, not .env."""
    try:
        import streamlit as st
        from streamlit.errors import StreamlitSecretNotFoundError

        try:
            secrets = st.secrets
        except StreamlitSecretNotFoundError:
            return
    except Exception:
        return
    for key in _SECRET_KEYS:
        try:
            if key in secrets:
                os.environ.setdefault(key, str(secrets[key]))
        except Exception:
            continue


def refresh_runtime_config() -> None:
    """Load Streamlit secrets (once) and refresh env-backed settings."""
    global _secrets_loaded, PREVIEW_ROW_LIMIT, GEMINI_API_KEY, GEMINI_MODEL, AI_BATCH_SIZE
    if not _secrets_loaded:
        _apply_streamlit_secrets()
        _secrets_loaded = True
    PREVIEW_ROW_LIMIT = int(os.getenv("PREVIEW_ROW_LIMIT", "500"))
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    AI_BATCH_SIZE = int(os.getenv("AI_BATCH_SIZE", "15"))


# Defaults from .env / process env only — Streamlit secrets applied lazily.
PREVIEW_ROW_LIMIT = int(os.getenv("PREVIEW_ROW_LIMIT", "500"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
AI_BATCH_SIZE = int(os.getenv("AI_BATCH_SIZE", "15"))
