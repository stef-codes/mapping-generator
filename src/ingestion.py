"""Load mapping documents and source CSV files."""

from __future__ import annotations

import re
from typing import BinaryIO

import pandas as pd

from src.column_mapping import (
    ColumnMapping,
    guess_vertical_columns,
    is_metadata_column_header,
    row_label_type,
    wide_target_column_headers,
)
from src.config import REQUIRED_TRUE_VALUES

_METADATA_TARGETS = frozenset(
    {
        "required",
        "yes",
        "no",
        "string",
        "int",
        "integer",
        "datetime",
        "date",
        "boolean",
        "bool",
        "map from",
        "hardcode to",
        "training",
        "transformation notes",
        "data type",
    }
)


def load_mapping_document(uploaded_file: BinaryIO, filename: str) -> pd.DataFrame:
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file, dtype=str)
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file, dtype=str)
    raise ValueError("Mapping document must be .xlsx or .csv")


def load_source_csv(uploaded_file: BinaryIO) -> pd.DataFrame:
    return pd.read_csv(uploaded_file, dtype=str, low_memory=False)


def parse_required(value: object) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    text = str(value).strip().lower()
    return bool(text) and text in REQUIRED_TRUE_VALUES


def build_mapping_rows(
    mapping_df: pd.DataFrame,
    target_col: str,
    required_col: str | None,
    dtype_col: str | None,
    notes_col: str | None,
) -> pd.DataFrame:
    rows = []
    for _, row in mapping_df.iterrows():
        target = row.get(target_col)
        if target is None or (isinstance(target, float) and pd.isna(target)):
            continue
        target = str(target).strip()
        if not target:
            continue

        required = parse_required(row.get(required_col)) if required_col else False
        data_type = ""
        if dtype_col and dtype_col in row.index:
            raw = row.get(dtype_col)
            if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
                data_type = str(raw).strip()

        notes = ""
        if notes_col and notes_col in row.index:
            raw = row.get(notes_col)
            if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
                notes = str(raw).strip()

        rows.append(
            {
                "target_field": target,
                "required": required,
                "data_type": data_type,
                "notes": notes,
            }
        )

    return pd.DataFrame(rows)


def _cell_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _targets_look_valid(targets: list[str]) -> bool:
    if not targets:
        return False
    valid = 0
    for target in targets:
        norm = re.sub(r"[^a-z0-9]+", " ", target.lower()).strip()
        if norm in _METADATA_TARGETS or len(norm) < 2:
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target):
            valid += 1
    return valid >= max(1, int(len(targets) * 0.5))


def _wide_target_columns(mapping_df: pd.DataFrame) -> list[str]:
    return wide_target_column_headers(mapping_df)


def build_mapping_rows_wide(mapping_df: pd.DataFrame) -> pd.DataFrame:
    """Parse wide layout: target field names are column headers (RowType label column)."""
    label_col = mapping_df.columns[0]
    rows = []

    for target_col in _wide_target_columns(mapping_df):
        target = _cell_text(target_col)
        if not target:
            continue

        required = False
        data_type = ""
        notes = ""

        for _, row in mapping_df.iterrows():
            label_kind = row_label_type(row.get(label_col))
            if label_kind == "required":
                required = parse_required(row.get(target_col))
            elif label_kind == "dtype":
                data_type = _cell_text(row.get(target_col))
            elif label_kind == "notes":
                notes = _cell_text(row.get(target_col))

        rows.append(
            {
                "target_field": target,
                "required": required,
                "data_type": data_type,
                "notes": notes,
            }
        )

    return pd.DataFrame(rows)


def _score_target_fields(targets: list[str]) -> int:
    score = 0
    for target in targets:
        norm = re.sub(r"[^a-z0-9]+", " ", target.lower()).strip()
        if norm in _METADATA_TARGETS or len(norm) < 2:
            continue
        if is_metadata_column_header(target):
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target):
            score += 1
    return score


def build_mapping_rows_auto(
    mapping_df: pd.DataFrame,
) -> tuple[pd.DataFrame, ColumnMapping]:
    vertical_mapping = guess_vertical_columns(mapping_df)
    vertical_rows = build_mapping_rows(
        mapping_df,
        vertical_mapping.target_col,
        vertical_mapping.required_col,
        vertical_mapping.dtype_col,
        vertical_mapping.notes_col,
    )
    wide_rows = build_mapping_rows_wide(mapping_df)
    vertical_score = _score_target_fields(vertical_rows["target_field"].tolist())
    wide_score = (
        _score_target_fields(wide_rows["target_field"].tolist())
        if not wide_rows.empty
        else 0
    )

    if wide_score > vertical_score and wide_score >= 2:
        mapping = ColumnMapping(
            target_col=str(mapping_df.columns[0]),
            required_col=None,
            dtype_col=None,
            notes_col=None,
            layout="wide",
        )
        rows = wide_rows
    else:
        mapping = vertical_mapping
        rows = vertical_rows

    if not _targets_look_valid(rows["target_field"].tolist()):
        if wide_score >= 2 and wide_score >= vertical_score:
            mapping = ColumnMapping(
                target_col=str(mapping_df.columns[0]),
                required_col=None,
                dtype_col=None,
                notes_col=None,
                layout="wide",
            )
            rows = wide_rows
        elif vertical_score >= 1:
            mapping = vertical_mapping
            rows = vertical_rows

    if rows.empty:
        raise ValueError("No target fields found in mapping document.")

    return rows, mapping
