"""Load mapping documents and source CSV files."""

from __future__ import annotations

from typing import BinaryIO

import pandas as pd

from src.column_mapping import ColumnMapping, guess_mapping_columns
from src.config import REQUIRED_TRUE_VALUES


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


def build_mapping_rows_auto(
    mapping_df: pd.DataFrame,
) -> tuple[pd.DataFrame, ColumnMapping]:
    mapping = guess_mapping_columns(mapping_df)
    rows = build_mapping_rows(
        mapping_df,
        mapping.target_col,
        mapping.required_col,
        mapping.dtype_col,
        mapping.notes_col,
    )
    if rows.empty:
        raise ValueError(
            f"No target fields found in column `{mapping.target_col}`."
        )
    return rows, mapping
