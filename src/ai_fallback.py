"""Gemini-assisted mapping suggestions for rows rules cannot resolve."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.config import AI_BATCH_SIZE, CATEGORIES, GEMINI_API_KEY, GEMINI_MODEL

_PROMPT = """You are a data-mapping assistant. For each target field, suggest how to map it from the source report.

Source columns (use EXACT names from this list only):
{source_columns}

Return a JSON array with one object per input row, in the same order. Each object:
{{
  "category": "direct|derived|hardcode|conditional|lookup|missing",
  "source_column": "<exact source column name or empty string>",
  "hardcode_value": "<literal value or empty string>",
  "detail": "<plain English summary of the mapping>",
  "spec": {{<structured spec for code generation>}},
  "confidence": <0.0 to 1.0>
}}

Spec formats by category:
- direct: {{"kind":"direct","source_column":"..."}}
- hardcode: {{"kind":"hardcode","value":"..."}}
- derived concat: {{"kind":"concat","tokens":[{{"type":"literal","value":"..."}},{{"type":"column","column":"..."}}]}}
- derived date: {{"kind":"date_format","source_column":"...","strftime_format":"%Y-%m-%d"}}
- conditional: {{"kind":"conditional","branches":[{{"condition_column":"...","condition_reference":"...","condition_value":"...","result":{{"type":"literal","value":"..."}}}}],"else":{{"type":"literal","value":"..."}}}}
- lookup: {{"kind":"lookup","lookup_target":"...","join_key":"...","reference":"..."}}
- missing: {{"kind":"missing"}}

Rules:
- Prefer direct when a source column clearly matches the target field name.
- Only use columns from the provided source list.
- If unsure, use category "missing" with low confidence.
- Do not invent source columns.

Input rows:
{rows}
"""


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


def _resolve_source_column(name: str, source_columns: list[str]) -> str:
    if not name:
        return ""
    for col in source_columns:
        if col.lower() == name.strip().lower():
            return col
    return ""


def _normalize_suggestion(raw: dict, source_columns: list[str]) -> AiSuggestion | None:
    if not isinstance(raw, dict):
        return None

    category = str(raw.get("category", "missing")).strip().lower()
    if category not in CATEGORIES:
        category = "missing"

    source_column = _resolve_source_column(
        str(raw.get("source_column", "")), source_columns
    )
    hardcode_value = str(raw.get("hardcode_value", "") or "").strip()
    detail = str(raw.get("detail", "") or "").strip() or "Gemini suggestion"
    spec = raw.get("spec")
    if not isinstance(spec, dict):
        spec = {"kind": category if category != "derived" else "missing"}

    if category == "direct" and not source_column:
        category = "missing"
        spec = {"kind": "missing"}
    if category == "hardcode" and not hardcode_value:
        category = "missing"
        spec = {"kind": "missing"}

    try:
        confidence = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    return AiSuggestion(
        category=category,
        source_column=source_column,
        hardcode_value=hardcode_value,
        detail=detail,
        spec=spec,
        confidence=round(confidence, 4),
    )


def _extract_json_array(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if isinstance(parsed, dict) and "suggestions" in parsed:
        parsed = parsed["suggestions"]
    if not isinstance(parsed, list):
        raise ValueError("Gemini response is not a JSON array.")
    return parsed


def _call_gemini(prompt: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    return response.text or "[]"


def suggest_mappings_batch(
    items: list[dict],
    source_columns: list[str],
) -> list[AiSuggestion | None]:
    """Ask Gemini to suggest mappings for a batch of target fields."""
    if not items or not is_ai_available():
        return [None] * len(items)

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
        parsed = _extract_json_array(raw_text)
    except Exception:
        return [None] * len(items)

    results: list[AiSuggestion | None] = []
    for idx in range(len(items)):
        if idx < len(parsed):
            results.append(_normalize_suggestion(parsed[idx], source_columns))
        else:
            results.append(None)
    return results


def parse_notes(
    target_field: str,
    notes: str,
    source_columns: list[str],
    data_type: str = "",
    required: bool = False,
) -> AiSuggestion | None:
    """Single-row Gemini fallback."""
    results = suggest_mappings_batch(
        [
            {
                "target_field": target_field,
                "notes": notes,
                "data_type": data_type,
                "required": required,
            }
        ],
        source_columns,
    )
    return results[0] if results else None


def enrich_missing_rows(
    rows: list[dict],
    source_columns: list[str],
    batch_size: int = AI_BATCH_SIZE,
) -> list[dict]:
    """Apply Gemini suggestions to rule-based rows classified as missing."""
    if not is_ai_available():
        return rows

    missing_indices = [i for i, row in enumerate(rows) if row["category"] == "missing"]
    if not missing_indices:
        return rows

    updated = list(rows)
    for start in range(0, len(missing_indices), batch_size):
        chunk_indices = missing_indices[start : start + batch_size]
        items = [rows[i] for i in chunk_indices]
        ai_results = suggest_mappings_batch(items, source_columns)

        for row_idx, ai in zip(chunk_indices, ai_results):
            if not ai or ai.category == "missing":
                continue
            updated[row_idx] = {
                **rows[row_idx],
                "category": ai.category,
                "source_column": ai.source_column,
                "hardcode_value": ai.hardcode_value,
                "confidence": ai.confidence,
                "match_reason": "Gemini-assisted suggestion (requires review)",
                "detail": ai.detail,
                "spec": json.dumps(ai.spec, sort_keys=True),
            }

    return updated
