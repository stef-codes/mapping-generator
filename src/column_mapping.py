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


LABEL_COLUMN_HEADERS = frozenset(
    {"rowtype", "row type", "field", "attribute", "label", "unnamed 0"}
)

SKIP_WIDE_TARGET_HEADERS = frozenset({"rowtype", "row type"})


@dataclass
class ColumnMapping:
    target_col: str
    required_col: str | None
    dtype_col: str | None
    notes_col: str | None
    layout: str = "vertical"

    def summary(self) -> str:
        parts = [f"layout={self.layout}"]
        if self.layout == "wide":
            parts.append(f"label_column=`{self.target_col}`")
        else:
            parts.append(f"target=`{self.target_col}`")
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


def row_label_type(value: object) -> str | None:
    """Classify a wide-format row label (required / dtype / notes)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    if _score_header(text, REQUIRED_PATTERNS) >= 7:
        return "required"
    if _score_header(text, DTYPE_PATTERNS) >= 6:
        return "dtype"
    if _score_header(text, NOTES_PATTERNS) >= 6:
        return "notes"
    return None


def looks_like_field_name(name: str) -> bool:
    norm = _normalize_header(name)
    if not norm or norm in SKIP_WIDE_TARGET_HEADERS:
        return False
    if norm in LABEL_COLUMN_HEADERS:
        return False
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", norm.replace(" ", "_")))


def is_metadata_column_header(name: str) -> bool:
    """True for Required / Data Type / Target Field-style headers, not data field names."""
    norm = _normalize_header(name)
    if not norm or norm in SKIP_WIDE_TARGET_HEADERS:
        return True
    if norm in LABEL_COLUMN_HEADERS:
        return True
    if _score_header(name, TARGET_PATTERNS) >= 5:
        return True
    if _score_header(name, REQUIRED_PATTERNS) >= 7:
        return True
    if _score_header(name, DTYPE_PATTERNS) >= 5:
        return True
    if _score_header(name, NOTES_PATTERNS) >= 4:
        return True
    if norm in {"source field", "source column", "source col", "source"}:
        return True
    return False


def wide_target_column_headers(mapping_df: pd.DataFrame) -> list[str]:
    """Column headers that are target field names in wide layout (not metadata columns)."""
    if mapping_df.empty or len(mapping_df.columns) < 2:
        return []
    return [
        str(col)
        for col in mapping_df.columns[1:]
        if _cell_text(col) and not is_metadata_column_header(str(col))
        and looks_like_field_name(str(col))
    ]


def _cell_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def is_wide_mapping_format(mapping_df: pd.DataFrame) -> bool:
    """True when target fields are column headers (RowType-style label column)."""
    if mapping_df.empty or len(mapping_df.columns) < 2:
        return False

    label_col = mapping_df.columns[0]
    labels = mapping_df[label_col].dropna().astype(str).str.strip()
    typed_count = int(labels.map(row_label_type).notna().sum()) if not labels.empty else 0
    wide_targets = wide_target_column_headers(mapping_df)

    if len(wide_targets) >= 2 and typed_count >= 2:
        return True

    label_header = _normalize_header(label_col)
    if label_header in LABEL_COLUMN_HEADERS and len(wide_targets) >= 2 and typed_count >= 1:
        return True

    return False


def guess_mapping_columns(mapping_df: pd.DataFrame) -> ColumnMapping:
    columns = list(mapping_df.columns)
    if not columns:
        raise ValueError("Mapping document has no columns.")

    target_col = _best_column(columns, TARGET_PATTERNS, exclude=set())
    has_vertical_target = bool(
        target_col and _score_header(target_col, TARGET_PATTERNS) >= 7
    )

    if not has_vertical_target and is_wide_mapping_format(mapping_df):
        return ColumnMapping(
            target_col=str(mapping_df.columns[0]),
            required_col=None,
            dtype_col=None,
            notes_col=None,
            layout="wide",
        )

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
        layout="vertical",
    )


def guess_vertical_columns(mapping_df: pd.DataFrame) -> ColumnMapping:
    """Detect vertical layout columns without considering wide format."""
    columns = list(mapping_df.columns)
    if not columns:
        raise ValueError("Mapping document has no columns.")

    target_col = _best_column(columns, TARGET_PATTERNS, exclude=set()) or columns[0]
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
        layout="vertical",
    )
