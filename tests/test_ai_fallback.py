"""Gemini AI fallback tests."""

from __future__ import annotations

from unittest.mock import patch

from src.ai_fallback import AiSuggestion, _normalize_suggestion, enrich_missing_rows


def test_normalize_direct_suggestion():
    raw = {
        "category": "direct",
        "source_column": "facility_id",
        "hardcode_value": "",
        "detail": "Map to facility_id",
        "spec": {"kind": "direct", "source_column": "facility_id"},
        "confidence": 0.95,
    }
    result = _normalize_suggestion(raw, ["facility_id", "facility_name"])
    assert result is not None
    assert result.category == "direct"
    assert result.source_column == "facility_id"


def test_normalize_rejects_unknown_source_column():
    raw = {
        "category": "direct",
        "source_column": "not_a_column",
        "detail": "bad",
        "spec": {"kind": "direct", "source_column": "not_a_column"},
        "confidence": 0.9,
    }
    result = _normalize_suggestion(raw, ["facility_id"])
    assert result is not None
    assert result.category == "missing"


@patch("src.ai_fallback.suggest_mappings_batch")
def test_enrich_missing_rows(mock_batch):
    mock_batch.return_value = [
        AiSuggestion(
            category="direct",
            source_column="facility_name",
            hardcode_value="",
            detail="Gemini matched facility_name",
            spec={"kind": "direct", "source_column": "facility_name"},
            confidence=0.88,
        )
    ]
    rows = [
        {
            "target_field": "tenant_name",
            "required": False,
            "data_type": "",
            "notes": "",
            "category": "missing",
            "source_column": "",
            "hardcode_value": "",
            "confidence": 0.3,
            "match_reason": "No confident source match",
            "detail": "No rule-based match",
            "spec": '{"kind": "missing"}',
        }
    ]
    with patch("src.ai_fallback.is_ai_available", return_value=True):
        updated = enrich_missing_rows(rows, ["facility_id", "facility_name"])
    assert updated[0]["category"] == "direct"
    assert updated[0]["source_column"] == "facility_name"
    assert "Gemini" in updated[0]["match_reason"]
