# main.py
from __future__ import annotations

import logging
import os
import re
import math
import time
from difflib import SequenceMatcher
from uuid import uuid4
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from contextlib import asynccontextmanager

from fastapi import FastAPI, Body, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Lokale Module
try:
    from app.db import load_products_file, build_vector_db
    from app.utils import extract_products_from_output, parse_positions, extract_json_array
    from app.uom_convert import harmonize_material_line
except ModuleNotFoundError:  # pragma: no cover - relative fallback for CLI tools
    from backend.app.db import load_products_file, build_vector_db
    from backend.app.utils import extract_products_from_output, parse_positions, extract_json_array
    from backend.app.uom_convert import harmonize_material_line
from backend.shared.normalize.text import normalize_query as shared_normalize_query
from backend.shared.normalize.text import tokenize as shared_tokenize
from backend.retriever.thin import search_catalog_thin
from backend.retriever.main import rank_main


# ---------- Logging ----------
logger = logging.getLogger("kalkulai")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ---------- Pfade & ENV ----------
BASE_DIR = Path(__file__).parent

try:  # bevorzugt lokale .env lesen, auch wenn uvicorn sie nicht lädt
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

DATA_ROOT  = Path(os.getenv("DATA_ROOT", str(BASE_DIR)))
DATA_DIR   = BASE_DIR / "data"
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(DATA_ROOT / "chroma_db")))
TEMPLATES  = BASE_DIR / "templates"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(DATA_ROOT / "outputs")))
SYNONYMS_PATH = BASE_DIR / "shared" / "normalize" / "synonyms.yaml"

CHROMA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEBUG = os.getenv("DEBUG", "0") == "1"
MODEL_PROVIDER  = os.getenv("MODEL_PROVIDER", "openai").lower()        
MODEL_LLM1      = os.getenv("MODEL_LLM1", "gpt-4o-mini")
MODEL_LLM2      = os.getenv("MODEL_LLM2", "gpt-4o-mini")
OPENAI_API_KEY  = (os.getenv("OPENAI_API_KEY") or "").strip() or None
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
VAT_RATE        = float(os.getenv("VAT_RATE", "0.19"))
SKIP_LLM_SETUP  = os.getenv("SKIP_LLM_SETUP", "0") == "1"
LLM1_THIN_RETRIEVAL = os.getenv("LLM1_THIN_RETRIEVAL", "0") == "1"
CATALOG_TOP_K       = max(1, int(os.getenv("CATALOG_TOP_K", "5")))
CATALOG_CACHE_TTL   = max(5, int(os.getenv("CATALOG_CACHE_TTL", "60")))
CATALOG_QUERIES_PER_TURN = max(1, int(os.getenv("CATALOG_QUERIES_PER_TURN", "2")))

LLM1_MODE = (os.getenv("LLM1_MODE", "assistive") or "assistive").strip().lower()
ADOPT_THRESHOLD = float(os.getenv("ADOPT_THRESHOLD", "0.82"))
BUSINESS_SCORING = [
    flag.strip()
    for flag in (os.getenv("BUSINESS_SCORING", "margin,availability") or "").split(",")
    if flag.strip()
]
logger.info(
    "Flags: LLM1_MODE=%s ADOPT_THRESHOLD=%.2f BUSINESS_SCORING=%s",
    LLM1_MODE,
    ADOPT_THRESHOLD,
    BUSINESS_SCORING,
)

_DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://Kalkuali-kalkulai-frontend.hf.space",
]
_origins_env = os.getenv("FRONTEND_ORIGINS", "")
ALLOWED_ORIGINS = (
    [origin.strip() for origin in _origins_env.split(",") if origin.strip()]
    if _origins_env.strip()
    else _DEFAULT_ALLOWED_ORIGINS
)
ALLOWED_ORIGIN_REGEX = os.getenv("FRONTEND_ORIGIN_REGEX", "").strip() or None

FORCE_RETRIEVER_BUILD = os.getenv("FORCE_RETRIEVER_BUILD", "0") == "1"

if not SKIP_LLM_SETUP:
    try:
        from app.llm import create_chat_llm, build_chains  # type: ignore
    except ModuleNotFoundError:  # pragma: no cover
        from backend.app.llm import create_chat_llm, build_chains  # type: ignore
else:  # pragma: no cover
    create_chat_llm = build_chains = None  # type: ignore

# ---------- Jinja2-Env (Filter) ----------
env = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    autoescape=select_autoescape(["html"])
)
env.filters["currency"] = (
    lambda v: f"{float(v):.2f}"
    if (isinstance(v, (int, float)) or str(v).replace(".", "", 1).isdigit())
    else "0.00"
)
def _date_format(value: str, fmt: str = "%d.%m.%Y") -> str:
    for f in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, f).strftime(fmt)
        except ValueError:
            continue
    return value
env.filters["date_format"] = _date_format

# ---------- Daten + Vektor-DB ----------
_product_file_env = os.getenv("PRODUCT_FILE", "").strip()
if _product_file_env:
    candidate = Path(_product_file_env)
    if not candidate.is_absolute():
        candidate = DATA_DIR / candidate
    PRODUCT_FILE = candidate
else:
    maler_default = DATA_DIR / "maler_lackierer_produkte.txt"
    if maler_default.exists():
        PRODUCT_FILE = maler_default
    else:
        PRODUCT_FILE = DATA_DIR / "bauprodukte_maurerprodukte.txt"
