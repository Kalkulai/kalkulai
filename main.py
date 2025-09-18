# main.py (Root)
from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from langchain.schema import AIMessage

from fastapi import FastAPI, Body, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from langchain.schema import Document as LCDocument

# --- Neu: Regex für robustes JSON-Parsing aus LLM-Antworten ---
import re

JSON_ARRAY_RE = re.compile(r"\[\s*\{.*?\}\s*\]", re.DOTALL)
CODEBLOCK_RE  = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.DOTALL)

def _extract_json_array(text: str) -> str:
    """Extrahiert das erste JSON-Array aus einem Text (auch wenn es in ```json-Codeblöcken``` steckt)."""
    if not isinstance(text, str):
        return ""
    # 1) Codeblock-Inhalt prüfen
    m = CODEBLOCK_RE.search(text)
    if m:
        inner = m.group(1) or ""
        m2 = JSON_ARRAY_RE.search(inner)
        if m2:
            return m2.group(0).strip()
    # 2) Direkt im Text suchen
    m = JSON_ARRAY_RE.search(text)
    if m:
        return m.group(0).strip()
    return ""

# --- Lokale Module ---
from app.db import load_products_file, build_vector_db
from app.llm import create_chat_llm, build_chains
from app.pdf import render_pdf_from_template
from app.utils import extract_products_from_output, parse_positions

# ---------- Pfade & ENV ----------
BASE_DIR = Path(__file__).parent

# WICHTIG: Alles unter /app halten (HF Spaces: /data ist oft nicht beschreibbar)
DATA_ROOT  = Path(os.getenv("DATA_ROOT", str(BASE_DIR)))
DATA_DIR   = BASE_DIR / "data"                 # Input-Dateien bleiben im Image
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(DATA_ROOT / "chroma_db")))
TEMPLATES  = BASE_DIR / "templates"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(DATA_ROOT / "outputs")))

# Schreibbare Ordner sicherstellen
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEBUG = os.getenv("DEBUG", "0") == "1"
MODEL_PROVIDER  = os.getenv("MODEL_PROVIDER", "openai").lower()        # openai|ollama
MODEL_LLM1      = os.getenv("MODEL_LLM1", "gpt-4o-mini")
MODEL_LLM2      = os.getenv("MODEL_LLM2", "gpt-4o-mini")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
VAT_RATE        = float(os.getenv("VAT_RATE", "0.19"))

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
PRODUCT_FILE = DATA_DIR / "maler_lackierer_produkte.txt"
DOCUMENTS = load_products_file(PRODUCT_FILE, debug=DEBUG)
DB, RETRIEVER = build_vector_db(DOCUMENTS, CHROMA_DIR, debug=DEBUG)

# ---------- LLMs & Chains ----------
llm1 = create_chat_llm(
    provider=MODEL_PROVIDER,
    model=MODEL_LLM1,
    temperature=0.1,
    top_p=0.9,
    api_key=OPENAI_API_KEY,
    base_url=OLLAMA_BASE_URL,
)
llm2 = create_chat_llm(
    provider=MODEL_PROVIDER,
    model=MODEL_LLM2,
    temperature=0.0,
    top_p=0.8,
    api_key=OPENAI_API_KEY,
    base_url=OLLAMA_BASE_URL,
)
chain1, chain2, memory1, PROMPT2 = build_chains(llm1, llm2, RETRIEVER, debug=DEBUG)

# ---------- FastAPI ----------
app = FastAPI(title="Kalkulai Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://Kalkuali-kalkulai-frontend.hf.space"],  # deine Frontend-URL hier
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Statische Auslieferung der generierten PDFs (aus /app/outputs)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# Root (hilfreich für Health-Checks)
@app.get("/")
def root():
    return {
        "ok": True,
        "service": "kalkulai-backend",
        "health": "/api/health",
        "docs": "/docs",
    }

# Health
@app.get("/api/health")
def api_health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

# Startup-Log
@app.on_event("startup")
def _startup():
    print("✅ Startup")
    print(f"   MODEL_PROVIDER={MODEL_PROVIDER}  LLM1={MODEL_LLM1}  LLM2={MODEL_LLM2}  VAT_RATE={VAT_RATE}")
    print(f"   Produktdatei: {'OK' if PRODUCT_FILE.exists() else 'FEHLT'}")
    print(f"   CHROMA_DIR={CHROMA_DIR}  (writable)")
    print(f"   OUTPUT_DIR={OUTPUT_DIR}  (writable)")

