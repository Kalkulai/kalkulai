"""Utility helpers for lightweight text normalization and synonym handling."""

from .text import (
    apply_synonyms,
    lemmatize_decompound,
    load_synonyms,
    normalize_query,
    tokenize,
)

__all__ = [
    "apply_synonyms",
    "lemmatize_decompound",
    "load_synonyms",
    "normalize_query",
    "tokenize",
]
