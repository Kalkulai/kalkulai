from __future__ import annotations

"""Main (server-side) retrieval pipeline with light-weight heuristics."""

import re
import logging
import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from shared.normalize import apply_synonyms, load_synonyms, normalize_query, tokenize

_SYN_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "shared" / "normalize" / "synonyms.yaml"
_RULE_COMPOUND = {"haft", "grund"}
_NUMERIC_RE = re.compile(r"^[0-9]+([.,][0-9]+)?$")
_UNIT_STOP = {
    "l",
    "liter",
    "kg",
    "g",
    "m",
    "mm",
    "cm",
    "m2",
    "m^2",
    "qm",
    "m3",
    "m^3",
    "stk",
    "stück",
    "rolle",
    "rollen",
    "eimer",
    "pack",
    "paket",
    "set",
    "kartusche",
    "platte",
    "platten",
    "sack",
    "beutel",
}
_GENERIC_STOP = {"weiß", "weiss", "beige", "grau", "premium", "matt", "seidenmatt", "wetterbeständig", "wetterbestaendig"}

_GRUND_QUERY_TOKENS = {"tiefgrund", "haftgrund", "grundierung", "putzgrund", "isoliergrund", "sperrgrund"}
_GRUND_NAME_TOKENS = {"tief", "haft", "grund", "grundierung", "putzgrund", "isolier", "sperr", "tiefgrund"}
DEFAULT_COMPANY_ID = os.getenv("DEFAULT_COMPANY_ID", "default")
logger = logging.getLogger("kalkulai.retriever")
_VOL_RE = re.compile(r"(\d+(?:[.,][0-9]+)?)\s*(l|liter|ml)\b", re.IGNORECASE)
_STOPWORDS = {
    "ich",
    "brauche",
    "bitte",
    "schnell",
    "für",
    "fuer",
    "dringend",
    "mal",
    "einmal",
    "der",
    "die",
    "das",
    "den",
    "dem",
    "und",
    "oder",
    "auch",
    "von",
    "mit",
    "innen",
    "aussen",
    "außen",
}


def _filter_semantic(tokens: Set[str]) -> Set[str]:
    out: Set[str] = set()
    for t in tokens:
        if not t:
            continue
        if _NUMERIC_RE.match(t):
            continue
        if t in _UNIT_STOP:
            continue
        if t in _GENERIC_STOP:
            continue
        if len(t) < 3:
            continue
        out.add(t)
    return out


def _needs_grund_anchor(q_tokens: Set[str]) -> bool:
    return bool(_GRUND_QUERY_TOKENS & q_tokens)


def _strip_noise_tokens(tokens: Set[str]) -> Set[str]:
    return {t for t in tokens if t and t not in _STOPWORDS and not t.isdigit() and len(t) >= 2}


def _contains_fragment(tokens: Set[str], *fragments: str) -> bool:
    return any(any(frag in token for frag in fragments) for token in tokens)


def _has_grund_anchor(name_tokens: Set[str]) -> bool:
    return bool(_GRUND_NAME_TOKENS & name_tokens)


def _has_putz_anchor(name_tokens: Set[str]) -> bool:
    return any(t in name_tokens for t in {"putz", "putzgrund"})


def _q_is_tiefgrund(tokens: Set[str]) -> bool:
    return "tiefgrund" in tokens or ({"tief", "grund"} <= tokens)


def _q_is_putzgrund(tokens: Set[str]) -> bool:
    return "putzgrund" in tokens or ("putz" in tokens and "grund" in tokens)


def _is_wrong_surface_for_tiefgrund(name_tokens: Set[str]) -> bool:
    return any(t in name_tokens for t in {"rost", "rostschutz", "metall", "holz"})


def _parse_volume(text: str | None) -> float | None:
    if not text:
        return None
    match = _VOL_RE.search(text)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    if unit == "ml":
        return value / 1000.0
    return value


@dataclass(frozen=True)
class _Candidate:
    sku: str
    name: str
    unit: str | None
    category: str | None
    brand: str | None
    tokens: Set[str]
    reasons: List[str]
    score_lex: float
    rule_bonus: float
    base_score: float


