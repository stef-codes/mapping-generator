"""Export mapping CSV, validation report, and draft transform.py."""

from __future__ import annotations

import re
from io import StringIO

import pandas as pd

from src.codegen import apply_transform, generate_transform_script_lines, parse_spec
from src.config import DIRECT_MATCH_THRESHOLD, LOW_CONFIDENCE_THRESHOLD

_TRANSFORM_NOTE_HINT = re.compile(
    r"(?i)(\+|\bif\b.*\belse\b|\bformat\b.*\bas\b)"
)


def _notes_suggest_transform(notes: str) -> bool:
    return bool(_TRANSFORM_NOTE_HINT.search(notes or ""))


def build_validation_report(suggestions: pd.DataFrame) -> pd.DataFrame:
    flags = []

    for _, row in suggestions.iterrows():
        issues: list[str] = []
        notes = str(row.get("notes", ""))
        category = row["category"]
        spec = parse_spec(str(row.get("spec", "")))

        if row["required"] and category == "missing":
            issues.append("required_but_missing")

        if category == "direct" and row["confidence"] < DIRECT_MATCH_THRESHOLD:
            issues.append("low_confidence_match")
        elif category == "direct" and row["confidence"] < 0.95:
            issues.append("review_match")

        if category == "hardcode" and not str(row.get("hardcode_value", "")).strip():
            issues.append("unresolved_hardcode")

        if category == "lookup":
            issues.append("lookup_manual_completion")
            if spec and not spec.get("join_key") and not spec.get("lookup_target"):
                issues.append("lookup_detail_incomplete")

        if category == "missing" and row["confidence"] >= LOW_CONFIDENCE_THRESHOLD:
            issues.append("possible_match_needs_review")

        if category in ("derived", "conditional") and spec is None:
            issues.append("invalid_spec_json")

        if category == "missing" and _notes_suggest_transform(notes):
            if re.search(r"\bif\b", notes, re.IGNORECASE):
                issues.append("unparsed_conditional_note")
            else:
                issues.append("unparsed_derived_note")

        if category == "conditional" and spec and spec.get("else") is None:
            issues.append("missing_else_default")

        if category == "derived" and spec and spec.get("kind") == "concat":
            for token in spec.get("tokens", []):
                if token.get("type") == "column" and not token.get("column"):
                    issues.append("unresolved_concat_token")

        if issues:
            flags.append(
                {
                    "target_field": row["target_field"],
                    "required": row["required"],
                    "category": category,
                    "confidence": row["confidence"],
                    "source_column": row.get("source_column", ""),
                    "detail": row.get("detail", ""),
                    "issues": "; ".join(dict.fromkeys(issues)),
                    "notes": notes,
                }
            )

    return pd.DataFrame(flags)


def generate_transform_script(suggestions: pd.DataFrame) -> str:
    return "\n".join(generate_transform_script_lines(suggestions))


def generate_transformed_data_csv(
    source_df: pd.DataFrame, suggestions: pd.DataFrame
) -> bytes:
    """Export source rows mapped into target-field columns."""
    transformed = apply_transform(source_df, suggestions)
    return dataframe_to_csv_bytes(transformed)


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")
