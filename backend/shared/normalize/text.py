from __future__ import annotations

"""Normalization primitives shared between retrieval and dialogue pipelines."""

from functools import lru_cache
from pathlib import Path
import re
from typing import Dict, List, Set, Tuple

try:  # pragma: no cover - import guard
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    yaml = None

_RE_WHITESPACE = re.compile(r"\s+")
_RE_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_SUFFIXES = ("en", "er", "es", "e", "s", "n")
_LEXEME_SEEDS = ("haft", "grund", "tief", "farbe", "weiß", "grundierung", "isolier", "sperr")
_LEXEME_EXPANSIONS = {
    "grundierung": ("grund",),
}
_COMPOUND_WHITELIST = {
    "abdeckband",
    "abklebeband",
    "tiefgrund",
    "haftgrund",
    "putzgrund",
    "dispersionsfarbe",
    "fassadenfarbe",
    "kalkfarbe",
}


def normalize_query(text: str) -> str:
    """Return a deterministic, ASCII-friendly representation of *text* for matching.

    The procedure lowercases, replaces German umlauts/ß with their ASCII variants,
    strips non alpha-numeric characters (converted to spaces) and collapses
    duplicate whitespace. Empty or whitespace-only inputs yield an empty string.
    """

    if not text:
        return ""

    normalized = text.strip().lower()
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
    for char, repl in replacements.items():
        normalized = normalized.replace(char, repl)

    normalized = _RE_NON_ALNUM.sub(" ", normalized)
    normalized = _RE_WHITESPACE.sub(" ", normalized).strip()
    return normalized


def tokenize(text: str) -> Set[str]:
    """Tokenize *text* into a set of normalized tokens and simple stems.

    Steps:
    - normalize the text via :func:`normalize_query`
    - split on whitespace/non-alphanumeric boundaries
    - append naive stems by stripping configured suffixes (if result length >= 3)
    - extend with components derived from :func:`lemmatize_decompound`

    The returned set never contains empty strings.
    """

    normalized = normalize_query(text)
    if not normalized:
        return set()

    tokens: Set[str] = set()
    base_tokens = [tok for tok in _RE_WHITESPACE.split(normalized) if tok]
    tokens.update(base_tokens)

    for token in base_tokens:
        for suffix in _SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                tokens.add(token[: -len(suffix)])
        components = _match_components(token)
        for component, _, _ in components:
            tokens.add(component)
        # Combine adjacent components to capture frequent compounds like "haftgrund".
        for first_idx, first in enumerate(components):
            for second_idx in range(first_idx + 1, len(components)):
                second = components[second_idx]
                if first[2] == second[1]:
                    combined = first[0] + second[0]
                    if len(combined) >= 3:
                        tokens.add(combined)

    for i in range(len(base_tokens) - 1):
        pair = base_tokens[i] + base_tokens[i + 1]
        if pair in _COMPOUND_WHITELIST:
            tokens.add(pair)

    return {tok for tok in tokens if tok}


def lemmatize_decompound(text: str) -> List[str]:
    """Split German compounds in *text* using a greedy lexeme heuristic.

    - The text is segmented by camel-case boundaries before normalization.
    - Each segment is normalized with :func:`normalize_query`.
    - Segments are greedily matched against a curated lexeme list. Matches keep
      their relative order; duplicates are removed while preserving first
      occurrence.
    - Additional helper lexemes (``_LEXEME_EXPANSIONS``) add domain-specific
      stems such as ``grund`` derived from ``grundierung``.

    If a segment does not match any lexeme, its normalized form is emitted as a
    fallback to avoid empty outputs.
    """

    if not text:
        return []

    terms: List[str] = []
    seen: Set[str] = set()
    for segment in _split_on_capitals(text):
        normalized_segment = normalize_query(segment)
        if not normalized_segment:
            continue
        matches = _match_components(normalized_segment)
        if not matches:
            if normalized_segment not in seen:
                terms.append(normalized_segment)
                seen.add(normalized_segment)
            continue
        for term, _, _ in matches:
            if term not in seen:
                terms.append(term)
                seen.add(term)
    return terms


