"""Fuzzy matching engine for target fields to source columns."""

from __future__ import annotations

import json
from typing import Callable

import pandas as pd

from src.ai_fallback import enrich_missing_rows, is_ai_available
from src.config import DIRECT_MATCH_THRESHOLD
from src.detection import ParsedSpec, analyze_notes, parse_transformation_notes
from src.similarity import best_source_match


def classify_field(
    target_field: str,
    required: bool,
    data_type: str,
    notes: str,
    source_columns: list[str],
) -> dict:
    note_info = analyze_notes(notes)

    if note_info.is_lookup:
        spec = {
            "kind": "lookup",
            "lookup_target": note_info.lookup_target or "",
            "join_key": note_info.lookup_join_key or "",
            "reference": note_info.lookup_reference or "",
        }
        detail_parts = ["Lookup required"]
        if note_info.lookup_target:
            detail_parts.append(f"target={note_info.lookup_target}")
        if note_info.lookup_join_key:
            detail_parts.append(f"join on {note_info.lookup_join_key}")
        if note_info.lookup_reference:
            detail_parts.append(f"via {note_info.lookup_reference}")
        return _row(
            target_field=target_field,
            required=required,
            data_type=data_type,
            notes=notes,
            category="lookup",
            source_column=note_info.lookup_join_key or "",
            hardcode_value="",
            confidence=1.0,
            match_reason="Notes indicate lookup/join required",
            detail="; ".join(detail_parts),
            spec=json.dumps(spec, sort_keys=True),
        )

    if note_info.is_hardcode:
        spec = {"kind": "hardcode", "value": note_info.hardcode_value or ""}
        return _row(
            target_field=target_field,
            required=required,
            data_type=data_type,
            notes=notes,
            category="hardcode",
            source_column="",
            hardcode_value=note_info.hardcode_value or "",
            confidence=1.0 if note_info.hardcode_value else 0.5,
            match_reason="Hardcode detected in notes"
            + ("" if note_info.hardcode_value else " (value not parsed)"),
            detail=f"Hardcode value: {note_info.hardcode_value!r}"
            if note_info.hardcode_value
            else "Hardcode detected but value not parsed",
            spec=json.dumps(spec, sort_keys=True),
        )

    parsed = parse_transformation_notes(notes, source_columns)
    if parsed and parsed.kind == "conditional":
        primary_col = parsed.spec["branches"][0]["condition_column"]
        return _row_from_parsed(
            target_field,
            required,
            data_type,
            notes,
            category="conditional",
            parsed=parsed,
            source_column=primary_col,
            match_reason="Conditional logic parsed from notes",
        )

    if parsed and parsed.kind in ("concat", "date_format"):
        source_col = _primary_source_from_parsed(parsed)
        return _row_from_parsed(
            target_field,
            required,
            data_type,
            notes,
            category="derived",
            parsed=parsed,
            source_column=source_col or "",
            match_reason=f"Derived transformation ({parsed.kind}) parsed from notes",
        )

    source_col, score = best_source_match(target_field, source_columns)
    if score >= DIRECT_MATCH_THRESHOLD:
        spec = {"kind": "direct", "source_column": source_col or ""}
        return _row(
            target_field=target_field,
            required=required,
            data_type=data_type,
            notes=notes,
            category="direct",
            source_column=source_col or "",
            hardcode_value="",
            confidence=round(score, 4),
            match_reason=f"Fuzzy match to '{source_col}'",
            detail=f"Direct map from {source_col}",
            spec=json.dumps(spec, sort_keys=True),
        )

    return _row(
        target_field=target_field,
        required=required,
        data_type=data_type,
        notes=notes,
        category="missing",
        source_column=source_col or "",
        hardcode_value="",
        confidence=round(score, 4),
        match_reason="No confident source match"
        + (f" (best: '{source_col}' @ {score:.2f})" if source_col else ""),
        detail="No rule-based match" + ("; notes not parsed" if notes.strip() else ""),
        spec=json.dumps({"kind": "missing"}, sort_keys=True),
    )


def _primary_source_from_parsed(parsed: ParsedSpec) -> str | None:
    if parsed.kind == "concat":
        for token in parsed.spec.get("tokens", []):
            if token.get("type") == "column":
                return token["column"]
    if parsed.kind == "date_format":
        return parsed.spec.get("source_column")
    if parsed.kind == "conditional":
        branches = parsed.spec.get("branches", [])
        if branches:
            return branches[0].get("condition_column")
    return None


def _row_from_parsed(
    target_field: str,
    required: bool,
    data_type: str,
    notes: str,
    category: str,
    parsed: ParsedSpec,
    source_column: str,
    match_reason: str,
) -> dict:
    return _row(
        target_field=target_field,
        required=required,
        data_type=data_type,
        notes=notes,
        category=category,
        source_column=source_column,
        hardcode_value="",
        confidence=parsed.confidence,
        match_reason=match_reason,
        detail=parsed.detail,
        spec=parsed.to_json(),
    )


def _row(**kwargs) -> dict:
    return kwargs


def generate_suggestions(
    mapping_rows: pd.DataFrame,
    source_columns: list[str],
    progress_callback: Callable[[float], None] | None = None,
    use_ai: bool = False,
) -> pd.DataFrame:
    results = []
    total = len(mapping_rows)
    rules_total = total if not use_ai or not is_ai_available() else max(total - 1, 1)

    for position, (_, row) in enumerate(mapping_rows.iterrows(), start=1):
        results.append(
            classify_field(
                target_field=row["target_field"],
                required=bool(row["required"]),
                data_type=row.get("data_type", ""),
                notes=row.get("notes", ""),
                source_columns=source_columns,
            )
        )
        if progress_callback and rules_total:
            progress_callback(min(position / rules_total, 0.9))

    if use_ai and is_ai_available():
        if progress_callback:
            progress_callback(0.92)
        results = enrich_missing_rows(results, source_columns)
        if progress_callback:
            progress_callback(1.0)

    elif progress_callback and total:
        progress_callback(1.0)

    return pd.DataFrame(results)
