"""Generate pandas transform code from structured mapping specs."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd


def parse_spec(spec_text: str) -> dict | None:
    if not str(spec_text).strip():
        return None
    try:
        return json.loads(spec_text)
    except (json.JSONDecodeError, TypeError):
        return None


def _expr_for_token(token: dict) -> str:
    if token.get("type") == "literal":
        return repr(str(token["value"]))
    return f"source_df[{token['column']!r}].astype(str)"


def _expr_for_result(result: dict) -> str:
    if result.get("type") == "literal":
        return repr(str(result["value"]))
    return f"source_df[{result['column']!r}]"


def _code_for_concat(target: str, spec: dict) -> list[str]:
    tokens = spec.get("tokens", [])
    if not tokens:
        return [
            f"    # TODO: invalid concat spec for {target!r}",
            f"    result[{target!r}] = None",
        ]
    parts = " + ".join(_expr_for_token(t) for t in tokens)
    return [f"    result[{target!r}] = {parts}"]


def _code_for_date_format(target: str, spec: dict) -> list[str]:
    col = spec.get("source_column")
    fmt = spec.get("strftime_format")
    if not col or not fmt:
        return [
            f"    # TODO: invalid date_format spec for {target!r}",
            f"    result[{target!r}] = None",
        ]
    return [
        f"    result[{target!r}] = pd.to_datetime("
        f"source_df[{col!r}], errors='coerce'"
        f").dt.strftime({fmt!r})"
    ]


def _code_for_conditional(target: str, spec: dict) -> list[str]:
    branches = spec.get("branches", [])
    else_result = spec.get("else")
    if not branches or else_result is None:
        return [
            f"    # TODO: invalid conditional spec for {target!r}",
            f"    result[{target!r}] = None",
        ]

    expr = _expr_for_result(else_result)
    for branch in reversed(branches):
        col = branch["condition_column"]
        value = branch["condition_value"]
        result_expr = _expr_for_result(branch["result"])
        expr = (
            f"np.where(source_df[{col!r}] == {value!r}, {result_expr}, {expr})"
        )

    return [f"    result[{target!r}] = {expr}"]


def generate_field_code(
    target: str,
    category: str,
    source_column: str,
    hardcode_value: str,
    notes: str,
    spec_text: str,
) -> list[str]:
    spec = parse_spec(spec_text)

    if category == "direct" and source_column:
        return [f"    result[{target!r}] = source_df[{source_column!r}]"]

    if category == "hardcode" and hardcode_value:
        return [f"    result[{target!r}] = {hardcode_value!r}"]

    if category == "hardcode":
        return [
            f"    # TODO: hardcode {target!r} — parse value from notes: {notes!r}",
            f"    result[{target!r}] = None",
        ]

    if category == "derived" and spec:
        kind = spec.get("kind")
        if kind == "concat":
            return _code_for_concat(target, spec)
        if kind == "date_format":
            return _code_for_date_format(target, spec)

    if category == "conditional" and spec and spec.get("kind") == "conditional":
        return _code_for_conditional(target, spec)

    if category == "lookup":
        detail = notes or "complete join/reference mapping"
        return [
            f"    # TODO: lookup {target!r} — {detail}",
            f"    result[{target!r}] = None",
        ]

    if spec:
        return [
            f"    # TODO: invalid or unsupported spec for {target!r}",
            f"    result[{target!r}] = None",
        ]

    return [
        f"    # TODO: missing mapping for {target!r}"
        + (f" — {notes}" if notes else ""),
        f"    result[{target!r}] = None",
    ]


def generate_transform_script_lines(suggestions) -> list[str]:
    """Build transform.py lines from a suggestions DataFrame or iterable of rows."""
    lines = [
        '"""Draft transform script — review and complete TODO items before use."""',
        "",
        "import pandas as pd",
        "",
        "",
        "def transform(source_df: pd.DataFrame) -> pd.DataFrame:",
        '    """Map source report columns to target schema."""',
        "    result = pd.DataFrame(index=source_df.index)",
        "",
    ]

    field_code: list[list[str]] = []
    needs_numpy = False

    for _, row in suggestions.iterrows():
        code = generate_field_code(
            target=row["target_field"],
            category=row["category"],
            source_column=str(row.get("source_column", "")).strip(),
            hardcode_value=str(row.get("hardcode_value", "")).strip(),
            notes=str(row.get("notes", "")).strip(),
            spec_text=str(row.get("spec", "")),
        )
        if any("np.where" in line for line in code):
            needs_numpy = True
        field_code.append(code)

    if needs_numpy:
        lines.insert(2, "import numpy as np")

    for code in field_code:
        lines.extend(code)
        lines.append("")

    lines.extend(["    return result", ""])
    return lines


def _empty_series(source_df: pd.DataFrame) -> pd.Series:
    return pd.Series(pd.NA, index=source_df.index, dtype="object")


def _result_series(source_df: pd.DataFrame, result: dict) -> pd.Series:
    if result.get("type") == "literal":
        return pd.Series(str(result["value"]), index=source_df.index, dtype="object")
    col = result.get("column", "")
    if col in source_df.columns:
        return source_df[col]
    return _empty_series(source_df)


def _apply_concat(source_df: pd.DataFrame, spec: dict) -> pd.Series:
    tokens = spec.get("tokens", [])
    if not tokens:
        return _empty_series(source_df)

    parts: list[pd.Series | str] = []
    for token in tokens:
        if token.get("type") == "literal":
            parts.append(str(token["value"]))
        else:
            col = token.get("column", "")
            if col not in source_df.columns:
                return _empty_series(source_df)
            parts.append(source_df[col].astype(str))

    combined = parts[0] if isinstance(parts[0], pd.Series) else pd.Series(
        parts[0], index=source_df.index, dtype="object"
    )
    for part in parts[1:]:
        if isinstance(part, pd.Series):
            combined = combined + part
        else:
            combined = combined + part
    return combined


def _apply_date_format(source_df: pd.DataFrame, spec: dict) -> pd.Series:
    col = spec.get("source_column")
    fmt = spec.get("strftime_format")
    if not col or not fmt or col not in source_df.columns:
        return _empty_series(source_df)
    return pd.to_datetime(source_df[col], errors="coerce").dt.strftime(fmt)


def _apply_conditional(source_df: pd.DataFrame, spec: dict) -> pd.Series:
    branches = spec.get("branches", [])
    else_result = spec.get("else")
    if not branches or else_result is None:
        return _empty_series(source_df)

    values = _result_series(source_df, else_result)
    for branch in reversed(branches):
        col = branch.get("condition_column", "")
        if col not in source_df.columns:
            return _empty_series(source_df)
        branch_values = _result_series(source_df, branch["result"])
        values = np.where(
            source_df[col].astype(str) == str(branch["condition_value"]),
            branch_values,
            values,
        )
    return pd.Series(values, index=source_df.index, dtype="object")


def apply_field_transform(source_df: pd.DataFrame, row) -> pd.Series:
    category = str(row.get("category", "")).strip()
    source_column = str(row.get("source_column", "")).strip()
    hardcode_value = str(row.get("hardcode_value", "")).strip()
    notes = str(row.get("notes", "")).strip()
    spec = parse_spec(str(row.get("spec", "")))

    if category == "direct" and source_column:
        if source_column in source_df.columns:
            return source_df[source_column]
        return _empty_series(source_df)

    if category == "hardcode" and hardcode_value:
        return pd.Series(hardcode_value, index=source_df.index, dtype="object")

    if category == "derived" and spec:
        kind = spec.get("kind")
        if kind == "concat":
            return _apply_concat(source_df, spec)
        if kind == "date_format":
            return _apply_date_format(source_df, spec)

    if category == "conditional" and spec and spec.get("kind") == "conditional":
        return _apply_conditional(source_df, spec)

    return _empty_series(source_df)


def build_mapped_output(
    source_df: pd.DataFrame,
    mapping_rows: pd.DataFrame,
    suggestions: pd.DataFrame,
) -> pd.DataFrame:
    """Build output with mapping-doc target columns filled from source data."""
    suggestion_by_target: dict[str, pd.Series] = {}
    for _, row in suggestions.iterrows():
        target = str(row.get("target_field", "")).strip()
        if target and target not in suggestion_by_target:
            suggestion_by_target[target] = row

    output: dict[str, pd.Series] = {}
    column_order: list[str] = []

    for _, mapping_row in mapping_rows.iterrows():
        target = str(mapping_row.get("target_field", "")).strip()
        if not target or target in output:
            continue

        column_order.append(target)
        suggestion = suggestion_by_target.get(target)
        output[target] = _values_for_target(source_df, target, suggestion)

    return pd.DataFrame(output, index=source_df.index)[column_order]


def _values_for_target(
    source_df: pd.DataFrame,
    target: str,
    suggestion: pd.Series | None,
) -> pd.Series:
    if suggestion is None:
        if target in source_df.columns:
            return source_df[target]
        return _empty_series(source_df)

    category = str(suggestion.get("category", "")).strip()
    source_column = str(suggestion.get("source_column", "")).strip()
    hardcode_value = str(suggestion.get("hardcode_value", "")).strip()

    if category in ("derived", "conditional"):
        return apply_field_transform(source_df, suggestion)

    if category == "hardcode" and hardcode_value:
        return pd.Series(hardcode_value, index=source_df.index, dtype="object")

    if category == "direct" and source_column and source_column in source_df.columns:
        return source_df[source_column]

    if source_column and source_column in source_df.columns:
        return source_df[source_column]

    if target in source_df.columns:
        return source_df[target]

    return apply_field_transform(source_df, suggestion)


def apply_transform(
    source_df: pd.DataFrame,
    mapping_rows: pd.DataFrame,
    suggestions: pd.DataFrame,
) -> pd.DataFrame:
    """Map source data into mapping-document target fields (not source column names)."""
    return build_mapped_output(source_df, mapping_rows, suggestions)


def expected_output_columns(mapping_rows: pd.DataFrame) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for _, row in mapping_rows.iterrows():
        target = str(row.get("target_field", "")).strip()
        if target and target not in seen:
            seen.add(target)
            columns.append(target)
    return columns


def transform_column_warnings(
    result: pd.DataFrame,
    mapping_rows: pd.DataFrame,
    source_df: pd.DataFrame,
) -> list[str]:
    """Return user-facing warnings when output columns look like source schema."""
    warnings: list[str] = []
    expected = expected_output_columns(mapping_rows)
    actual = list(result.columns)

    if expected and actual != expected:
        warnings.append(
            "Output columns do not match the mapping document field list. "
            f"Expected {len(expected)} mapping targets, got {len(actual)} columns."
        )

    if not expected:
        return warnings

    expected_set = set(expected)
    source_set = set(source_df.columns)
    overlap = expected_set & source_set
    extra_source_cols = [col for col in actual if col in source_set and col not in expected_set]

    if extra_source_cols:
        preview = ", ".join(extra_source_cols[:8])
        suffix = "…" if len(extra_source_cols) > 8 else ""
        warnings.append(
            "Output includes source report columns that are not mapping targets: "
            f"{preview}{suffix}. Re-upload the mapping document and confirm step 1 target fields."
        )

    if (
        len(expected) <= 30
        and len(actual) >= len(source_df.columns) * 0.8
        and len(overlap) >= len(expected) * 0.8
        and len(actual) > len(expected) + 3
    ):
        warnings.append(
            "Output looks like the full source schema instead of your mapping targets. "
            "Check step 1 — target fields should be names like item_id, not every source column."
        )

    return warnings
