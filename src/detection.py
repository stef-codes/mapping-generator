"""Transformation-note parsing: hardcode, lookup, concat, conditional, date format."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.config import CONCAT_COLUMN_THRESHOLD
from src.similarity import best_source_match, resolve_column_reference

HARDCODE_PATTERNS = re.compile(
    r"\b(hard\s*code|hardcode|constant|always\s+set\s+to|fixed\s+value|"
    r"default\s+to|set\s+to\s+['\"]|populate\s+with\s+['\"]|value\s+is\s+['\"])\b",
    re.IGNORECASE,
)

LOOKUP_PATTERNS = re.compile(
    r"\b(lookup|look\s*up|join\s+to|join\s+with|reference\s+table|ref\s+table|"
    r"foreign\s+key|\bfk\b|map\s+via|lookup\s+table|cross\s+reference|xref)\b",
    re.IGNORECASE,
)

QUOTED_VALUE = re.compile(r"""['"]([^'"]+)['"]""")
TRAILING_EQUALS = re.compile(r"=\s*['\"]?([^'\";\n]+)['\"]?\s*$", re.IGNORECASE)
TRAILING_TO = re.compile(r"\bto\s+['\"]?([^'\";\n]+)['\"]?\s*$", re.IGNORECASE)

LOOKUP_BY_RE = re.compile(
    r"\blookup\s+(\w+)\s+by\s+(\w+)\b", re.IGNORECASE
)
LOOKUP_VIA_RE = re.compile(
    r"\blookup\s+(\w+)\s+(?:via|from|in|against)\s+([\w.]+)\b", re.IGNORECASE
)
JOIN_ON_RE = re.compile(
    r"\bjoin\s+(?:to|with)\s+[\w.]+\s+(?:reference\s+table\s+)?on\s+(\w+)\b",
    re.IGNORECASE,
)

CONCAT_SPLIT = re.compile(r"\s*\+\s*")
QUOTED_TOKEN = re.compile(r"""^['"]([^'"]*)['"]$""")
IDENT_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DATE_FORMAT_RE = re.compile(
    r"(?i)\bformat(?:\s+the)?(?:\s+date)?(?:\s+column)?\s+(\w+)?"
    r".*?\bas\s+([YMDHmSs/\-\.:]+)\b"
)

BRANCH_RE = re.compile(
    r"(?is)(?:\bif|\belif)\s+(\w+)\s*=\s*(['\"]?)(.+?)\2\s+then\s+"
)

DATE_TOKEN_MAP = {
    "YYYY": "%Y",
    "YY": "%y",
    "MM": "%m",
    "DD": "%d",
    "HH": "%H",
    "mm": "%M",
    "SS": "%S",
}


@dataclass
class NoteAnalysis:
    is_hardcode: bool
    is_lookup: bool
    hardcode_value: str | None
    lookup_target: str | None = None
    lookup_join_key: str | None = None
    lookup_reference: str | None = None


@dataclass
class ParsedSpec:
    kind: str
    detail: str
    spec: dict
    confidence: float = 1.0

    def to_json(self) -> str:
        return json.dumps(self.spec, sort_keys=True)


def extract_hardcode_value(notes: str) -> str | None:
    if not notes:
        return None

    quoted = QUOTED_VALUE.findall(notes)
    if quoted:
        return quoted[-1].strip()

    for pattern in (TRAILING_EQUALS, TRAILING_TO):
        match = pattern.search(notes.strip())
        if match:
            value = match.group(1).strip()
            if value and not LOOKUP_PATTERNS.search(value):
                return value

    return None


def extract_lookup_detail(notes: str) -> tuple[str | None, str | None, str | None]:
    text = notes or ""
    by_match = LOOKUP_BY_RE.search(text)
    if by_match:
        return by_match.group(1), by_match.group(2), None

    via_match = LOOKUP_VIA_RE.search(text)
    if via_match:
        return via_match.group(1), None, via_match.group(2)

    on_match = JOIN_ON_RE.search(text)
    if on_match:
        return None, on_match.group(1), None

    return None, None, None


def analyze_notes(notes: str) -> NoteAnalysis:
    text = notes or ""
    is_lookup = bool(LOOKUP_PATTERNS.search(text))
    is_hardcode = bool(HARDCODE_PATTERNS.search(text)) and not is_lookup
    hardcode_value = extract_hardcode_value(text) if is_hardcode else None
    lookup_target, lookup_join_key, lookup_reference = extract_lookup_detail(text)
    return NoteAnalysis(
        is_hardcode=is_hardcode,
        is_lookup=is_lookup,
        hardcode_value=hardcode_value,
        lookup_target=lookup_target,
        lookup_join_key=lookup_join_key,
        lookup_reference=lookup_reference,
    )


def _parse_value_token(
    token: str, source_columns: list[str]
) -> tuple[dict | None, float]:
    token = token.strip()
    quoted = QUOTED_TOKEN.match(token)
    if quoted:
        return {"type": "literal", "value": quoted.group(1)}, 1.0

    if IDENT_TOKEN.match(token):
        col, score = resolve_column_reference(token, source_columns)
        if col:
            return {"type": "column", "column": col, "reference": token}, score

    return None, 0.0


def parse_concat(notes: str, source_columns: list[str]) -> ParsedSpec | None:
    text = (notes or "").strip()
    if "+" not in text:
        return None

    parts = CONCAT_SPLIT.split(text)
    if len(parts) < 2:
        return None

    tokens: list[dict] = []
    scores: list[float] = []
    has_column = False

    for part in parts:
        parsed, score = _parse_value_token(part, source_columns)
        if parsed is None:
            return None
        tokens.append(parsed)
        scores.append(score)
        if parsed["type"] == "column":
            has_column = True

    if not has_column:
        return None

    detail_parts = []
    for tok in tokens:
        if tok["type"] == "literal":
            detail_parts.append(f'"{tok["value"]}"')
        else:
            detail_parts.append(tok["column"])

    detail = "Concatenate: " + " + ".join(detail_parts)
    confidence = min(scores) if scores else 1.0
    return ParsedSpec(
        kind="concat",
        detail=detail,
        spec={"kind": "concat", "tokens": tokens},
        confidence=round(confidence, 4),
    )


def _normalize_condition_value(raw: str) -> str:
    value = raw.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _parse_result_value(
    raw: str, source_columns: list[str]
) -> tuple[dict, float]:
    value = raw.strip().rstrip(";.")
    quoted = QUOTED_TOKEN.match(value)
    if quoted:
        return {"type": "literal", "value": quoted.group(1)}, 1.0

    col, score = resolve_column_reference(value, source_columns)
    if col:
        return {"type": "column", "column": col, "reference": value}, score

    return {"type": "literal", "value": _normalize_condition_value(value)}, 1.0


def parse_conditional(notes: str, source_columns: list[str]) -> ParsedSpec | None:
    text = (notes or "").strip()
    if not re.search(r"\bif\b", text, re.IGNORECASE) or not re.search(
        r"\bthen\b", text, re.IGNORECASE
    ):
        return None

    else_match = re.search(r"\belse\s+(.+)\s*$", text, re.IGNORECASE)
    if not else_match:
        return None

    else_raw = else_match.group(1).strip()
    body = text[: else_match.start()].strip()

    branch_matches = list(BRANCH_RE.finditer(body))
    if not branch_matches:
        return None

    branches: list[dict] = []
    branch_scores: list[float] = []

    for idx, branch_match in enumerate(branch_matches):
        start = branch_match.end()
        end = (
            branch_matches[idx + 1].start()
            if idx + 1 < len(branch_matches)
            else len(body)
        )
        then_raw = body[start:end].strip()

        cond_col_ref = branch_match.group(1)
        cond_col, cond_col_score = resolve_column_reference(
            cond_col_ref, source_columns
        )
        if not cond_col:
            return None

        then_val, then_score = _parse_result_value(then_raw, source_columns)
        branches.append(
            {
                "condition_column": cond_col,
                "condition_reference": cond_col_ref,
                "condition_value": _normalize_condition_value(
                    branch_match.group(3).strip()
                ),
                "result": then_val,
            }
        )
        branch_scores.extend([cond_col_score, then_score])

    else_val, else_score = _parse_result_value(else_raw, source_columns)
    branch_scores.append(else_score)

    cond_summary = "; ".join(
        f"if {b['condition_reference']} = {b['condition_value']!r} then "
        f"{_result_summary(b['result'])}"
        for b in branches
    )
    detail = f"{cond_summary}; else {_result_summary(else_val)}"

    return ParsedSpec(
        kind="conditional",
        detail=detail,
        spec={
            "kind": "conditional",
            "branches": branches,
            "else": else_val,
        },
        confidence=round(min(branch_scores), 4),
    )


def _result_summary(result: dict) -> str:
    if result["type"] == "literal":
        return repr(result["value"])
    return result.get("column", result.get("reference", "?"))


def _format_to_strftime(fmt: str) -> str | None:
    remaining = fmt.strip()
    if not remaining:
        return None

    parts: list[str] = []
    i = 0
    while i < len(remaining):
        matched = False
        for token in sorted(DATE_TOKEN_MAP, key=len, reverse=True):
            if remaining[i:].startswith(token):
                parts.append(DATE_TOKEN_MAP[token])
                i += len(token)
                matched = True
                break
        if not matched:
            ch = remaining[i]
            if ch in "/-.:":
                parts.append(ch)
                i += 1
            else:
                return None
    return "".join(parts) if parts else None


def parse_date_format(notes: str, source_columns: list[str]) -> ParsedSpec | None:
    text = notes or ""
    match = DATE_FORMAT_RE.search(text)
    if not match:
        return None

    col_ref = match.group(1)
    format_pattern = match.group(2)
    strftime_fmt = _format_to_strftime(format_pattern)
    if not strftime_fmt:
        return None

    if col_ref:
        source_col, score = resolve_column_reference(col_ref, source_columns)
    else:
        source_col, score = best_source_match(
            notes.split()[0] if notes.split() else "", source_columns
        )
        if not source_col or score < CONCAT_COLUMN_THRESHOLD:
            source_col, score = None, 0.0

    if not source_col:
        for word in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text):
            if word.lower() in {"format", "the", "date", "column", "as"}:
                continue
            source_col, score = resolve_column_reference(word, source_columns)
            if source_col:
                col_ref = word
                break

    if not source_col:
        return None

    detail = f"Format {source_col} as {format_pattern} ({strftime_fmt})"
    return ParsedSpec(
        kind="date_format",
        detail=detail,
        spec={
            "kind": "date_format",
            "source_column": source_col,
            "source_reference": col_ref or source_col,
            "format_pattern": format_pattern,
            "strftime_format": strftime_fmt,
        },
        confidence=round(score, 4),
    )


def parse_transformation_notes(
    notes: str, source_columns: list[str]
) -> ParsedSpec | None:
    """Try note-driven parsers in priority order (excluding lookup/hardcode)."""
    for parser in (parse_conditional, parse_concat, parse_date_format):
        result = parser(notes, source_columns)
        if result:
            return result
    return None
