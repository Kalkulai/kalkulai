# main.py
from __future__ import annotations

import logging
import os
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from contextlib import asynccontextmanager

from fastapi import FastAPI, Body, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Setup paths FIRST before any local imports
BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

# Load .env EARLY (before any local imports that might read env vars)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

# Add backend dir to path so we can import with 'app.' prefix
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Lokale Module
from app.db import load_products_file, build_vector_db
from app.pdf import list_offer_templates
from app.services.quote_service import (
    QuoteServiceContext,
    ServiceError,
    chat_turn,
    generate_offer_positions,
    reset_session,
    render_offer_or_invoice_pdf,
    get_revenue_guard_materials,
    run_revenue_guard,
    save_revenue_guard_materials,
    search_catalog as service_catalog_search,
    wizard_finalize,
    wizard_next_step,
)
from app import admin_api
from app import auth_api
from app import auth
from app import offers_api
from app import speech_api
from app.services import quote_service as _quote_service_module
from retriever.thin import search_catalog_thin as _thin_search_catalog
from store import catalog_store

search_catalog_thin = _thin_search_catalog


# ---------- Logging ----------
logger = logging.getLogger("kalkulai")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ---------- Pfade & ENV ----------
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
DEFAULT_COMPANY_ID = os.getenv("DEFAULT_COMPANY_ID", "default")

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
    "http://test.local",
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
        from app.llm import create_chat_llm, build_chains  # type: ignore
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

# LangChain imports - optional for smoke tests without full dependencies
try:
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.documents import Document as LCDocument
    from langchain_core.callbacks import CallbackManagerForRetrieverRun

    class IndexManagerRetrieverWrapper(BaseRetriever):
        """Wrapper to make index_manager compatible with LangChain retriever interface"""
        company_id: str = "demo"
        
        class Config:
            arbitrary_types_allowed = True
        
        def _get_relevant_documents(
            self, query: str, *, run_manager: CallbackManagerForRetrieverRun
        ) -> List[LCDocument]:
            """Retrieve relevant documents from index_manager"""
            # Ensure index exists
            index = index_manager.ensure_index(self.company_id)
            
            # Search
            results = index_manager.search(self.company_id, query, top_k=20)
            
            # Convert to LangChain Document format
            docs = []
            for result in results:
                doc = LCDocument(
                    page_content=result.get("text", ""),
                    metadata={
                        "sku": result.get("sku", ""),
                        "name": result.get("name", ""),
                        "score": result.get("score", 0.0)
                    }
                )
                docs.append(doc)
            
            return docs

except ImportError:  # pragma: no cover - smoke tests without langchain
    IndexManagerRetrieverWrapper = None  # type: ignore[misc, assignment]

if SKIP_LLM_SETUP and not FORCE_RETRIEVER_BUILD:
    DB = None
    RETRIEVER = None
else:
    # Old Chroma system (fallback for DOCUMENTS)
    DB, _ = build_vector_db(DOCUMENTS, CHROMA_DIR, debug=DEBUG)
    
    # New index_manager system (for dynamic products)
    if IndexManagerRetrieverWrapper is not None:
        RETRIEVER = IndexManagerRetrieverWrapper(company_id="demo")
    else:
        RETRIEVER = None  # pragma: no cover

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

import time
from functools import lru_cache

_CATALOG_CACHE_TTL = 60  # Sekunden
_CATALOG_LAST_REFRESH = 0
_CATALOG_CACHE = []

