# main.py
from __future__ import annotations

import os
import re
import math
from uuid import uuid4
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, Body, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Lokale Module
from app.db import load_products_file, build_vector_db
from app.utils import extract_products_from_output, parse_positions, extract_json_array


# ---------- Pfade & ENV ----------
BASE_DIR = Path(__file__).parent

DATA_ROOT  = Path(os.getenv("DATA_ROOT", str(BASE_DIR)))
DATA_DIR   = BASE_DIR / "data"
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(DATA_ROOT / "chroma_db")))
TEMPLATES  = BASE_DIR / "templates"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(DATA_ROOT / "outputs")))

CHROMA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEBUG = os.getenv("DEBUG", "0") == "1"
MODEL_PROVIDER  = os.getenv("MODEL_PROVIDER", "openai").lower()        
MODEL_LLM1      = os.getenv("MODEL_LLM1", "gpt-4o-mini")
MODEL_LLM2      = os.getenv("MODEL_LLM2", "gpt-4o-mini")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
VAT_RATE        = float(os.getenv("VAT_RATE", "0.19"))
SKIP_LLM_SETUP  = os.getenv("SKIP_LLM_SETUP", "0") == "1"

if not SKIP_LLM_SETUP:
    from app.llm import create_chat_llm, build_chains  # type: ignore
else:  # pragma: no cover - placeholder for smoke tests
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
PRODUCT_FILE = DATA_DIR / "bauprodukte_maurerprodukte.txt"
DOCUMENTS = load_products_file(PRODUCT_FILE, debug=DEBUG)
if SKIP_LLM_SETUP:
    DB = None
    RETRIEVER = None
else:
    DB, RETRIEVER = build_vector_db(DOCUMENTS, CHROMA_DIR, debug=DEBUG)

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
app = FastAPI(title="Kalkulai Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://Kalkuali-kalkulai-frontend.hf.space"],  # Frontend-URL hier
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

# Startup-Log
@app.on_event("startup")
def _startup():
    print("✅ Startup")
    print(f"   MODEL_PROVIDER={MODEL_PROVIDER}  LLM1={MODEL_LLM1}  LLM2={MODEL_LLM2}  VAT_RATE={VAT_RATE}")
    print(f"   Produktdatei: {'OK' if PRODUCT_FILE.exists() else 'FEHLT'}")
    print(f"   CHROMA_DIR={CHROMA_DIR}  (writable)")
    print(f"   OUTPUT_DIR={OUTPUT_DIR}  (writable)")

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
    if not has_machine_block:
        items = _extract_materials_from_text_any(reply_text)
        if items:
            machine_block = _make_machine_block("schätzung", items)
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
        items = _extract_materials_from_text_any(reply_text)
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
        else:
            # wir können nicht bestätigen, weil uns Materials fehlen
            ready = False

    # (Sicherheitsnetz) Falls zwar ein Maschinenanhang existiert, aber keine explizite Bestätigung erkannt wurde,
    # markieren wir trotzdem ready → UI kann Angebot erzeugen.
    if not ready and has_machine_block:
        ready = True

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

    # --- exakte Katalogzeilen finden ---
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
                    ctx.append(line); seen.add(line)
        # 2) Fallback Retriever
        for t in terms:
            key = (t or "").strip().lower()
            if not key or key in catalog_lower:
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
