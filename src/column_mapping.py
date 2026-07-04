"""Auto-detect mapping document column headers."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

TARGET_PATTERNS: list[tuple[str, int]] = [
    (r"target\s*field", 10),
    (r"target\s*column", 9),
    (r"target\s*name", 9),
    (r"^field\s*name$", 8),
    (r"^column\s*name$", 8),
    (r"^target$", 8),
    (r"destination\s*(field|column|name)", 7),
    (r"output\s*(field|column|name)", 7),
    (r"^field$", 5),
    (r"^name$", 4),
]

REQUIRED_PATTERNS: list[tuple[str, int]] = [
    (r"^required$", 10),
    (r"required\s*flag", 9),
    (r"mandatory", 8),
    (r"^req$", 7),
    (r"is\s*required", 8),
]

DTYPE_PATTERNS: list[tuple[str, int]] = [
    (r"data\s*type", 10),
    (r"field\s*type", 9),
    (r"^dtype$", 8),
    (r"^type$", 6),
    (r"format", 5),
]

NOTES_PATTERNS: list[tuple[str, int]] = [
    (r"transformation\s*notes?", 10),
    (r"mapping\s*notes?", 9),
    (r"business\s*rule", 8),
    (r"^transformation$", 8),
    (r"^notes?$", 7),
    (r"transformation\s*logic", 9),
    (r"^logic$", 6),
    (r"^comment$", 5),
    (r"^description$", 5),
    (r"rule", 4),
]


@dataclass
class ColumnMapping:
    target_col: str
    required_col: str | None
    dtype_col: str | None
    notes_col: str | None

    def summary(self) -> str:
        parts = [f"target=`{self.target_col}`"]
        if self.required_col:
            parts.append(f"required=`{self.required_col}`")
        if self.dtype_col:
            parts.append(f"type=`{self.dtype_col}`")
        if self.notes_col:
            parts.append(f"notes=`{self.notes_col}`")
        return ", ".join(parts)


def _normalize_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def _score_header(header: str, patterns: list[tuple[str, int]]) -> int:
    norm = _normalize_header(header)
    if not norm:
        return 0
    return max(
        (weight for pattern, weight in patterns if re.search(pattern, norm)),
        default=0,
    )


def _best_column(
    columns: list[str],
    patterns: list[tuple[str, int]],
    exclude: set[str],
) -> str | None:
    best_col: str | None = None
    best_score = 0
    for col in columns:
        if col in exclude:
            continue
        score = _score_header(col, patterns)
        if score > best_score:
            best_score = score
            best_col = col
    return best_col if best_score > 0 else None


def guess_mapping_columns(mapping_df: pd.DataFrame) -> ColumnMapping:
    columns = list(mapping_df.columns)
    if not columns:
        raise ValueError("Mapping document has no columns.")

    target_col = _best_column(columns, TARGET_PATTERNS, exclude=set())
    if not target_col:
        target_col = columns[0]

    used = {target_col}
    required_col = _best_column(columns, REQUIRED_PATTERNS, used)
    if required_col:
        used.add(required_col)

    dtype_col = _best_column(columns, DTYPE_PATTERNS, used)
    if dtype_col:
        used.add(dtype_col)

    notes_col = _best_column(columns, NOTES_PATTERNS, used)

    return ColumnMapping(
        target_col=target_col,
        required_col=required_col,
        dtype_col=dtype_col,
        notes_col=notes_col,
    )