def load_synonyms(path: str) -> Dict[str, List[str]]:
    """Load and normalize a synonym mapping from *path*.

    The YAML schema is ``{canon: [syn1, syn2, ...]}``. All canonical keys and
    synonym entries are normalized via :func:`normalize_query`. Empty entries are
    ignored. When PyYAML is unavailable, a minimal parser for this schema is
    used.
    """

    content = Path(path).read_text(encoding="utf-8")
    entries: Dict[str, List[str]]
    if yaml is not None:
        loaded = yaml.safe_load(content) or {}
        if not isinstance(loaded, dict):
            raise ValueError("synonyms YAML must define a mapping")
        normalized_entries: Dict[str, List[str]] = {}
        for key, value in loaded.items():
            if value is None:
                values: List[str] = []
            elif isinstance(value, list):
                values = [str(item) for item in value]
            else:
                values = [str(value)]
            normalized_entries[str(key)] = values
        entries = normalized_entries
    else:
        entries = _parse_simple_synonym_yaml(content)

    normalized_map: Dict[str, List[str]] = {}
    for canon_raw, synonyms in entries.items():
        canon = normalize_query(canon_raw)
        if not canon:
            continue
        collected: List[str] = []
        for synonym in synonyms:
            normalized_syn = normalize_query(synonym)
            if normalized_syn:
                collected.append(normalized_syn)
        if collected:
            normalized_map[canon] = collected
    return normalized_map


def apply_synonyms(tokens: Set[str], synonyms: Dict[str, List[str]]) -> Set[str]:
    """Augment *tokens* with canonical forms derived from *synonyms* mapping."""

    if not tokens:
        return set()

    result = set(tokens)
    for canon, variants in synonyms.items():
        if any(token in result for token in variants):
            result.add(canon)
    return result


def _split_on_capitals(text: str) -> List[str]:
    segments: List[str] = []
    buffer = []
    for char in text:
        if buffer and char.isalpha() and char.isupper():
            segments.append("".join(buffer))
            buffer = [char]
        else:
            buffer.append(char)
    if buffer:
        segments.append("".join(buffer))
    return segments


def _match_components(token: str) -> List[Tuple[str, int, int]]:
    """Greedy lexeme matching that also injects configured expansions."""

    lexemes = _get_lexemes()
    matches: List[Tuple[str, int, int]] = []
    idx = 0
    while idx < len(token):
        found: Tuple[str, int, int] | None = None
        for lexeme in lexemes:
            if token.startswith(lexeme, idx):
                found = (lexeme, idx, idx + len(lexeme))
                break
        if found:
            matches.append(found)
            idx = found[2]
            continue
        idx += 1

    expanded: List[Tuple[str, int, int]] = []
    for term, start, end in matches:
        expanded.append((term, start, end))
        for extra in _LEXEME_EXPANSIONS.get(term, ()):  # type: ignore[arg-type]
            expanded.append((extra, start, start + len(extra)))

    ordered: List[Tuple[str, int, int]] = []
    seen_terms: Set[str] = set()
    for term, start, end in expanded:
        if term not in seen_terms:
            ordered.append((term, start, end))
            seen_terms.add(term)
    return ordered


@lru_cache(maxsize=1)
def _get_lexemes() -> Tuple[str, ...]:
    lexemes: List[str] = []
    for seed in _LEXEME_SEEDS:
        normalized = normalize_query(seed)
        if normalized and normalized not in lexemes:
            lexemes.append(normalized)
    lexemes.sort(key=len, reverse=True)
    return tuple(lexemes)


def _parse_simple_synonym_yaml(content: str) -> Dict[str, List[str]]:
    """Parse a subset of YAML supporting ``key:`` with ``- value`` lists."""

    mapping: Dict[str, List[str]] = {}
    current_key: str | None = None
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line.startswith(" ") and stripped.endswith(":"):
            current_key = stripped[:-1].strip()
            mapping[current_key] = []
            continue
        if stripped.startswith("- ") and current_key is not None:
            value = stripped[2:].strip()
            mapping[current_key].append(value)
    return mapping
