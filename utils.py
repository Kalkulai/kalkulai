import json
from typing import List, Dict, Any

def extract_products_from_output(output: str) -> List[str]:
    bad = ("angebot wird", "ich erstelle", "perfekt", "sammle", "gerne")
    out: List[str] = []
    for line in output.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(("•", "–", "-")) and len(s) > 3:
            cl = s.lstrip("•–-").strip()
            if cl and not any(b in cl.lower() for b in bad):
                out.append(cl)
            continue
        if ":" in s and not any(b in s.lower() for b in bad):
            left, right = s.split(":", 1)
            if len(left.strip()) > 3 and right.strip():
                out.append(s)
    return out


def clean_json_string(s: str) -> str:
    s = s.strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


def parse_positions(llm2_json: str) -> List[Dict[str, Any]]:
    raw = json.loads(clean_json_string(llm2_json))
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("Erwarte JSON-Array")

    out: List[Dict[str, Any]] = []
    for i, pos in enumerate(raw, 1):
        name = str(pos.get("name", "")).strip()
        einheit = str(pos.get("einheit", "")).strip()
        try:
            menge = float(pos.get("menge", 0))
            epreis = float(pos.get("epreis", 0))
        except Exception:
            continue
        if not name or not einheit or menge <= 0 or epreis < 0:
            continue
        gesamt = round(menge * epreis, 2)
        out.append(
            {
                "nr": i,
                "name": name,
                "menge": int(menge) if float(menge).is_integer() else menge,
                "einheit": einheit,
                "epreis": round(epreis, 2),
                "gesamtpreis": gesamt,
            }
        )
    return out
