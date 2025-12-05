from __future__ import annotations

"""Simple deterministic retrieval for the lightweight ("thin") catalog.

Now includes Hybrid Search with BM25 + Lexical + RRF.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - graceful degradation
    yaml = None

from shared.normalize import (  # type: ignore[import]
    apply_synonyms,
    load_synonyms,
    normalize_query,
    tokenize,
)

# Try to import hybrid search (for upgraded search)
try:
    from retriever.hybrid_search import hybrid_search as _hybrid_search, invalidate_bm25_cache
    _HAS_HYBRID = True
except ImportError:
    _HAS_HYBRID = False
    _hybrid_search = None
    invalidate_bm25_cache = lambda: None

_CANON_COMPOUND = {"haft", "grund"}
_PREFIX_BOOST_VALUE = 0.02
_SUBSTRING_BOOST_VALUE = 0.01
_SYNONYM_HIT_BONUS = 0.15  # Increased from 0.05 - stronger synonym matching
_COMPOUND_BONUS = 0.1
_EXACT_MATCH_BONUS = 0.25  # Bonus for exact name matches
_PRICE_AVAILABLE_BONUS = 0.03  # Bonus if product has price
_KEYWORD_MATCH_BONUS = 0.15  # Bonus for critical keyword matches (krepp, tape, etc.)
_KEYWORD_MISMATCH_PENALTY = 0.3  # Penalty for confusing similar terms (krepp vs kreide)
_ROLE_SYNONYM_BOOST = 0.2  # Extra boost for rolle/farbrolle/fassadenrolle matches
_RULES_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "shared" / "normalize" / "rules.yaml"

# Critical keyword pairs that should NOT be confused
_CONFUSION_PAIRS = [
    ({"krepp", "kreppband", "malerkrepp", "abklebeband"}, {"kreide", "malerkreide"}),
    ({"grund", "grundierung", "tiefengrund"}, {"grund", "grundierung"}),  # No confusion here, but for future
]

# Pre-filtering: Exclude test products and inactive items
_TEST_SKU_PREFIXES = {"test-", "test_", "demo-", "demo_"}
_TEST_NAME_KEYWORDS = {"test", "demo", "beispiel", "sample"}


def _pre_filter_catalog(
    catalog_items: List[Dict[str, object]],
    category_filter: str | None = None,
) -> List[Dict[str, object]]:
    """Pre-filter catalog items to remove test products and apply category filter."""
    filtered = []
    
    # Detect category from common product types if not specified
    category_keywords = {
        "paint": {"farbe", "dispersionsfarbe", "latexfarbe", "wandfarbe", "fassadenfarbe"},
        "primer": {"grund", "grundierung", "tiefengrund", "haftgrund", "sperrgrund"},
        "tools": {"rolle", "pinsel", "werkzeug", "gerät", "leiter"},
        "tape": {"klebeband", "malerkrepp", "kreppband", "abklebeband"},
        "filler": {"spachtel", "spachtelmasse", "füller"},
    }
    
    for item in catalog_items:
        sku = str(item.get("sku", "")).lower()
        name = str(item.get("name", "")).lower()
        
        # Skip test products by SKU prefix
        if any(sku.startswith(prefix) for prefix in _TEST_SKU_PREFIXES):
            continue
        
        # Skip test products by name
        name_tokens = set(name.split())
        if name_tokens & _TEST_NAME_KEYWORDS:
            continue
        
        # Skip inactive products
        is_active = item.get("is_active")
        if is_active is not None and not is_active:
            continue
        
        # Apply category filter if specified
        if category_filter:
            item_category = str(item.get("category", "")).lower()
            if item_category and item_category != category_filter.lower():
                continue
        
        filtered.append(item)
    
    return filtered


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
    category_filter: str | None = None,
    use_hybrid: bool = True,  # NEW: Enable hybrid search by default
) -> List[Dict[str, object]]:
    """Return at most *top_k* catalog candidates ranked by similarity.

    Uses Hybrid Search (BM25 + Lexical + RRF) when available, falls back to
    lexical-only search otherwise.
    
    Args:
        query: Search query string
        top_k: Maximum number of results to return
        catalog_items: List of product dictionaries
        synonyms_path: Optional path to synonyms file
        category_filter: Optional category to filter by (e.g. "paint", "primer")
        use_hybrid: Whether to use hybrid search (BM25 + Lexical + RRF)
    """

    if top_k <= 0:
        return []

    base_query_tokens = tokenize(query)
    if not base_query_tokens:
        return []
    
    # Pre-filter catalog items (remove test products, inactive items, wrong categories)
    filtered_items = _pre_filter_catalog(catalog_items, category_filter)
    
    # Try Hybrid Search first (BM25 + Lexical + RRF)
    if use_hybrid and _HAS_HYBRID and _hybrid_search:
        try:
            hybrid_results = _hybrid_search(
                query=query,
                catalog_items=filtered_items,
                top_k=top_k * 2,  # Get more candidates for better ranking
                synonyms_path=synonyms_path,
            )
            if hybrid_results:
                # Convert hybrid results to expected format
                return [
                    {
                        "sku": r.get("sku"),
                        "name": r.get("name"),
                        "unit": r.get("unit"),
                        "category": r.get("category"),
                        "score_final": r.get("score_final", 0.0),
                        "hard_filters_passed": True,
                        "reasons": ["hybrid_search (BM25 + Lexical + RRF)"],
                    }
                    for r in hybrid_results[:top_k]
                ]
        except Exception:
            pass  # Fall back to lexical search

    # Fallback: Lexical-only search
    synonyms = _load_synonyms_cached(synonyms_path)
    query_tokens = apply_synonyms(base_query_tokens, synonyms) if synonyms else set(base_query_tokens)
    synonym_only_tokens = query_tokens - base_query_tokens

    rulebook = _load_rules_cached()

    scored_items: List[Dict[str, object]] = []
    for item in filtered_items:  # Use pre-filtered items
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
        
        # SPECIAL: Extra boost for rolle/farbrolle/fassadenrolle matches
        rolle_keywords = {"rolle", "farbrolle", "malerrolle", "fassadenrolle"}
        query_has_rolle = bool(query_tokens & rolle_keywords)
        item_has_rolle = bool(item_tokens & rolle_keywords)
        if query_has_rolle and item_has_rolle:
            rule_bonus += _ROLE_SYNONYM_BOOST
            reasons.append(f"rolle synonym boost +{_ROLE_SYNONYM_BOOST:.3f}")

        if _CANON_COMPOUND <= (query_tokens | item_tokens):
            rule_bonus += _COMPOUND_BONUS
            reasons.append("compound bonus +0.100 (haft+grund)")

        # EXACT MATCH BONUS: Boost products with exact name matches
        query_normalized = normalize_query(query).replace(" ", "")
        name_normalized = normalize_query(entry.name).replace(" ", "")
        if query_normalized and name_normalized and query_normalized == name_normalized:
            rule_bonus += _EXACT_MATCH_BONUS
            reasons.append(f"exact match bonus +{_EXACT_MATCH_BONUS:.3f}")
        elif query_normalized and name_normalized and query_normalized in name_normalized:
            partial_bonus = _EXACT_MATCH_BONUS * 0.4
            rule_bonus += partial_bonus
            reasons.append(f"partial match bonus +{partial_bonus:.3f}")
        
        # SIZE/SPECIFICATION MATCH: Boost if size specifications match (25cm, 10L, etc.)
        import re
        size_pattern = r'(\d+(?:\.\d+)?)\s*(cm|mm|l|liter|kg|m)'
        query_sizes = set(re.findall(size_pattern, query.lower()))
        name_sizes = set(re.findall(size_pattern, entry.name.lower()))
        if query_sizes and name_sizes and query_sizes & name_sizes:
            size_match_bonus = 0.1
            rule_bonus += size_match_bonus
            reasons.append(f"size specification match +{size_match_bonus:.3f}")

        # PRICE AVAILABLE BONUS: Prefer products with pricing
        if _has_price(item):
            rule_bonus += _PRICE_AVAILABLE_BONUS
            reasons.append(f"price available +{_PRICE_AVAILABLE_BONUS:.3f}")

        # KEYWORD MATCH BONUS: Boost critical keywords (krepp, tape, etc.)
        query_lower = query.lower()
        name_lower = entry.name.lower()
        critical_keywords = {"krepp", "kreppband", "malerkrepp", "abklebeband", "tape", "klebeband"}
        for keyword in critical_keywords:
            if keyword in query_lower and keyword in name_lower:
                rule_bonus += _KEYWORD_MATCH_BONUS
                reasons.append(f"critical keyword match '{keyword}' +{_KEYWORD_MATCH_BONUS:.3f}")
                break  # Only count once
        
        # KEYWORD MISMATCH PENALTY: Penalize confusing matches (krepp vs kreide)
        for positive_set, negative_set in _CONFUSION_PAIRS:
            query_has_positive = any(kw in query_lower for kw in positive_set)
            query_has_negative = any(kw in query_lower for kw in negative_set)
            name_has_positive = any(kw in name_lower for kw in positive_set)
            name_has_negative = any(kw in name_lower for kw in negative_set)
            
            if query_has_positive and name_has_negative:
                rule_bonus -= _KEYWORD_MISMATCH_PENALTY
                reasons.append(f"keyword mismatch penalty -{_KEYWORD_MISMATCH_PENALTY:.3f} (query has {positive_set}, product has {negative_set})")
            elif query_has_negative and name_has_positive:
                rule_bonus -= _KEYWORD_MISMATCH_PENALTY
                reasons.append(f"keyword mismatch penalty -{_KEYWORD_MISMATCH_PENALTY:.3f} (query has {negative_set}, product has {positive_set})")

        score_lex = round(score_lex, 3)
        rule_bonus = round(max(rule_bonus, -0.5), 3)  # Cap penalty at -0.5
        score_final = round(0.7 * score_lex + 0.3 * rule_bonus, 3)  # Increased rule_bonus weight

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


def _detect_category_from_query(query_tokens: Set[str]) -> str | None:
    """Detect product category from query tokens."""
    category_keywords = {
        "paint": {"farbe", "dispersionsfarbe", "latexfarbe", "wandfarbe", "fassadenfarbe"},
        "primer": {"grund", "grundierung", "tiefengrund", "haftgrund", "sperrgrund"},
        "tools": {"rolle", "pinsel", "werkzeug", "gerät", "leiter"},
        "tape": {"klebeband", "malerkrepp", "kreppband", "abklebeband"},
        "filler": {"spachtel", "spachtelmasse", "füller"},
    }
    
    for category, keywords in category_keywords.items():
        if query_tokens & keywords:
            return category
    
    return None


def _passes_pre_filters(
    entry: _CatalogEntry, 
    raw_item: Dict[str, object],
    category_filter: str | None = None,
) -> bool:
    """Pre-filter to exclude test products, inactive items, and wrong categories."""
    
    # Filter 1: Exclude test/demo products by SKU
    sku_lower = entry.sku.lower()
    for prefix in _TEST_SKU_PREFIXES:
        if sku_lower.startswith(prefix):
            return False
    
    # Filter 2: Exclude test/demo products by name (only if very obvious)
    name_lower = entry.name.lower()
    name_tokens = set(name_lower.split())
    # Only exclude if "test" or "demo" is a standalone word, not part of another word
    if name_tokens & _TEST_NAME_KEYWORDS:
        # Exception: Allow if it's part of a compound word like "testalarm" or "demonstration"
        if any(keyword in name_lower for keyword in ["testfarbe", "testprodukt", "demo-", "beispiel"]):
            return False
    
    # Filter 3: Only include active products (if is_active field exists)
    is_active = raw_item.get("is_active")
    if is_active is not None and not is_active:
        return False
    
    # Filter 4: Category filter (if specified)
    if category_filter and entry.category:
        if entry.category.lower() != category_filter.lower():
            return False
    
    return True


def _has_price(item: Dict[str, object]) -> bool:
    """Check if product has pricing information."""
    price = item.get("price_eur")
    if price is None:
        return False
    try:
        return float(price) > 0
    except (TypeError, ValueError):
        return False


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
