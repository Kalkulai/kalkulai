import json, re
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
        except Exception:
            continue

        epreis_raw = pos.get("epreis", None)
        if epreis_raw in (None, ""):
            epreis_raw = pos.get("preis", None)
        if epreis_raw in (None, ""):
            epreis_raw = pos.get("einzelpreis", None)
        try:
            epreis = float(epreis_raw) if epreis_raw not in (None, "") else None
        except Exception:
            epreis = None

        if epreis is None:
            gesamt_raw = pos.get("gesamtpreis", None)
            try:
                gesamtpreis = float(gesamt_raw) if gesamt_raw not in (None, "") else None
            except Exception:
                gesamtpreis = None
            if gesamtpreis is not None and menge:
                epreis = round(gesamtpreis / menge, 2)
        if epreis is None:
            epreis = 0.0

        if not name or not einheit or menge <= 0 or epreis < 0:
            continue
        gesamt = round(menge * epreis, 2)
        if not gesamt and pos.get("gesamtpreis"):
            try:
                gesamt = float(pos["gesamtpreis"])
            except Exception:
                pass
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


def extract_json_array(s: str) -> str:
    if not s:
        raise ValueError("LLM2 lieferte keinen JSON-Array")

    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)```", s, re.IGNORECASE)
    if fence_match:
        s = fence_match.group(1)
    else:
        s = clean_json_string(s)

    start = s.find("[")
    end = s.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM2 lieferte keinen JSON-Array")
    return s[start:end+1]
