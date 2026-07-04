"""Codegen and export tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

from src.codegen import (
    apply_transform,
    generate_field_code,
    generate_transform_script_lines,
    parse_spec,
)
from src.export import (
    build_validation_report,
    generate_transform_script,
    generate_transformed_data_csv,
)

SOURCE_COLS = ["ActivityCode", "occupancy_status", "lease_start_date"]


def _sample_source_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ActivityCode": ["A1", "B2"],
            "occupancy_status": ["Active", "Inactive"],
            "lease_start_date": ["2024-01-15", "2023-06-01"],
        }
    )


def test_codegen_concat():
    spec = '{"kind": "concat", "tokens": [{"type": "literal", "value": "DT"}, {"type": "column", "column": "ActivityCode"}]}'
    lines = generate_field_code(
        "composite_key", "derived", "", "", '"DT" + ActivityCode', spec
    )
    assert len(lines) == 1
    assert "astype(str)" in lines[0]


def test_codegen_invalid_spec_falls_back_to_todo():
    lines = generate_field_code(
        "bad_field", "derived", "", "", "notes", "{not-json"
    )
    assert any("TODO" in line for line in lines)


def test_apply_transform_matches_generated_script():
    suggestions = pd.DataFrame(
        [
            {
                "target_field": "composite_key",
                "category": "derived",
                "source_column": "ActivityCode",
                "hardcode_value": "",
                "notes": '"DT" + ActivityCode',
                "spec": (
                    '{"kind": "concat", "tokens": ['
                    '{"type": "literal", "value": "DT"}, '
                    '{"type": "column", "column": "ActivityCode"}]}'
                ),
            },
            {
                "target_field": "active_flag",
                "category": "conditional",
                "source_column": "occupancy_status",
                "hardcode_value": "",
                "notes": 'if occupancy_status = Active then "Y" else "N"',
                "spec": (
                    '{"kind": "conditional", "branches": [{"condition_column": '
                    '"occupancy_status", "condition_reference": "occupancy_status", '
                    '"condition_value": "Active", "result": {"type": "literal", '
                    '"value": "Y"}}], "else": {"type": "literal", "value": "N"}}'
                ),
            },
            {
                "target_field": "country",
                "category": "hardcode",
                "source_column": "",
                "hardcode_value": "US",
                "notes": 'Hardcode to "US"',
                "spec": '{"kind": "hardcode", "value": "US"}',
            },
        ]
    )

    source_df = _sample_source_df()
    result = apply_transform(source_df, suggestions)
    assert list(result["composite_key"]) == ["DTA1", "DTB2"]
    assert list(result["active_flag"]) == ["Y", "N"]
    assert list(result["country"]) == ["US", "US"]


def test_generate_transformed_data_csv():
    suggestions = pd.DataFrame(
        [
            {
                "target_field": "facility_id",
                "category": "direct",
                "source_column": "ActivityCode",
                "hardcode_value": "",
                "notes": "",
                "spec": '{"kind": "direct", "source_column": "ActivityCode"}',
            }
        ]
    )
    csv_bytes = generate_transformed_data_csv(_sample_source_df(), suggestions)
    text = csv_bytes.decode("utf-8")
    assert "facility_id" in text.splitlines()[0]
    assert "A1" in text


def test_execute_generated_transform():
    suggestions = pd.DataFrame(
        [
            {
                "target_field": "composite_key",
                "category": "derived",
                "source_column": "ActivityCode",
                "hardcode_value": "",
                "notes": '"DT" + ActivityCode',
                "spec": (
                    '{"kind": "concat", "tokens": ['
                    '{"type": "literal", "value": "DT"}, '
                    '{"type": "column", "column": "ActivityCode"}]}'
                ),
            },
            {
                "target_field": "active_flag",
                "category": "conditional",
                "source_column": "occupancy_status",
                "hardcode_value": "",
                "notes": 'if occupancy_status = Active then "Y" else "N"',
                "spec": (
                    '{"kind": "conditional", "branches": [{"condition_column": '
                    '"occupancy_status", "condition_reference": "occupancy_status", '
                    '"condition_value": "Active", "result": {"type": "literal", '
                    '"value": "Y"}}], "else": {"type": "literal", "value": "N"}}'
                ),
            },
            {
                "target_field": "country",
                "category": "hardcode",
                "source_column": "",
                "hardcode_value": "US",
                "notes": 'Hardcode to "US"',
                "spec": '{"kind": "hardcode", "value": "US"}',
            },
        ]
    )

    script = generate_transform_script(suggestions)
    assert "np.where" in script
    assert "TODO" not in script.split("country")[1][:80]

    module_path = Path("_test_transform_exec.py")
    module_path.write_text(script, encoding="utf-8")
    try:
        spec = importlib.util.spec_from_file_location("test_transform", module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["test_transform"] = module
        spec.loader.exec_module(module)

        source_df = _sample_source_df()
        result = module.transform(source_df)
        assert list(result["composite_key"]) == ["DTA1", "DTB2"]
        assert list(result["active_flag"]) == ["Y", "N"]
        assert list(result["country"]) == ["US", "US"]
    finally:
        module_path.unlink(missing_ok=True)
        sys.modules.pop("test_transform", None)


def test_validation_flags_required_missing():
    suggestions = pd.DataFrame(
        [
            {
                "target_field": "missing_field",
                "required": True,
                "category": "missing",
                "confidence": 0.2,
                "source_column": "",
                "hardcode_value": "",
                "notes": "",
                "detail": "",
                "spec": '{"kind": "missing"}',
            }
        ]
    )
    report = build_validation_report(suggestions)
    assert "required_but_missing" in report.iloc[0]["issues"]


def test_parse_spec_invalid():
    assert parse_spec("{bad") is None
