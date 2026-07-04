"""Matching and classification tests."""

from __future__ import annotations

import pandas as pd

from src.matching import classify_field, generate_suggestions

SOURCE_COLS = ["facility_id", "facility_name", "ActivityCode", "lease_start_date"]


def test_direct_match():
    row = classify_field("facility_id", True, "string", "", SOURCE_COLS)
    assert row["category"] == "direct"
    assert row["source_column"] == "facility_id"


def test_derived_concat():
    row = classify_field(
        "composite_key",
        False,
        "string",
        '"DT" + ActivityCode',
        SOURCE_COLS,
    )
    assert row["category"] == "derived"
    assert "Concatenate" in row["detail"]


def test_lookup_beats_direct():
    row = classify_field(
        "region_name",
        False,
        "string",
        "Lookup region_code by facility_id",
        SOURCE_COLS,
    )
    assert row["category"] == "lookup"


def test_generate_suggestions_columns():
    mapping = pd.DataFrame(
        [
            {"target_field": "facility_id", "required": True, "data_type": "", "notes": ""},
            {
                "target_field": "country_code",
                "required": False,
                "data_type": "",
                "notes": 'Hardcode to "US"',
            },
        ]
    )
    result = generate_suggestions(mapping, SOURCE_COLS)
    assert "detail" in result.columns
    assert "spec" in result.columns
    assert set(result["category"]) >= {"direct", "hardcode"}