DOCUMENTS = load_products_file(PRODUCT_FILE, debug=DEBUG)
if SKIP_LLM_SETUP and not FORCE_RETRIEVER_BUILD:
    DB = None
    RETRIEVER = None
else:
    DB, RETRIEVER = build_vector_db(DOCUMENTS, CHROMA_DIR, debug=DEBUG)

def _sku_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or f"produkt-{abs(hash(name))}"

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
    entry = {
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
    return entry

CATALOG_ITEMS: List[Dict[str, Any]] = [_document_to_catalog_entry(doc) for doc in DOCUMENTS]
CATALOG_BY_NAME: Dict[str, Dict[str, Any]] = {
    (item["name"] or "").lower(): item for item in CATALOG_ITEMS if item.get("name")
}
CATALOG_BY_SKU: Dict[str, Dict[str, Any]] = {
    item["sku"]: item for item in CATALOG_ITEMS if item.get("sku")
}
CATALOG_TEXT_BY_NAME: Dict[str, str] = {
    (item["name"] or "").lower(): item.get("raw", "") for item in CATALOG_ITEMS if item.get("name")
}
CATALOG_TEXT_BY_SKU: Dict[str, str] = {
    item["sku"]: item.get("raw", "") for item in CATALOG_ITEMS if item.get("sku")
}
CATALOG_SEARCH_CACHE: Dict[Tuple[str, int], Tuple[float, List[Dict[str, Any]]]] = {}


def _normalize_query(text: str) -> str:
    """Backward compatible wrapper that delegates to shared normalize module."""
    return shared_normalize_query(text)

def _tokenize(text: str) -> set[str]:
    """Wrapper to keep legacy call sites while using shared tokenizer."""
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
        # reward substring matches without forcing perfect alignment
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


def _catalog_lookup(query: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not query:
        return []
    if RETRIEVER is None:
        return []

    top_k = min(limit or CATALOG_TOP_K, CATALOG_TOP_K)
    key = _catalog_cache_key(query, top_k)
    now = time.time()
    cached = CATALOG_SEARCH_CACHE.get(key)
    if cached and now - cached[0] <= CATALOG_CACHE_TTL:
        return cached[1]

    q_lower = _normalize_query(query)

    # 1) Lexikalische Treffer anhand der vorhandenen Katalogdaten
    lexical_candidates: List[Tuple[float, Dict[str, Any]]] = []
    for item in CATALOG_ITEMS:
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
        CATALOG_SEARCH_CACHE[key] = (now, results)
        return results

    # 2) Fallback Retriever mit Score-Filter
    try:
        docs = RETRIEVER.get_relevant_documents(query)[: max(top_k * 2, top_k)]
    except Exception as exc:  # pragma: no cover - defensive
        if DEBUG:
            print(f"[WARN] Retrieval fehlgeschlagen für '{query}': {exc}")
        return []

    seen: set[str] = set()
    scored: List[Tuple[float, Dict[str, Any]]] = []

    for doc in docs:
        meta = getattr(doc, "metadata", None) or {}
        name = meta.get("name")
        sku = meta.get("sku")

        entry: Optional[Dict[str, Any]] = None
        if sku and sku in CATALOG_BY_SKU:
            entry = CATALOG_BY_SKU[sku]
        elif name and name.lower() in CATALOG_BY_NAME:
            entry = CATALOG_BY_NAME[name.lower()]

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

    CATALOG_SEARCH_CACHE[key] = (now, results)
    return results

# ---------- LLMs ----------
llm1 = llm2 = None
chain1 = chain2 = memory1 = PROMPT2 = None

if not SKIP_LLM_SETUP:
    llm1 = create_chat_llm(
        provider=MODEL_PROVIDER,
        model=MODEL_LLM1,
        temperature=0.15,
        top_p=0.9,
        seed=42,
        api_key=OPENAI_API_KEY,
        base_url=OLLAMA_BASE_URL,
    )
    llm2 = create_chat_llm(
        provider=MODEL_PROVIDER,
        model=MODEL_LLM2,
        temperature=0.0,
        top_p=0.8,
        seed=42,
        api_key=OPENAI_API_KEY,
        base_url=OLLAMA_BASE_URL,
    )

# ---------- Chains + Memory (global, werden per Reset neu gebaut) ----------
def _rebuild_chains():
    global chain1, chain2, memory1, PROMPT2
    if SKIP_LLM_SETUP:
        chain1 = chain2 = memory1 = PROMPT2 = None
        return
    chain1, chain2, memory1, PROMPT2 = build_chains(llm1, llm2, RETRIEVER, debug=DEBUG)

if not SKIP_LLM_SETUP:
    _rebuild_chains()

# ---------- Wizard: LLM1-gestützte Live-Vorschläge ----------
SUG_RE = re.compile(
    r"name\s*=\s*(.+?),\s*menge\s*=\s*([0-9]+(?:[.,][0-9]+)?)\s*,\s*einheit\s*=\s*([A-Za-zÄÖÜäöü]+)",
    re.IGNORECASE,
)

def _ensure_llm_enabled(component: str) -> None:
    """Guards endpoints when SKIP_LLM_SETUP=1 is active (CI smoke tests)."""
    if SKIP_LLM_SETUP:
        raise HTTPException(
            status_code=503,
            detail=f"{component} aktuell deaktiviert (SKIP_LLM_SETUP=1 – nur Health-Check aktiv).",
        )

def _ctx_to_brief(ctx: dict) -> str:
    """Kompakte Projektbeschreibung aus Wizard-Kontext."""
    innen_aussen = ctx.get("innen_aussen") or ctx.get("innen_außen") or "unbekannt"
    untergrund   = ctx.get("untergrund") or "unbekannt"
    flaeche      = float(ctx.get("flaeche_m2") or 0)
    decke        = float(ctx.get("deckenflaeche_m2") or 0)
    schichten    = int(ctx.get("anzahl_schichten") or 2)
    vorarb       = ctx.get("vorarbeiten") or []
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
    """Parst Maschinenanhang zu Vorschlags-Objekten."""
    if not text:
        return []
    out = []
    for i, m in enumerate(SUG_RE.finditer(text), start=1):
        name    = (m.group(1) or "").strip()
        menge   = float((m.group(2) or "0").replace(",", "."))
        einheit = (m.group(3) or "").strip()
        out.append({"nr": i, "name": name, "menge": round(menge, 2), "einheit": einheit, "text": ""})
    return out

def suggest_with_llm1(ctx: dict, limit: int = 6) -> List[dict]:
    """
    Ruft LLM1 (ohne Memory) auf, um Materialvorschläge in Basis-Einheiten zu schätzen.
    """
    if SKIP_LLM_SETUP or llm1 is None:
        raise RuntimeError("LLM1 ist deaktiviert (SKIP_LLM_SETUP=1).")
    brief = _ctx_to_brief(ctx)
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
    resp = llm1.invoke(prompt)
    txt = getattr(resp, "content", str(resp))
    items = _parse_materialien(txt)

    # Duplikate zusammenfassen (Name+Einheit)
    seen: Dict[tuple, float] = {}
    for it in items:
        key = (it["name"].lower(), it["einheit"].lower())
        seen[key] = seen.get(key, 0.0) + float(it["menge"])

    merged, i = [], 1
    for (name_l, unit_l), qty in seen.items():
        # originaler Name (korrekte Groß-/Kleinschreibung) wiederfinden
        name = next((it["name"] for it in items if it["name"].lower() == name_l), name_l)
        merged.append({"nr": i, "name": name, "menge": round(qty, 2), "einheit": unit_l, "text": ""})
        i += 1
    return merged[:limit]

# ---------- FastAPI ----------


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    print("✅ Startup")
    print(f"   MODEL_PROVIDER={MODEL_PROVIDER}  LLM1={MODEL_LLM1}  LLM2={MODEL_LLM2}  VAT_RATE={VAT_RATE}")
    print(f"   Produktdatei: {'OK' if PRODUCT_FILE.exists() else 'FEHLT'}")
    print(f"   CHROMA_DIR={CHROMA_DIR}  (writable)")
    print(f"   OUTPUT_DIR={OUTPUT_DIR}  (writable)")
    print(f"   ALLOWED_ORIGINS={ALLOWED_ORIGINS}")
    if ALLOWED_ORIGIN_REGEX:
        print(f"   ALLOWED_ORIGIN_REGEX={ALLOWED_ORIGIN_REGEX}")
    yield


app = FastAPI(title="Kalkulai Backend", lifespan=_lifespan)
ALLOW_ALL_ORIGINS = os.getenv("ALLOW_ALL_ORIGINS", "0") == "1"
cors_kwargs = dict(
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if ALLOW_ALL_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=["*"], **cors_kwargs)
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_origin_regex=ALLOWED_ORIGIN_REGEX,
        **cors_kwargs,
    )

# Statische Auslieferung der generierten PDFs (aus /app/outputs)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# Root (Health)
@app.get("/")
def root():
    return {"ok": True, "service": "kalkulai-backend", "health": "/api/health", "docs": "/docs"}

@app.get("/api/health")
def api_health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

@app.get("/api/catalog/search")
def api_catalog_search(
    q: str = Query(..., min_length=2, description="Freitext-Suche (Name, Synonym)"),
    top_k: int = Query(5, ge=1, le=10, description="Anzahl der Treffer (maximal)"),
):
    if RETRIEVER is None:
        raise HTTPException(
            status_code=503,
            detail="Katalogsuche aktuell nicht verfügbar (Retriever nicht initialisiert).",
        )
    limit = min(top_k, CATALOG_TOP_K)
    started = time.time()
    try:
        hits = search_catalog_thin(
            query=q,
            top_k=limit,
            catalog_items=CATALOG_ITEMS,
            synonyms_path=str(SYNONYMS_PATH),
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
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Thin retrieval failed, fallback to legacy _catalog_lookup: %s", exc)
        results = _catalog_lookup(q, limit)

    took = int((time.time() - started) * 1000)
    logger.info("catalog.search q=%r limit=%d took_ms=%d count=%d", q, limit, took, len(results))
    return {
        "query": q,
        "limit": limit,
        "count": len(results),
        "results": results,
        "took_ms": took,
    }

# ---- NEU: Reset-Endpoints (Memory & Wizard) ----
@app.post("/api/session/reset")
def api_session_reset():
    """
    Leert serverseitig den Zustand:
    - Chat-Memory/Prompt-Chains werden neu aufgebaut.
    - Wizard-Sessions werden gelöscht.
    -> Nach einem Page-Reload ist alles „frisch“.
    """
    global WIZ_SESSIONS
    if SKIP_LLM_SETUP:
        WIZ_SESSIONS.clear()
        return {"ok": True, "message": "LLM-Reset übersprungen: SKIP_LLM_SETUP=1 (Smoke-Test-Modus)."}
    _rebuild_chains()
    WIZ_SESSIONS.clear()
    return {"ok": True, "message": "Server state cleared (memory + wizard sessions)."}

# kompatibler Alias
@app.post("/api/reset")
def api_reset_alias():
    return api_session_reset()

# ---------- ROBUSTE BESTÄTIGUNGS-/MATERIAL-ERKENNUNG ----------
CONFIRM_USER_RE = re.compile(
    r"(passen\s*so|passen|stimmen\s*so|stimmen|best[aä]tig|übernehmen|so\s*übernehmen|klingt\s*g?ut|mengen\s*(?:sind\s*)?(?:korrekt|okay|in\s*ordnung)|freigeben|erstelle\s+(?:das\s+)?angebot|ja[,!\s]*(?:bitte\s*)?(?:das\s*)?angebot)",
    re.IGNORECASE,
)
CONFIRM_REPLY_RE = re.compile(r"status\s*:\s*best[aä]tigt", re.IGNORECASE)

# Bullets wie "- Dispersionsfarbe: 20 kg"
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
LAST_QTY_UNIT_RE = re.compile(rf"([0-9]+(?:[.,][0-9]+)?)\s*({_UNIT_PATTERN})(?![A-Za-zÄÖÜäöü0-9])",
                               re.IGNORECASE)

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
    """Versucht Materialzeilen zu extrahieren – zuerst Maschinensyntax, sonst Bullet-Liste."""
    items = []
    # 1) Maschinensyntax (--- status: … materialien: - name=…, menge=…, einheit=…)
    for m in SUG_RE.finditer(text or ""):
        items.append({
            "name": (m.group(1) or "").strip(),
            "menge": float((m.group(2) or "0").replace(",", ".")),
            "einheit": (m.group(3) or "").strip(),
        })
    if items:
        return items
    # 2) Bullet-Liste "Materialbedarf"
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


CATALOG_BLOCK_RE = re.compile(r"---\s*status:\s*katalog\s*candidates:\s*(.*?)---", re.IGNORECASE | re.DOTALL)
MACHINE_BLOCK_RE = re.compile(r"---\s*(?:projekt_id:.*?\n)?(?:version:.*?\n)?status:\s*([a-zäöüß]+)\s*materialien:\s*(.*?)---", re.IGNORECASE | re.DOTALL)

def _build_catalog_candidates(items: List[dict]) -> List[Dict[str, Any]]:
    if not LLM1_THIN_RETRIEVAL or not items:
        return []

    candidates: List[Dict[str, Any]] = []
    seen_queries: set[str] = set()
    for item in items:
        query = (item.get("name") or "").strip()
        if not query:
            continue
        key = query.lower()
        if key in seen_queries or len(seen_queries) >= CATALOG_QUERIES_PER_TURN:
            continue
        seen_queries.add(key)

        try:
            raw_hits = search_catalog_thin(
                query=query,
                top_k=CATALOG_TOP_K,
                catalog_items=CATALOG_ITEMS,
                synonyms_path=str(SYNONYMS_PATH),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("LLM1 thin retrieval failed for %s: %s", query, exc)
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
            if LLM1_MODE == "strict":
                if allowed:
                    adoptable = True
            elif LLM1_MODE == "merge":
                if allowed and best_score >= ADOPT_THRESHOLD:
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
    """
    Strict-Regel: Nur übernehmen, wenn
    - hard_filters_passed (aus Thin-Retrieval Ergebnis) und
    - der (normalisierte) Titel das Canonical-Token enthält.
    """

    try:
        from backend.shared.normalize.text import tokenize  # local import to avoid cycles
    except Exception:
        return False

    if not item_name:
        return False
    if not best.get("hard_filters_passed"):
        return False
    title = (best.get("name") or "").strip()
    if not title:
        return False
    title_toks = set(tokenize(title))
    item_toks = set(tokenize(item_name))
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

# ---- API: Chat (LLM1) ----
@app.post("/api/chat")
def api_chat(payload: Dict[str, str] = Body(...)):
    if chain1 is None:
        _ensure_llm_enabled("Chat-Funktion (LLM1)")
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message required")

    # 1) LLM1 antworten lassen (landet auch in der Memory)
    result = chain1.run(human_input=message)
    reply_text = result or ""
    reply_lower = reply_text.lower()

    # 2) Materials extrahieren – falls der Bot KEINEN Maschinenanhang schreibt,
    #    erzeugen wir einen aus "Materialbedarf" und legen ihn als AI-Message in die Memory.
    has_machine_block = ("status:" in reply_lower) and ("materialien:" in reply_lower) and ("- name=" in reply_lower)
    materials_in_reply = _extract_materials_from_text_any(reply_text)
    if not has_machine_block:
        if materials_in_reply:
            machine_block = _make_machine_block("schätzung", materials_in_reply)
            try:
                memory1.chat_memory.add_ai_message(machine_block)
            except Exception:
                pass
            has_machine_block = True

    # 3) Bestätigung erkennen – in NutzerTEXT ODER Bot-Antwort
    user_confirms = bool(CONFIRM_USER_RE.search(message))
    bot_confirms  = bool(CONFIRM_REPLY_RE.search(reply_text))
    ready = bot_confirms or user_confirms

    # 4) Wenn Nutzer bestätigt und wir Materialzeilen haben → bestätigten Block erzeugen
    if ready:
        # Letzte verwertbare Materials suchen (aus aktueller Antwort oder History)
        items = materials_in_reply or []
        if not items:
            hist = memory1.load_memory_variables({}).get("chat_history", "")
            items = _extract_materials_from_text_any(hist)

        if items:
            confirmed_block = _make_machine_block("bestätigt", items)
            try:
                memory1.chat_memory.add_ai_message(confirmed_block)
            except Exception:
                pass
            # Optional: klare, kurze Antwort statt erneutem Schätzungstext
            reply_text = (
                "**Zusammenfassung**\n"
                "- Mengen übernommen; Angebot wird jetzt erstellt.\n\n"
                + confirmed_block
            )
            materials_in_reply = items
        else:
            # wir können nicht bestätigen, weil uns Materials fehlen
            ready = False

    # (Sicherheitsnetz) Falls zwar ein Maschinenanhang existiert, aber keine explizite Bestätigung erkannt wurde,
    # markieren wir trotzdem ready → UI kann Angebot erzeugen.
    if not ready and has_machine_block:
        ready = True

    # 5) Dünne Katalogsuche für Vorschläge
    catalog_candidates: List[Dict[str, Any]] = []
    if LLM1_THIN_RETRIEVAL:
        # Falls aktuelle Antwort nichts enthält, versuche letzte AI-Nachricht aus History
        lookup_materials = materials_in_reply
        if not lookup_materials:
            hist = memory1.load_memory_variables({}).get("chat_history", "")
            lookup_materials = _extract_materials_from_text_any(hist)
        if lookup_materials:
            catalog_candidates = _build_catalog_candidates(lookup_materials)
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
                if LLM1_MODE == "merge":
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
                    memory1.chat_memory.add_ai_message(catalog_block)
                except Exception:
                    pass

    return {"reply": reply_text, "ready_for_offer": ready}


# ---- API: Angebot (LLM2 → JSON) ----
@app.post("/api/offer")
def api_offer(payload: Dict[str, Any] = Body(...)):
    if not DOCUMENTS:
        raise HTTPException(500, "Produktdaten nicht geladen (data/bauprodukte_maurerprodukte.txt).")
    if chain2 is None or llm2 is None:
        _ensure_llm_enabled("Angebotsfunktion (LLM2)")

    message = (payload.get("message") or "").strip()
    products = payload.get("products")
    business_cfg = {"availability": {}, "price": {}, "margin": {}, "brand_boost": {}}

    # --- exakte Katalogzeilen finden ---
    def find_exact_catalog_lines(terms: list[str], skus: list[str]) -> list[str]:
        ctx, seen = [], set()
        # 1) Treffer via SKU
        for sku in skus:
            if not sku:
                continue
            line = CATALOG_TEXT_BY_SKU.get(sku)
            if line and line not in seen:
                ctx.append(line); seen.add(line)
        # 2) exakte Treffer nach Name
        for t in terms:
            key = (t or "").strip().lower()
            if key and key in CATALOG_TEXT_BY_NAME:
                line = CATALOG_TEXT_BY_NAME[key]
                if line not in seen:
                    ctx.append(line); seen.add(line)
        # 3) Fallback Retriever
        for t in terms:
            key = (t or "").strip().lower()
            if not key or key in CATALOG_TEXT_BY_NAME:
                continue
            hits = RETRIEVER.get_relevant_documents(t)[:8]
            for h in hits:
                line = (h.page_content or "").strip()
                if line and line not in seen:
                    ctx.append(line); seen.add(line)
        return ctx

    # --- Produkte aus Payload oder Chat extrahieren ---
    products_from_message = extract_products_from_output(message) if message else []
    if products and isinstance(products, list) and all(isinstance(x, str) for x in products):
        chosen_products = [p.strip() for p in products if p and isinstance(p, str)]
    elif products_from_message:
        chosen_products = products_from_message
    else:
        # Fallback: aus Chat-Memory lesen
        hist = memory1.load_memory_variables({}).get("chat_history", "")
        if not hist and not message:
            raise HTTPException(400, "No context. Provide 'message' or call /api/chat first.")
        if message:
            if chain1 is None:
                _ensure_llm_enabled("Chat-Funktion (LLM1)")
            _ = chain1.run(human_input=message)
            hist = memory1.load_memory_variables({}).get("chat_history", "")
        last = hist.split("Assistent:")[-1] if "Assistent:" in hist else hist
        chosen_products = extract_products_from_output(last)
        if not chosen_products:
            raise HTTPException(400, "Keine Produkte erkannt. Sende 'products'[] oder eine Materialien-Liste im 'message'.")

    hist_for_catalog = memory1.load_memory_variables({}).get("chat_history", "")
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

    # --- Kontext bauen ---
    ctx_lines = find_exact_catalog_lines(normalized_names, matched_skus)
    if not ctx_lines and not matched_skus and normalized_names and RETRIEVER is not None:
        try:
            rerank = rank_main(normalized_names[0], RETRIEVER, top_k=1, business_cfg=business_cfg)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("rank_main fallback failed: %s", exc)
            rerank = []
        if rerank:
            top = rerank[0]
            ctx_line = CATALOG_TEXT_BY_SKU.get(top.get("sku") or "") or CATALOG_TEXT_BY_NAME.get(
                (top.get("name") or "").lower(), ""
            )
            if ctx_line:
                logger.info("offer.rank_main_fallback sku=%s name=%s", top.get("sku"), top.get("name"))
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

    context = "\n\n---\n".join(chunks)
    product_query = "Erstelle ein Angebot für folgende Produkte:\n" + "\n".join(
        f"- {name}" + (f" (SKU: {sku})" if sku else "")
        for (_, name, sku) in normalized_pairs
    )

    # --- LLM2 direkt ansteuern ---
    formatted = PROMPT2.format(context=context, question=product_query)
    resp = llm2.invoke(formatted)
    answer = getattr(resp, "content", str(resp))

    # --- JSON extrahieren ---
    try:
        json_text = extract_json_array(answer)
    except Exception:
        raise HTTPException(status_code=422, detail=f"LLM2 lieferte kein gültiges JSON. Preview: {answer[:200]}")

    try:
        positions = parse_positions(json_text)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"JSON-Parsing-Fehler: {e}. Preview: {json_text[:200]}")

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

    if RETRIEVER is not None:
        for pos in positions:
            if pos.get("matched_sku"):
                continue
            query_name = pos.get("name") or ""
            if not query_name:
                continue
            try:
                ranked = rank_main(query_name, RETRIEVER, top_k=5, business_cfg=business_cfg)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("rank_main enrichment failed: %s", exc)
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

# ---- API: PDF bauen ----
@app.post("/api/pdf")
def api_pdf(payload: Dict[str, Any] = Body(...)):
    from app.pdf import render_pdf_from_template  # Lazy import to avoid heavy deps during smoke tests

    positions = payload.get("positions")
    if not positions or not isinstance(positions, list):
        raise HTTPException(400, "positions[] required")

    for p in positions:
        if "gesamtpreis" not in p:
            p["gesamtpreis"] = round(float(p["menge"]) * float(p["epreis"]), 2)

    netto  = round(sum(float(p["gesamtpreis"]) for p in positions), 2)
    ust    = round(netto * VAT_RATE, 2)
    brutto = round(netto + ust, 2)

    context = {
        "kunde": payload.get("kunde") or "Max Mustermann GmbH\nMusterstraße 1\n12345 Musterstadt",
        "angebot_nr": payload.get("angebot_nr") or f"A-{datetime.now():%Y%m%d-%H%M}",
        "datum": payload.get("datum") or datetime.now().strftime("%Y-%m-%d"),
        "positionen": positions,
        "netto_summe": netto,
        "ust_betrag": ust,
        "brutto_summe": brutto,
        "ust_satz_prozent": int(VAT_RATE * 100),
    }

    pdf_path = render_pdf_from_template(env, context, OUTPUT_DIR)
    rel = os.path.relpath(pdf_path, start=OUTPUT_DIR)
    return {"pdf_url": f"/outputs/{rel}", "context": context}

@app.get("/api/catalog")
def api_catalog(limit: int = 50):
    items = [d.page_content for d in DOCUMENTS[:limit]]
    return {"count": len(DOCUMENTS), "sample": items}

@app.get("/api/search")
def api_search(q: str = Query(..., min_length=2), k: int = 8):
    if RETRIEVER is None:
        _ensure_llm_enabled("Suchfunktion (Vektor-DB)")
    docs = RETRIEVER.get_relevant_documents(q)[:k]
    return {"query": q, "results": [d.page_content for d in docs]}

# ---------- Wizard (Maler) ----------
WIZ_SESSIONS: dict[str, dict] = {}  # session_id -> {"ctx": {...}, "step_idx": int}

MALER_STEPS: list[dict] = [
    {"key": "innen_aussen",      "question": "Innen oder Außen?",                                   "ui": {"type": "singleSelect", "options": ["Innen", "Aussen"]}},
    {"key": "untergrund",        "question": "Welcher Untergrund?",                                 "ui": {"type": "singleSelect", "options": ["Putz","Gipskarton","Beton","Altanstrich","Tapete","unbekannt"]}},
    {"key": "flaeche_m2",        "question": "Wie groß ist die zu streichende Wandfläche in m²? (0, falls keine)",   "ui": {"type": "number", "min": 0, "max": 10000, "step": 1}},
    {"key": "deckenflaeche_m2",  "question": "Wie groß ist die zu streichende Deckenfläche in m²? (0, falls keine)", "ui": {"type": "number", "min": 0, "max": 10000, "step": 1}},
    {"key": "anzahl_schichten",  "question": "Wie viele Anstriche (Schichten)?",                     "ui": {"type": "number", "min": 1, "max": 5, "step": 1}},
    {"key": "vorarbeiten",       "question": "Vorarbeiten auswählen (optional)",                      "ui": {"type": "multiSelect", "options": ["Abkleben","Spachteln","Grundieren","Schleifen","Ausbessern"]}},
    {"key": "abklebeflaeche_m",  "question": "Geschätzte Abklebekanten in Metern? (optional, 0 wenn unbekannt)", "ui": {"type": "number", "min": 0, "max": 1000, "step": 1}},
    {"key": "besonderheiten",    "question": "Gibt es Besonderheiten? (z. B. Schimmel, Nikotin, etc.)",           "ui": {"type": "singleSelect", "options": ["keine","Nikotin","Schimmel","Feuchtraum","Dunkle Altfarbe"]}},
]

def _wizard_new_session() -> str:
    sid = uuid4().hex
    WIZ_SESSIONS[sid] = {"ctx": {}, "step_idx": 0}
    return sid

def _wizard_get_state(session_id: str) -> dict:
    st = WIZ_SESSIONS.get(session_id)
    if not st:
        st = {"ctx": {}, "step_idx": 0}
        WIZ_SESSIONS[session_id] = st
    return st

def _wizard_current_step(state: dict) -> dict | None:
    idx = int(state.get("step_idx", 0))
    return MALER_STEPS[idx] if 0 <= idx < len(MALER_STEPS) else None

def _wizard_next_state(state: dict):
    state["step_idx"] = int(state.get("step_idx", 0)) + 1

@app.post("/wizard/maler/next")
def wizard_maler_next(payload: Dict[str, Any] = Body(...)):
    session_id = (payload or {}).get("session_id")
    answers    = (payload or {}).get("answers") or {}

    # 1) Neue Session?
    if not session_id:
        session_id = _wizard_new_session()
        st = _wizard_get_state(session_id)
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

    # 2) Bestehende Session fortführen
    st = _wizard_get_state(session_id)
    ctx = st["ctx"]

    # aktuelle Antwort übernehmen (payload = { step_key: value })
    if isinstance(answers, dict) and answers:
        for k, v in answers.items():
            ctx[k] = v
        _wizard_next_state(st)

    # 3) Nächsten Schritt bestimmen
    step = _wizard_current_step(st)
    done = step is None

    # 4) LLM1-gestützte Live-Vorschläge erzeugen (wenn genug Kontext)
    ready_for_suggestions = (
        (float(ctx.get("flaeche_m2") or 0) > 0 or float(ctx.get("deckenflaeche_m2") or 0) > 0)
        and int(ctx.get("anzahl_schichten") or 0) > 0
    )
    try:
        suggestions = suggest_with_llm1(ctx) if ready_for_suggestions else []
    except Exception as e:
        if DEBUG:
            print("[Wizard] Vorschlagsfehler:", e)
        suggestions = []

    if done:
        return {
            "session_id": session_id,
            "step": "",
            "question": "",
            "ui": {"type": "info"},
            "context_partial": ctx,
            "done": True,
            "suggestions": suggestions,
        }

    return {
        "session_id": session_id,
        "step": step["key"],
        "question": step["question"],
        "ui": step["ui"],
        "context_partial": ctx,
        "done": False,
        "suggestions": suggestions,
    }

@app.post("/wizard/maler/finalize")
def wizard_maler_finalize(payload: Dict[str, Any] = Body(...)):
    session_id = (payload or {}).get("session_id")
    if not session_id or session_id not in WIZ_SESSIONS:
        raise HTTPException(400, "session_id ungültig oder abgelaufen")

    ctx = WIZ_SESSIONS[session_id]["ctx"]

    # Finale Positionen aus LLM1-Vorschlägen (Basis-Einheiten)
    try:
        suggestions = suggest_with_llm1(ctx)
    except Exception as e:
        if DEBUG:
            print("[Wizard] Finalize Vorschlagsfehler:", e)
        suggestions = []

    positions = [
        {"nr": s["nr"], "name": s["name"], "menge": s["menge"], "einheit": s["einheit"], "text": ""}
        for s in suggestions
    ]
    summary = _ctx_to_brief(ctx).replace("\n", " · ")

    return {"session_id": session_id, "summary": summary, "positions": positions, "done": True}

# ---------- Revenue Guard: Vergessene-Posten-Wächter ----------
from typing import Tuple

def _norm(s: str) -> str:
    return (s or "").lower()

def _has_any(positions: list[dict], keywords: list[str]) -> bool:
    for p in positions or []:
        name = _norm(p.get("name", ""))
        if any(k in name for k in keywords):
            return True
    return False

def _ctx_num(ctx: dict, key: str, default: float = 0.0) -> float:
    try:
        v = ctx.get(key, default)
        return float(v if v is not None else default)
    except Exception:
        return default

def _area_total(ctx: dict) -> float:
    return _ctx_num(ctx, "flaeche_m2", 0.0) + _ctx_num(ctx, "deckenflaeche_m2", 0.0)

# ---- Regeln (deterministisch, ohne LLM) ----

def rule_masking_cover(positions: list[dict], ctx: dict) -> Tuple[bool, dict | None]:
    """Abdeckfolie/Abdeckvlies für Innenarbeiten."""
    innen = _norm(ctx.get("innen_aussen", "")) == "innen"
    if not innen:
        return False, None
    if _has_any(positions, ["abdeckfolie", "abdeckvlies", "abdeckpapier", "schutzfolie"]):
        return False, None

    flaeche = max(_area_total(ctx), _ctx_num(ctx, "flaeche_m2", 0.0))
    # Richtwert: 1 Rolle je ~40 m² begangener Fläche (vereinfachend über Wand-/Deckenfläche)
    rolls = int(math.ceil(max(1.0, flaeche / 40.0)))
    sug = {
        "id": "masking_cover",
        "name": "Abdeckfolie 4×5 m (20 m²/Rolle)",
        "menge": rolls,
        "einheit": "Rolle",
        "reason": "Innenarbeiten: Richtwert 1 Rolle je ~40 m² begehter Fläche.",
        "confidence": 0.7,
        "severity": "medium",
        "category": "Schutz",
    }
    return True, sug

def rule_masking_tape(positions: list[dict], ctx: dict) -> Tuple[bool, dict | None]:
    """Abklebeband/Kreppband für Kanten/Anschlüsse."""
    if _has_any(positions, ["abklebeband", "kreppband", "malerkrepp"]):
        return False, None
    kanten_m = _ctx_num(ctx, "abklebeflaeche_m", 0.0)
    if kanten_m <= 0:
        # Heuristik-Fallback: 1 Rolle je ~40 m²
        flaeche = max(_area_total(ctx), _ctx_num(ctx, "flaeche_m2", 0.0))
        rolls = int(math.ceil(max(1.0, flaeche / 40.0)))
        reason = "Kein Kantenmaß angegeben → Heuristik aus Fläche (~1 Rolle / 40 m²)."
    else:
        # 1 Rolle ≈ 25 m
        rolls = int(math.ceil(kanten_m / 25.0))
        reason = f"Abklebekanten ≈ {int(kanten_m)} m → ~{rolls} Rolle(n) à ~25 m."

    sug = {
        "id": "masking_tape",
        "name": "Abklebeband (Malerkrepp), 50 m",
        "menge": rolls,
        "einheit": "Rolle",
        "reason": reason,
        "confidence": 0.6,
        "severity": "low",
        "category": "Schutz",
    }
    return True, sug

def rule_primer_tiefgrund(positions: list[dict], ctx: dict) -> Tuple[bool, dict | None]:
    """Grundierung/Tiefgrund bei saugendem Untergrund."""
    if _has_any(positions, ["tiefgrund", "grundierung", "haftgrund", "isoliergrund", "sperrgrund"]):
        return False, None

    untergrund = _norm(ctx.get("untergrund", ""))
    saugend = any(k in untergrund for k in ["putz", "beton", "gipskarton"])
    if not saugend:
        return False, None

    flaeche = max(1.0, _area_total(ctx))
    # 1 L / 15 m² (Reserve macht später LLM2 bei Gebinde)
    liter = flaeche / 15.0
    eimer_10l = int(math.ceil(liter / 10.0))
    sug = {
        "id": "primer_tiefgrund",
        "name": "Tiefgrund (Grundierung), 10 L",
        "menge": float(eimer_10l),
        "einheit": "Eimer",
        "reason": f"Saugender Untergrund (Putz/Beton/GK) bei {int(flaeche)} m² → ca. {liter:.1f} L (~{eimer_10l} Eimer à 10 L).",
        "confidence": 0.9,
        "severity": "high",
        "category": "Vorarbeiten",
    }
    return True, sug

def rule_scratch_spackle(positions: list[dict], ctx: dict) -> Tuple[bool, dict | None]:
    """Kratz-/Zwischenspachtelung bei Altanstrich/Tapete."""
    if _has_any(positions, ["spachtel", "spachtelmasse", "kratzspachtel", "q2", "q3"]):
        return False, None

    untergrund = _norm(ctx.get("untergrund", ""))
    if not any(k in untergrund for k in ["altanstrich", "tapete"]):
        return False, None

    flaeche = max(1.0, _ctx_num(ctx, "flaeche_m2", 0.0))
    # Richtwert: 0,5 kg/m²
    kg = round(flaeche * 0.5, 1)
    sug = {
        "id": "scratch_spackle",
        "name": "Spachtelmasse (Zwischenspachtelung)",
        "menge": kg,
        "einheit": "kg",
        "reason": f"Untergrund {ctx.get('untergrund')} → Ausgleich/Haftverbesserung (≈0,5 kg/m²).",
        "confidence": 0.6,
        "severity": "medium",
        "category": "Vorarbeiten",
    }
    return True, sug

def rule_travel(positions: list[dict], ctx: dict) -> Tuple[bool, dict | None]:
    """Anfahrtpauschale."""
    if _has_any(positions, ["anfahrt", "fahrtkosten", "an- und abfahrt", "anlieferung"]):
        return False, None

    dist = _ctx_num(ctx, "entfernung_km", 0.0)
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


#Wichtig -> gibt Arbeiten die meist vergessen werden vor
REVENUE_RULES = [
    ("primer_tiefgrund", "Grundierung/Haftverbesserung fehlt?", rule_primer_tiefgrund),
    ("masking_cover", "Abdecken/Schutz fehlt?", rule_masking_cover),
    ("masking_tape", "Abklebeband fehlt?", rule_masking_tape),
    ("scratch_spackle", "Spachtelarbeiten (Kratz-/Zwischenspachtelung) fehlen?", rule_scratch_spackle),
    ("travel", "Anfahrtpauschale fehlt?", rule_travel),
]

@app.post("/revenue-guard/check")
def revenue_guard_check(payload: Dict[str, Any] = Body(...)):
    positions = payload.get("positions") or []
    ctx = payload.get("context") or {}

    if not isinstance(positions, list):
        raise HTTPException(400, "positions[] required (array)")

    missing, rules_fired = [], []
    for rid, label, fn in REVENUE_RULES:
        try:
            hit, suggestion = fn(positions, ctx)
        except Exception as e:
            hit, suggestion = False, None
            if DEBUG:
                print(f"[revenue-guard] Rule {rid} error:", e)
        rules_fired.append({"id": rid, "label": label, "hit": bool(hit), "explanation": ""})
        if hit and suggestion:
            missing.append(suggestion)

    # passed = keine high/medium Lücken
    passed = not any(s["severity"] in ("high", "medium") for s in missing)
    return {"passed": passed, "missing": missing, "rules_fired": rules_fired}


# ---------- Lokaler Start ----------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
