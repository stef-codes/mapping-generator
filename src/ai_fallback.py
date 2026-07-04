"""Gemini-powered source-to-target column mapping."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from src.config import AI_BATCH_SIZE, GEMINI_API_KEY, GEMINI_MODEL
from src.similarity import resolve_column_reference

_PROMPT = """You are a data-mapping assistant. Map each TARGET FIELD to the best SOURCE COLUMN.

SOURCE COLUMNS (use exact names from this list only):
{source_columns}

TARGET FIELDS TO MAP (each needs one mapping):
{rows}

Return JSON only:
{{
  "mappings": [
    {{
      "target_field": "<exact target name from input>",
      "source_column": "<exact source column name, or empty string>",
      "category": "direct|hardcode|missing",
      "hardcode_value": "<only when category is hardcode>",
      "detail": "<short explanation>",
      "confidence": 0.95
    }}
  ]
}}

Rules:
- Return exactly one mapping per target field from the input.
- category "direct": copy data from source_column into target_field.
- category "hardcode": use hardcode_value; leave source_column empty.
- category "missing": only if no reasonable source column exists.
- If transformation notes say "Map from X", use source column X.
- If transformation notes say "Hardcode to Y", use category hardcode with value Y.
- Match semantically when names differ (e.g. start_datetime ← lease_start_date, external_key ← external_ref_id).
- When target name exactly matches a source column, map it directly.
- source_column must be copied exactly from the SOURCE COLUMNS list.
"""


class GeminiMappingError(RuntimeError):
    """Raised when the Gemini API call fails."""


@dataclass
class AiSuggestion:
    category: str
    source_column: str
    hardcode_value: str
    detail: str
    spec: dict
    confidence: float


def is_ai_available() -> bool:
    return bool(GEMINI_API_KEY)


def _pick_source_column(raw: dict, source_columns: list[str]) -> str:
    candidates = [
        raw.get("source_column"),
        raw.get("sourceColumn"),
        raw.get("source_col"),
    ]
    spec = raw.get("spec")
    if isinstance(spec, dict):
        candidates.append(spec.get("source_column"))

    for candidate in candidates:
        if not candidate:
            continue
        col, _ = resolve_column_reference(str(candidate), source_columns, threshold=0.5)
        if col:
            return col
    return ""


def _parse_note_mapping(notes: str, source_columns: list[str]) -> str | None:
    text = (notes or "").strip()
    if not text:
        return None

    hardcode_match = re.search(
        r"(?i)(?:hardcode|hard\s*code|constant|fixed\s*value|default)\s+(?:to\s+)?['\"]?([^'\";\n]+)['\"]?",
        text,
    )
    if hardcode_match:
        return None  # handled as hardcode category separately

    map_from = re.search(
        r"(?i)(?:map\s+from|source\s+(?:is|column)|from\s+column)\s+([A-Za-z_][A-Za-z0-9_]*)",
        text,
    )
    if map_from:
        col, _ = resolve_column_reference(map_from.group(1), source_columns, threshold=0.5)
        if col:
            return col
    return None


def _parse_note_hardcode(notes: str) -> str | None:
    text = (notes or "").strip()
    match = re.search(
        r"(?i)(?:hardcode|hard\s*code|constant|fixed\s*value|default)\s+(?:to\s+)?['\"]?([^'\";\n]+)['\"]?",
        text,
    )
    if match:
        return match.group(1).strip()
    return None


def _normalize_suggestion(
    raw: dict | None,
    item: dict,
    source_columns: list[str],
) -> AiSuggestion:
    if not isinstance(raw, dict):
        return _fallback_suggestion(item, source_columns, "Gemini returned no mapping")

    notes = str(item.get("notes", "") or "")
    note_hardcode = _parse_note_hardcode(notes)
    if note_hardcode:
        return AiSuggestion(
            category="hardcode",
            source_column="",
            hardcode_value=note_hardcode,
            detail=f"Hardcode from notes: {note_hardcode!r}",
            spec={"kind": "hardcode", "value": note_hardcode},
            confidence=0.95,
        )

    note_source = _parse_note_mapping(notes, source_columns)
    if note_source:
        return AiSuggestion(
            category="direct",
            source_column=note_source,
            hardcode_value="",
            detail=f"Mapped from notes: {note_source!r}",
            spec={"kind": "direct", "source_column": note_source},
            confidence=0.95,
        )

    category = str(raw.get("category", "direct")).strip().lower()
    if category not in {"direct", "hardcode", "missing"}:
        category = "direct"

    source_column = _pick_source_column(raw, source_columns)
    hardcode_value = str(raw.get("hardcode_value") or raw.get("hardcodeValue") or "").strip()
    detail = str(raw.get("detail", "") or "").strip() or "Gemini mapping"
    target = item.get("target_field", "")

    if category == "hardcode" and hardcode_value:
        return AiSuggestion(
            category="hardcode",
            source_column="",
            hardcode_value=hardcode_value,
            detail=detail,
            spec={"kind": "hardcode", "value": hardcode_value},
            confidence=_confidence(raw),
        )

    if not source_column and target:
        col, score = resolve_column_reference(target, source_columns, threshold=0.85)
        if col:
            source_column = col
            detail = f"Matched target {target!r} to source column {col!r}"
            return AiSuggestion(
                category="direct",
                source_column=source_column,
                hardcode_value="",
                detail=detail,
                spec={"kind": "direct", "source_column": source_column},
                confidence=max(_confidence(raw), round(score, 4)),
            )

    if source_column:
        return AiSuggestion(
            category="direct",
            source_column=source_column,
            hardcode_value="",
            detail=detail,
            spec={"kind": "direct", "source_column": source_column},
            confidence=_confidence(raw),
        )

    return _fallback_suggestion(item, source_columns, detail or "No source column matched")


def _confidence(raw: dict) -> float:
    try:
        value = float(raw.get("confidence", 0.75))
    except (TypeError, ValueError):
        value = 0.75
    return round(max(0.0, min(1.0, value)), 4)


def _fallback_suggestion(item: dict, source_columns: list[str], detail: str) -> AiSuggestion:
    target = item.get("target_field", "")
    notes = str(item.get("notes", "") or "")

    note_hardcode = _parse_note_hardcode(notes)
    if note_hardcode:
        return AiSuggestion(
            category="hardcode",
            source_column="",
            hardcode_value=note_hardcode,
            detail=f"Hardcode from notes: {note_hardcode!r}",
            spec={"kind": "hardcode", "value": note_hardcode},
            confidence=0.9,
        )

    note_source = _parse_note_mapping(notes, source_columns)
    if note_source:
        return AiSuggestion(
            category="direct",
            source_column=note_source,
            hardcode_value="",
            detail=f"Mapped from notes: {note_source!r}",
            spec={"kind": "direct", "source_column": note_source},
            confidence=0.9,
        )

    col, score = resolve_column_reference(target, source_columns, threshold=0.85)
    if col:
        return AiSuggestion(
            category="direct",
            source_column=col,
            hardcode_value="",
            detail=f"Name match: {target!r} → {col!r}",
            spec={"kind": "direct", "source_column": col},
            confidence=round(score, 4),
        )

    from src.similarity import best_source_match

    best_col, best_score = best_source_match(target, source_columns)
    if best_col and best_score >= 0.55:
        return AiSuggestion(
            category="direct",
            source_column=best_col,
            hardcode_value="",
            detail=f"Best semantic match: {target!r} → {best_col!r}",
            spec={"kind": "direct", "source_column": best_col},
            confidence=round(best_score, 4),
        )

    return AiSuggestion(
        category="missing",
        source_column="",
        hardcode_value="",
        detail=detail,
        spec={"kind": "missing"},
        confidence=0.0,
    )


def _extract_mappings(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    parsed = json.loads(text)
    if isinstance(parsed, dict):
        for key in ("mappings", "suggestions", "results"):
            if isinstance(parsed.get(key), list):
                return parsed[key]
        if "target_field" in parsed:
            return [parsed]
    if isinstance(parsed, list):
        return parsed
    raise ValueError("Gemini response is not a mappings list.")


def _call_gemini(prompt: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY)
    models_to_try = [GEMINI_MODEL, "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    seen: set[str] = set()
    errors: list[str] = []

    for model_name in models_to_try:
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            text = response.text or ""
            if text.strip():
                return text
        except Exception as exc:
            errors.append(f"{model_name}: {exc}")

    raise GeminiMappingError(
        "Gemini API failed for all models. " + " | ".join(errors[:3])
    )


def suggest_mappings_batch(
    items: list[dict],
    source_columns: list[str],
) -> tuple[list[AiSuggestion], str | None]:
    """Ask Gemini to map target fields to source columns."""
    if not items or not is_ai_available():
        return [_fallback_suggestion(item, source_columns, "AI unavailable") for item in items], None

    rows_payload = json.dumps(
        [
            {
                "target_field": item.get("target_field", ""),
                "data_type": item.get("data_type", ""),
                "notes": item.get("notes", ""),
                "required": item.get("required", False),
            }
            for item in items
        ],
        indent=2,
    )
    prompt = _PROMPT.format(
        source_columns=json.dumps(source_columns),
        rows=rows_payload,
    )

    try:
        raw_text = _call_gemini(prompt)
        parsed = _extract_mappings(raw_text)
    except Exception as exc:
        return (
            [_fallback_suggestion(item, source_columns, str(exc)) for item in items],
            str(exc),
        )

    by_target = {
        str(obj.get("target_field", "")).strip(): obj
        for obj in parsed
        if isinstance(obj, dict) and obj.get("target_field")
    }

    results: list[AiSuggestion] = []
    for idx, item in enumerate(items):
        target = str(item.get("target_field", "")).strip()
        raw = by_target.get(target)
        if raw is None and idx < len(parsed) and isinstance(parsed[idx], dict):
            raw = parsed[idx]
        results.append(_normalize_suggestion(raw, item, source_columns))

    return results, None


def _row_from_ai(item: dict, ai: AiSuggestion) -> dict:
    return {
        "target_field": item["target_field"],
        "required": item.get("required", False),
        "data_type": item.get("data_type", ""),
        "notes": item.get("notes", ""),
        "category": ai.category,
        "source_column": ai.source_column,
        "hardcode_value": ai.hardcode_value,
        "confidence": ai.confidence,
        "match_reason": "Gemini mapping suggestion (requires review)",
        "detail": ai.detail,
        "spec": json.dumps(ai.spec, sort_keys=True),
    }


def generate_gemini_suggestions(
    mapping_rows: pd.DataFrame,
    source_columns: list[str],
    progress_callback: Callable[[float], None] | None = None,
    batch_size: int = AI_BATCH_SIZE,
) -> pd.DataFrame:
    """Map all target fields via Gemini (sole mapping step)."""
    if not is_ai_available():
        raise ValueError(
            "GEMINI_API_KEY is required. Add it to .env (see .env.example)."
        )

    items = [
        {
            "target_field": row["target_field"],
            "required": bool(row["required"]),
            "data_type": row.get("data_type", ""),
            "notes": row.get("notes", ""),
        }
        for _, row in mapping_rows.iterrows()
    ]
    if not items:
        return pd.DataFrame()

    results: list[dict] = []
    errors: list[str] = []
    total = len(items)

    for start in range(0, total, batch_size):
        chunk = items[start : start + batch_size]
        ai_results, batch_error = suggest_mappings_batch(chunk, source_columns)
        if batch_error:
            errors.append(batch_error)

        for item, ai in zip(chunk, ai_results):
            results.append(_row_from_ai(item, ai))

        if progress_callback:
            progress_callback(min((start + len(chunk)) / total, 1.0))

    df = pd.DataFrame(results)
    if errors and not df.empty:
        df.attrs["gemini_errors"] = errors[:3]
    return df
