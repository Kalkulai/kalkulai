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

# Lokale Module
try:
    from app.db import load_products_file, build_vector_db
    from app.services.quote_service import (
        QuoteServiceContext,
        ServiceError,
        chat_turn,
        generate_offer_positions,
        reset_session,
        render_offer_or_invoice_pdf,
        run_revenue_guard,
        search_catalog as service_catalog_search,
        wizard_finalize,
        wizard_next_step,
    )
except ModuleNotFoundError:  # pragma: no cover - relative fallback for CLI tools
    from backend.app.db import load_products_file, build_vector_db
    from backend.app.services.quote_service import (
        QuoteServiceContext,
        ServiceError,
        chat_turn,
        generate_offer_positions,
        reset_session,
        render_offer_or_invoice_pdf,
        run_revenue_guard,
        search_catalog as service_catalog_search,
        wizard_finalize,
        wizard_next_step,
    )
BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
if str(REPO_ROOT) not in sys.path:  # allow running from backend/ or repo root
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import admin_api


# ---------- Logging ----------
logger = logging.getLogger("kalkulai")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# ---------- Pfade & ENV ----------
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
WIZ_SESSIONS: dict[str, dict] = {}
SERVICE_CONTEXT: QuoteServiceContext | None = None


def _get_service_context() -> QuoteServiceContext:
    if SERVICE_CONTEXT is None:
        raise RuntimeError("Service context not initialized.")
    return SERVICE_CONTEXT


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

# Statische Auslieferung der generierten PDFs (aus /app/outputs)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.include_router(admin_api.router)

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


# ---------- Lokaler Start ----------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
