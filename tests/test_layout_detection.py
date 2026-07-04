"""Mapping document layout detection edge cases."""

from __future__ import annotations

import pandas as pd

from src.codegen import apply_transform, expected_output_columns
from src.ingestion import build_mapping_rows_auto


def test_rowtype_with_vertical_metadata_columns_not_wide_misfire():
    df = pd.DataFrame(
        [
            {
                "RowType": "",
                "Destination Field": "item_id",
                "Mandatory": "Yes",
                "Format": "string",
                "Rules": "Map from legacy_system_id",
            },
            {
                "RowType": "",
                "Destination Field": "item_title",
                "Mandatory": "Yes",
                "Format": "string",
                "Rules": "",
            },
        ]
    )
    rows, mapping = build_mapping_rows_auto(df)
    assert mapping.layout == "vertical"
    assert list(rows["target_field"]) == ["item_id", "item_title"]


def test_wide_training_spec_still_detected():
    df = pd.read_csv("sample_data/training_mapping_spec_wide.csv", dtype=str)
    rows, mapping = build_mapping_rows_auto(df)
    assert mapping.layout == "wide"
    assert "item_id" in rows["target_field"].tolist()
    assert "Required" not in rows["target_field"].tolist()


def test_transform_uses_mapping_targets_not_source_headers():
    mapping_rows, _ = build_mapping_rows_auto(
        pd.read_csv("sample_data/training_mapping_spec.csv", dtype=str)
    )
    source_df = pd.read_csv("sample_data/training_source_report.csv", dtype=str, nrows=2)
    suggestions = pd.DataFrame(
        [
            {
                "target_field": "item_id",
                "category": "direct",
                "source_column": "legacy_system_id",
                "hardcode_value": "",
                "notes": "",
                "spec": "{}",
            }
        ]
    )
    result = apply_transform(source_df, mapping_rows, suggestions)
    assert list(result.columns) == expected_output_columns(mapping_rows)
    assert "legacy_system_id" not in result.columns
    assert "property_type" not in result.columns
