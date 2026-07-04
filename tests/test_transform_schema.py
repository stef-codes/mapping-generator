"""Transformed output uses mapping doc columns, not source columns."""

from __future__ import annotations

import pandas as pd

from src.codegen import apply_transform


def test_output_columns_follow_mapping_doc_not_source():
    source_df = pd.DataFrame(
        {
            "ActivityCode": ["A1", "B2"],
            "occupancy_status": ["Active", "Inactive"],
            "extra_source_col": ["x", "y"],
        }
    )
    mapping_rows = pd.DataFrame(
        [
            {"target_field": "my_target_a"},
            {"target_field": "my_target_b"},
            {"target_field": "unmapped_target"},
        ]
    )
    suggestions = pd.DataFrame(
        [
            {
                "target_field": "my_target_a",
                "category": "direct",
                "source_column": "ActivityCode",
                "hardcode_value": "",
                "notes": "",
                "spec": '{"kind": "direct", "source_column": "ActivityCode"}',
            },
            {
                "target_field": "my_target_b",
                "category": "hardcode",
                "source_column": "",
                "hardcode_value": "US",
                "notes": "",
                "spec": '{"kind": "hardcode", "value": "US"}',
            },
        ]
    )

    result = apply_transform(source_df, mapping_rows, suggestions)

    assert list(result.columns) == ["my_target_a", "my_target_b", "unmapped_target"]
    assert "ActivityCode" not in result.columns
    assert "extra_source_col" not in result.columns
    assert list(result["my_target_a"]) == ["A1", "B2"]
    assert list(result["my_target_b"]) == ["US", "US"]
    assert result["unmapped_target"].isna().all()
