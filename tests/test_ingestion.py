"""Ingestion and column-guessing tests."""

from __future__ import annotations

import pandas as pd

from src.column_mapping import guess_mapping_columns
from src.ingestion import build_mapping_rows_auto


def test_guess_sample_mapping_columns():
    df = pd.DataFrame(
        columns=[
            "Target Field",
            "Required",
            "Data Type",
            "Transformation Notes",
        ]
    )
    mapping = guess_mapping_columns(df)
    assert mapping.target_col == "Target Field"
    assert mapping.required_col == "Required"
    assert mapping.dtype_col == "Data Type"
    assert mapping.notes_col == "Transformation Notes"


def test_build_mapping_rows_auto():
    df = pd.DataFrame(
        [
            {
                "Target Field": "facility_id",
                "Required": "Yes",
                "Data Type": "string",
                "Transformation Notes": "",
            }
        ]
    )
    rows, mapping = build_mapping_rows_auto(df)
    assert len(rows) == 1
    assert rows.iloc[0]["target_field"] == "facility_id"
    assert rows.iloc[0]["required"]
    assert mapping.target_col == "Target Field"
    assert mapping.layout == "vertical"


def test_build_mapping_rows_wide_format():
    df = pd.read_csv(
        "sample_data/training_mapping_spec_wide.csv",
        dtype=str,
    )
    rows, mapping = build_mapping_rows_auto(df)
    assert mapping.layout == "wide"
    assert list(rows["target_field"]) == [
        "item_id",
        "item_title",
        "item_type",
        "start_datetime",
        "end_datetime",
        "facility_id",
        "facility_name",
        "training_contact_id",
        "instructor_user_id",
        "max_enrollments",
        "status",
        "external_key",
        "migration_notes",
    ]
    assert rows.loc[rows["target_field"] == "item_id", "notes"].iloc[0] == (
        "Map from legacy_system_id"
    )
    assert rows.loc[rows["target_field"] == "item_id", "required"].iloc[0]