def _get_dynamic_catalog_items(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Get catalog items from database (dynamic) + static file (fallback)"""
    global _CATALOG_LAST_REFRESH, _CATALOG_CACHE
    
    # Check if cache is still valid
    now = time.time()
    if not force_refresh and _CATALOG_CACHE and (now - _CATALOG_LAST_REFRESH) < _CATALOG_CACHE_TTL:
        return _CATALOG_CACHE
    
    items = []
    
    # 1. Load from database (dynamic products)
    try:
        from store.catalog_store import get_active_products
        db_products = get_active_products("demo")
        for prod in db_products:
            items.append({
                "sku": prod.get("sku"),
                "name": prod.get("name"),
                "unit": prod.get("unit"),
                "volume_l": prod.get("volume_l"),
                "price_eur": prod.get("price_eur"),
                "pack_sizes": None,
                "synonyms": [],
                "category": prod.get("category"),
                "material_type": prod.get("material_type"),
                "unit_package": prod.get("unit_package"),
                "tags": prod.get("tags"),
                "brand": None,
                "description": prod.get("description"),
                "raw": f"{prod.get('name')} - {prod.get('description', '')}",
            })
    except Exception as e:
        import logging
        logging.warning(f"Could not load database products: {e}")
    
    # 2. Add static file products (fallback)
    for doc in DOCUMENTS:
        items.append(_document_to_catalog_entry(doc))
    
    # Update cache
    _CATALOG_CACHE = items
    _CATALOG_LAST_REFRESH = now
    
    logger.info(f"📦 Catalog cache refreshed: {len(items)} products loaded")
    
    return items

CATALOG_ITEMS: List[Dict[str, Any]] = _get_dynamic_catalog_items()
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
WIZ_SESSIONS: dict[str, dict] = {}
SERVICE_CONTEXT: QuoteServiceContext | None = None
_DB_INITIALIZED = False


def refresh_catalog_cache(force: bool = True) -> Dict[str, Any]:
    """
    Refresh the catalog cache and update all related dictionaries.
    Called automatically after admin operations (create/update/delete/rebuild).
    """
    global CATALOG_ITEMS, CATALOG_BY_NAME, CATALOG_BY_SKU, CATALOG_TEXT_BY_NAME, CATALOG_TEXT_BY_SKU
    
    # Force reload from database
    catalog_items = _get_dynamic_catalog_items(force_refresh=force)
    
    # Update all global dictionaries
    CATALOG_ITEMS = catalog_items
    
    CATALOG_BY_NAME.clear()
    CATALOG_BY_NAME.update({
        (item["name"] or "").lower(): item for item in catalog_items if item.get("name")
    })
    
    CATALOG_BY_SKU.clear()
    CATALOG_BY_SKU.update({
        item["sku"]: item for item in catalog_items if item.get("sku")
    })
    
    CATALOG_TEXT_BY_NAME.clear()
    CATALOG_TEXT_BY_NAME.update({
        (item["name"] or "").lower(): item.get("raw", "") for item in catalog_items if item.get("name")
    })
    
    CATALOG_TEXT_BY_SKU.clear()
    CATALOG_TEXT_BY_SKU.update({
        item["sku"]: item.get("raw", "") for item in catalog_items if item.get("sku")
    })
    
    # Clear search cache to force fresh searches
    CATALOG_SEARCH_CACHE.clear()
    
    # Update SERVICE_CONTEXT if it exists
    if SERVICE_CONTEXT is not None:
        SERVICE_CONTEXT.catalog_items = CATALOG_ITEMS
        SERVICE_CONTEXT.catalog_by_name = CATALOG_BY_NAME
        SERVICE_CONTEXT.catalog_by_sku = CATALOG_BY_SKU
        SERVICE_CONTEXT.catalog_text_by_name = CATALOG_TEXT_BY_NAME
        SERVICE_CONTEXT.catalog_text_by_sku = CATALOG_TEXT_BY_SKU
        SERVICE_CONTEXT.catalog_search_cache = CATALOG_SEARCH_CACHE
    
    logger.info(f"✅ Catalog cache refreshed: {len(catalog_items)} products, {len(CATALOG_BY_NAME)} by name, {len(CATALOG_BY_SKU)} by SKU")
    
    return {
        "status": "success",
        "products_loaded": len(catalog_items),
        "indexed_by_name": len(CATALOG_BY_NAME),
        "indexed_by_sku": len(CATALOG_BY_SKU),
    }


def _initialize_database() -> None:
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    catalog_store.init_db()
    auth.init_auth_tables()
    offers_api.init_offers_table()
    _DB_INITIALIZED = True


def _get_service_context() -> QuoteServiceContext:
    _initialize_database()
    if SERVICE_CONTEXT is None:
        raise RuntimeError("Service context not initialized.")
    _sync_service_context()
    return SERVICE_CONTEXT


def _build_catalog_candidates(items: List[dict], context_text: Optional[str] = None) -> List[Dict[str, Any]]:
    ctx = _get_service_context()
    ctx.llm1_mode = LLM1_MODE
    ctx.adopt_threshold = ADOPT_THRESHOLD
    ctx.catalog_queries_per_turn = CATALOG_QUERIES_PER_TURN
    ctx.llm1_thin_retrieval = LLM1_THIN_RETRIEVAL
    return _quote_service_module._build_catalog_candidates(items, ctx, context_text=context_text)


# ---------- LLMs ----------
llm1 = llm2 = None
chain1 = chain2 = memory1 = PROMPT2 = None

def _sync_service_context() -> None:
    if SERVICE_CONTEXT is None:
        return
    SERVICE_CONTEXT.chain1 = chain1
    SERVICE_CONTEXT.chain2 = chain2
    SERVICE_CONTEXT.llm1 = llm1
    SERVICE_CONTEXT.llm2 = llm2
    SERVICE_CONTEXT.prompt2 = PROMPT2
    SERVICE_CONTEXT.memory1 = memory1
    SERVICE_CONTEXT.retriever = RETRIEVER

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
        _sync_service_context()
        return
    chain1, chain2, memory1, PROMPT2 = build_chains(llm1, llm2, RETRIEVER, debug=DEBUG)
    _sync_service_context()

if not SKIP_LLM_SETUP:
    _rebuild_chains()

SERVICE_CONTEXT = QuoteServiceContext(
    chain1=chain1,
    chain2=chain2,
    llm1=llm1,
    llm2=llm2,
    prompt2=PROMPT2,
    memory1=memory1,
    retriever=RETRIEVER,
    reset_callback=_rebuild_chains,
    documents=DOCUMENTS,
    catalog_items=CATALOG_ITEMS,
    catalog_by_name=CATALOG_BY_NAME,
    catalog_by_sku=CATALOG_BY_SKU,
    catalog_text_by_name=CATALOG_TEXT_BY_NAME,
    catalog_text_by_sku=CATALOG_TEXT_BY_SKU,
    catalog_search_cache=CATALOG_SEARCH_CACHE,
    wizard_sessions=WIZ_SESSIONS,
    env=env,
    output_dir=OUTPUT_DIR,
    vat_rate=VAT_RATE,
    synonyms_path=SYNONYMS_PATH,
    logger=logger,
    llm1_mode=LLM1_MODE,
    adopt_threshold=ADOPT_THRESHOLD,
    business_scoring=BUSINESS_SCORING,
    llm1_thin_retrieval=LLM1_THIN_RETRIEVAL,
    catalog_top_k=CATALOG_TOP_K,
    catalog_cache_ttl=CATALOG_CACHE_TTL,
    catalog_queries_per_turn=CATALOG_QUERIES_PER_TURN,
    skip_llm_setup=SKIP_LLM_SETUP,
    default_company_id=DEFAULT_COMPANY_ID,
    debug=DEBUG,
)
_sync_service_context()

def _ensure_llm_enabled(component: str) -> None:
    """Guards endpoints when SKIP_LLM_SETUP=1 is active (CI smoke tests)."""
    if SKIP_LLM_SETUP:
        raise HTTPException(
            status_code=503,
            detail=f"{component} aktuell deaktiviert (SKIP_LLM_SETUP=1 – nur Health-Check aktiv).",
        )

# ---------- FastAPI ----------


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _initialize_database()
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ECHO_ORIGINS = set(ALLOWED_ORIGINS or [])


@app.middleware("http")
async def _cors_echo_middleware(request, call_next):
    response = await call_next(request)
    origin = request.headers.get("origin")
    if origin and origin in ECHO_ORIGINS:
        response.headers["access-control-allow-origin"] = origin
    return response

# Statische Auslieferung der generierten PDFs (aus /app/outputs)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.include_router(admin_api.router)
app.include_router(auth_api.router)
app.include_router(offers_api.router)
app.include_router(speech_api.router)

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
    company_id: Optional[str] = Query(None),
):
    try:
        return service_catalog_search(
            query=q,
            limit=top_k,
            company_id=company_id,
            ctx=_get_service_context(),
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ---- NEU: Reset-Endpoints (Memory & Wizard) ----
@app.post("/api/session/reset")
def api_session_reset():
    return reset_session(ctx=_get_service_context())

# kompatibler Alias
@app.post("/api/reset")
def api_reset_alias():
    return api_session_reset()

# ---- API: Chat (LLM1) ----
@app.post("/api/chat")
def api_chat(payload: Dict[str, str] = Body(...)):
    try:
        return chat_turn(message=(payload.get("message") or ""), ctx=_get_service_context())
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ---- API: Angebot (LLM2 → JSON) ----
@app.post("/api/offer")
def api_offer(payload: Dict[str, Any] = Body(...), company_id: Optional[str] = Query(None)):
    try:
        return generate_offer_positions(
            payload=payload,
            ctx=_get_service_context(),
            company_id=company_id,
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

# ---- API: PDF bauen ----
@app.post("/api/pdf")
def api_pdf(payload: Dict[str, Any] = Body(...)):
    try:
        return render_offer_or_invoice_pdf(payload=payload, ctx=_get_service_context())
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

@app.get("/api/pdf/templates")
def api_pdf_templates():
    return {"templates": list_offer_templates()}

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

@app.post("/wizard/maler/next")
def wizard_maler_next(payload: Dict[str, Any] = Body(...)):
    try:
        return wizard_next_step(payload=payload or {}, ctx=_get_service_context())
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

@app.post("/wizard/maler/finalize")
def wizard_maler_finalize(payload: Dict[str, Any] = Body(...)):
    try:
        return wizard_finalize(payload=payload or {}, ctx=_get_service_context())
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

@app.post("/revenue-guard/check")
def revenue_guard_check(payload: Dict[str, Any] = Body(...)):
    try:
        return run_revenue_guard(payload=payload or {}, debug=DEBUG)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get("/api/revenue-guard/materials")
def api_revenue_guard_materials():
    return get_revenue_guard_materials()


@app.put("/api/revenue-guard/materials")
def api_revenue_guard_materials_update(payload: Dict[str, Any] = Body(...)):
    try:
        return save_revenue_guard_materials(payload=payload or {})
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ---------- Lokaler Start ----------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
