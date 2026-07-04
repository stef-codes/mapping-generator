"""Training schema mapping tests."""

from __future__ import annotations

from src.ai_fallback import _fallback_suggestion, _parse_note_hardcode, _parse_note_mapping


TRAINING_TARGETS = [
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

SOURCE_COLS = [
    "facility_id",
    "facility_name",
    "legacy_system_id",
    "property_type",
    "lease_start_date",
    "lease_end_date",
    "vendor_id",
    "manager_name",
    "unit_count",
    "is_active",
    "external_ref_id",
    "notes",
]


def test_parse_map_from_note():
    col = _parse_note_mapping("Map from legacy_system_id", SOURCE_COLS)
    assert col == "legacy_system_id"


def test_parse_hardcode_note():
    value = _parse_note_hardcode('Hardcode to Training')
    assert value == "Training"


def test_fallback_training_field_mappings():
    cases = [
        ("item_id", "Map from legacy_system_id", "direct", "legacy_system_id"),
        ("facility_id", "", "direct", "facility_id"),
        ("migration_notes", "Map from notes", "direct", "notes"),
    ]
    for target, notes, category, expected in cases:
        result = _fallback_suggestion(
            {"target_field": target, "notes": notes},
            SOURCE_COLS,
            "test",
        )
        assert result.category == category, target
        if category == "direct":
            assert result.source_column == expected, target
        else:
            assert result.hardcode_value == expected, target
