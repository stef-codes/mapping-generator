"""Matching suggestion tests."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from src.ai_fallback import AiSuggestion
from src.matching import generate_suggestions, is_ai_available


SOURCE_COLS = ["facility_id", "facility_name", "ActivityCode"]


@patch("src.matching.generate_gemini_suggestions")
def test_generate_suggestions_delegates_to_gemini(mock_gemini):
    mock_gemini.return_value = pd.DataFrame(
        [
            {
                "target_field": "facility_id",
                "required": True,
                "data_type": "string",
                "notes": "",
                "category": "direct",
                "source_column": "facility_id",
                "hardcode_value": "",
                "confidence": 0.95,
                "match_reason": "Gemini mapping suggestion (requires review)",
                "detail": "Direct map",
                "spec": '{"kind": "direct", "source_column": "facility_id"}',
            }
        ]
    )
    mapping = pd.DataFrame(
        [{"target_field": "facility_id", "required": True, "data_type": "", "notes": ""}]
    )
    result = generate_suggestions(mapping, SOURCE_COLS)
    mock_gemini.assert_called_once()
    assert result.iloc[0]["category"] == "direct"
    assert "detail" in result.columns


def test_is_ai_available_reexported():
    assert isinstance(is_ai_available(), bool)
