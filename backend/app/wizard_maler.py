# app/wizard_maler.py
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import uuid

router = APIRouter(prefix="/wizard/maler", tags=["wizard-maler"])

# --- In-Memory Session Store (einheitlich!) ---
WIZ_SESSIONS: Dict[str, Dict[str, Any]] = {}

def reset_all_sessions() -> None:
    """Wird von main.py (/api/session/reset) aufgerufen."""
    WIZ_SESSIONS.clear()

# Schritte des Fragebaums
STEPS: List[str] = [
    "innen_aussen",
    "untergrund",
    "flaeche_m2",
    "deckenflaeche_m2",
    "anzahl_schichten",
    "vorarbeiten",
    "farbe_typ",
    "farbe_glanzgrad",
]

OPTIONS: Dict[str, List[str]] = {
    "innen_aussen": ["Innen", "Aussen"],  # Schreibweise mit Doppel-s bleibt; _norm() im Revenue Guard lowercased
    "untergrund": ["Putz", "Gipskarton", "Beton", "Altanstrich", "Tapete", "Unbekannt"],
    "vorarbeiten": ["Abdecken", "Abkleben", "Grundieren", "Spachteln", "Schleifen"],
    "farbe_typ": ["Dispersionsfarbe", "Latexfarbe", "Silikat", "Acryl"],
    "farbe_glanzgrad": ["Matt", "Seidenglanz", "Glanz"],
}

QUESTIONS: Dict[str, str] = {
    "innen_aussen": "Handelt es sich um Innen- oder Außenarbeiten?",
    "untergrund": "Welcher Untergrund liegt überwiegend vor?",
    "flaeche_m2": "Wie groß ist die zu streichende Wandfläche in m²?",
    "deckenflaeche_m2": "Wie groß ist die zu streichende Deckenfläche in m²? (0, falls keine)",
    "anzahl_schichten": "Wie viele Anstrichschichten sind gewünscht?",
    "vorarbeiten": "Welche Vorarbeiten fallen an?",
    "farbe_typ": "Welche Farbart soll verwendet werden?",
    "farbe_glanzgrad": "Welcher Glanzgrad ist gewünscht?",
}

# --- Pydantic Modelle ---
class Suggestion(BaseModel):
    nr: int
    name: str
    menge: float
    einheit: str
    text: str

class WizardNextRequest(BaseModel):
    session_id: Optional[str] = None
    answers: Optional[Dict[str, Any]] = None

class WizardNextResponse(BaseModel):
    session_id: str
    step: str
    question: str
    ui: Dict[str, Any]
    context_partial: Dict[str, Any]
    done: bool
    suggestions: List[Suggestion] = Field(default_factory=list)

class FinalizeRequest(BaseModel):
    session_id: str

class Position(BaseModel):
    nr: int
    name: str
    menge: float
    einheit: str
    text: str

class FinalizeResponse(BaseModel):
    session_id: str
    summary: str
    positions: List[Position]
    done: bool = True

# --- Hilfsfunktionen ---
def _ensure_session(session_id: Optional[str]) -> str:
    if session_id and session_id in WIZ_SESSIONS:
        return session_id
    sid = session_id or str(uuid.uuid4())
    WIZ_SESSIONS[sid] = {"context": {}, "step_idx": 0}
    return sid

def _get_session(sid: str) -> Dict[str, Any]:
    if sid not in WIZ_SESSIONS:
        WIZ_SESSIONS[sid] = {"context": {}, "step_idx": 0}
    return WIZ_SESSIONS[sid]

def _current_step(session: Dict[str, Any]) -> str:
    idx = int(session.get("step_idx", 0))
    return STEPS[idx] if 0 <= idx < len(STEPS) else "done"

def _advance(session: Dict[str, Any]) -> None:
    session["step_idx"] = int(session.get("step_idx", 0)) + 1

def _ui_for_step(step: str) -> Dict[str, Any]:
    if step in ["innen_aussen", "untergrund", "farbe_typ", "farbe_glanzgrad"]:
        return {"type": "singleSelect", "options": OPTIONS[step]}
    if step == "vorarbeiten":
        return {"type": "multiSelect", "options": OPTIONS[step]}
    if step in ["flaeche_m2", "deckenflaeche_m2"]:
        return {"type": "number", "min": 0, "max": 10000, "step": 0.5}
    if step == "anzahl_schichten":
        return {"type": "number", "min": 1, "max": 4, "step": 1}
    return {"type": "info"}