def rank_main(
    query: str,
    retriever: Any,
    top_k: int = 5,
    business_cfg: Optional[Dict[str, Any]] = None,
    company_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return top-N catalog candidates combining lexical and business scoring."""

    if top_k <= 0:
        return []

    company_key = company_id or None
    if retriever is None and company_key:
        retriever = get_company_index(company_key)
    if retriever is None:
        return _thin_fallback_results(query, top_k)

    normalized_query = normalize_query(query)
    base_query_tokens = tokenize(normalized_query)
    if not base_query_tokens:
        return []

    synonyms = _load_synonyms_cached(str(_SYN_DEFAULT_PATH))
    query_tokens = apply_synonyms(base_query_tokens, synonyms) if synonyms else set(base_query_tokens)
    synonym_only_tokens = query_tokens - base_query_tokens

    docs = (
        retriever.get_relevant_documents(query)
        if hasattr(retriever, "get_relevant_documents")
        else (retriever.invoke({"query": query}) if hasattr(retriever, "invoke") else [])
    )
    if not isinstance(docs, Sequence):
        docs = list(docs or [])
    max_candidates = max(top_k * 6, top_k)
    docs = list(docs[:max_candidates])

    # --- Hard filter prep: load synonyms and build query token set ---
    try:
        _syn_path = Path(__file__).resolve().parents[1] / "shared" / "normalize" / "synonyms.yaml"
        _synonyms = load_synonyms(str(_syn_path))
    except Exception:  # pragma: no cover - fallback for eval-only runs
        _synonyms = {}

    _q_raw = tokenize(query)
    _q_raw_sem = _strip_noise_tokens(_filter_semantic(_q_raw))
    _q_aug = apply_synonyms(_q_raw, _synonyms) if _q_raw else set()
    _q_aug_sem = _strip_noise_tokens(_filter_semantic(_q_aug))
    _q_sem = _q_aug_sem or _q_raw_sem
    _q_is_tiefgrund_flag = _q_is_tiefgrund(_q_raw_sem) or _q_is_tiefgrund(_q_sem)
    _q_is_putzgrund_flag = _q_is_putzgrund(_q_raw_sem) or _q_is_putzgrund(_q_sem)
    _q_requires_grund = _needs_grund_anchor(_q_sem) or _q_is_tiefgrund_flag or _q_is_putzgrund_flag
    _q_vol_l = _parse_volume(query)

    candidates: List[_Candidate] = []
    seen_skus: Set[str] = set()
    for doc in docs:
        entry = _extract_entry(doc)
        if entry is None or entry.sku in seen_skus:
            continue
        seen_skus.add(entry.sku)

        name = entry.name
        _lname = (name or "").lower()
        _name_tokens_all = tokenize(name or "")
        if _name_tokens_all and _synonyms:
            _name_tokens_all = apply_synonyms(_name_tokens_all, _synonyms)
        _name_sem = _filter_semantic(_name_tokens_all)
        _name_sem = _strip_noise_tokens(_name_sem)
        if _q_sem and not (_q_sem & _name_sem):
            continue
        if _q_requires_grund and not _has_grund_anchor(_name_sem):
            continue
        if _q_is_tiefgrund_flag:
            if _is_wrong_surface_for_tiefgrund(_name_sem):
                continue
            if "sperrgrund" in _name_sem or "isoliergrund" in _name_sem:
                continue
            if not _contains_fragment(_name_sem, "tief"):
                continue
            if "haftgrund" in _name_sem and "tiefgrund" not in _name_sem:
                continue
        if _q_is_putzgrund_flag and not _has_putz_anchor(_name_sem):
            continue
        if _q_is_putzgrund_flag and not _contains_fragment(_name_sem, "putz"):
            continue
        cand_liters_primary = _parse_volume(name)
        if _q_vol_l is not None and _q_vol_l > 0 and cand_liters_primary is not None:
            if cand_liters_primary < (_q_vol_l * 0.25):
                continue

        item_tokens = _collect_item_tokens(entry, synonyms)
        if not item_tokens:
            continue
        if not _passes_token_gate(query_tokens, item_tokens):
            continue

        score_lex, lex_reasons = _score_lexical(query_tokens, item_tokens, normalized_query, normalize_query(entry.name))
        if score_lex <= 0:
            continue

        rule_bonus, rule_reasons = _rule_bonus(query_tokens, item_tokens, synonym_only_tokens)
        if _q_sem & _name_sem:
            rule_bonus += 0.05
        if _q_requires_grund:
            if _q_vol_l is not None:
                c_l = cand_liters_primary
                if c_l is None and _name_sem:
                    c_l = _parse_volume(" ".join(sorted(_name_sem)))
                if c_l is not None and c_l > 0:
                    rel = c_l / max(_q_vol_l, 1e-9)
                    if rel < 0.60:
                        rule_bonus -= 0.25
                    elif 0.80 <= rel <= 1.25:
                        rule_bonus += 0.10
                    elif 0.60 <= rel < 0.80 or 1.25 < rel <= 1.60:
                        rule_bonus += 0.02

            if "tiefengrund" in _lname:
                rule_bonus += 0.35
            elif "putzgrund" in _lname:
                rule_bonus += 0.18

            if _q_is_tiefgrund_flag:
                if not _has_grund_anchor(_name_sem):
                    rule_bonus -= 0.25
                if _is_wrong_surface_for_tiefgrund(_name_sem):
                    rule_bonus -= 0.12
                if "sperrgrund" in _name_sem or "isoliergrund" in _name_sem:
                    rule_bonus -= 0.2
                if _contains_fragment(_name_sem, "tiefgrund", "tiefengrund"):
                    rule_bonus += 0.08
                if _contains_fragment(_name_sem, "putzgrund"):
                    rule_bonus += 0.05
                if "haftgrund" in _name_sem and "tiefgrund" not in _name_sem:
                    rule_bonus -= 0.4

            if _q_is_putzgrund_flag:
                if not _has_putz_anchor(_name_sem):
                    rule_bonus -= 0.3
                else:
                    rule_bonus += 0.2
                if "tiefgrund" in _name_sem and "putz" not in _name_sem:
                    rule_bonus -= 0.2
                if "sperrgrund" in _name_sem or "isoliergrund" in _name_sem or "haftgrund" in _name_sem:
                    rule_bonus -= 0.12

            if "rost" in _lname or "rostschutz" in _lname:
                rule_bonus -= 0.12
        base_score = _clamp(0.7 * score_lex + 0.2 * rule_bonus, 0.0, 1.0)

        candidates.append(
            _Candidate(
                sku=entry.sku,
                name=entry.name,
                unit=entry.unit,
                category=entry.category,
                brand=entry.brand,
                tokens=item_tokens,
                reasons=lex_reasons + rule_reasons,
                score_lex=score_lex,
                rule_bonus=rule_bonus,
                base_score=base_score,
            )
        )

    if not candidates:
        return _thin_fallback_results(query, top_k)

    business_cfg = business_cfg or {}
    availability_map: Dict[str, int] = {str(k): int(v) for k, v in (business_cfg.get("availability") or {}).items()}
    price_map: Dict[str, float] = {str(k): float(v) for k, v in (business_cfg.get("price") or {}).items()}
    margin_map: Dict[str, float] = {str(k): float(v) for k, v in (business_cfg.get("margin") or {}).items()}
    brand_boost_map: Dict[str, float] = {str(k).lower(): float(v) for k, v in (business_cfg.get("brand_boost") or {}).items()}

    price_values = [price_map.get(candidate.sku) for candidate in candidates if candidate.sku in price_map]
    price_values = [p for p in price_values if p is not None]
    price_min = min(price_values) if price_values else 0.0
    price_max = max(price_values) if price_values else 0.0
    price_span = price_max - price_min

    ranked: List[Dict[str, Any]] = []
    for candidate in candidates:
        reasons = list(candidate.reasons)
        score_business = 0.0

        availability_flag = availability_map.get(candidate.sku, 0)
        if availability_flag == 1:
            score_business += 0.1
            reasons.append("availability")

        margin_value = margin_map.get(candidate.sku)
        if margin_value is not None and margin_value > 0:
            margin_bonus = min(0.15, margin_value * 0.2)
            score_business += margin_bonus
            reasons.append("margin")
        else:
            margin_bonus = 0.0

        brand_lower = (candidate.brand or "").lower()
        brand_bonus = brand_boost_map.get(brand_lower, 0.0)
        if brand_bonus:
            score_business += brand_bonus
            reasons.append("brand_boost")

        price_value = price_map.get(candidate.sku)
        penalty = 0.0
        if price_value is not None and price_span > 0:
            normalized = (price_value - price_min) / price_span
            penalty = min(0.15, max(0.0, normalized * 0.15))
            if penalty > 0:
                score_business -= penalty
                reasons.append("price_penalty")

        score_business = _clamp(score_business, 0.0, 1.0)
        score_main = _clamp(candidate.base_score + score_business, 0.0, 1.0)

        ranked.append(
            {
                "sku": candidate.sku,
                "name": candidate.name,
                "unit": candidate.unit,
                "category": candidate.category,
                "brand": candidate.brand,
                "score_main": round(score_main, 3),
                "score_business": round(score_business, 3),
                "reasons": reasons,
                "_availability": availability_flag,
                "_price": price_value,
                "_margin": margin_value,
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["score_main"],
            -item["_availability"],
            item["_price"] if item["_price"] is not None else float("inf"),
            -item["_margin"] if item["_margin"] is not None else float("inf"),
            item["name"].lower(),
            item["sku"],
        )
    )

    for item in ranked:
        item.pop("_availability", None)
        item.pop("_price", None)
        item.pop("_margin", None)

    return ranked[: min(top_k, len(ranked))]


# ---------------------------------------------------------------------------
# Helper utilities


def _extract_entry(doc: Any) -> "_CatalogEntry" | None:
    metadata = getattr(doc, "metadata", {}) or {}
    page_content = getattr(doc, "page_content", "")
    name = metadata.get("name") or page_content or metadata.get("title") or ""
    if not name:
        return None
    sku = str(metadata.get("sku") or metadata.get("id") or metadata.get("code") or name).strip()
    unit = metadata.get("unit")
    category = metadata.get("category")
    brand = metadata.get("brand")
    synonyms = metadata.get("synonyms")
    return _CatalogEntry(
        sku=sku,
        name=str(name),
        unit=str(unit) if unit is not None else None,
        category=str(category) if category is not None else None,
        brand=str(brand) if brand is not None else None,
        synonyms=[str(s) for s in synonyms] if isinstance(synonyms, (list, tuple, set)) else [],
    )


@dataclass(frozen=True)
class _CatalogEntry:
    sku: str
    name: str
    unit: str | None
    category: str | None
    brand: str | None
    synonyms: List[str]


def _collect_item_tokens(entry: _CatalogEntry, synonyms: Dict[str, List[str]]) -> Set[str]:
    tokens = tokenize(entry.name)
    if entry.synonyms:
        for synonym in entry.synonyms:
            tokens.update(tokenize(synonym))
    if synonyms:
        tokens = apply_synonyms(tokens, synonyms)
    return tokens


def _passes_token_gate(query_tokens: Set[str], item_tokens: Set[str]) -> bool:
    return bool(query_tokens & item_tokens)


def _score_lexical(
    query_tokens: Set[str],
    item_tokens: Set[str],
    normalized_query: str,
    normalized_name: str,
) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    overlap = len(query_tokens & item_tokens)
    overlap_ratio = overlap / max(len(query_tokens), 1)
    if overlap_ratio > 0:
        reasons.append("lex_overlap")

    boost, boost_reasons = _prefix_substring_boost(query_tokens, item_tokens)
    reasons.extend(boost_reasons)

    seq_ratio = SequenceMatcher(None, normalized_query, normalized_name).ratio()
    lex_score = max(seq_ratio, min(1.0, overlap_ratio + boost))
    return round(lex_score, 3), reasons


def _prefix_substring_boost(query_tokens: Set[str], item_tokens: Set[str]) -> Tuple[float, List[str]]:
    boost = 0.0
    reasons: List[str] = []
    for q_token in query_tokens:
        for item_token in item_tokens:
            if q_token == item_token:
                boost = max(boost, 1.0)
                if "lex_exact" not in reasons:
                    reasons.append("lex_exact")
            elif q_token in item_token or item_token in q_token:
                boost = max(boost, 0.85)
                if "lex_substring" not in reasons:
                    reasons.append("lex_substring")
            elif q_token.replace(" ", "") and q_token.replace(" ", "") in item_token.replace(" ", ""):
                boost = max(boost, 0.82)
                if "lex_compact" not in reasons:
                    reasons.append("lex_compact")
    return boost, reasons


def _rule_bonus(
    query_tokens: Set[str],
    item_tokens: Set[str],
    synonym_only_tokens: Set[str],
) -> Tuple[float, List[str]]:
    bonus = 0.0
    reasons: List[str] = []
    synonym_hits = synonym_only_tokens & item_tokens
    if synonym_hits:
        bonus += 0.05 * len(synonym_hits)
        reasons.append("synonym_bonus")
    if _RULE_COMPOUND <= (query_tokens | item_tokens):
        bonus += 0.1
        reasons.append("compound")
    return round(bonus, 3), reasons


def _load_synonyms_cached(path: str) -> Dict[str, List[str]]:
    resolved = str(Path(path).expanduser())
    return _synonym_cache(resolved)


@lru_cache(maxsize=1)
def _synonym_cache(path: str) -> Dict[str, List[str]]:
    try:
        return load_synonyms(path)
    except FileNotFoundError:
        return {}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _thin_fallback_results(query: str, top_k: int) -> List[Dict[str, Any]]:
    try:
        from retriever.thin import search_catalog_thin
        import backend.main as backend_main  # type: ignore
    except Exception:
        return []
    catalog_items = getattr(backend_main, "CATALOG_ITEMS", [])
    if not catalog_items:
        return []
    thin_hits = search_catalog_thin(
        query=query,
        top_k=top_k,
        catalog_items=catalog_items,
        synonyms_path=str(getattr(backend_main, "SYNONYMS_PATH", "")) or None,
    )
    q_tokens = _strip_noise_tokens(_filter_semantic(tokenize(query)))
    q_is_tief = _q_is_tiefgrund(q_tokens)
    q_is_putz = _q_is_putzgrund(q_tokens)

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for hit in thin_hits[: max(top_k * 2, top_k)]:
        name = hit.get("name") or ""
        name_tokens = _strip_noise_tokens(_filter_semantic(tokenize(name)))
        score = float(hit.get("score_final", 0.0))
        if q_is_tief:
            if not _contains_fragment(name_tokens, "tief"):
                score -= 0.4
            if _contains_fragment(name_tokens, "tief"):
                score += 0.1
            if _contains_fragment(name_tokens, "haft") and not _contains_fragment(name_tokens, "tief"):
                score -= 0.4
        if q_is_putz:
            if not _has_putz_anchor(name_tokens):
                score -= 0.3
            else:
                score += 0.2
        scored.append((score, hit))

    scored.sort(key=lambda item: (-item[0], (item[1].get("name") or "").lower()))
    fallback_results: List[Dict[str, Any]] = []
    for score, hit in scored[:top_k]:
        fallback_results.append(
            {
                "sku": hit.get("sku"),
                "name": hit.get("name"),
                "unit": hit.get("unit"),
                "category": hit.get("category"),
                "brand": hit.get("brand"),
                "score_main": round(score, 3),
                "score_business": 0.0,
                "reasons": list(hit.get("reasons", [])) + ["thin_fallback"],
            }
        )
    return fallback_results


def get_company_index(company_id: Optional[str] = None):
    target = company_id or DEFAULT_COMPANY_ID
    if not target:
        return None
    try:
        from retriever import index_manager
    except Exception as exc:  # pragma: no cover
        logger.warning("Dynamic index unavailable for %s (%s)", target, exc)
        return None
    logger.info("Using dynamic retriever company_id=%s", target)
    return _CompanyRetriever(target, index_manager)


class _CompanyRetriever:
    def __init__(self, company_id: str, manager_module):
        self.company_id = company_id
        self._manager = manager_module

    def get_relevant_documents(self, query: str):
        from langchain.schema import Document as LCDocument  # type: ignore

        hits = self._manager.search_index(self.company_id, query, top_k=20)
        return [
            LCDocument(
                page_content=hit.get("text") or hit.get("name") or "",
                metadata={"name": hit.get("name"), "sku": hit.get("sku")},
            )
            for hit in hits
        ]
