"""Quote service layer centralizing business logic and guardrails.

This module backs both FastAPI handlers and the MCP tool layer by exposing
typed functions (chat, offer generation, wizard flows, revenue guard, etc.).
It enforces shared guardrails (LLM readiness, deterministic rules) and should
remain the single source of truth for core workflows. See docs/mcp-overview.md
for architecture and tool-chain details.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from jinja2 import Environment

from app.error_messages import (
    chat_unknown_products_message,
    offer_unknown_products_message,
)
from app.uom_convert import harmonize_material_line
from app.utils import extract_json_array, extract_products_from_output, parse_positions
from retriever import index_manager
from retriever.main import rank_main as default_rank_main
from retriever.thin import search_catalog_thin as default_search_catalog_thin
from shared.normalize.text import normalize_query as shared_normalize_query
from shared.normalize.text import tokenize as shared_tokenize

CATALOG_MATCH_THRESHOLD = 0.45
CATALOG_STRONG_MATCH_THRESHOLD = 0.5  # Lowered from 0.6 for better fuzzy matching with dynamic catalogs

NO_DATA_DETAILS_MESSAGE = (
    "Es liegen noch keine Angebotsdaten vor.\n\n"
    "Bitte teilen Sie mir Details zu Ihrem Projekt mit, zum Beispiel:\n"
    "- Welche Fläche (m²) oder welche Räume sollen bearbeitet werden?\n"
    "- Welche Arbeiten sind geplant (z. B. Wände/Decken streichen, spachteln, lackieren)?\n"
    "- Welche Materialien stellen Sie sich vor (z. B. Dispersionsfarbe weiß, Tiefgrund, Kreppband)?\n"
    "- Gibt es Besonderheiten wie Risse, Feuchtigkeit, Altanstriche oder Wunschfarben?"
)
MATERIAL_NAME_SPLIT_RE = re.compile(r"[:\n]")
PACK_SIZE_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(m²|m2|m|mm|cm|kg|g|l|liter|stk|stück|rollen?|rolle|paket|packung)",
    re.IGNORECASE,
)
BASE_UNIT_MAP = {
    "l": "L",
    "liter": "L",
    "litre": "L",
    "m": "m",
    "meter": "m",
    "m²": "m²",
    "m2": "m²",
    "qm": "m²",
    "kg": "kg",
    "g": "kg",
    "gramm": "kg",
    "stk": "Stück",
    "stück": "Stück",
    "piece": "Stück",
    "pcs": "Stück",
}
CONTAINER_UNITS = {
    "kanister",
    "eimer",
    "rolle",
    "rollen",
    "paket",
    "pack",
    "packung",
    "gebinde",
    "karton",
    "dose",
    "kiste",
    "set",
}
UNIT_HINT_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(l|liter|m²|m2|qm|m|kg|g|stk|stück)",
    re.IGNORECASE,
)
ROOM_TOKENS = {
    "wohnzimmer",
    "schlafzimmer",
    "kinderzimmer",
    "flur",
    "kuche",
    "küche",
    "bad",
    "badezimmer",
    "arbeitszimmer",
    "buero",
    "büro",
    "innenraum",
    "innenbereich",
}
WALL_TOKENS = {"wand", "wande", "wände", "decke", "decken", "waende"}
INTERIOR_HINT_TOKENS = {"innen", "innenraum", "innenbereich"}
WOOD_TOKENS = {"holz", "holzzaun", "holzbalken", "sichtbalken", "holzdecke"}
FACADE_TOKENS = {"fassade", "fassaden", "außen", "aussen", "außenbereich", "außenwand", "aussenwand"}
TAPE_TOKENS = {"abklebeband", "abdeckband", "kreppband", "malerband", "band"}
FOIL_TOKENS = {"abdeckfolie", "folie"}
VLIES_TOKENS = {"abdeckvlies", "malervlies", "vlies"}
SPACHTEL_TOKENS = {"spachtel", "spachtelmasse", "füller", "fuller"}
MaterialType = str
PRODUCT_TYPE_KEYWORDS = {
    "primer_mineral": [
        "tiefgrund",
        "tiefengrund",
        "putzgrund",
        "mineral",
    ],
    "primer_wood_metal": [
        "haftgrund",
        "grundierung",
        "primer",
    ],
    "wood_preserver": [
        "holzschutz",
        "holzschutzgrund",
        "lasur",
        "holzöl",
    ],
    "wood_paint": [
        "holzlack",
        "holzfarbe",
    ],
    "metal_paint": [
        "metalllack",
        "metallfarbe",
        "metallschutz",
    ],
    "tape": [
        "abklebeband",
        "abdeckband",
        "kreppband",
        "malerband",
        "band",
    ],
    "foil": [
        "abdeckfolie",
        "folie",
    ],
    "vlies": [
        "vlies",
        "abdeckvlies",
    ],
    "filler_spachtel": [
        "spachtel",
        "spachtelmasse",
        "füller",
        "spachtelmasse",
    ],
    "wall_paint_interior": [
        "innenfarbe",
        "dispersionsfarbe",
        "wandfarbe",
        "raufaser",
        "raumfarbe",
        "wohnzimmer",
    ],
    "ceiling_paint_interior": [
        "deckenfarbe",
        "decke",
    ],
    "facade_paint_exterior": [
        "fassadenfarbe",
        "außen",
        "aussen",
        "fassade",
        "wetterbest",
    ],
    "tool_accessory": [
        "rolle",
        "pinsel",
        "teleskop",
        "eimer",
        "werkzeug",
    ],
}
REQUEST_COMPATIBILITY: Dict[str, set[str]] = {
    "wall_paint_interior": {"wall_paint_interior", "ceiling_paint_interior"},
    "ceiling_paint_interior": {"wall_paint_interior", "ceiling_paint_interior"},
    "facade_paint_exterior": {"facade_paint_exterior"},
    "wood_preserver": {"wood_preserver", "wood_paint"},
    "wood_paint": {"wood_paint", "wood_preserver"},
    "metal_paint": {"metal_paint"},
    "primer_mineral": {"primer_mineral"},
    "primer_wood_metal": {"primer_wood_metal"},
    "tape": {"tape"},
    "foil": {"foil"},
    "vlies": {"vlies"},
    "filler_spachtel": {"filler_spachtel"},
    "tool_accessory": {"tool_accessory"},
}


def _run_thin_catalog_search(**kwargs):
    try:
        from backend import main as backend_main

        func = getattr(backend_main, "search_catalog_thin", default_search_catalog_thin)
    except Exception:
        func = default_search_catalog_thin
    return func(**kwargs)


def _run_rank_main(*args, **kwargs):
    try:
        from backend import main as backend_main

        func = getattr(backend_main, "rank_main", default_rank_main)
    except Exception:
        func = default_rank_main
    return func(*args, **kwargs)


def _normalize_material_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        return ""
    parts = MATERIAL_NAME_SPLIT_RE.split(cleaned, 1)
    cleaned = parts[0].strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _collect_tokens(*parts: Optional[str]) -> set[str]:
    combined = " ".join(part or "" for part in parts)
    return {tok.lower() for tok in shared_tokenize(combined) if tok}


def _build_generic_token_set() -> set[str]:
    allowed: set[str] = set()
    for keywords in PRODUCT_TYPE_KEYWORDS.values():
        for keyword in keywords:
            allowed.update(_collect_tokens(keyword))
    extra_terms = [
        "farbe",
        "farben",
        "streichfarbe",
        "wand",
        "decken",
        "streichen",
        "streiche",
        "beschichten",
        "weiß",
        "weiss",
        "weiße",
        "weisse",
        "hell",
        "dunkel",
        "matt",
        "seidenmatt",
        "glanz",
        "innenwand",
        "innenwände",
        "innenwaende",
        "innenwande",
        "wandfarbe",
        "deckenfarbe",
        "streichen",
        "streiche",
        "wand",
        "wände",
        "waende",
        "decke",
        "decken",
        "raum",
        "raumfarbe",
        "standard",
        "basis",
        "premium",
        "klassisch",
        "zaun",
        "gartenzaun",
        "balken",
        "sichtbalken",
        "holzdecke",
        "holzfenster",
        "holzfassade",
    ]
    for term in extra_terms:
        allowed.update(_collect_tokens(term))
    return allowed


GENERIC_ALLOWED_TOKENS = _build_generic_token_set()
# measurement/unit tokens considered generic regardless of appearance
GENERIC_NEUTRAL_TOKENS = {
    "l",
    "liter",
    "m",
    "m²",
    "m2",
    "qm",
    "kg",
    "g",
    "ml",
}
GENERIC_STOP_TOKENS = {
    "fur",
    "fuer",
    "für",
    "mit",
    "und",
    "auch",
    "noch",
    "bitte",
    "lieber",
    "gern",
    "gerne",
    "mehr",
    "weniger",
    "brauche",
    "braucht",
    "brauchen",
    "zum",
    "zur",
    "der",
    "die",
    "das",
    "den",
    "dem",
    "ein",
    "eine",
    "einen",
    "einem",
    "einer",
    "auf",
    "im",
    "in",
    "vom",
    "von",
    "am",
    "oder",
    "plus",
}


def _token_match(tokens: set[str], keywords: set[str]) -> bool:
    return any(keyword in tokens for keyword in keywords)


def _infer_contextual_type(context_text: Optional[str]) -> MaterialType:
    if not context_text:
        return "other"
    tokens = _collect_tokens(context_text)
    if not tokens:
        return "other"
    if _token_match(tokens, TAPE_TOKENS):
        return "tape"
    if _token_match(tokens, FOIL_TOKENS):
        return "foil"
    if _token_match(tokens, VLIES_TOKENS):
        return "vlies"
    if _token_match(tokens, SPACHTEL_TOKENS):
        return "filler_spachtel"
    if _token_match(tokens, WOOD_TOKENS):
        return "wood_preserver"
    if _token_match(tokens, FACADE_TOKENS):
        return "facade_paint_exterior"
    interior_hit = (_token_match(tokens, ROOM_TOKENS) or _token_match(tokens, INTERIOR_HINT_TOKENS)) and _token_match(tokens, WALL_TOKENS)
    if interior_hit:
        return "wall_paint_interior"
    return "other"


def _classify_material_from_tokens(tokens: set[str]) -> MaterialType:
    for material_type, keywords in PRODUCT_TYPE_KEYWORDS.items():
        if any(keyword in tokens for keyword in keywords):
            return material_type
    return "other"


def _is_generic_material_query(name: str) -> bool:
    tokens = _collect_tokens(name)
    if not tokens:
        return False
    for token in tokens:
        if token.isdigit():
            continue
        if token in GENERIC_NEUTRAL_TOKENS:
            continue
        if token in GENERIC_STOP_TOKENS:
            continue
        if token in GENERIC_ALLOWED_TOKENS:
            continue
        return False
    return True


def _compose_context_text(message: Optional[str], ctx: QuoteServiceContext) -> str:
    parts: List[str] = []
    if message:
        parts.append(message)
    if ctx.memory1 is not None:
        try:
            history = ctx.memory1.load_memory_variables({}).get("chat_history", "")  # type: ignore[union-attr]
        except Exception:
            history = ""
        if history:
            parts.append(history)
    return " ".join(part for part in parts if part).strip()


def _classify_requested_material_type(name: str, context: Optional[str] = None) -> MaterialType:
    tokens = _collect_tokens(name)
    raw_text = " ".join(part for part in [name or "", context or ""] if part).lower()
    direct_type = _classify_material_from_tokens(tokens)
    if direct_type != "other":
        return direct_type
    if "holzschutz" in raw_text or ("holz" in raw_text and ("schutz" in raw_text or "pflege" in raw_text)):
        return "wood_preserver"
    if "holz" in raw_text and ("lack" in raw_text or "farbe" in raw_text):
        return "wood_paint"
    if any(term in raw_text for term in ("fassade", "außen", "aussen")):
        return "facade_paint_exterior"
    context_type = _infer_contextual_type(context or raw_text)
    if context_type != "other":
        return context_type
    return "other"


def _classify_product_entry(
    entry: Optional[Dict[str, Any]],
    fallback_name: Optional[str] = None,
) -> MaterialType:
    if not entry and not fallback_name:
        return "other"
    category = (entry.get("category") or "") if entry else ""
    tokens = _collect_tokens(entry.get("name") if entry else "", entry.get("description") if entry else "", fallback_name, category)
    raw_text = " ".join(
        [
            entry.get("name") if entry else "",
            entry.get("description") if entry else "",
            category,
            fallback_name or "",
        ]
    ).lower()
    if "holzschutz" in raw_text or ("holz" in raw_text and ("schutz" in raw_text or "pflege" in raw_text)):
        return "wood_preserver"
    if "holz" in raw_text and ("lack" in raw_text or "farbe" in raw_text):
        return "wood_paint"
    unit = (entry.get("unit") or "").lower() if entry else ""
    if unit in {"l", "liter", "litre"} and "holz" in tokens:
        return "wood_paint"
    if unit in {"l", "liter", "litre"} and ("metall" in tokens or "stahl" in tokens):
        return "metal_paint"
    classified = _classify_material_from_tokens(tokens)
    if classified != "other":
        return classified
    return _infer_contextual_type(raw_text)


def _is_type_compatible(
    requested: MaterialType,
    product: MaterialType,
    context_text: Optional[str] = None,
) -> bool:
    adjusted = requested
    if adjusted == "other" and context_text:
        inferred = _infer_contextual_type(context_text)
        if inferred != "other":
            adjusted = inferred
    if adjusted == "other":
        return True
    if product == "other":
        return False
    allowed = REQUEST_COMPATIBILITY.get(adjusted)
    if allowed is None:
        return True
    return product in allowed


def _load_company_catalog_products(company_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
    if not company_id:
        return {}
    try:
        from store import catalog_store
    except Exception:
        return {}

    try:
        rows = catalog_store.get_active_products(company_id) or []
    except Exception:
        rows = []

    products: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = (row.get("name") or "").strip().lower()
        if key:
            products[key] = row
    return products


def _load_company_synonym_map(company_id: Optional[str]) -> Dict[str, str]:
    if not company_id:
        return {}
    try:
        from store import catalog_store
    except Exception:
        return {}

    try:
        mapping_raw = catalog_store.list_synonyms(company_id) or {}
    except Exception:
        mapping_raw = {}

    synonyms: Dict[str, str] = {}
    for canon, variants in mapping_raw.items():
        canon_key = (canon or "").strip().lower()
        if canon_key:
            synonyms[canon_key] = canon_key
        for variant in variants or []:
            var_key = (variant or "").strip().lower()
            if var_key:
                synonyms[var_key] = canon_key or var_key
    return synonyms


def _match_catalog_entry(
    query: str,
    ctx: QuoteServiceContext,
    *,
    company_id: Optional[str],
    company_products: Dict[str, Dict[str, Any]],
    company_synonyms: Dict[str, str],
    context_text: Optional[str] = None,
) -> Dict[str, Any]:
    cleaned = _normalize_material_name(query)
    lower = cleaned.lower()
    requested_type = _classify_requested_material_type(cleaned, context_text)
    result = {
        "query": cleaned,
        "matched": False,
        "match_type": "",
        "confidence": 0.0,
        "canonical_name": None,
        "sku": None,
        "suggestions": [],
    }
    if not cleaned:
        return result

    entry = ctx.catalog_by_name.get(lower)
    if entry:
        product_type = _classify_product_entry(entry)
        if not _is_type_compatible(requested_type, product_type, context_text):
            entry = None
    if entry:
        result.update(
            {
                "matched": True,
                "match_type": "direct",
                "confidence": 1.0,
                "canonical_name": entry.get("name") or cleaned,
                "sku": entry.get("sku"),
            }
        )
        return result

    if lower in company_synonyms:
        canonical_lower = company_synonyms[lower]
        entry = ctx.catalog_by_name.get(canonical_lower)
        if not entry:
            entry = _find_company_product_by_lower(canonical_lower, company_products)
        if entry:
            product_type = _classify_product_entry(entry)
            if not _is_type_compatible(requested_type, product_type, context_text):
                entry = None
        if entry:
            result.update(
                {
                    "matched": True,
                    "match_type": "synonym",
                    "confidence": 0.9,
                    "canonical_name": entry.get("name") or cleaned,
                    "sku": entry.get("sku"),
                }
            )
            return result

    for product in company_products.values():
        product_name = (product.get("name") or "").strip()
        if not product_name:
            continue
        if _material_names_match(cleaned, product_name):
            product_type = _classify_product_entry(product)
            if not _is_type_compatible(requested_type, product_type, context_text):
                continue
            result.update(
                {
                    "matched": True,
                    "match_type": "company_db",
                    "confidence": 0.85,
                    "canonical_name": product_name,
                    "sku": product.get("sku"),
                }
            )
            return result

    if lower in company_products:
        product = company_products[lower]
        product_type = _classify_product_entry(product)
        if not _is_type_compatible(requested_type, product_type, context_text):
            product = None
        result.update(
            {
                "matched": True,
                "match_type": "company_db",
                "confidence": 0.85,
                "canonical_name": product.get("name") or cleaned,
                "sku": product.get("sku"),
            }
        )
        return result

    hits = _run_thin_catalog_search(
        query=cleaned,
        top_k=ctx.catalog_top_k,
        catalog_items=ctx.catalog_items,
        synonyms_path=str(ctx.synonyms_path),
    )
    suggestions = [h.get("name") for h in hits if h.get("name")]
    result["suggestions"] = suggestions

    top_hit: Dict[str, Any] | None = None
    top_conf = 0.0
    for hit in hits:
        conf_raw = hit.get("confidence", hit.get("score_final"))
        try:
            confidence = float(conf_raw or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence > top_conf:
            top_conf = confidence
            top_hit = hit
        product_entry = None
        sku = (hit.get("sku") or "").strip()
        if sku:
            product_entry = ctx.catalog_by_sku.get(sku)
        if not product_entry and hit.get("name"):
            product_entry = ctx.catalog_by_name.get((hit.get("name") or "").strip().lower())
        product_type = _classify_product_entry(product_entry, hit.get("name"))
        if product_entry and not _is_type_compatible(requested_type, product_type, context_text):
            continue
        if confidence >= CATALOG_STRONG_MATCH_THRESHOLD:
            result.update(
                {
                    "matched": True,
                    "match_type": "vector",
                    "confidence": confidence,
                    "canonical_name": hit.get("name") or cleaned,
                    "sku": hit.get("sku"),
                }
            )
            break

    if not result["matched"]:
        lexical_entry = _lexical_partial_catalog_match(cleaned, ctx, company_products, requested_type, context_text)
        if lexical_entry:
            entry, similarity = lexical_entry
            if similarity >= CATALOG_STRONG_MATCH_THRESHOLD:
                result.update(
                    {
                        "matched": True,
                        "match_type": "lexical_partial",
                        "confidence": similarity,
                        "canonical_name": entry.get("name") or cleaned,
                        "sku": entry.get("sku"),
                    }
                )
            else:
                name = entry.get("name")
                if name and name not in result["suggestions"]:
                    result["suggestions"].append(name)

    if (
        not result["matched"]
        and requested_type != "other"
        and _is_generic_material_query(cleaned)
    ):
        candidate = _find_type_candidate(ctx, requested_type)
        if candidate:
            result.update(
                {
                    "matched": True,
                    "match_type": "type_generic",
                    "confidence": 0.55,
                    "canonical_name": candidate.get("name") or cleaned,
                    "sku": candidate.get("sku"),
                }
            )

    # Enhanced fuzzy matching as final fallback
    if not result["matched"]:
        try:
            from shared.fuzzy_matcher import find_best_matches
            
            # Get all catalog product names
            catalog_names = [item.get("name") for item in ctx.catalog_items if item.get("name")]
            
            # Try fuzzy matching with threshold 0.25
            fuzzy_matches = find_best_matches(cleaned, catalog_names, top_k=5, min_score=0.25)
            
            if fuzzy_matches:
                best_match_name, best_score = fuzzy_matches[0]
                
                # Find the full catalog entry
                matched_entry = None
                for item in ctx.catalog_items:
                    if item.get("name") == best_match_name:
                        matched_entry = item
                        break
                
                if matched_entry:
                    # Check type compatibility
                    product_type = _classify_product_entry(matched_entry)
                    if _is_type_compatible(requested_type, product_type, context_text):
                        result.update({
                            "matched": True,
                            "match_type": "fuzzy_enhanced",
                            "confidence": best_score,
                            "canonical_name": best_match_name,
                            "sku": matched_entry.get("sku"),
                        })
                
                # Add all fuzzy matches as suggestions
                for match_name, match_score in fuzzy_matches:
                    if match_name not in result["suggestions"]:
                        result["suggestions"].append(match_name)
        except ImportError:
            # Fuzzy matcher not available, skip
            pass
        except Exception:
            # Don't let fuzzy matching break the system
            pass

    return result


def _lexical_partial_catalog_match(
    cleaned: str,
    ctx: QuoteServiceContext,
    company_products: Dict[str, Dict[str, Any]],
    requested_type: MaterialType,
    context_text: Optional[str],
) -> Optional[Tuple[Dict[str, Any], float]]:
    q_norm = _normalize_query(cleaned)
    if not q_norm:
        return None
    q_words = [word for word in q_norm.split() if word]
    if not q_words:
        return None
    significant_tokens = [word for word in q_words if len(word) >= 4]
    if not significant_tokens:
        return None

    entries: List[Dict[str, Any]] = list(ctx.catalog_by_name.values())
    seen_names = {((entry.get("name") or "").strip().lower()) for entry in entries if entry.get("name")}
    if company_products:
        for product in company_products.values():
            name = (product.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen_names:
                continue
            entries.append(product)
            seen_names.add(key)

    candidates: List[Tuple[int, float, int, str, Dict[str, Any], float]] = []
    for entry in entries:
        entry_name = (entry.get("name") or "").strip()
        if not entry_name:
            continue
        entry_norm = _normalize_query(entry_name)
        if not entry_norm:
            continue
        entry_words = [word for word in entry_norm.split() if word]
        if not entry_words:
            continue
        product_type = _classify_product_entry(entry)
        if not _is_type_compatible(requested_type, product_type, context_text):
            continue
        match_kind = _lexical_match_kind(q_words, significant_tokens, entry_words)
        if match_kind is None:
            continue
        similarity = SequenceMatcher(None, q_norm, entry_norm).ratio()
        candidates.append((match_kind, -similarity, len(entry_words), entry_norm, entry, similarity))

    if not candidates:
        return None

    candidates.sort(key=lambda tpl: (tpl[0], tpl[1], tpl[2], tpl[3]))
    best = candidates[0]
    return best[4], best[5]


def _lexical_match_kind(
    q_words: List[str],
    significant_tokens: List[str],
    entry_words: List[str],
) -> Optional[int]:
    if not entry_words or not q_words:
        return None

    prefix_len = min(len(q_words), len(entry_words))
    if prefix_len and q_words[:prefix_len] == entry_words[:prefix_len]:
        if len(q_words) <= len(entry_words):
            return 0
        return 1

    if significant_tokens and any(token == word for token in significant_tokens for word in entry_words):
        return 2
    for q in q_words:
        for word in entry_words:
            if q and word and (q in word or word in q):
                return 2

    return None


def _find_company_product_by_lower(
    key_lower: str,
    company_products: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    key_lower = (key_lower or "").strip().lower()
    if not key_lower:
        return None
    direct = company_products.get(key_lower)
    if direct:
        return direct
    for product in company_products.values():
        name = (product.get("name") or "").strip()
        if not name:
            continue
        pname_lower = name.lower()
        if key_lower == pname_lower:
            return product
        if key_lower in pname_lower:
            return product
        if _material_names_match(key_lower, name):
            return product
    return None


def _find_type_candidate(
    ctx: QuoteServiceContext,
    requested_type: MaterialType,
) -> Optional[Dict[str, Any]]:
    for entry in ctx.catalog_items:
        if _classify_product_entry(entry) == requested_type:
            return entry
    return None


def _validate_materials(
    materials: List[dict],
    ctx: QuoteServiceContext,
    *,
    company_id: Optional[str],
    context_text: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not materials:
        return [], []

    company_products = _load_company_catalog_products(company_id)
    company_synonyms = _load_company_synonym_map(company_id)

    seen: set[str] = set()
    results: List[Dict[str, Any]] = []
    unknown: List[Dict[str, Any]] = []

    for item in materials:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        item_context = item.get("context_text") or context_text
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        match = _match_catalog_entry(
            name,
            ctx,
            company_id=company_id,
            company_products=company_products,
            company_synonyms=company_synonyms,
            context_text=item_context,
        )
        results.append(match)
        if not match["matched"]:
            unknown.append(match)

    return results, unknown


def _normalize_material_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    name = (entry.get("name") or "").strip()
    if name:
        normalized["name"] = name
    sku_val = (entry.get("sku") or "").strip()
    if sku_val:
        normalized["sku"] = sku_val
    raw_qty = entry.get("menge")
    qty_val: Optional[float]
    try:
        qty_val = float(raw_qty)
    except (TypeError, ValueError):
        qty_val = None
    if qty_val is None:
        normalized["menge"] = 0.0
    else:
        normalized["menge"] = int(qty_val) if qty_val.is_integer() else round(qty_val, 3)
    normalized["einheit"] = _normalize_unit(entry.get("einheit") or "")
    if entry.get("locked"):
        normalized["locked"] = True
    if entry.get("locked_menge") not in (None, ""):
        try:
            locked_qty = float(entry.get("locked_menge"))
        except (TypeError, ValueError):
            locked_qty = None
        if locked_qty is not None:
            normalized["locked_menge"] = int(locked_qty) if locked_qty.is_integer() else round(locked_qty, 3)
            normalized["locked"] = True
    locked_unit = entry.get("locked_einheit") or entry.get("locked_unit")
    if locked_unit:
        normalized["locked_einheit"] = _normalize_unit(locked_unit)
    if entry.get("context_text"):
        normalized["context_text"] = entry.get("context_text")
    return normalized


def _material_key_and_canonical(
    name: str,
    ctx: QuoteServiceContext,
    *,
    company_id: Optional[str],
    company_products: Dict[str, Dict[str, Any]],
    company_synonyms: Dict[str, str],
    context_text: Optional[str],
) -> Tuple[str, str, Optional[str]]:
    match = _match_catalog_entry(
        name,
        ctx,
        company_id=company_id,
        company_products=company_products,
        company_synonyms=company_synonyms,
        context_text=context_text,
    )
    canonical = (match.get("canonical_name") or _normalize_material_name(name) or name).strip()
    key = canonical.lower()
    if not key:
        key = (_normalize_material_name(name) or name).strip().lower()
    sku = (match.get("sku") or "").strip() or None
    return key, canonical or name, sku


def _apply_material_override(
    current: Dict[str, Any],
    update: Dict[str, Any],
    *,
    canonical_name: Optional[str],
    canonical_sku: Optional[str],
    has_qty: bool,
    has_unit: bool,
    lock_quantity: bool,
    context_text: Optional[str],
) -> Tuple[Dict[str, Any], bool]:
    changed = False
    target = canonical_name or (update.get("name") or "").strip() or current.get("name")
    if target and target != current.get("name"):
        current["name"] = target
        changed = True
    if canonical_sku and canonical_sku != current.get("sku"):
        current["sku"] = canonical_sku
        changed = True
    if has_qty:
        qty_val = update.get("menge")
        if qty_val is not None and qty_val != current.get("menge"):
            current["menge"] = qty_val
            changed = True
    if has_unit:
        unit_val = update.get("einheit") or ""
        if unit_val and unit_val != current.get("einheit"):
            current["einheit"] = unit_val
            changed = True
    if lock_quantity and has_qty:
        current["locked"] = True
        current["locked_menge"] = update.get("menge")
        lock_unit = update.get("einheit") or current.get("einheit")
        if lock_unit:
            current["locked_einheit"] = lock_unit
    elif lock_quantity and not has_qty and current.get("locked_menge") is not None:
        current["locked"] = True
    if context_text:
        current["context_text"] = context_text
    return current, changed


def _merge_material_state(
    previous_items: List[Dict[str, Any]],
    new_items: List[Dict[str, Any]],
    ctx: QuoteServiceContext,
    *,
    company_id: Optional[str],
    lock_on_update: bool = False,
    context_text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    prev_normalized = [
        _normalize_material_entry(item)
        for item in (previous_items or [])
        if (item.get("name") or "").strip()
    ]
    if not new_items:
        return [dict(entry) for entry in prev_normalized]

    company_products = _load_company_catalog_products(company_id)
    company_synonyms = _load_company_synonym_map(company_id)

    merged = [dict(entry) for entry in prev_normalized]
    base_lookup: Dict[str, int] = {}
    for idx, entry in enumerate(merged):
        key, _, sku = _material_key_and_canonical(
            entry.get("name") or "",
            ctx,
            company_id=company_id,
            company_products=company_products,
            company_synonyms=company_synonyms,
            context_text=context_text,
        )
        if key:
            base_lookup.setdefault(key, idx)
        if sku and not entry.get("sku"):
            entry["sku"] = sku

    for raw in new_items:
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        has_qty = raw.get("menge") not in (None, "")
        has_unit = bool(raw.get("einheit"))
        normalized_update = _normalize_material_entry(raw)
        key, canonical, detected_sku = _material_key_and_canonical(
            name,
            ctx,
            company_id=company_id,
            company_products=company_products,
            company_synonyms=company_synonyms,
            context_text=context_text,
        )
        target_idx = base_lookup.get(key)
        if target_idx is None and canonical:
            for idx, existing in enumerate(merged):
                if _material_names_match(canonical, existing.get("name", "")):
                    target_idx = idx
                    break
        if target_idx is not None:
            updated_entry, _ = _apply_material_override(
                merged[target_idx],
                normalized_update,
                canonical_name=canonical,
                canonical_sku=detected_sku,
                has_qty=has_qty,
                has_unit=has_unit,
                lock_quantity=bool(lock_on_update and has_qty),
                context_text=context_text,
            )
            merged[target_idx] = updated_entry
            continue
        new_entry = dict(normalized_update)
        if canonical:
            new_entry["name"] = canonical
        if detected_sku:
            new_entry["sku"] = detected_sku
        if lock_on_update and has_qty:
            new_entry["locked"] = True
            new_entry["locked_menge"] = new_entry.get("menge")
            new_entry["locked_einheit"] = new_entry.get("einheit")
        if context_text:
            new_entry["context_text"] = context_text
        merged.append(new_entry)
        if key:
            base_lookup.setdefault(key, len(merged) - 1)

    return merged


def _parse_pack_value(candidate: str, unit_hint: str) -> Optional[Tuple[float, str]]:
    text = (candidate or "").strip()
    if not text:
        return None
    match = PACK_SIZE_PATTERN.search(text)
    if match:
        value = float(match.group(1).replace(",", "."))
        unit = _normalize_unit(match.group(2))
        return value, unit
    try:
        value = float(text.replace(",", "."))
    except (TypeError, ValueError):
        return None
    unit = unit_hint or ""
    if unit:
        return value, unit
    return None


def _resolve_pack_info(
    entry: Optional[Dict[str, Any]],
    fallback_name: Optional[str],
) -> Optional[Tuple[float, str]]:
    unit_hint = _normalize_unit(entry.get("unit") or "") if entry else ""
    candidates: List[str] = []
    if entry:
        pack_sizes = entry.get("pack_sizes")
        if isinstance(pack_sizes, list):
            candidates.extend(str(item) for item in pack_sizes if item not in (None, ""))
        elif pack_sizes not in (None, ""):
            candidates.append(str(pack_sizes))
        if entry.get("description"):
            candidates.append(str(entry["description"]))
        if entry.get("name"):
            candidates.append(str(entry["name"]))
    if fallback_name:
        candidates.append(str(fallback_name))
    for candidate in candidates:
        info = _parse_pack_value(candidate, unit_hint)
        if info:
            value, unit = info
            canonical = _resolve_canonical_unit(unit, candidate, candidate)
            return value, canonical
    return None


def _resolve_canonical_unit(
    product_unit: Optional[str],
    name: Optional[str],
    description: Optional[str],
) -> str:
    raw = (product_unit or "").strip().lower()
    if raw in BASE_UNIT_MAP:
        return BASE_UNIT_MAP[raw]
    if raw in CONTAINER_UNITS or not raw:
        sources = [name or "", description or ""]
        for text in sources:
            for match in UNIT_HINT_PATTERN.finditer(text):
                candidate = match.group(2).lower()
                if candidate in BASE_UNIT_MAP:
                    return BASE_UNIT_MAP[candidate]
        return "Stück"
    return BASE_UNIT_MAP.get(raw, "Stück")


def _enforce_locked_quantities(
    positions: List[Dict[str, Any]],
    latest_items: List[Dict[str, Any]],
    ctx: QuoteServiceContext,
) -> List[Dict[str, Any]]:
    if not positions or not latest_items:
        return positions
    locked_items = [
        item for item in latest_items if item.get("locked") and item.get("locked_menge") not in (None, "")
    ]
    if not locked_items:
        return positions

    def _entry_for_position(pos: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        sku = (pos.get("matched_sku") or "").strip()
        if sku:
            return ctx.catalog_by_sku.get(sku)
        name = (pos.get("name") or "").strip().lower()
        if name:
            return ctx.catalog_by_name.get(name)
        return None

    def _match_position(item: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        sku_target = (item.get("sku") or "").strip().lower()
        for pos in positions:
            pos_sku = (pos.get("matched_sku") or "").strip().lower()
            if sku_target and pos_sku == sku_target:
                return pos, _entry_for_position(pos)
        target_name = (item.get("name") or "").strip()
        for pos in positions:
            pname = (pos.get("name") or "").strip()
            if pname and target_name and _material_names_match(pname, target_name):
                return pos, _entry_for_position(pos)
        return None, None

    for item in locked_items:
        locked_qty_raw = item.get("locked_menge", item.get("menge"))
        try:
            locked_qty = float(locked_qty_raw)
        except (TypeError, ValueError):
            continue
        if locked_qty <= 0:
            continue
        pos, entry = _match_position(item)
        if not pos:
            continue
        try:
            current_qty = float(pos.get("menge", 0))
        except (TypeError, ValueError):
            current_qty = 0.0
        locked_unit = _resolve_canonical_unit(
            item.get("locked_einheit") or item.get("einheit"),
            item.get("name"),
            None,
        )
        target_unit = (
            _resolve_canonical_unit(entry.get("unit"), entry.get("name"), entry.get("description"))
            if entry
            else _resolve_canonical_unit(pos.get("einheit"), pos.get("name"), None)
        )
        if locked_unit and target_unit and locked_unit != target_unit:
            locked_unit = target_unit
        min_required = max(current_qty, locked_qty)
        enforced_qty = min_required
        pack_info = _resolve_pack_info(entry, pos.get("name"))
        if pack_info and target_unit and _normalize_unit(pack_info[1]) == target_unit:
            pack_value = float(pack_info[0])
            if pack_value > 0:
                packs_needed = math.ceil(min_required / pack_value)
                enforced_qty = packs_needed * pack_value
        if enforced_qty > current_qty + 1e-6:
            pos["menge"] = int(enforced_qty) if float(enforced_qty).is_integer() else round(enforced_qty, 3)
            if target_unit:
                pos["einheit"] = target_unit
            if pos.get("epreis") not in (None, ""):
                try:
                    epreis_val = float(pos.get("epreis", 0))
                except (TypeError, ValueError):
                    epreis_val = 0.0
                pos["gesamtpreis"] = round(epreis_val * float(pos["menge"]), 2)
            pos.setdefault("reasons", []).append("locked_quantity")
    return positions


def _format_unknown_products_reply(unknown_entries: List[Dict[str, Any]]) -> str:
    if not unknown_entries:
        return ""
    lines = [
        "**Produktprüfung**",
        "",
        "Folgende Produkte konnten wir nicht im Katalog finden:",
    ]
    for entry in unknown_entries:
        line = f"- {entry['query']}"
        suggestions = entry.get("suggestions") or []
        if suggestions:
            line += f" (ähnliche Treffer: {', '.join(suggestions[:3])})"
        lines.append(line)
    lines.append("")
    lines.append(
        "Bitte nennen Sie alternative Produkte aus dem vorhandenen Katalog oder lassen Sie Ihren Innendienst die Datenbank erweitern."
    )
    return "\n".join(lines).strip()


class ServiceError(Exception):
    """Domain specific error that can be translated to HTTP responses."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class QuoteServiceContext:
    chain1: Any | None
    chain2: Any | None
    llm1: Any | None
    llm2: Any | None
    prompt2: Any | None
    memory1: Any | None
    retriever: Any | None
    reset_callback: Callable[[], None] | None
    documents: List[Any]
    catalog_items: List[Dict[str, Any]]
    catalog_by_name: Dict[str, Dict[str, Any]]
    catalog_by_sku: Dict[str, Dict[str, Any]]
    catalog_text_by_name: Dict[str, str]
    catalog_text_by_sku: Dict[str, str]
    catalog_search_cache: Dict[Tuple[str, int], Tuple[float, List[Dict[str, Any]]]]
    wizard_sessions: Dict[str, Dict[str, Any]]
    env: Environment
    output_dir: Path
    vat_rate: float
    synonyms_path: Path
    logger: Any
    llm1_mode: str = "assistive"
    adopt_threshold: float = 0.82
    business_scoring: List[str] = field(default_factory=list)
    llm1_thin_retrieval: bool = False
    catalog_top_k: int = 5
    catalog_cache_ttl: int = 60
    catalog_queries_per_turn: int = 2
    skip_llm_setup: bool = False
    default_company_id: str = "default"
    debug: bool = False


