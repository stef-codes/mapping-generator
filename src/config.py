"""Application constants and thresholds."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DIRECT_MATCH_THRESHOLD = 0.85
LOW_CONFIDENCE_THRESHOLD = 0.70
CONCAT_COLUMN_THRESHOLD = 0.60
DEFAULT_ROW_LIMIT = 1000
MAX_ROW_LIMIT = 10000
TOKEN_WEIGHT = 0.55
BIGRAM_WEIGHT = 0.45
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
AI_BATCH_SIZE = int(os.getenv("AI_BATCH_SIZE", "15"))
AI_FALLBACK_ENABLED = bool(GEMINI_API_KEY)
CATEGORIES = ("direct", "derived", "hardcode", "conditional", "lookup", "missing")
REQUIRED_TRUE_VALUES = frozenset({"yes", "y", "true", "1", "required", "mandatory", "x"})
