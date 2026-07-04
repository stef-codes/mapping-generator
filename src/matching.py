"""Mapping suggestion generation via Gemini."""

from __future__ import annotations

from typing import Callable

import pandas as pd

from src.ai_fallback import generate_gemini_suggestions, is_ai_available


def generate_suggestions(
    mapping_rows: pd.DataFrame,
    source_columns: list[str],
    progress_callback: Callable[[float], None] | None = None,
) -> pd.DataFrame:
    """Generate source-to-target mapping suggestions using Gemini only."""
    return generate_gemini_suggestions(
        mapping_rows,
        source_columns,
        progress_callback=progress_callback,
    )


__all__ = ["generate_suggestions", "is_ai_available"]
