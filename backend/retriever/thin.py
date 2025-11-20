from __future__ import annotations

"""Simple deterministic retrieval for the lightweight ("thin") catalog."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set, Tuple

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - graceful degradation
    yaml = None

from backend.shared.normalize import (  # type: ignore[import]
    apply_synonyms,
    load_synonyms,
    normalize_query,
    tokenize,
)

_CANON_COMPOUND = {"haft", "grund"}
_PREFIX_BOOST_VALUE = 0.02
_SUBSTRING_BOOST_VALUE = 0.01
_SYNONYM_HIT_BONUS = 0.05
_COMPOUND_BONUS = 0.1
_RULES_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "shared" / "normalize" / "rules.yaml"


@dataclass(frozen=True)
class _CatalogEntry:
    sku: str
    name: str
    unit: str | None
    category: str | None
    metadata: Dict[str, object]


def search_catalog_thin(
    query: str,
    top_k: int,
    catalog_items: List[Dict[str, object]],
    synonyms_path: str | None = None,
) -> List[Dict[str, object]]:
    """Return at most *top_k* catalog candidates ranked by lexical similarity.

    The scoring is intentionally deterministic so the thin client can run pure
    Python retrieval locally without model dependencies.
    """

    if top_k <= 0:
        return []

    base_query_tokens = tokenize(query)
    if not base_query_tokens:
        return []

    synonyms = _load_synonyms_cached(synonyms_path)
    query_tokens = apply_synonyms(base_query_tokens, synonyms) if synonyms else set(base_query_tokens)
    synonym_only_tokens = query_tokens - base_query_tokens

    rulebook = _load_rules_cached()

    scored_items: List[Dict[str, object]] = []
    for item in catalog_items:
        entry = _to_catalog_entry(item)
        if entry is None:
            continue

        item_tokens = tokenize(entry.name)
        if synonyms:
            item_tokens = apply_synonyms(item_tokens, synonyms)

        if not _passes_token_gate(query_tokens, item_tokens):
            continue

        uom_passed, uom_reason = _passes_uom_filter(entry, rulebook)
        if not uom_passed:
            continue

        overlap = len(query_tokens & item_tokens)
        overlap_ratio = overlap / max(len(query_tokens), 1)
        reasons = [f"token overlap {overlap}/{len(query_tokens)}"]

        prefix_boost, prefix_reasons = _prefix_boost(query_tokens, item_tokens)
        if prefix_boost > 0:
            reasons.extend(prefix_reasons)

        score_lex = overlap_ratio + prefix_boost

        rule_bonus = 0.0
        synonym_matches = synonym_only_tokens & item_tokens
        if synonym_matches:
            bonus = _SYNONYM_HIT_BONUS * len(synonym_matches)
            rule_bonus += bonus
            reasons.append(
                f"synonym bonus +{bonus:.3f} via {', '.join(sorted(synonym_matches))}"
            )

        if _CANON_COMPOUND <= (query_tokens | item_tokens):
            rule_bonus += _COMPOUND_BONUS
            reasons.append("compound bonus +0.100 (haft+grund)")

        score_lex = round(score_lex, 3)
        rule_bonus = round(rule_bonus, 3)
        score_final = round(0.8 * score_lex + 0.2 * rule_bonus, 3)

        scored_items.append(
            {
                "sku": entry.sku,
                "name": entry.name,
                "unit": entry.unit,
                "category": entry.category,
                "score_final": score_final,
                "hard_filters_passed": True,
                "reasons": reasons,
            }
        )

    if scored_items:
        top_score = max(item["score_final"] for item in scored_items)
        if top_score < 0.55:
            q_join = normalize_query(query).replace(" ", "")
            for item in scored_items:
                name_join = normalize_query(item["name"]).replace(" ", "")
                if q_join and name_join and q_join in name_join:
                    item["score_final"] = round(item["score_final"] + 0.05, 3)

    scored_items.sort(key=lambda item: (-item["score_final"], item["name"].lower()))
    return scored_items[: min(top_k, len(scored_items))]


def _to_catalog_entry(raw: Dict[str, object]) -> _CatalogEntry | None:
    name = str(raw.get("name", "")).strip()
    if not name:
        return None
    sku = str(raw.get("sku", "")).strip() or name
    unit = raw.get("unit")
    category = raw.get("category")
    return _CatalogEntry(
        sku=sku,
        name=name,
        unit=str(unit) if unit is not None else None,
        category=str(category) if category is not None else None,
        metadata=raw,
    )


def _passes_token_gate(query_tokens: Set[str], item_tokens: Set[str]) -> bool:
    return bool(query_tokens & item_tokens)


def _prefix_boost(query_tokens: Set[str], item_tokens: Set[str]) -> Tuple[float, List[str]]:
    boost = 0.0
    reasons: List[str] = []
    for q_token in query_tokens:
        for item_token in item_tokens:
            if item_token == q_token:
                continue
            if item_token.startswith(q_token) and len(item_token) > len(q_token):
                boost += _PREFIX_BOOST_VALUE
                reasons.append(f"prefix match {q_token}->{item_token}")
            elif q_token.startswith(item_token) and len(q_token) > len(item_token):
                boost += _PREFIX_BOOST_VALUE
                reasons.append(f"prefix match {item_token}->{q_token}")
            elif q_token in item_token or item_token in q_token:
                boost += _SUBSTRING_BOOST_VALUE
                reasons.append(f"substring match {q_token}~{item_token}")
    return round(boost, 3), reasons


def _passes_uom_filter(entry: _CatalogEntry, rules: Dict[str, object]) -> Tuple[bool, str | None]:
    hard_filters = rules.get("hard_filters") if isinstance(rules, dict) else None
    uom_rules = None
    if isinstance(hard_filters, dict):
        uom_rules = hard_filters.get("uom_compatibility")
    if not isinstance(uom_rules, dict):
        return True, None

    category = (entry.category or "").lower()
    unit = (entry.unit or "").lower()
    allowed_units = uom_rules.get(category)
    if not isinstance(allowed_units, list):
        return True, None
    allowed_normalized = {normalize_query(str(u)) for u in allowed_units}
    if normalize_query(unit) in allowed_normalized:
        return True, None
    return False, f"unit '{entry.unit}' incompatible with category '{entry.category}'"


def _load_synonyms_cached(path: str | None) -> Dict[str, List[str]]:
    if not path:
        return {}
    resolved = str(Path(path).expanduser().resolve())
    return _synonym_cache(resolved)


@lru_cache(maxsize=4)
def _synonym_cache(resolved_path: str) -> Dict[str, List[str]]:
    return load_synonyms(resolved_path)


@lru_cache(maxsize=1)
def _load_rules_cached(path: str | None = None) -> Dict[str, object]:
    rules_path = Path(path).expanduser() if path else _RULES_DEFAULT_PATH
    if not rules_path.exists() or yaml is None:
        return {}
    data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
