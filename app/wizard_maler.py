# app/wizard_maler.py
from fastapi import APIRouter, Body
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import uuid

router = APIRouter(prefix="/wizard/maler", tags=["wizard-maler"])

# --- In-Memory Session Store ---
SESSIONS: Dict[str, Dict[str, Any]] = {}

# Schritte des Fragebaums
STEPS = [
    "innen_aussen",
    "untergrund",
    "flaeche_m2",
    "deckenflaeche_m2",
    "anzahl_schichten",
    "vorarbeiten",
    "farbe_typ",
    "farbe_glanzgrad",
]

OPTIONS = {
    "innen_aussen": ["innen", "aussen"],
    "untergrund": ["putz", "gipskarton", "beton", "altanstrich", "tapete", "unbekannt"],
    "vorarbeiten": ["abdecken", "abkleben", "grundieren", "spachteln", "schleifen", "nikotin_sperre"],
    "farbe_typ": ["dispersionsfarbe", "latexfarbe", "silikat", "acryl"],
    "farbe_glanzgrad": ["matt", "seidenglanz", "glanz"],
}

QUESTIONS = {
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
    if session_id and session_id in SESSIONS:
        return session_id
    sid = session_id or str(uuid.uuid4())
    SESSIONS[sid] = {"context": {}, "step_idx": 0}
    return sid

def _current_step(session) -> str:
    idx = session["step_idx"]
    return STEPS[idx] if idx < len(STEPS) else "done"

def _advance(session):
    session["step_idx"] += 1

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

# --- API ---
@router.post("/next", response_model=WizardNextResponse)
def wizard_next(payload: WizardNextRequest = Body(...)):
    sid = _ensure_session(payload.session_id)
    session = SESSIONS[sid]

    if payload.answers:
        session["context"].update(payload.answers)
        _advance(session)

    step = _current_step(session)
    if step == "done":
        return WizardNextResponse(
            session_id=sid,
            step="done",
            question="Alle Angaben sind vollständig. Möchtest du jetzt finalisieren?",
            ui={"type": "info"},
            context_partial=session["context"],
            done=True,
        )

    return WizardNextResponse(
        session_id=sid,
        step=step,
        question=QUESTIONS.get(step, "Weiter"),
        ui=_ui_for_step(step),
        context_partial=session["context"],
        done=False,
    )

@router.post("/finalize", response_model=FinalizeResponse)
def wizard_finalize(payload: FinalizeRequest = Body(...)):
    sid = payload.session_id
    session = SESSIONS.get(sid)
    if not session:
        raise ValueError("Ungültige Session")

    ctx = session["context"]
    fl = float(ctx.get("flaeche_m2", 0) or 0)
    dl = float(ctx.get("deckenflaeche_m2", 0) or 0)
    schichten = int(ctx.get("anzahl_schichten", 2) or 2)
    total = fl + dl

    # Materialmengen (Mock-Logik)
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