# Wizard configuration stays alongside service logic so it can be reused elsewhere.
MALER_STEPS: List[Dict[str, Any]] = [
    {"key": "innen_aussen",      "question": "Innen oder Außen?",                                   "ui": {"type": "singleSelect", "options": ["Innen", "Aussen"]}},
    {"key": "untergrund",        "question": "Welcher Untergrund?",                                 "ui": {"type": "singleSelect", "options": ["Putz","Gipskarton","Beton","Altanstrich","Tapete","unbekannt"]}},
    {"key": "flaeche_m2",        "question": "Wie groß ist die zu streichende Wandfläche in m²? (0, falls keine)",   "ui": {"type": "number", "min": 0, "max": 10000, "step": 1}},
    {"key": "deckenflaeche_m2",  "question": "Wie groß ist die zu streichende Deckenfläche in m²? (0, falls keine)", "ui": {"type": "number", "min": 0, "max": 10000, "step": 1}},
    {"key": "anzahl_schichten",  "question": "Wie viele Anstriche (Schichten)?",                     "ui": {"type": "number", "min": 1, "max": 5, "step": 1}},
    {"key": "vorarbeiten",       "question": "Vorarbeiten auswählen (optional)",                      "ui": {"type": "multiSelect", "options": ["Abkleben","Spachteln","Grundieren","Schleifen","Ausbessern"]}},
    {"key": "abklebeflaeche_m",  "question": "Geschätzte Abklebekanten in Metern? (optional, 0 wenn unbekannt)", "ui": {"type": "number", "min": 0, "max": 1000, "step": 1}},
    {"key": "besonderheiten",    "question": "Gibt es Besonderheiten? (z. B. Schimmel, Nikotin, etc.)",           "ui": {"type": "singleSelect", "options": ["keine","Nikotin","Schimmel","Feuchtraum","Dunkle Altfarbe"]}},
]