# ---- API: Chat (LLM1) ----
@app.post("/api/chat")
def api_chat(payload: Dict[str, str] = Body(...)):
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message required")
    result = chain1.run(human_input=message)
    ready = any(t in result for t in (
        "Perfekt! Ich erstelle Ihnen das Angebot",
        "Ich erstelle Ihnen das Angebot",
        "Ihr Angebot wird vorbereitet",
        "Perfekt",
    )) and (len(extract_products_from_output(result)) > 0)
    return {"reply": result, "ready_for_offer": ready}

# ---- API: Angebot (LLM2 → JSON) ----
from utils import extract_json_array  # ganz oben importieren

@app.post("/api/offer")
def api_offer(payload: Dict[str, Any] = Body(...)):
    if not DOCUMENTS:
        raise HTTPException(500, "Produktdaten nicht geladen (data/maler_lackierer_produkte.txt).")
    if chain2 is None:
        raise HTTPException(500, "LLM2/ Retriever nicht initialisiert.")

    message = (payload.get("message") or "").strip()
    products = payload.get("products")

    # --- Helper: exakte Katalogzeilen finden (Case-insensitive) ---
    catalog_lines = [(d.page_content or "").strip() for d in DOCUMENTS]
    catalog_lower = {line.lower(): line for line in catalog_lines}

    def find_exact_catalog_lines(terms: list[str]) -> list[str]:
        ctx, seen = [], set()
        # 1) exakte Treffer
        for t in terms:
            key = (t or "").strip().lower()
            if key and key in catalog_lower:
                line = catalog_lower[key]
                if line not in seen:
                    ctx.append(line)
                    seen.add(line)
        # 2) Fallback Retriever
        for t in terms:
            key = (t or "").strip().lower()
            if not key or key in catalog_lower:
                continue
            hits = RETRIEVER.get_relevant_documents(t)[:8]
            for h in hits:
                line = (h.page_content or "").strip()
                if line and line not in seen:
                    ctx.append(line)
                    seen.add(line)
        return ctx

    # --- Produkte aus Payload oder Chat extrahieren ---
    products_from_message = extract_products_from_output(message) if message else []
    if products and isinstance(products, list) and all(isinstance(x, str) for x in products):
        chosen_products = [p.strip() for p in products if p and isinstance(p, str)]
    elif products_from_message:
        chosen_products = products_from_message
    else:
        hist = memory1.load_memory_variables({}).get("chat_history", "")
        if not hist and not message:
            raise HTTPException(400, "No context. Provide 'message' or call /api/chat first.")
        if message:
            _ = chain1.run(human_input=message)
            hist = memory1.load_memory_variables({}).get("chat_history", "")
        last = hist.split("Assistent:")[-1] if "Assistent:" in hist else hist
        chosen_products = extract_products_from_output(last)
        if not chosen_products:
            raise HTTPException(400, "Keine Produkte erkannt. Sende 'products'[] oder eine Materialien-Liste im 'message'.")

    # --- Kontext bauen ---
    ctx_lines = find_exact_catalog_lines(chosen_products)
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
    product_query = "Erstelle ein Angebot für folgende Produkte:\n" + "\n".join(f"- {p}" for p in chosen_products)

    # --- LLM2 direkt ansteuern ---
    formatted = PROMPT2.format(context=context, question=product_query)
    resp = llm2.invoke(formatted)
    answer = resp.content if isinstance(resp, AIMessage) else str(resp)

    # --- JSON extrahieren ---
    try:
        json_text = extract_json_array(answer)
    except Exception:
        raise HTTPException(
            status_code=422,
            detail=f"LLM2 lieferte kein gültiges JSON. Preview: {answer[:200]}"
        )

    try:
        positions = parse_positions(json_text)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"JSON-Parsing-Fehler: {e}. Preview: {json_text[:200]}"
        )

    return {"positions": positions, "raw": answer}


# ---- API: PDF bauen ----
@app.post("/api/pdf")
def api_pdf(payload: Dict[str, Any] = Body(...)):
    positions = payload.get("positions")
    if not positions or not isinstance(positions, list):
        raise HTTPException(400, "positions[] required")

    # Summen berechnen (falls gesamtpreis fehlt)
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
    # Roh-Content der geladenen Dokumente zeigen (zum Abgleichen deiner Strings)
    items = [d.page_content for d in DOCUMENTS[:limit]]
    return {"count": len(DOCUMENTS), "sample": items}

@app.get("/api/search")
def api_search(q: str = Query(..., min_length=2), k: int = 8):
    docs: list[LCDocument] = RETRIEVER.get_relevant_documents(q)[:k]
    return {"query": q, "results": [d.page_content for d in docs]}

# ---------- Lokaler Start ----------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    # Modulname ist "main", Variable heißt "app"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
