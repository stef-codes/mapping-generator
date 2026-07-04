"""Fuzzy name matching utilities (token-Jaccard + character-bigram)."""

from __future__ import annotations

import re
from typing import Callable

from src.config import BIGRAM_WEIGHT, CONCAT_COLUMN_THRESHOLD, TOKEN_WEIGHT


def normalize_name(name: str) -> str:
    text = name.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(name: str) -> set[str]:
    normalized = normalize_name(name)
    if not normalized:
        return set()
    tokens = set(normalized.split())
    expanded: set[str] = set()
    for token in tokens:
        expanded.add(token)
        parts = re.findall(r"[a-z]+|\d+", token)
        expanded.update(p for p in parts if len(p) > 1)
    return expanded


def char_bigrams(name: str) -> set[str]:
    normalized = normalize_name(name).replace(" ", "")
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[i : i + 2] for i in range(len(normalized) - 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def blended_similarity(target: str, source: str) -> float:
    token_score = jaccard(tokenize(target), tokenize(source))
    bigram_score = jaccard(char_bigrams(target), char_bigrams(source))
    return TOKEN_WEIGHT * token_score + BIGRAM_WEIGHT * bigram_score


def best_source_match(
    target: str, source_columns: list[str]
) -> tuple[str | None, float]:
    best_col: str | None = None
    best_score = 0.0
    for col in source_columns:
        score = blended_similarity(target, col)
        if score > best_score:
            best_score = score
            best_col = col
    return best_col, best_score


def resolve_column_reference(
    reference: str,
    source_columns: list[str],
    threshold: float = CONCAT_COLUMN_THRESHOLD,
) -> tuple[str | None, float]:
    ref = reference.strip()
    if not ref:
        return None, 0.0

    for col in source_columns:
        if col.lower() == ref.lower():
            return col, 1.0

    col, score = best_source_match(ref, source_columns)
    if col and score >= threshold:
        return col, score
    return None, score
