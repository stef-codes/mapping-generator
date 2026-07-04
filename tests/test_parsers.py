"""Parser unit tests."""

from __future__ import annotations

from src.detection import (
    analyze_notes,
    parse_concat,
    parse_conditional,
    parse_date_format,
    parse_transformation_notes,
)

SOURCE_COLS = [
    "facility_id",
    "ActivityCode",
    "lease_start_date",
    "occupancy_status",
    "region_code",
]


def test_hardcode_detection():
    info = analyze_notes('Hardcode to "US"')
    assert info.is_hardcode
    assert info.hardcode_value == "US"


def test_lookup_by_phrasing():
    info = analyze_notes("Lookup region_code by facility_id")
    assert info.is_lookup
    assert info.lookup_target == "region_code"
    assert info.lookup_join_key == "facility_id"


def test_concat_literal_plus_column():
    parsed = parse_concat('"DT" + ActivityCode', SOURCE_COLS)
    assert parsed is not None
    assert parsed.kind == "concat"
    assert parsed.spec["tokens"][0]["value"] == "DT"
    assert parsed.spec["tokens"][1]["column"] == "ActivityCode"


def test_concat_rejects_unresolved_column():
    assert parse_concat('"X" + UnknownCol', SOURCE_COLS) is None


def test_conditional_if_then_else():
    parsed = parse_conditional(
        'if occupancy_status = Active then "Y" else "N"', SOURCE_COLS
    )
    assert parsed is not None
    assert parsed.spec["branches"][0]["condition_column"] == "occupancy_status"
    assert parsed.spec["else"]["value"] == "N"


def test_conditional_requires_else():
    assert parse_conditional("if occupancy_status = Active then Y", SOURCE_COLS) is None


def test_date_format_parsing():
    parsed = parse_date_format(
        "Format lease_start_date as YYYY-MM-DD", SOURCE_COLS
    )
    assert parsed is not None
    assert parsed.spec["source_column"] == "lease_start_date"
    assert parsed.spec["strftime_format"] == "%Y-%m-%d"


def test_transformation_priority_conditional_over_concat():
    notes = 'if occupancy_status = Active then "A" else "B" + suffix'
    parsed = parse_transformation_notes(notes, SOURCE_COLS)
    assert parsed is not None
    assert parsed.kind == "conditional"
