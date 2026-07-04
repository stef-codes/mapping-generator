"""Gemini mapping tests."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from src.ai_fallback import (
    AiSuggestion,
    _normalize_suggestion,
    generate_gemini_suggestions,
    suggest_mappings_batch,
)


def test_normalize_direct_suggestion():
    raw = {
        "target_field": "facility_id",
        "category": "direct",
        "source_column": "facility_id",
        "detail": "Map to facility_id",
        "confidence": 0.95,
    }
    item = {"target_field": "facility_id"}
    result = _normalize_suggestion(raw, item, ["facility_id", "facility_name"])
    assert result.category == "direct"
    assert result.source_column == "facility_id"


def test_normalize_fuzzy_source_column_name():
    raw = {
        "target_field": "facility_id",
        "category": "direct",
        "source_column": "Facility_ID",
        "detail": "match",
        "confidence": 0.9,
    }
    item = {"target_field": "facility_id"}
    result = _normalize_suggestion(raw, item, ["facility_id"])
    assert result.category == "direct"
    assert result.source_column == "facility_id"


def test_fallback_name_match_when_gemini_empty():
    item = {"target_field": "facility_name"}
    result = _normalize_suggestion(None, item, ["facility_id", "facility_name"])
    assert result.category == "direct"
    assert result.source_column == "facility_name"


@patch("src.ai_fallback._call_gemini")
def test_suggest_mappings_batch_by_target_field(mock_call):
    mock_call.return_value = """{
      "mappings": [
        {"target_field": "tenant_name", "source_column": "facility_name", "category": "direct", "detail": "best fit", "confidence": 0.8}
      ]
    }"""
    items = [{"target_field": "tenant_name", "data_type": "", "notes": "", "required": False}]
    results, error = suggest_mappings_batch(items, ["facility_id", "facility_name"])
    assert error is None
    assert results[0].source_column == "facility_name"


@patch("src.ai_fallback.suggest_mappings_batch")
def test_generate_gemini_suggestions(mock_batch):
    mock_batch.return_value = (
        [
            AiSuggestion(
                category="direct",
                source_column="facility_name",
                hardcode_value="",
                detail="Gemini matched facility_name",
                spec={"kind": "direct", "source_column": "facility_name"},
                confidence=0.88,
            )
        ],
        None,
    )
    mapping = pd.DataFrame(
        [{"target_field": "tenant_name", "required": False, "data_type": "", "notes": ""}]
    )
    with patch("src.ai_fallback.is_ai_available", return_value=True):
        result = generate_gemini_suggestions(mapping, ["facility_id", "facility_name"])
    assert len(result) == 1
    assert result.iloc[0]["category"] == "direct"
    assert result.iloc[0]["source_column"] == "facility_name"