def _calc_positions(ctx: Dict[str, Any]) -> List[Suggestion]:
    """Einfache Heuristiken für Live-Vorschläge (rechts im UI angezeigt)."""
    fl = float(ctx.get("flaeche_m2", 0) or 0)
    dl = float(ctx.get("deckenflaeche_m2", 0) or 0)
    schichten = int(ctx.get("anzahl_schichten", 2) or 2)
    total = fl + dl

    if total <= 0:
        return []

    farbe_l = round(((total / 10.0) * schichten) * 1.10, 1)   # 1 L / 10 m² pro Schicht +10% Reserve
    folie_rollen = int((total + 39.9) // 40)                   # ~1 Rolle/40 m²

    out: List[Suggestion] = []
    out.append(Suggestion(
        nr=1,
        name="Dispersionsfarbe, weiß, 10 L",
        menge=farbe_l,
        einheit="L",
        text=f"Wand/Decke {int(total)} m², {schichten} Schichten (1 L/10 m²/Schicht +10% Reserve)"
    ))
    out.append(Suggestion(
        nr=2,
        name="Abdeckfolie 4x5 m",
        menge=folie_rollen,
        einheit="Rolle",
        text="Schutz für Böden/Möbel (~1 Rolle/40 m²)"
    ))
    return out

# --- API ---
@router.post("/next", response_model=WizardNextResponse)
def wizard_next(payload: WizardNextRequest = Body(...)):
    sid = _ensure_session(payload.session_id)
    session = _get_session(sid)

    # Antwort übernehmen
    if payload.answers:
        session["context"].update(payload.answers)
        _advance(session)

    step = _current_step(session)
    suggestions = _calc_positions(session["context"])  # Live-Vorschläge (rechts)

    if step == "done":
        return WizardNextResponse(
            session_id=sid,
            step="done",
            question="Alle Angaben sind vollständig. Möchtest du jetzt finalisieren?",
            ui={"type": "info"},
            context_partial=session["context"],
            done=True,
            suggestions=suggestions,
        )

    return WizardNextResponse(
        session_id=sid,
        step=step,
        question=QUESTIONS.get(step, "Weiter"),
        ui=_ui_for_step(step),
        context_partial=session["context"],
        done=False,
        suggestions=suggestions,
    )

@router.post("/finalize", response_model=FinalizeResponse)
def wizard_finalize(payload: FinalizeRequest = Body(...)):
    sid = payload.session_id
    session = WIZ_SESSIONS.get(sid)
    if not session:
        raise HTTPException(status_code=400, detail="Ungültige Session")

    ctx = session["context"]
    fl = float(ctx.get("flaeche_m2", 0) or 0)
    dl = float(ctx.get("deckenflaeche_m2", 0) or 0)
    schichten = int(ctx.get("anzahl_schichten", 2) or 2)
    total = fl + dl

    farbe = round(((total / 10.0) * schichten) * 1.10, 1)
    folie = int((total + 39.9) // 40) if total > 0 else 0

    positions = [
        Position(nr=1, name="Dispersionsfarbe, weiß, 10 L", menge=farbe, einheit="L",
                 text=f"Wandanstrich für {int(total)} m² in {schichten} Schichten"),
        Position(nr=2, name="Abdeckfolie 4x5 m", menge=folie, einheit="Rolle",
                 text="Schutz für Böden/Möbel"),
    ]

    return FinalizeResponse(
        session_id=sid,
        summary=f"Projekt mit {int(total)} m² Fläche, {schichten} Schichten.",
        positions=positions,
        done=True,
    )

# (optional) JSON-Schema – hilfreich fürs Debuggen
SCHEMA_MALER_WIZARD = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "MalerWizardState",
  "type": "object",
  "properties": {
    "session_id": { "type": "string" },
    "context": {
      "type": "object",
      "properties": {
        "innen_aussen": { "type": "string", "enum": ["innen", "aussen"] },
        "untergrund": { "type": "string", "enum": ["putz", "gipskarton", "beton", "altanstrich", "tapete", "unbekannt"] },
        "flaeche_m2": { "type": "number", "minimum": 0 },
        "deckenflaeche_m2": { "type": "number", "minimum": 0 },
        "anzahl_schichten": { "type": "integer", "minimum": 1, "maximum": 4, "default": 2 },
        "vorarbeiten": {
          "type": "array",
          "items": { "type": "string", "enum": ["abdecken", "abkleben", "grundieren", "spachteln", "schleifen"] },
          "default": []
        },
        "farbe_typ": { "type": "string", "enum": ["dispersionsfarbe", "latexfarbe", "silikat", "acryl"], "default": "dispersionsfarbe" },
        "farbe_glanzgrad": { "type": "string", "enum": ["matt", "seidenglanz", "glanz"], "default": "matt" }
      }
    },
    "step": { "type": "string" },
    "completed": { "type": "boolean" }
  },
  "required": ["session_id"]
}

@router.get("/schema")
def wizard_schema():
    return SCHEMA_MALER_WIZARD
