"""Quote service layer centralizing business logic and guardrails.

This module backs both FastAPI handlers and the MCP tool layer by exposing
typed functions (chat, offer generation, wizard flows, revenue guard, etc.).
It enforces shared guardrails (LLM readiness, deterministic rules) and should
remain the single source of truth for core workflows. See docs/mcp-overview.md
for architecture and tool-chain details.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from jinja2 import Environment

from backend.app.uom_convert import harmonize_material_line
from backend.app.utils import extract_json_array, extract_products_from_output, parse_positions
from backend.retriever import index_manager
from backend.retriever.main import rank_main
from backend.retriever.thin import search_catalog_thin
from backend.shared.normalize.text import normalize_query as shared_normalize_query
from backend.shared.normalize.text import tokenize as shared_tokenize


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
    if not query or ctx.retriever is None:
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
    lines = [f"- name={it['name']}, menge={it['menge']}, einheit={it['einheit']}" for it in items]
    return f"---\nstatus: {status}\nmaterialien:\n" + "\n".join(lines) + "\n---"


def _strip_machine_sections(text: str) -> str:
    if not text:
        return ""
    cleaned = MACHINE_BLOCK_RE.sub("", text)
    cleaned = CATALOG_BLOCK_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _build_catalog_candidates(items: List[dict], ctx: QuoteServiceContext) -> List[Dict[str, Any]]:
    if not ctx.llm1_thin_retrieval or not items:
        return []

    candidates: List[Dict[str, Any]] = []
    seen_queries: set[str] = set()
    for item in items:
        query = (item.get("name") or "").strip()
        if not query:
            continue
        key = query.lower()
        if key in seen_queries or len(seen_queries) >= ctx.catalog_queries_per_turn:
            continue
        seen_queries.add(key)

        try:
            raw_hits = search_catalog_thin(
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
        for m in SUG_RE.finditer(body):
            items.append({
                "name": (m.group(1) or "").strip(),
                "menge": float((m.group(2) or "0").replace(",", ".")),
                "einheit": (m.group(3) or "").strip(),
            })
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
- Tiefgrund: 1 L / 15 m² (bei saugendem Untergrund wie Putz/Beton).
- Abdeckfolie (4×5 m ≈ 20 m²/Rolle): ~1 Rolle / 40 m² begeh-/bewohnter Fläche.
- Abklebeband: ~1 Rolle / 25 m Kanten/Anschlüsse (Standardraum grob 1 Rolle/Raum).
- Nur sinnvolle Verbrauchsmaterialien aufführen.

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
        "reason": f"Untergrund {ctx_dict.get('untergrund')} → Tiefgrund (≈1 L / 15 m²).",
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
        if ctx.retriever is None:
            raise ServiceError(
                "Katalogsuche aktuell nicht verfügbar (Retriever nicht initialisiert).",
                status_code=503,
            )
        try:
            hits = search_catalog_thin(
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

    result = ctx.chain1.run(human_input=message)
    reply_text = result or ""
    reply_lower = reply_text.lower()

    has_machine_block = ("status:" in reply_lower) and ("materialien:" in reply_lower) and ("- name=" in reply_lower)
    materials_in_reply = _extract_materials_from_text_any(reply_text)
    if not has_machine_block and materials_in_reply:
        machine_block = _make_machine_block("schätzung", materials_in_reply)
        try:
            ctx.memory1.chat_memory.add_ai_message(machine_block)  # type: ignore[union-attr]
        except Exception:
            pass
        has_machine_block = True

    user_confirms = bool(CONFIRM_USER_RE.search(message))
    bot_confirms = bool(CONFIRM_REPLY_RE.search(reply_text))
    ready = bot_confirms or user_confirms

    if ready:
        items = materials_in_reply or []
        if not items:
            hist = ctx.memory1.load_memory_variables({}).get("chat_history", "")
            items = _extract_materials_from_text_any(hist)

        if items:
            confirmed_block = _make_machine_block("bestätigt", items)
            try:
                ctx.memory1.chat_memory.add_ai_message(confirmed_block)  # type: ignore[union-attr]
            except Exception:
                pass
            reply_text = (
                "**Zusammenfassung**\n"
                "- Mengen übernommen; Angebot wird jetzt erstellt.\n\n"
                + confirmed_block
            )
            materials_in_reply = items
        else:
            ready = False

    if not ready and has_machine_block:
        ready = True

    catalog_candidates: List[Dict[str, Any]] = []
    if ctx.llm1_thin_retrieval:
        lookup_materials = materials_in_reply
        if not lookup_materials:
            hist = ctx.memory1.load_memory_variables({}).get("chat_history", "")
            lookup_materials = _extract_materials_from_text_any(hist)
        if lookup_materials:
            catalog_candidates = _build_catalog_candidates(lookup_materials, ctx)
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
    if products and isinstance(products, list) and all(isinstance(x, str) for x in products):
        chosen_products = [p.strip() for p in products if p and isinstance(p, str)]
    elif products_from_message:
        chosen_products = products_from_message
    else:
        if ctx.memory1 is None:
            raise ServiceError("No context. Provide 'message' or call /api/chat first.", status_code=400)
        hist = ctx.memory1.load_memory_variables({}).get("chat_history", "")
        if not hist and not message:
            raise ServiceError("No context. Provide 'message' or call /api/chat first.", status_code=400)
        if message:
            if ctx.chain1 is None:
                raise ServiceError("Chat-Funktion (LLM1) aktuell deaktiviert.", status_code=503)
            _ = ctx.chain1.run(human_input=message)
            hist = ctx.memory1.load_memory_variables({}).get("chat_history", "")
        last = hist.split("Assistent:")[-1] if "Assistent:" in hist else hist
        chosen_products = extract_products_from_output(last)
        if not chosen_products:
            raise ServiceError(
                "Keine Produkte erkannt. Sende 'products'[] oder eine Materialien-Liste im 'message'.",
                status_code=400,
            )

    hist_for_catalog = ctx.memory1.load_memory_variables({}).get("chat_history", "") if ctx.memory1 else ""
    catalog_memory_map = _extract_catalog_map(hist_for_catalog)
    normalized_pairs: List[Tuple[str, str, Optional[str]]] = []
    normalized_lookup: Dict[str, Tuple[str, Optional[str]]] = {}
    for original in chosen_products:
        info = catalog_memory_map.get((original or "").lower())
        canonical = info.get("canonical_name") if info else None
        sku = info.get("matched_sku") if info else None
        canonical_name = canonical or original
        normalized_pairs.append((original, canonical_name, sku))
        normalized_lookup[original.strip().lower()] = (canonical_name, sku)

    normalized_names = [pair[1] for pair in normalized_pairs]
    matched_skus = [pair[2] for pair in normalized_pairs if pair[2]]
    chosen_products = normalized_names

    ctx_lines = find_exact_catalog_lines(normalized_names, matched_skus)
    if not ctx_lines and not matched_skus and normalized_names and ctx.retriever is not None:
        try:
            rerank = rank_main(
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
            key = (target or "").strip().lower()
            for pos in positions:
                pname = (pos.get("name") or "").strip().lower()
                if not pname:
                    continue
                if pname == key or pname in key or key in pname:
                    return pos
            return None

        for item in latest_items:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            if _find_existing(name):
                continue
            lookup_key = name.lower()
            if lookup_key in normalized_lookup:
                name = normalized_lookup[lookup_key][0]
            raw_qty = item.get("menge") or 0
            einheit = item.get("einheit") or ""
            try:
                menge_float = float(raw_qty)
            except (TypeError, ValueError):
                menge_float = 0.0
            menge_value = int(menge_float) if menge_float.is_integer() else round(menge_float, 3)
            new_pos = {
                "nr": len(positions) + 1,
                "name": name,
                "menge": menge_value,
                "einheit": einheit,
                "epreis": 0.0,
                "gesamtpreis": 0.0,
            }
            positions.append(new_pos)

    if ctx.retriever is not None:
        for pos in positions:
            if pos.get("matched_sku"):
                continue
            query_name = pos.get("name") or ""
            if not query_name:
                continue
            try:
                ranked = rank_main(
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
        pos2, harmonize_reasons = harmonize_material_line(pos)
        if harmonize_reasons:
            pos2.setdefault("reasons", []).extend(harmonize_reasons)
        try:
            menge_val = float(pos2.get("menge", 0))
            pos2["menge"] = int(menge_val) if menge_val.is_integer() else round(menge_val, 3)
        except (TypeError, ValueError):
            pass
        harmonized_positions.append(pos2)
    positions = harmonized_positions

    return {"positions": positions, "raw": answer}


def render_offer_or_invoice_pdf(*, payload: Dict[str, Any], ctx: QuoteServiceContext) -> Dict[str, Any]:
    from backend.app.pdf import render_pdf_from_template

    positions = payload.get("positions")
    if not positions or not isinstance(positions, list):
        raise ServiceError("positions[] required", status_code=400)

    for p in positions:
        if "gesamtpreis" not in p:
            p["gesamtpreis"] = round(float(p["menge"]) * float(p["epreis"]), 2)

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

    missing, rules_fired = [], []
    for rid, label, fn in REVENUE_RULES:
        try:
            hit, suggestion = fn(positions, ctx_dict)
        except Exception as exc:
            hit, suggestion = False, None
            if debug:
                print(f"[revenue-guard] Rule {rid} error:", exc)
        rules_fired.append({"id": rid, "label": label, "hit": bool(hit), "explanation": ""})
        if hit and suggestion:
            missing.append(suggestion)

    passed = not any(s["severity"] in ("high", "medium") for s in missing)
    return {"passed": passed, "missing": missing, "rules_fired": rules_fired}