APP_BASE_DIR = Path(__file__).resolve().parents[1]
REVENUE_GUARD_CONFIG_PATH = Path(
    os.getenv("REVENUE_GUARD_CONFIG", str(APP_BASE_DIR / "data" / "revenue_guard_materials.json"))
)


def reset_session(*, ctx: QuoteServiceContext, reason: Optional[str] = None) -> Dict[str, Any]:
    """
    Reset wizard sessions and, when possible, rebuild the LLM chains/state.

    Args:
        ctx: Shared service context containing wizard sessions and reset callback.
        reason: Optional human readable reason for audit/logging (currently informational).

    Returns:
        Dict with ok/message fields mirroring the HTTP endpoint contract.
    """
    if ctx.skip_llm_setup:
        ctx.wizard_sessions.clear()
        return {"ok": True, "message": "LLM-Reset übersprungen: SKIP_LLM_SETUP=1 (Smoke-Test-Modus)."}

    if ctx.reset_callback:
        ctx.reset_callback()
        ctx.wizard_sessions.clear()
        return {"ok": True, "message": "Server state cleared (memory + wizard sessions)."}

    ctx.wizard_sessions.clear()
    return {"ok": True, "message": "Wizard sessions cleared; LLM reset callback unavailable."}


CONFIRM_USER_RE = re.compile(
    r"(passen\s*so|passen|stimmen\s*so|stimmen|best[aä]tig|übernehmen|so\s*übernehmen|klingt\s*g?ut|"
    r"mengen\s*(?:sind\s*)?(?:korrekt|okay|in\s*ordnung)|freigeben|erstelle\s+(?:das\s+)?angebot|"
    r"ja[,!\s]*(?:bitte\s*)?(?:das\s*)?angebot)",
    re.IGNORECASE,
)
CONFIRM_REPLY_RE = re.compile(r"status\s*:\s*best[aä]tigt", re.IGNORECASE)
SUG_RE = re.compile(
    r"name\s*=\s*(.+?),\s*menge\s*=\s*([0-9]+(?:[.,][0-9]+)?)\s*,\s*einheit\s*=\s*([A-Za-zÄÖÜäöü]+)",
    re.IGNORECASE,
)
BULLET_LINE_RE = re.compile(r"^[\-\*]\s*([^:\n]+?)\s*:\s*(.+)$", re.MULTILINE)
_UNIT_CANDIDATES = [
    "m²", "m2", "m^2", "qm", "m³", "m3", "m", "lfm", "cm", "mm",
    "kg", "g", "t", "l", "L", "ml", "dl", "cl", "liter",
    "stück", "Stück", "stk", "Stk", "sack", "Sack",
    "rolle", "Rolle", "rollen", "Rollen",
    "platte", "Platte", "platten", "Platten",
    "paket", "Paket", "pakete", "Pakete",
    "eimer", "Eimer", "kartusche", "Kartusche", "kartuschen", "Kartuschen",
    "set", "Set", "sets", "Sets", "beutel", "Beutel",
]
_UNIT_PATTERN = "|".join(sorted({re.escape(u) for u in _UNIT_CANDIDATES}, key=len, reverse=True))
LAST_QTY_UNIT_RE = re.compile(rf"([0-9]+(?:[.,][0-9]+)?)\s*({_UNIT_PATTERN})(?![A-Za-zÄÖÜäöü0-9])", re.IGNORECASE)
CATALOG_BLOCK_RE = re.compile(r"---\s*status:\s*katalog\s*candidates:\s*(.*?)---", re.IGNORECASE | re.DOTALL)
MACHINE_BLOCK_RE = re.compile(
    r"---\s*(?:projekt_id:.*?\n)?(?:version:.*?\n)?status:\s*([a-zäöüß]+)\s*materialien:\s*(.*?)---",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_query(text: str) -> str:
    return shared_normalize_query(text)


def _tokenize(text: str) -> set[str]:
    return set(shared_tokenize(text))


def _catalog_cache_key(query: str, limit: int) -> Tuple[str, int]:
    return (_normalize_query(query), limit)


def _score_entry(query: str, entry: Dict[str, Any]) -> float:
    q = _normalize_query(query)
    if not q:
        return 0.0
    name_raw = (entry.get("name") or "")
    name = _normalize_query(name_raw)
    if not name:
        return 0.0
    if q == name:
        return 1.0
    if q in name:
        base = SequenceMatcher(None, q, name).ratio()
        return max(base, 0.85)

    q_tokens = _tokenize(q)
    name_tokens = _tokenize(name)
    overlap = len(q_tokens & name_tokens)
    ratio = SequenceMatcher(None, q, name).ratio()
    if overlap:
        ratio = max(ratio, 0.6 + 0.1 * min(overlap, 3))
    compact_q = q.replace(" ", "")
    compact_name = name.replace(" ", "")
    if compact_q and compact_name and compact_q in compact_name:
        ratio = max(ratio, 0.82)

    desc_raw = (entry.get("description") or "")
    desc = _normalize_query(desc_raw)
    if desc:
        if q == desc:
            ratio = max(ratio, 0.9)
        if q in desc:
            ratio = max(ratio, 0.8)
        desc_tokens = _tokenize(desc)
        overlap_desc = len(q_tokens & desc_tokens)
        if overlap_desc:
            ratio = max(ratio, 0.55 + 0.1 * min(overlap_desc, 3))
        ratio = max(ratio, SequenceMatcher(None, q, desc).ratio())
        compact_desc = desc.replace(" ", "")
        if compact_q and compact_desc and compact_q in compact_desc:
            ratio = max(ratio, 0.78)

    for syn in entry.get("synonyms") or []:
        s = _normalize_query(syn or "")
        if not s:
            continue
        if q == s:
            return 0.95
        if q in s:
            ratio = max(ratio, 0.85)
        ratio = max(ratio, SequenceMatcher(None, q, s).ratio())

    return ratio


def _catalog_lookup(query: str, limit: int, ctx: QuoteServiceContext) -> List[Dict[str, Any]]:
    if not query:
        return []

    top_k = min(limit, ctx.catalog_top_k)
    key = _catalog_cache_key(query, top_k)
    now = time.time()
    cached = ctx.catalog_search_cache.get(key)
    if cached and now - cached[0] <= ctx.catalog_cache_ttl:
        return cached[1]

    q_lower = _normalize_query(query)
    lexical_candidates: List[Tuple[float, Dict[str, Any]]] = []
    for item in ctx.catalog_items:
        score = _score_entry(q_lower, item)
        if score >= 0.55:
            lexical_candidates.append((score, item))

    lexical_candidates.sort(key=lambda tpl: tpl[0], reverse=True)
    if lexical_candidates:
        selected = lexical_candidates[:top_k]
        results = [
            {
                "sku": item.get("sku"),
                "name": item.get("name"),
                "unit": item.get("unit"),
                "pack_sizes": item.get("pack_sizes"),
                "synonyms": item.get("synonyms") or [],
                "category": item.get("category"),
                "brand": item.get("brand"),
                "confidence": round(score, 3),
            }
            for score, item in selected
        ]
        ctx.catalog_search_cache[key] = (now, results)
        return results

    if ctx.retriever is None:
        return []

    try:
        docs = ctx.retriever.get_relevant_documents(query)[: max(top_k * 2, top_k)]  # type: ignore[union-attr]
    except Exception:
        return []

    seen: set[str] = set()
    scored: List[Tuple[float, Dict[str, Any]]] = []

    for doc in docs:
        meta = getattr(doc, "metadata", None) or {}
        name = meta.get("name")
        sku = meta.get("sku")

        entry: Optional[Dict[str, Any]] = None
        if sku and sku in ctx.catalog_by_sku:
            entry = ctx.catalog_by_sku[sku]
        elif name and name.lower() in ctx.catalog_by_name:
            entry = ctx.catalog_by_name[name.lower()]

        if entry is None:
            entry = _document_to_catalog_entry(doc)

        key_seen = entry.get("sku") or entry.get("name") or str(entry)
        if key_seen in seen:
            continue

        score = _score_entry(q_lower, entry)
        if score < 0.45:
            continue

        seen.add(key_seen)
        scored.append((score, entry))
        if len(scored) >= top_k:
            break

    scored.sort(key=lambda tpl: tpl[0], reverse=True)
    results = [
        {
            "sku": item.get("sku"),
            "name": item.get("name"),
            "unit": item.get("unit"),
            "pack_sizes": item.get("pack_sizes"),
            "synonyms": item.get("synonyms") or [],
            "category": item.get("category"),
            "brand": item.get("brand"),
            "confidence": round(score, 3),
        }
        for score, item in scored[:top_k]
    ]
    ctx.catalog_search_cache[key] = (now, results)
    return results


def _document_to_catalog_entry(doc) -> Dict[str, Any]:
    text = (getattr(doc, "page_content", "") or "").strip()
    lines = text.splitlines()
    fallback_name = ""
    if lines:
        first = lines[0]
        fallback_name = first.replace("Produkt:", "", 1).strip()

    meta = getattr(doc, "metadata", None) or {}
    name = meta.get("name") or fallback_name
    if name:
        sku = meta.get("sku") or _sku_from_name(name)
    else:
        sku = meta.get("sku") or _sku_from_name(text)
    return {
        "sku": sku,
        "name": name,
        "unit": meta.get("unit"),
        "pack_sizes": meta.get("pack_sizes"),
        "synonyms": meta.get("synonyms") or [],
        "category": meta.get("category"),
        "brand": meta.get("brand"),
        "description": meta.get("description"),
        "raw": text,
    }


def _sku_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or f"produkt-{abs(hash(name))}"


def _company_catalog_search(company_id: str, query: str, limit: int, ctx: QuoteServiceContext) -> List[Dict[str, object]]:
    try:
        hits = index_manager.search_index(company_id, query, top_k=limit)
    except Exception as exc:
        ctx.logger.warning("company catalog search failed for %s: %s", company_id, exc)
        hits = []
    results: List[Dict[str, object]] = []
    for hit in hits:
        results.append(
            {
                "sku": hit.get("sku"),
                "name": hit.get("name"),
                "unit": None,
                "pack_sizes": None,
                "synonyms": [],
                "category": None,
                "brand": None,
                "confidence": 1.0,
            }
        )
    return results


def _normalize_unit(u: str) -> str:
    u = (u or "").strip()
    lower = u.lower()
    if lower in {"m2", "m^2", "qm"}:
        return "m²"
    if lower in {"m3", "m^3"}:
        return "m³"
    if lower in {"stk", "stück"}:
        return "Stück"
    if lower in {"rolle", "rollen"}:
        return "Rolle"
    if lower in {"sack"}:
        return "Sack"
    if lower in {"platte", "platten"}:
        return "Platte"
    if lower in {"paket", "pakete"}:
        return "Paket"
    if lower in {"set", "sets"}:
        return "Set"
    if lower in {"kartusche", "kartuschen"}:
        return "Kartusche"
    if lower in {"eimer"}:
        return "Eimer"
    if lower in {"beutel"}:
        return "Beutel"
    if lower in {"liter"}:
        return "L"
    return u


def _extract_materials_from_text_any(text: str) -> list[dict]:
    items = []
    for m in SUG_RE.finditer(text or ""):
        items.append({
            "name": (m.group(1) or "").strip(),
            "menge": float((m.group(2) or "0").replace(",", ".")),
            "einheit": (m.group(3) or "").strip(),
        })
    if items:
        return items
    for m in BULLET_LINE_RE.finditer(text or ""):
        name = (m.group(1) or "").strip()
        rest = (m.group(2) or "").strip()
        match_candidates = list(LAST_QTY_UNIT_RE.finditer(rest))
        if not match_candidates:
            continue
        qty_match = match_candidates[-1]
        qty_raw = qty_match.group(1) or "0"
        unit_raw = qty_match.group(2) or ""
        try:
            qty = float(qty_raw.replace(",", "."))
        except ValueError:
            continue
        unit = _normalize_unit(unit_raw)
        items.append({"name": name, "menge": qty, "einheit": unit})
    return items


def _make_machine_block(status: str, items: list[dict]) -> str:
    lines = []
    for it in items:
        name = it.get("name") or ""
        menge = it.get("menge")
        einheit = it.get("einheit") or ""
        base = f"- name={name}, menge={menge}, einheit={einheit}"
        extras: List[str] = []
        sku = (it.get("sku") or "").strip()
        if sku:
            extras.append(f"sku={sku}")
        if it.get("locked"):
            extras.append("locked=1")
            locked_qty = it.get("locked_menge", menge)
            if locked_qty not in (None, ""):
                extras.append(f"locked_qty={locked_qty}")
            locked_unit = it.get("locked_einheit") or it.get("einheit")
            if locked_unit:
                extras.append(f"locked_unit={locked_unit}")
        if extras:
            base += ", " + ", ".join(extras)
        lines.append(base)
    return f"---\nstatus: {status}\nmaterialien:\n" + "\n".join(lines) + "\n---"


def _strip_machine_sections(text: str) -> str:
    if not text:
        return ""
    cleaned = MACHINE_BLOCK_RE.sub("", text)
    cleaned = CATALOG_BLOCK_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _build_catalog_candidates(
    items: List[dict],
    ctx: QuoteServiceContext,
    context_text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not ctx.llm1_thin_retrieval or not items:
        return []

    candidates: List[Dict[str, Any]] = []
    seen_queries: set[str] = set()
    for item in items:
        query = (item.get("name") or "").strip()
        if not query:
            continue
        requested_type = _classify_requested_material_type(query, context_text)
        key = query.lower()
        if key in seen_queries or len(seen_queries) >= ctx.catalog_queries_per_turn:
            continue
        seen_queries.add(key)

        try:
            raw_hits = _run_thin_catalog_search(
                query=query,
                top_k=ctx.catalog_top_k,
                catalog_items=ctx.catalog_items,
                synonyms_path=str(ctx.synonyms_path),
            )
        except Exception as exc:
            ctx.logger.warning("LLM1 thin retrieval failed for %s: %s", query, exc)
            raw_hits = []

        matches: List[Dict[str, Any]] = []
        for hit in raw_hits:
            score_final = float(hit.get("score_final", hit.get("confidence", 0.0)) or 0.0)
            product_entry = None
            hit_sku = (hit.get("sku") or "").strip()
            if hit_sku:
                product_entry = ctx.catalog_by_sku.get(hit_sku)
            if not product_entry and hit.get("name"):
                product_entry = ctx.catalog_by_name.get((hit.get("name") or "").strip().lower())
            product_type = _classify_product_entry(product_entry, hit.get("name"))
            if product_entry and not _is_type_compatible(requested_type, product_type, context_text):
                continue
            mapped = {
                "sku": hit.get("sku"),
                "name": hit.get("name"),
                "unit": hit.get("unit"),
                "pack_sizes": hit.get("pack_sizes"),
                "synonyms": hit.get("synonyms", []),
                "category": hit.get("category"),
                "brand": hit.get("brand"),
                "confidence": round(score_final, 3),
                "score_final": score_final,
                "hard_filters_passed": bool(hit.get("hard_filters_passed", True)),
            }
            matches.append(mapped)

        best = matches[0] if matches else None
        unit = best.get("unit") if best and best.get("unit") else item.get("einheit")
        status = "matched" if best else "oov"
        adoptable = False
        selected_catalog_item_id: Optional[str] = None
        selection_reason = ""

        if best:
            allowed = _adopt_candidate_allowed(query, best)
            best_score = float(best.get("score_final", 0.0))
            if ctx.llm1_mode == "strict":
                if allowed:
                    adoptable = True
            elif ctx.llm1_mode == "merge":
                if allowed and best_score >= ctx.adopt_threshold:
                    adoptable = True
                    selected_catalog_item_id = best.get("sku")
                    selection_reason = "rule"
                    status = "matched"
                    if best.get("unit"):
                        unit = best.get("unit")

        candidates.append(
            {
                "query": query,
                "canonical_name": best.get("name") if best else None,
                "unit": _normalize_unit(unit) if unit else "",
                "matched_sku": best.get("sku") if best else None,
                "confidence": best.get("confidence") if best else None,
                "status": status,
                "oov": status != "matched",
                "options": matches,
                "adoptable": adoptable,
                "selected_catalog_item_id": selected_catalog_item_id,
                "selection_reason": selection_reason,
            }
        )
    return candidates


def _make_catalog_block(candidates: List[Dict[str, Any]]) -> str:
    rows = []
    for cand in candidates:
        conf = cand.get("confidence")
        conf_str = f"{float(conf):.3f}" if conf not in (None, "") else ""
        parts = [
            f"query={cand.get('query', '')}",
            f"canonical={cand.get('canonical_name', '') or ''}",
            f"unit={cand.get('unit', '') or ''}",
            f"sku={cand.get('matched_sku', '') or ''}",
            f"status={cand.get('status', '') or ''}",
            f"oov={'1' if cand.get('oov') else '0'}",
            f"confidence={conf_str}",
        ]
        if "adoptable" in cand:
            parts.append(f"adoptable={'1' if cand.get('adoptable') else '0'}")
        if "selected_catalog_item_id" in cand:
            parts.append(f"selected={cand.get('selected_catalog_item_id') or ''}")
        if "selection_reason" in cand:
            parts.append(f"reason={cand.get('selection_reason') or ''}")
        rows.append("- " + "; ".join(parts))
    return "---\nstatus: katalog\ncandidates:\n" + "\n".join(rows) + "\n---"


def _adopt_candidate_allowed(item_name: str, best: dict) -> bool:
    if not item_name:
        return False
    if not best.get("hard_filters_passed"):
        return False
    title = (best.get("name") or "").strip()
    if not title:
        return False
    title_toks = set(shared_tokenize(title))
    item_toks = set(shared_tokenize(item_name))
    if not title_toks or not item_toks:
        return False
    return bool(item_toks & title_toks)


def _extract_catalog_map(text: str) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    if not text:
        return mapping
    for block in CATALOG_BLOCK_RE.finditer(text):
        body = block.group(1)
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line.startswith("-"):
                continue
            data: Dict[str, Any] = {}
            for part in line.lstrip("- ").split(";"):
                part = part.strip()
                if not part or "=" not in part:
                    continue
                key, value = part.split("=", 1)
                data[key.strip()] = value.strip()
            query = data.get("query")
            if not query:
                continue
            mapping[query.lower()] = {
                "canonical_name": data.get("canonical") or None,
                "unit": data.get("unit") or None,
                "matched_sku": data.get("sku") or None,
                "status": data.get("status") or None,
                "oov": data.get("oov") == "1",
            }
    return mapping


def _extract_last_machine_items(history: str, prefer_status: Optional[str] = None) -> list[dict]:
    if not history:
        return []
    blocks = []
    for match in MACHINE_BLOCK_RE.finditer(history):
        status = (match.group(1) or "").strip().lower()
        body = match.group(2) or ""
        items = []
        for raw_line in body.splitlines():
            line = (raw_line or "").strip()
            if not line.startswith("- name=") or ", menge=" not in line or ", einheit=" not in line:
                continue
            try:
                name_part, rest = line.split(", menge=", 1)
                qty_part, unit_rest = rest.split(", einheit=", 1)
            except ValueError:
                continue
            name_val = name_part.replace("- name=", "", 1).strip()
            qty_str = qty_part.strip()
            unit_clean = unit_rest.strip()
            extra = ""
            if ", " in unit_clean:
                unit_clean, extra = unit_clean.split(", ", 1)
            elif ",\t" in unit_clean:
                unit_clean, extra = unit_clean.split(",\t", 1)
            try:
                menge_val = float(qty_str.replace(",", "."))
            except ValueError:
                menge_val = 0.0
            entry = {
                "name": name_val,
                "menge": menge_val,
                "einheit": unit_clean.strip(),
            }
            if extra:
                for token in extra.split(","):
                    token = token.strip()
                    if not token or "=" not in token:
                        continue
                    key, value = token.split("=", 1)
                    key = key.strip().lower()
                    value = value.strip()
                    if key == "locked":
                        entry["locked"] = value in {"1", "true", "True"}
                    elif key == "locked_qty":
                        try:
                            entry["locked_menge"] = float(value.replace(",", "."))
                        except ValueError:
                            pass
                    elif key == "locked_unit":
                        entry["locked_einheit"] = value
                    elif key == "sku":
                        entry["sku"] = value
            items.append(entry)
        blocks.append({"status": status, "items": items})

    if not blocks:
        return []

    if prefer_status:
        prefer = prefer_status.lower()
        for block in reversed(blocks):
            if block["status"] == prefer and block["items"]:
                return block["items"]

    for block in reversed(blocks):
        if block["items"]:
            return block["items"]
    return []


def _ctx_to_brief(ctx: dict) -> str:
    innen_aussen = ctx.get("innen_aussen") or ctx.get("innen_außen") or "unbekannt"
    untergrund = ctx.get("untergrund") or "unbekannt"
    flaeche = float(ctx.get("flaeche_m2") or 0)
    decke = float(ctx.get("deckenflaeche_m2") or 0)
    schichten = int(ctx.get("anzahl_schichten") or 2)
    vorarb = ctx.get("vorarbeiten") or []
    if isinstance(vorarb, str):
        vorarb = [vorarb]
    return (
        "Projekt: Malerarbeiten\n"
        f"Bereich: {innen_aussen}\n"
        f"Untergrund: {untergrund}\n"
        f"Wandfläche: {flaeche:.0f} m²\n"
        f"Deckenfläche: {decke:.0f} m²\n"
        f"Anzahl Anstriche: {schichten}\n"
        f"Vorarbeiten: {', '.join(vorarb) if vorarb else 'keine'}"
    )


def _parse_materialien(text: str) -> List[dict]:
    if not text:
        return []
    out = []
    for i, m in enumerate(SUG_RE.finditer(text), start=1):
        name = (m.group(1) or "").strip()
        menge = float((m.group(2) or "0").replace(",", "."))
        einheit = (m.group(3) or "").strip()
        out.append({"nr": i, "name": name, "menge": round(menge, 2), "einheit": einheit, "text": ""})
    return out


def suggest_with_llm1(ctx_dict: dict, ctx: QuoteServiceContext, limit: int = 6) -> List[dict]:
    if ctx.skip_llm_setup or ctx.llm1 is None:
        raise ServiceError("LLM1 ist deaktiviert (SKIP_LLM_SETUP=1).", status_code=503)
    brief = _ctx_to_brief(ctx_dict)
    prompt = f"""
Du bist Malermeister. Schätze den Materialbedarf in **Basis-Einheiten** (kg, L, m², m, Stück, Platte).

Heuristiken:
- Dispersionsfarbe: 1 L / 10 m² **pro Schicht** + 10 % Reserve (Wände/Decken).
- Tiefgrund: 1 L / 10 m² (bei saugendem Untergrund wie Putz/Beton).
- Abdeckfolie (4×5 m ≈ 20 m²/Rolle): ~1 Rolle / 40 m² begeh-/bewohnter Fläche.
- Abklebeband: ~1 Rolle / 25 m Kanten/Anschlüsse (Standardraum grob 1 Rolle/Raum).
- Nur sinnvolle Verbrauchsmaterialien aufführen.

Alle genannten Verbrauchswerte müssen zur berechneten Menge passen (z. B. 0,1 L/m² × 20 m² = 2 L).

GIB NUR DEN MASCHINENANHANG AUS – keine Einleitung, kein Markdown:
---
status: schätzung
materialien:
- name=..., menge=..., einheit=...
---

Nutze klare Produktbezeichnungen wie „Dispersionsfarbe, weiß, 10 L“, „Tiefgrund, 10 L“, „Abdeckfolie 4×5 m“.

Kontext:
{brief}
"""
    resp = ctx.llm1.invoke(prompt)
    txt = getattr(resp, "content", str(resp))
    items = _parse_materialien(txt)

    seen: Dict[tuple, float] = {}
    for it in items:
        key = (it["name"].lower(), it["einheit"].lower())
        seen[key] = seen.get(key, 0.0) + float(it["menge"])

    merged, i = [], 1
    for (name_l, unit_l), qty in seen.items():
        name = next((it["name"] for it in items if it["name"].lower() == name_l), name_l)
        merged.append({"nr": i, "name": name, "menge": round(qty, 2), "einheit": unit_l, "text": ""})
        i += 1
    return merged[:limit]


def _wizard_new_session(ctx: QuoteServiceContext) -> str:
    sid = uuid4().hex
    ctx.wizard_sessions[sid] = {"ctx": {}, "step_idx": 0}
    return sid


def _wizard_get_state(ctx: QuoteServiceContext, session_id: str) -> dict:
    st = ctx.wizard_sessions.get(session_id)
    if not st:
        st = {"ctx": {}, "step_idx": 0}
        ctx.wizard_sessions[session_id] = st
    return st


def _wizard_current_step(state: dict) -> dict | None:
    idx = int(state.get("step_idx", 0))
    return MALER_STEPS[idx] if 0 <= idx < len(MALER_STEPS) else None


def _wizard_next_state(state: dict) -> None:
    state["step_idx"] = int(state.get("step_idx", 0)) + 1


def _norm(s: str) -> str:
    return (s or "").lower()


def _has_any(positions: list[dict], keywords: list[str]) -> bool:
    for p in positions or []:
        name = _norm(p.get("name", ""))
        if any(k in name for k in keywords):
            return True
    return False


def _ctx_num(ctx_dict: dict, key: str, default: float = 0.0) -> float:
    try:
        v = ctx_dict.get(key, default)
        return float(v if v is not None else default)
    except Exception:
        return float(default)


def rule_primer_tiefgrund(positions: list[dict], ctx_dict: dict) -> Tuple[bool, dict | None]:
    """Fehlt Tiefgrund/Grundierung?"""
    if _has_any(positions, ["tiefgrund", "grundierung", "primer", "haftgrund"]):
        return False, None
    untergrund = _norm(ctx_dict.get("untergrund", ""))
    if not any(token in untergrund for token in ["putz", "gipskarton", "beton", "tapete", "altanstrich"]):
        return False, None
    flaeche = max(1.0, _ctx_num(ctx_dict, "flaeche_m2", 0.0) + _ctx_num(ctx_dict, "deckenflaeche_m2", 0.0))
    liter = round(flaeche / 15.0, 1)
    sug = {
        "id": "primer_tiefgrund",
        "name": "Tiefgrund / Grundierung",
        "menge": max(1.0, liter),
        "einheit": "L",
        "reason": f"Untergrund {ctx_dict.get('untergrund')} → Tiefgrund (≈1 L / 10 m²).",
        "confidence": 0.7,
        "severity": "high",
        "category": "Vorarbeiten",
    }
    return True, sug


def rule_masking_cover(positions: list[dict], ctx_dict: dict) -> Tuple[bool, dict | None]:
    """Abdeckfolie / Abdeckvlies."""
    if _has_any(positions, ["abdeckfolie", "abdeckvlies", "abdeckband", "abdecken", "schutzfolie"]):
        return False, None
    flaeche = max(1.0, _ctx_num(ctx_dict, "flaeche_m2", 0.0))
    rollen = max(1.0, math.ceil(flaeche / 40.0))
    sug = {
        "id": "masking_cover",
        "name": "Abdeckfolie 4×5 m",
        "menge": rollen,
        "einheit": "Rolle",
        "reason": f"{int(flaeche)} m² Wandfläche → Folie (≈1 Rolle / 40 m²).",
        "confidence": 0.65,
        "severity": "medium",
        "category": "Vorarbeiten",
    }
    return True, sug


def rule_masking_tape(positions: list[dict], ctx_dict: dict) -> Tuple[bool, dict | None]:
    """Abklebeband/Kreppband für Kanten/Anschlüsse."""
    if _has_any(positions, ["abklebeband", "kreppband", "abkleben"]):
        return False, None

    kanten = _ctx_num(ctx_dict, "abklebeflaeche_m", 0.0)
    if kanten <= 0 and ctx_dict.get("besonderheiten") == "keine":
        return False, None

    meter = kanten if kanten > 0 else (_ctx_num(ctx_dict, "flaeche_m2", 0.0) * 2.5)
    rollen = max(1.0, round(meter / 25.0, 1))
    sug = {
        "id": "masking_tape",
        "name": "Abklebeband / Kreppband",
        "menge": rollen,
        "einheit": "Rolle",
        "reason": f"{int(meter)} m Kanten → ≈1 Rolle / 25 m.",
        "confidence": 0.6,
        "severity": "high",
        "category": "Vorarbeiten",
    }
    return True, sug


def rule_scratch_spackle(positions: list[dict], ctx_dict: dict) -> Tuple[bool, dict | None]:
    """Kratz-/Zwischenspachtelung bei Altanstrich/Tapete."""
    if _has_any(positions, ["spachtel", "spachtelmasse", "kratzspachtel", "q2", "q3"]):
        return False, None

    untergrund = _norm(ctx_dict.get("untergrund", ""))
    if not any(k in untergrund for k in ["altanstrich", "tapete"]):
        return False, None

    flaeche = max(1.0, _ctx_num(ctx_dict, "flaeche_m2", 0.0))
    kg = round(flaeche * 0.5, 1)
    sug = {
        "id": "scratch_spackle",
        "name": "Spachtelmasse (Zwischenspachtelung)",
        "menge": kg,
        "einheit": "kg",
        "reason": f"Untergrund {ctx_dict.get('untergrund')} → Ausgleich/Haftverbesserung (≈0,5 kg/m²).",
        "confidence": 0.6,
        "severity": "medium",
        "category": "Vorarbeiten",
    }
    return True, sug


def rule_travel(positions: list[dict], ctx_dict: dict) -> Tuple[bool, dict | None]:
    """Anfahrtpauschale."""
    if _has_any(positions, ["anfahrt", "fahrtkosten", "an- und abfahrt", "anlieferung"]):
        return False, None

    dist = _ctx_num(ctx_dict, "entfernung_km", 0.0)
    tier = "Pauschale bis 10 km" if dist <= 10 else ("Pauschale bis 25 km" if dist <= 25 else "Pauschale > 25 km")
    sug = {
        "id": "travel",
        "name": f"Anfahrt ({tier})",
        "menge": 1,
        "einheit": "Pauschale",
        "reason": f"Keine Anfahrtposition gefunden (Entfernung ≈ {int(dist)} km).",
        "confidence": 0.7,
        "severity": "low",
        "category": "Allgemein",
    }
    return True, sug


REVENUE_RULES = [
    ("primer_tiefgrund", "Grundierung/Haftverbesserung fehlt?", rule_primer_tiefgrund),
    ("masking_cover", "Abdecken/Schutz fehlt?", rule_masking_cover),
    ("masking_tape", "Abklebeband fehlt?", rule_masking_tape),
    ("scratch_spackle", "Spachtelarbeiten (Kratz-/Zwischenspachtelung) fehlen?", rule_scratch_spackle),
    ("travel", "Anfahrtpauschale fehlt?", rule_travel),
]

BUILTIN_GUARD_ITEMS: List[Dict[str, Any]] = [
    {
        "id": "primer_tiefgrund",
        "name": "Tiefgrund / Grundierung",
        "severity": "medium",
        "category": "Vorarbeiten",
        "description": "Empfiehlt saugfähige Grundierung, wenn Untergrund oder Positionen keine Haftbrücke enthalten.",
        "editable": True,
    },
    {
        "id": "masking_cover",
        "name": "Abdeckmaterial",
        "severity": "medium",
        "category": "Schutz",
        "description": "Überprüft, ob Folien/Vlies zum Abdecken empfindlicher Bereiche vorgesehen sind.",
        "editable": True,
    },
    {
        "id": "masking_tape",
        "name": "Abklebeband / Kreppband",
        "severity": "high",
        "category": "Schutz",
        "description": "Empfiehlt Kreppband in passenden Rollenlängen relativ zur Kantenmeterzahl.",
        "editable": True,
    },
    {
        "id": "scratch_spackle",
        "name": "Zwischenspachtelung",
        "severity": "medium",
        "category": "Vorarbeiten",
        "description": "Schlägt Spachtelarbeiten bei Altanstrichen oder Tapeten vor.",
        "editable": True,
    },
    {
        "id": "travel",
        "name": "Anfahrtpauschale",
        "severity": "low",
        "category": "Allgemein",
        "description": "Stellt sicher, dass Fahrtkosten bzw. Pauschalen eingeplant sind.",
        "editable": True,
    },
]

BUILTIN_ID_MAP: Dict[str, Dict[str, Any]] = {item["id"]: item for item in BUILTIN_GUARD_ITEMS}
GUARD_CONFIG_CACHE: Dict[str, Any] | None = None


def _ensure_guard_config_dir() -> None:
    REVENUE_GUARD_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _guard_config_defaults() -> Dict[str, Any]:
    return {"custom": [], "overrides": {}}


def _load_guard_config() -> Dict[str, Any]:
    global GUARD_CONFIG_CACHE
    if GUARD_CONFIG_CACHE is not None:
        return GUARD_CONFIG_CACHE

    if not REVENUE_GUARD_CONFIG_PATH.exists():
        GUARD_CONFIG_CACHE = _guard_config_defaults()
        return GUARD_CONFIG_CACHE

    try:
        data = json.loads(REVENUE_GUARD_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        data = {}

    if isinstance(data, list):
        raw_custom = data
        raw_overrides: Dict[str, Any] = {}
    else:
        raw_custom = data.get("custom") or []
        raw_overrides = data.get("overrides") or {}
        if isinstance(raw_overrides, list):
            raw_overrides = {str(entry.get("id")): entry for entry in raw_overrides if entry}

    custom_items: List[Dict[str, Any]] = []
    for entry in raw_custom:
        try:
            custom_items.append(_normalize_guard_item(entry, require_keywords=True))
        except ServiceError:
            continue

    overrides: Dict[str, Dict[str, Any]] = {}
    for oid, entry in raw_overrides.items():
        if not oid:
            continue
        try:
            overrides[oid] = _normalize_builtin_override({**entry, "id": oid})
        except ServiceError:
            continue

    GUARD_CONFIG_CACHE = {"custom": custom_items, "overrides": overrides}
    return GUARD_CONFIG_CACHE


def _write_guard_config(custom_items: List[Dict[str, Any]], overrides: Dict[str, Dict[str, Any]]) -> None:
    _ensure_guard_config_dir()
    payload = {"custom": custom_items, "overrides": overrides}
    REVENUE_GUARD_CONFIG_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    global GUARD_CONFIG_CACHE
    GUARD_CONFIG_CACHE = {"custom": custom_items, "overrides": overrides}


def _normalize_guard_item(raw: Dict[str, Any], *, require_keywords: bool) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ServiceError("Guard-Item muss ein Objekt sein.", status_code=400)

    item_id = str(raw.get("id") or f"custom_{uuid4().hex[:8]}")
    name = (raw.get("name") or "").strip()
    if not name:
        raise ServiceError("Guard-Item benötigt einen Namen.", status_code=400)

    keywords_raw = raw.get("keywords")
    if isinstance(keywords_raw, str):
        keywords = [keywords_raw]
    else:
        keywords = keywords_raw or []
    keywords = [str(k).strip().lower() for k in keywords if str(k).strip()]
    if require_keywords and not keywords:
        raise ServiceError(f"Guard-Item '{name}' benötigt mindestens ein Schlüsselwort.", status_code=400)

    severity = (raw.get("severity") or "medium").lower()
    if severity not in {"low", "medium", "high"}:
        raise ServiceError("severity muss 'low', 'medium' oder 'high' sein.", status_code=400)

    halb_menge = raw.get("default_menge")
    default_menge: float | None
    if halb_menge in (None, ""):
        default_menge = None
    else:
        try:
            default_menge = float(halb_menge)
        except (TypeError, ValueError):
            raise ServiceError("default_menge muss eine Zahl sein.", status_code=400) from None

    confidence_raw = raw.get("confidence", 0.5)
    try:
        confidence_val = float(confidence_raw)
    except (TypeError, ValueError):
        confidence_val = 0.5
    confidence_val = max(0.0, min(1.0, confidence_val))

    return {
        "id": item_id,
        "name": name,
        "keywords": keywords,
        "severity": severity,
        "category": (raw.get("category") or "Benutzerdefiniert").strip() or "Benutzerdefiniert",
        "reason": (raw.get("reason") or "").strip(),
        "description": (raw.get("description") or "").strip(),
        "einheit": (raw.get("einheit") or "").strip() or None,
        "default_menge": default_menge,
        "confidence": confidence_val,
        "enabled": bool(raw.get("enabled", True)),
        "editable": bool(raw.get("editable", True)),
        "origin": raw.get("origin"),
    }


def _normalize_custom_guard_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    item = _normalize_guard_item(raw, require_keywords=True)
    item["origin"] = "custom"
    return item


def _load_custom_guard_items() -> List[Dict[str, Any]]:
    config = _load_guard_config()
    return [dict(item) for item in config["custom"]]


def _load_builtin_overrides() -> Dict[str, Dict[str, Any]]:
    return dict(_load_guard_config()["overrides"])


def _normalize_builtin_override(raw: Dict[str, Any]) -> Dict[str, Any]:
    item_id = str(raw.get("id") or "").strip()
    if not item_id or item_id not in BUILTIN_ID_MAP:
        raise ServiceError("Ungültige builtin-id für Guard-Override.", status_code=400)
    item = _normalize_guard_item(raw, require_keywords=False)
    item["id"] = item_id
    item["origin"] = "builtin"
    return item


def _resolved_builtin_guard_items() -> List[Dict[str, Any]]:
    overrides = _load_builtin_overrides()
    resolved: List[Dict[str, Any]] = []
    for base in BUILTIN_GUARD_ITEMS:
        override = overrides.get(base["id"])
        merged = dict(base)
        if override:
            merged.update(override)
        merged["origin"] = "builtin"
        resolved.append(merged)
    return resolved


def _resolved_custom_guard_items() -> List[Dict[str, Any]]:
    custom_items = []
    for item in _load_custom_guard_items():
        entry = dict(item)
        entry["origin"] = "custom"
        custom_items.append(entry)
    return custom_items


def _all_guard_items() -> List[Dict[str, Any]]:
    return _resolved_builtin_guard_items() + _resolved_custom_guard_items()


def _positions_cover_keywords(positions: List[Dict[str, Any]], keywords: List[str]) -> bool:
    tokens = [kw.lower() for kw in keywords if kw]
    if not tokens:
        return True

    for pos in positions:
        combined = " ".join(
            str(val or "")
            for val in (
                pos.get("name"),
                pos.get("text"),
                pos.get("beschreibung"),
                pos.get("category"),
            )
        ).lower()
        if any(token in combined for token in tokens):
            return True
    return False


def _evaluate_custom_guard_rules(
    positions: List[Dict[str, Any]],
    ctx_dict: Dict[str, Any],  # noqa: ARG001 - reserved for future extensions
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    missing: List[Dict[str, Any]] = []
    fired: List[Dict[str, Any]] = []

    for entry in _load_custom_guard_items():
        enabled = bool(entry.get("enabled", True))
        matches = _positions_cover_keywords(positions, entry.get("keywords", []))
        hit = enabled and not matches
        fired.append(
            {
                "id": entry["id"],
                "label": entry.get("name"),
                "hit": hit,
                "explanation": entry.get("description") or entry.get("reason") or "",
            }
        )
        if not hit:
            continue
        missing.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "menge": entry.get("default_menge"),
                "einheit": entry.get("einheit"),
                "reason": entry.get("reason") or "Gemäß benutzerdefinierter Vorgabe erforderlich.",
                "confidence": entry.get("confidence", 0.5),
                "severity": entry.get("severity", "medium"),
                "category": entry.get("category") or "Benutzerdefiniert",
            }
        )

    return missing, fired


def get_revenue_guard_materials() -> Dict[str, Any]:
    """
    Return builtin guard information and custom definitions for UI consumption.
    """
    resolved = _all_guard_items()
    return {"items": resolved}


def save_revenue_guard_materials(*, payload: Dict[str, Any]) -> Dict[str, Any]:
    items_payload = payload.get("items")
    if items_payload is None:
        # Legacy payload (custom-only)
        candidates = payload.get("custom")
        if candidates is None:
            raise ServiceError("Feld 'items' fehlt oder ist ungültig.", status_code=400)
        if not isinstance(candidates, list):
            raise ServiceError("'custom' muss eine Liste sein.", status_code=400)
        normalized_custom = [_normalize_custom_guard_item(entry) for entry in candidates]
        _write_guard_config(normalized_custom, {})
        return {"items": _all_guard_items()}

    if not isinstance(items_payload, list):
        raise ServiceError("'items' muss eine Liste sein.", status_code=400)

    custom_items: List[Dict[str, Any]] = []
    overrides: Dict[str, Dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for entry in items_payload:
        if not isinstance(entry, dict):
            raise ServiceError("Ungültiges Guard-Item (kein Objekt).", status_code=400)
        item_id = str(entry.get("id") or "")
        if item_id in seen_ids and item_id not in BUILTIN_ID_MAP:
            raise ServiceError(f"Doppelte Guard-ID '{item_id}' erkannt.", status_code=400)
        if item_id in BUILTIN_ID_MAP:
            overrides[item_id] = _normalize_builtin_override(entry)
        else:
            normalized = _normalize_custom_guard_item(entry)
            seen_ids.add(normalized["id"])
            custom_items.append(normalized)

    _write_guard_config(custom_items, overrides)
    return {"items": _all_guard_items()}


def _apply_builtin_override_to_suggestion(
    suggestion: Dict[str, Any],
    override: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not override:
        return suggestion
    merged = dict(suggestion)
    for field in ("name", "reason", "category", "einheit", "severity", "confidence"):
        val = override.get(field)
        if val not in (None, ""):
            merged[field] = val
    if override.get("default_menge") not in (None, ""):
        merged["menge"] = override["default_menge"]
    return merged

def search_catalog(
    *,
    query: str,
    limit: int,
    company_id: Optional[str],
    ctx: QuoteServiceContext,
) -> Dict[str, Any]:
    query = (query or "").strip()
    if not query:
        raise ServiceError("query required", status_code=400)
    limit = max(1, min(limit, ctx.catalog_top_k))
    started = time.time()

    if company_id:
        results = _company_catalog_search(company_id, query, limit, ctx)
    else:
        try:
            hits = _run_thin_catalog_search(
                query=query,
                top_k=limit,
                catalog_items=ctx.catalog_items,
                synonyms_path=str(ctx.synonyms_path),
            )
            results = [
                {
                    "sku": h.get("sku"),
                    "name": h.get("name"),
                    "unit": h.get("unit"),
                    "pack_sizes": h.get("pack_sizes"),
                    "synonyms": h.get("synonyms", []),
                    "category": h.get("category"),
                    "brand": h.get("brand"),
                    "confidence": round(float(h.get("score_final", 0.0)), 3),
                }
                for h in hits
            ]
        except Exception as exc:
            ctx.logger.warning("Thin retrieval failed, fallback to legacy _catalog_lookup: %s", exc)
            results = _catalog_lookup(query, limit, ctx)
            if not results and ctx.catalog_items:
                fallback_entries = ctx.catalog_items[:limit]
                results = [
                    {
                        "sku": item.get("sku"),
                        "name": item.get("name"),
                        "unit": item.get("unit"),
                        "pack_sizes": item.get("pack_sizes"),
                        "synonyms": item.get("synonyms") or [],
                        "category": item.get("category"),
                        "brand": item.get("brand"),
                        "confidence": 0.3,
                    }
                    for item in fallback_entries
                ]

    took = int((time.time() - started) * 1000)
    ctx.logger.info(
        "catalog.search q=%r company=%s limit=%d took_ms=%d count=%d",
        query,
        company_id or ctx.default_company_id,
        limit,
        took,
        len(results),
    )
    return {
        "query": query,
        "limit": limit,
        "count": len(results),
        "results": results,
        "took_ms": took,
    }


def chat_turn(*, message: str, ctx: QuoteServiceContext) -> Dict[str, Any]:
    if ctx.chain1 is None or ctx.memory1 is None:
        raise ServiceError("Chat-Funktion (LLM1) aktuell deaktiviert.", status_code=503)
    message = (message or "").strip()
    if not message:
        raise ServiceError("message required", status_code=400)
    history_before = ctx.memory1.load_memory_variables({}).get("chat_history", "")
    context_hint = _compose_context_text(message, ctx)
    previous_items = (
        _extract_last_machine_items(history_before, prefer_status="bestätigt")
        or _extract_last_machine_items(history_before)
        or []
    )

    result = ctx.chain1.run(human_input=message)
    reply_text = result or ""
    reply_lower = reply_text.lower()

    has_machine_block = ("status:" in reply_lower) and ("materialien:" in reply_lower) and ("- name=" in reply_lower)
    pending_machine_block: Optional[str] = None
    pending_confirmed_block: Optional[str] = None
    raw_materials = _extract_materials_from_text_any(reply_text)
    for item in raw_materials:
        item["context_text"] = context_hint
    materials_in_reply = _merge_material_state(
        previous_items,
        raw_materials,
        ctx,
        company_id=ctx.default_company_id,
        lock_on_update=bool(previous_items),
        context_text=context_hint,
    )
    if not has_machine_block and raw_materials:
        machine_block = _make_machine_block("schätzung", materials_in_reply)
        pending_machine_block = machine_block
        has_machine_block = True

    user_confirms = bool(CONFIRM_USER_RE.search(message))
    bot_confirms = bool(CONFIRM_REPLY_RE.search(reply_text))
    ready = bot_confirms or user_confirms
    ready_confirmed = ready

    if not ready and has_machine_block:
        ready = True

    if ready:
        items = materials_in_reply or []
        if not items:
            hist = ctx.memory1.load_memory_variables({}).get("chat_history", "")
            items = _extract_materials_from_text_any(hist)

        if items:
            confirmed_block = _make_machine_block("bestätigt", items)
            if ready_confirmed:
                reply_text = (
                    "**Zusammenfassung**\n"
                    "- Mengen übernommen; Angebot wird jetzt erstellt.\n\n"
                    + confirmed_block
                )
            materials_in_reply = items
            pending_confirmed_block = confirmed_block
        else:
            ready = False

    lookup_materials = materials_in_reply
    if not lookup_materials and ctx.memory1 is not None:
        hist_lookup = ctx.memory1.load_memory_variables({}).get("chat_history", "")
        lookup_materials = _extract_materials_from_text_any(hist_lookup)

    if lookup_materials:
        _, unknown_entries = _validate_materials(
            lookup_materials,
            ctx,
            company_id=ctx.default_company_id,
            context_text=context_hint,
        )
        if unknown_entries:
            products = [entry["query"] for entry in unknown_entries]
            reply_text = chat_unknown_products_message(products)
            display_text = reply_text.strip()
            return {"reply": display_text, "ready_for_offer": False}
    else:
        reply_text = NO_DATA_DETAILS_MESSAGE

    if pending_machine_block:
        try:
            ctx.memory1.chat_memory.add_ai_message(pending_machine_block)  # type: ignore[union-attr]
        except Exception:
            pass
    if pending_confirmed_block:
        try:
            ctx.memory1.chat_memory.add_ai_message(pending_confirmed_block)  # type: ignore[union-attr]
        except Exception:
            pass

    catalog_candidates: List[Dict[str, Any]] = []
    if ctx.llm1_thin_retrieval and lookup_materials:
        if lookup_materials:
            catalog_candidates = _build_catalog_candidates(lookup_materials, ctx, context_text=context_hint)
            if catalog_candidates:
                lines = []
                for cand in catalog_candidates:
                    options = [opt.get("name") for opt in cand.get("options", []) if opt.get("name")]
                    options = [o for o in options if o]
                    if cand.get("status") == "matched" and options:
                        top_line = f"- {cand['query']} → {options[0]}"
                        if len(options) > 1:
                            top_line += f" (Alternativen: {', '.join(options[1:3])})"
                        lines.append(top_line)
                    else:
                        lines.append(f"- {cand['query']} → kein Treffer (bitte spezifizieren)")
                reply_text += "\n\n**Katalog-Vorschläge**\n\n" + "\n".join(lines)
                if ctx.llm1_mode == "merge":
                    auto_lines = []
                    for cand in catalog_candidates:
                        sku = cand.get("selected_catalog_item_id")
                        if not sku:
                            continue
                        canonical = cand.get("canonical_name") or cand.get("matched_sku") or ""
                        auto_lines.append(f"Automatisch zugeordnet: {cand.get('query')} → {canonical} (SKU {sku})")
                    if auto_lines:
                        reply_text += "\n\n" + "\n".join(auto_lines)
                catalog_block = _make_catalog_block(catalog_candidates)
                try:
                    ctx.memory1.chat_memory.add_ai_message(catalog_block)  # type: ignore[union-attr]
                except Exception:
                    pass

    should_prompt_quantities = bool(has_machine_block or raw_materials)
    display_text = _strip_machine_sections(reply_text) or reply_text.strip()
    followup_prompt = "Passen die Mengen so oder wünschen Sie Änderungen?"
    if should_prompt_quantities and not (bot_confirms or user_confirms):
        if followup_prompt.lower() not in display_text.lower():
            display_text = (display_text.rstrip() + ("\n\n" if display_text else "") + followup_prompt).strip()

    return {"reply": display_text, "ready_for_offer": ready}


def _thin_catalog_hits(query: str, ctx: QuoteServiceContext, top_k: int = 3) -> List[Dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []
    try:
        hits = _run_thin_catalog_search(
            query=query,
            top_k=max(1, min(top_k, ctx.catalog_top_k)),
            catalog_items=ctx.catalog_items,
            synonyms_path=str(ctx.synonyms_path),
        )
    except Exception as exc:
        ctx.logger.warning("Thin retrieval failed for %s: %s", query, exc)
        hits = []
    return hits


_COLON_SUFFIX_PREFIXES = (
    "noch",
    "nutzer",
    "kunde",
    "status",
    "reserve",
    "annahme",
    "verbrauch",
    "bedarf",
    "menge",
    "update",
    "hinweis",
    "schicht",
    "pro ",
    "info",
)
_PAREN_SUFFIX_KEYWORDS = (
    "nutzervorgabe",
    "kundenvorgabe",
    "reserve",
    "status",
    "update",
    "annahme",
    "hinweis",
)


def _strip_colon_suffix(value: str) -> str:
    text = value.strip()
    if ":" not in text:
        return text
    head, tail = text.split(":", 1)
    normalized_tail = tail.strip().lower()
    if not normalized_tail:
        return head.strip()
    first = normalized_tail[0]
    if first.isdigit() or first in "+-(":
        return head.strip()
    for prefix in _COLON_SUFFIX_PREFIXES:
        if normalized_tail.startswith(prefix):
            return head.strip()
    return text.strip()


def _strip_parenthetical_suffix(value: str) -> str:
    text = value.strip()
    while True:
        match = re.search(r"\s*\(([^)]*)\)\s*$", text)
        if not match:
            break
        inner = (match.group(1) or "").strip().lower()
        if not inner or any(keyword in inner for keyword in _PAREN_SUFFIX_KEYWORDS):
            text = text[: match.start()].rstrip()
            continue
        break
    return text.strip()


def _material_lookup_variants(name: str) -> List[str]:
    base = (name or "").strip()
    if not base:
        return []
    variants: List[str] = []
    seen: set[str] = set()

    def _add(candidate: str) -> None:
        cleaned = re.sub(r"\s+", " ", candidate.strip("•-–—· ")).strip().rstrip(".,;:-")
        if cleaned:
            key = cleaned.lower()
            if key not in seen:
                variants.append(cleaned)
                seen.add(key)

    _add(base)
    no_colon = _strip_colon_suffix(base)
    _add(no_colon)
    no_paren = _strip_parenthetical_suffix(no_colon)
    _add(no_paren)
    generic_trim = re.sub(r"\s*\([^)]*\)\s*$", "", no_colon).strip()
    if generic_trim:
        _add(generic_trim)
    measurement_source = generic_trim or no_paren
    measurement_trim = re.sub(
        r"\s+\d+(?:[.,]\d+)?\s*(m²|m2|m|mm|cm|kg|g|l|liter|stk|stück|rollen|rolle|pack|paket|sack)\b$",
        "",
        measurement_source,
        flags=re.IGNORECASE,
    ).strip()
    if measurement_trim:
        _add(measurement_trim)
    extras = list(variants)
    for existing in extras:
        for sep in (",", ";"):
            if sep in existing:
                head = existing.split(sep, 1)[0].strip()
                if head:
                    _add(head)
    return variants


def _material_names_match(lhs: str, rhs: str) -> bool:
    if not lhs or not rhs:
        return False
    left_variants = {v.lower() for v in _material_lookup_variants(lhs)} or {lhs.strip().lower()}
    right_variants = {v.lower() for v in _material_lookup_variants(rhs)} or {rhs.strip().lower()}
    return bool(left_variants & right_variants)


def _build_catalog_synonym_map(ctx: QuoteServiceContext) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for entry in ctx.catalog_items:
        for syn in entry.get("synonyms") or []:
            syn_key = (syn or "").strip().lower()
            if syn_key and syn_key not in mapping:
                mapping[syn_key] = entry
    return mapping


def _resolve_catalog_entry_from_name(
    raw_name: str,
    ctx: QuoteServiceContext,
) -> Tuple[bool, Optional[Dict[str, Any]], List[str]]:
    variants = _material_lookup_variants(raw_name)
    if not variants:
        return False, None, []
    suggestions: List[str] = []
    synonym_index = _build_catalog_synonym_map(ctx)
    for variant in variants:
        key = variant.lower()
        if not key:
            continue
        entry = ctx.catalog_by_name.get(key) or synonym_index.get(key)
        if entry:
            return True, entry, []
        hits = _thin_catalog_hits(variant, ctx, top_k=3)
        if hits and not suggestions:
            suggestions = [h.get("name") for h in hits if h.get("name")]
        for hit in hits:
            conf_raw = hit.get("confidence", hit.get("score_final"))
            try:
                confidence = float(conf_raw or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < CATALOG_MATCH_THRESHOLD:
                continue
            sku = (hit.get("sku") or "").strip()
            if sku:
                entry = ctx.catalog_by_sku.get(sku)
                if entry:
                    return True, entry, suggestions
            hit_name = (hit.get("name") or "").strip().lower()
            if hit_name:
                entry = ctx.catalog_by_name.get(hit_name)
                if entry:
                    return True, entry, suggestions
    return False, None, suggestions


    display_text = _strip_machine_sections(reply_text) or reply_text.strip()
    followup_prompt = "Passen die Mengen so oder wünschen Sie Änderungen?"
    if not (bot_confirms or user_confirms):
        if followup_prompt.lower() not in display_text.lower():
            display_text = (display_text.rstrip() + ("\n\n" if display_text else "") + followup_prompt).strip()

    return {"reply": display_text, "ready_for_offer": ready}


def generate_offer_positions(
    *,
    payload: Dict[str, Any],
    ctx: QuoteServiceContext,
    company_id: Optional[str] = None,
    business_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not ctx.documents:
        raise ServiceError("Produktdaten nicht geladen (data/bauprodukte_maurerprodukte.txt).", status_code=500)
    if ctx.llm2 is None or ctx.prompt2 is None:
        raise ServiceError("Angebotsfunktion (LLM2) aktuell deaktiviert.", status_code=503)

    message = (payload.get("message") or "").strip()
    products = payload.get("products")
    business_cfg = business_cfg or {"availability": {}, "price": {}, "margin": {}, "brand_boost": {}}

    def find_exact_catalog_lines(terms: list[str], skus: list[str]) -> list[str]:
        ctx_lines, seen = [], set()
        for sku in skus:
            if not sku:
                continue
            line = ctx.catalog_text_by_sku.get(sku)
            if line and line not in seen:
                ctx_lines.append(line)
                seen.add(line)
        for t in terms:
            key = (t or "").strip().lower()
            if key and key in ctx.catalog_text_by_name:
                line = ctx.catalog_text_by_name[key]
                if line not in seen:
                    ctx_lines.append(line)
                    seen.add(line)
        if ctx.retriever is not None:
            for t in terms:
                key = (t or "").strip().lower()
                if not key or key in ctx.catalog_text_by_name:
                    continue
                hits = ctx.retriever.get_relevant_documents(t)[:8]
                for h in hits:
                    line = (h.page_content or "").strip()
                    if line and line not in seen:
                        ctx_lines.append(line)
                        seen.add(line)
        return ctx_lines

    products_from_message = extract_products_from_output(message) if message else []
    hist_for_catalog = ctx.memory1.load_memory_variables({}).get("chat_history", "") if ctx.memory1 else ""
    latest_items = _extract_last_machine_items(hist_for_catalog, prefer_status="bestätigt") or _extract_last_machine_items(hist_for_catalog)
    if products and isinstance(products, list) and all(isinstance(x, str) for x in products):
        chosen_products = [p.strip() for p in products if p and isinstance(p, str)]
    elif products_from_message:
        chosen_products = products_from_message
    else:
        if ctx.memory1 is None:
            raise ServiceError("No context. Provide 'message' or call /api/chat first.", status_code=400)
        hist = hist_for_catalog
        if not hist and not message:
            raise ServiceError("No context. Provide 'message' or call /api/chat first.", status_code=400)
        if message:
            if ctx.chain1 is None:
                raise ServiceError("Chat-Funktion (LLM1) aktuell deaktiviert.", status_code=503)
            _ = ctx.chain1.run(human_input=message)
            hist = ctx.memory1.load_memory_variables({}).get("chat_history", "")
            hist_for_catalog = hist
            latest_items = _extract_last_machine_items(hist_for_catalog, prefer_status="bestätigt") or _extract_last_machine_items(hist_for_catalog)
        last = hist.split("Assistent:")[-1] if "Assistent:" in hist else hist
        chosen_products = extract_products_from_output(last)
        if not chosen_products:
            raise ServiceError(
                "Keine Produkte erkannt. Sende 'products'[] oder eine Materialien-Liste im 'message'.",
                status_code=400,
            )

    if not products and latest_items:
        chosen_products_from_state = [(item.get("name") or "").strip() for item in latest_items if item.get("name")]
        if chosen_products_from_state:
            chosen_products = chosen_products_from_state

    company_for_validation = company_id or ctx.default_company_id
    context_hint_offer = _compose_context_text(message, ctx)
    validation_results, validation_unknown = _validate_materials(
        [{"name": name} for name in chosen_products],
        ctx,
        company_id=company_for_validation,
        context_text=context_hint_offer,
    )
    if validation_unknown:
        detail = {
            "error": "unknown_products",
            "unknown_products": [entry["query"] for entry in validation_unknown],
            "message": offer_unknown_products_message([entry["query"] for entry in validation_unknown]),
        }
        raise ServiceError(detail, status_code=400)
    match_lookup = {
        (res["query"] or "").strip().lower(): res
        for res in validation_results
        if res.get("matched")
    }

    catalog_memory_map = _extract_catalog_map(hist_for_catalog)
    normalized_pairs: List[Tuple[str, str, Optional[str]]] = []
    for original in chosen_products:
        info = catalog_memory_map.get((original or "").lower())
        canonical = info.get("canonical_name") if info else None
        sku = info.get("matched_sku") if info else None
        match = match_lookup.get((original or "").strip().lower())
        canonical_name = match.get("canonical_name") if match else canonical or original
        sku = match.get("sku") if match and match.get("sku") else sku
        normalized_pairs.append((original, canonical_name, sku))

    updated_pairs: List[Tuple[str, str, Optional[str]]] = []
    for original, canonical_name, sku in normalized_pairs:
        new_canonical = canonical_name
        new_sku = sku
        if not new_sku and new_canonical:
            matched, entry, _ = _resolve_catalog_entry_from_name(new_canonical, ctx)
            if matched and entry:
                new_canonical = entry.get("name") or new_canonical
                new_sku = entry.get("sku") or new_sku
        updated_pairs.append((original, new_canonical, new_sku))
    normalized_pairs = updated_pairs

    normalized_lookup: Dict[str, Tuple[str, Optional[str]]] = {}
    for original, canonical_name, sku in normalized_pairs:
        normalized_lookup[(original or "").strip().lower()] = (canonical_name, sku)

    normalized_names = [pair[1] for pair in normalized_pairs]
    matched_skus = [pair[2] for pair in normalized_pairs if pair[2]]
    chosen_products = normalized_names

    if company_id and ctx.retriever is not None and normalized_names:
        try:
            _run_rank_main(
                normalized_names[0],
                ctx.retriever,
                top_k=1,
                business_cfg=business_cfg,
                company_id=company_id,
            )
        except Exception as exc:
            ctx.logger.debug("Pre-priming rank_main failed: %s", exc)

    ctx_lines = find_exact_catalog_lines(normalized_names, matched_skus)
    if not ctx_lines and not matched_skus and normalized_names and ctx.retriever is not None:
        try:
            rerank = _run_rank_main(
                normalized_names[0],
                ctx.retriever,
                top_k=1,
                business_cfg=business_cfg,
                company_id=company_id,
            )
        except Exception as exc:
            ctx.logger.warning("rank_main fallback failed: %s", exc)
            rerank = []
        if rerank:
            top = rerank[0]
            ctx_line = ctx.catalog_text_by_sku.get(top.get("sku") or "") or ctx.catalog_text_by_name.get(
                (top.get("name") or "").lower(), ""
            )
            if ctx_line:
                ctx.logger.info("offer.rank_main_fallback sku=%s name=%s", top.get("sku"), top.get("name"))
                ctx_lines.append(ctx_line)

    if not ctx_lines:
        return {"positions": [], "raw": "[]"}

    chunks, total_chars = [], 0
    for line in ctx_lines:
        t = line[:1000]
        chunks.append(t)
        total_chars += len(t)
        if total_chars > 8000:
            break

    context_block = "\n\n---\n".join(chunks)
    product_query = "Erstelle ein Angebot für folgende Produkte:\n" + "\n".join(
        f"- {name}" + (f" (SKU: {sku})" if sku else "")
        for (_, name, sku) in normalized_pairs
    )

    formatted = ctx.prompt2.format(context=context_block, question=product_query)
    resp = ctx.llm2.invoke(formatted)
    answer = getattr(resp, "content", str(resp))

    try:
        json_text = extract_json_array(answer)
    except Exception:
        raise ServiceError(f"LLM2 lieferte kein gültiges JSON. Preview: {answer[:200]}", status_code=422)

    try:
        positions = parse_positions(json_text)
    except Exception as exc:
        raise ServiceError(f"JSON-Parsing-Fehler: {exc}. Preview: {json_text[:200]}", status_code=422)

    latest_items = _extract_last_machine_items(hist_for_catalog, prefer_status="bestätigt") or _extract_last_machine_items(hist_for_catalog)

    if latest_items:
        def _find_existing(target: str) -> Optional[dict]:
            for pos in positions:
                pname = (pos.get("name") or "").strip()
                if not pname:
                    continue
                if _material_names_match(target, pname):
                    return pos
                t_lower = target.lower()
                p_lower = pname.lower()
                if t_lower and p_lower and (t_lower in p_lower or p_lower in t_lower):
                    return pos
            return None

        for item in latest_items:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            lookup_key = name.lower()
            canonical_name = name
            canonical_sku = None
            if lookup_key in normalized_lookup:
                canonical_name, canonical_sku = normalized_lookup[lookup_key]
            else:
                matched, entry, _ = _resolve_catalog_entry_from_name(name, ctx)
                if matched and entry:
                    canonical_name = entry.get("name") or canonical_name
                    canonical_sku = entry.get("sku") or canonical_sku
            name = canonical_name
            existing = _find_existing(name)
            raw_qty = item.get("menge") or 0
            einheit = item.get("einheit") or ""
            try:
                menge_float = float(raw_qty)
            except (TypeError, ValueError):
                menge_float = 0.0
            menge_value = int(menge_float) if menge_float.is_integer() else round(menge_float, 3)
            if existing:
                if menge_float > 0:
                    existing["menge"] = menge_value
                    existing["gesamtpreis"] = round(float(existing.get("epreis", 0)) * float(existing["menge"]), 2)
                if einheit:
                    existing["einheit"] = einheit
                if canonical_sku and not existing.get("matched_sku"):
                    existing["matched_sku"] = canonical_sku
                continue
            new_pos = {
                "nr": len(positions) + 1,
                "name": name,
                "menge": menge_value,
                "einheit": einheit,
                "epreis": 0.0,
                "gesamtpreis": 0.0,
            }
            if canonical_sku:
                new_pos["matched_sku"] = canonical_sku
            positions.append(new_pos)

    if ctx.retriever is not None:
        for pos in positions:
            if pos.get("matched_sku"):
                continue
            query_name = pos.get("name") or ""
            if not query_name:
                continue
            try:
                ranked = _run_rank_main(
                    query_name,
                    ctx.retriever,
                    top_k=5,
                    business_cfg=business_cfg,
                    company_id=company_id,
                )
            except Exception as exc:
                ctx.logger.warning("rank_main enrichment failed: %s", exc)
                ranked = []
            if not ranked:
                continue
            top = ranked[0]
            if top.get("sku"):
                pos["matched_sku"] = top["sku"]
            if top.get("name"):
                pos["name"] = top["name"]
            pos.setdefault("reasons", []).append("rank_main_top1")

    harmonized_positions: List[Dict[str, Any]] = []
    for pos in positions:
        entry = None
        matched_sku = (pos.get("matched_sku") or "").strip()
        if matched_sku:
            entry = ctx.catalog_by_sku.get(matched_sku)
        elif (pos.get("name") or "").strip():
            entry = ctx.catalog_by_name.get((pos.get("name") or "").strip().lower())
        pack_info = _resolve_pack_info(entry, pos.get("name"))
        if entry:
            base_unit_hint = _resolve_canonical_unit(entry.get("unit"), entry.get("name"), entry.get("description"))
        else:
            base_unit_hint = _resolve_canonical_unit(pos.get("einheit"), pos.get("name"), None)
        try:
            original_qty = float(pos.get("menge", 0))
        except (TypeError, ValueError):
            original_qty = 0.0
        try:
            original_epreis = float(pos.get("epreis", 0))
        except (TypeError, ValueError):
            original_epreis = 0.0
        try:
            original_total = float(pos.get("gesamtpreis", 0))
        except (TypeError, ValueError):
            original_total = 0.0
        if not original_total and original_qty and original_epreis:
            original_total = round(original_qty * original_epreis, 2)

        pos2, harmonize_reasons, conversion_info = harmonize_material_line(
            pos,
            pack_info=pack_info,
            base_unit_hint=base_unit_hint or None,
        )
        if harmonize_reasons:
            pos2.setdefault("reasons", []).extend(harmonize_reasons)
        try:
            menge_val = float(pos2.get("menge", 0))
            normalized_qty = int(menge_val) if menge_val.is_integer() else round(menge_val, 3)
            pos2["menge"] = normalized_qty
            menge_val = float(pos2["menge"])
        except (TypeError, ValueError):
            menge_val = 0.0
        if base_unit_hint:
            pos2["einheit"] = base_unit_hint
        conversion_applied = conversion_info is not None
        if menge_val > 0 and original_total:
            corrected_total = round(original_total, 2)
            decimals = 4 if conversion_applied else 2
            # Keep the total from the LLM output but adapt the unit price so pack-to-base
            # conversions express prices per base unit instead of per package.
            unit_price = corrected_total / menge_val
            pos2["epreis"] = round(unit_price, decimals)
            pos2["gesamtpreis"] = corrected_total
        else:
            try:
                epreis_val = float(pos2.get("epreis", 0))
            except (TypeError, ValueError):
                epreis_val = 0.0
            pos2["gesamtpreis"] = round(epreis_val * menge_val, 2)
        harmonized_positions.append(pos2)
    positions = _enforce_locked_quantities(harmonized_positions, latest_items, ctx)
    final_positions = positions
    # raw now mirrors the final offer positions so clients see consistent numbers everywhere.
    return {"positions": final_positions, "raw": json.dumps(final_positions, ensure_ascii=False)}


def render_offer_or_invoice_pdf(*, payload: Dict[str, Any], ctx: QuoteServiceContext) -> Dict[str, Any]:
    from app.pdf import render_pdf_from_template

    positions = payload.get("positions")
    if not positions or not isinstance(positions, list):
        raise ServiceError("positions[] required", status_code=400)

    # Convert positions to package units (Stück) for PDF
    from shared.package_converter import convert_to_package_units
    positions = convert_to_package_units(positions, ctx.catalog_by_name)

    for p in positions:
        try:
            menge_val = float(p.get("menge", 0))
        except (TypeError, ValueError):
            menge_val = 0.0
        try:
            # Support both "epreis" and "einzelpreis"
            epreis_val = float(p.get("epreis") or p.get("einzelpreis", 0))
        except (TypeError, ValueError):
            epreis_val = 0.0
        p["gesamtpreis"] = round(menge_val * epreis_val, 2)

    netto = round(sum(float(p["gesamtpreis"]) for p in positions), 2)
    ust = round(netto * ctx.vat_rate, 2)
    brutto = round(netto + ust, 2)

    context = {
        "kunde": payload.get("kunde") or "Max Mustermann GmbH\nMusterstraße 1\n12345 Musterstadt",
        "angebot_nr": payload.get("angebot_nr") or f"A-{datetime.now():%Y%m%d-%H%M}",
        "datum": payload.get("datum") or datetime.now().strftime("%Y-%m-%d"),
        "positionen": positions,
        "netto_summe": netto,
        "ust_betrag": ust,
        "brutto_summe": brutto,
        "ust_satz_prozent": int(ctx.vat_rate * 100),
    }

    pdf_path = render_pdf_from_template(ctx.env, context, ctx.output_dir)
    rel = Path(pdf_path).relative_to(ctx.output_dir)
    return {"pdf_url": f"/outputs/{rel}", "context": context}


def wizard_next_step(*, payload: Dict[str, Any], ctx: QuoteServiceContext) -> Dict[str, Any]:
    session_id = (payload or {}).get("session_id")
    answers = (payload or {}).get("answers") or {}

    if not session_id:
        session_id = _wizard_new_session(ctx)
        st = _wizard_get_state(ctx, session_id)
        step = _wizard_current_step(st)
        return {
            "session_id": session_id,
            "step": step["key"],
            "question": step["question"],
            "ui": step["ui"],
            "context_partial": st["ctx"],
            "done": False,
            "suggestions": [],
        }

    st = _wizard_get_state(ctx, session_id)
    ctx_partial = st["ctx"]

    if isinstance(answers, dict) and answers:
        for k, v in answers.items():
            ctx_partial[k] = v
        _wizard_next_state(st)

    step = _wizard_current_step(st)
    done = step is None
    ready_for_suggestions = (
        (float(ctx_partial.get("flaeche_m2") or 0) > 0 or float(ctx_partial.get("deckenflaeche_m2") or 0) > 0)
        and int(ctx_partial.get("anzahl_schichten") or 0) > 0
    )
    try:
        suggestions = suggest_with_llm1(ctx_partial, ctx) if ready_for_suggestions else []
    except Exception as exc:
        if ctx.debug:
            print("[Wizard] Vorschlagsfehler:", exc)
        suggestions = []

    if done:
        return {
            "session_id": session_id,
            "step": "",
            "question": "",
            "ui": {"type": "info"},
            "context_partial": ctx_partial,
            "done": True,
            "suggestions": suggestions,
        }

    return {
        "session_id": session_id,
        "step": step["key"],
        "question": step["question"],
        "ui": step["ui"],
        "context_partial": ctx_partial,
        "done": False,
        "suggestions": suggestions,
    }


def wizard_finalize(*, payload: Dict[str, Any], ctx: QuoteServiceContext) -> Dict[str, Any]:
    session_id = (payload or {}).get("session_id")
    if not session_id or session_id not in ctx.wizard_sessions:
        raise ServiceError("session_id ungültig oder abgelaufen", status_code=400)

    ctx_partial = ctx.wizard_sessions[session_id]["ctx"]

    try:
        suggestions = suggest_with_llm1(ctx_partial, ctx)
    except Exception as exc:
        if ctx.debug:
            print("[Wizard] Finalize Vorschlagsfehler:", exc)
        suggestions = []

    positions = [
        {"nr": s["nr"], "name": s["name"], "menge": s["menge"], "einheit": s["einheit"], "text": ""}
        for s in suggestions
    ]
    summary = _ctx_to_brief(ctx_partial).replace("\n", " · ")

    return {"session_id": session_id, "summary": summary, "positions": positions, "done": True}


def run_revenue_guard(*, payload: Dict[str, Any], debug: bool = False) -> Dict[str, Any]:
    positions = payload.get("positions") or []
    ctx_dict = payload.get("context") or {}

    if not isinstance(positions, list):
        raise ServiceError("positions[] required (array)", status_code=400)

    override_map = _load_builtin_overrides()
    missing, rules_fired = [], []
    for rid, label, fn in REVENUE_RULES:
        try:
            hit, suggestion = fn(positions, ctx_dict)
        except Exception as exc:
            hit, suggestion = False, None
            if debug:
                print(f"[revenue-guard] Rule {rid} error:", exc)
        override = override_map.get(rid)
        explanation = ""
        if override:
            explanation = override.get("description") or override.get("reason") or ""
            if not override.get("enabled", True):
                hit = False
        rules_fired.append({"id": rid, "label": label, "hit": bool(hit), "explanation": explanation})
        if hit and suggestion:
            adjusted = _apply_builtin_override_to_suggestion(suggestion, override)
            missing.append(adjusted)

    custom_missing, custom_rules = _evaluate_custom_guard_rules(positions, ctx_dict)
    missing.extend(custom_missing)
    rules_fired.extend(custom_rules)

    passed = not any(s["severity"] in ("high", "medium") for s in missing)
    return {"passed": passed, "missing": missing, "rules_fired": rules_fired}
