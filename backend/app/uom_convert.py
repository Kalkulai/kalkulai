from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

_UOM_ALIASES = {
    "l": "L",
    "liter": "L",
    "lt": "L",
    "lit": "L",
    "kg": "kg",
    "kilogramm": "kg",
    "g": "g",
    "gramm": "g",
    "m": "m",
    "meter": "m",
    "lfm": "m",
    "m2": "m²",
    "m^2": "m²",
    "qm": "m²",
    "m3": "m³",
    "m^3": "m³",
    "cbm": "m³",
    "stk": "Stück",
    "stück": "Stück",
    "pieces": "Stück",
    "rolle": "Rolle",
    "rollen": "Rolle",
    "eimer": "Eimer",
    "kanister": "Kanister",
    "dose": "Dose",
    "pack": "Packung",
    "packung": "Packung",
    "paket": "Paket",
    "karton": "Karton",
    "gebinde": "Gebinde",
    "satz": "Set",
    "set": "Set",
    "sack": "Sack",
    "rolle(n)": "Rolle",
    "st": "Stück",
}

_CONTAINER_UNITS = {
    "Eimer",
    "Rolle",
    "Packung",
    "Paket",
    "Karton",
    "Dose",
    "Kanister",
    "Gebinde",
    "Sack",
    "Set",
}

_PACK_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(l|kg|m|m2|m²|qm)", re.IGNORECASE)


def normalize_uom(u: str) -> str:
    if not u:
        return ""
    value = u.strip()
    if not value:
        return ""
    key = value.lower()
    return _UOM_ALIASES.get(key, value)


def pack_to_base(qty: float, pack: Optional[str | float], unit: str) -> Tuple[float, str, Optional[float]]:
    if qty is None:
        return 0.0, unit, None
    try:
        qty_val = float(qty)
    except (TypeError, ValueError):
        return 0.0, unit, None

    pack_value: Optional[float] = None
    pack_unit = unit

    if isinstance(pack, (int, float)):
        pack_value = float(pack)
    elif isinstance(pack, str):
        match = _PACK_PATTERN.search(pack)
        if match:
            pack_value = float(match.group(1).replace(",", "."))
            pack_unit = match.group(2)

    pack_unit = normalize_uom(pack_unit or unit)
    if pack_value is None or not pack_unit:
        return qty_val, unit, None

    return qty_val * pack_value, pack_unit, pack_value


def paint_l_consumption(area_m2: float, coats: int, reserve: float = 0.1) -> float:
    base = (area_m2 or 0.0) * max(coats, 1) / 10.0
    return round(base * (1 + reserve), 3)


def primer_l_consumption(area_m2: float, reserve: float = 0.1) -> float:
    base = (area_m2 or 0.0) / 15.0
    return round(base * (1 + reserve), 3)


def tape_m_consumption(edge_m: float, reserve: float = 0.1) -> float:
    base = edge_m or 0.0
    return round(base * (1 + reserve), 3)


def harmonize_material_line(
    line: Dict[str, Any],
    pack_info: Optional[Tuple[float, str]] = None,
    base_unit_hint: Optional[str] = None,
) -> Tuple[Dict[str, Any], list[str], Optional[Dict[str, Any]]]:
    updated = dict(line)
    reasons: list[str] = []
    conversion_info: Optional[Dict[str, Any]] = None

    unit_raw = updated.get("einheit") or ""
    normalized_unit = normalize_uom(unit_raw)
    if normalized_unit and normalized_unit != unit_raw:
        updated["einheit"] = normalized_unit
        reasons.append("unit_normalized")
    elif not normalized_unit:
        normalized_unit = unit_raw

    detected_pack = pack_info or _detect_pack_from_name(updated.get("name") or "")
    requires_conversion = normalized_unit in _CONTAINER_UNITS or (
        normalized_unit == "Stück" and base_unit_hint and base_unit_hint != "Stück"
    )

    if requires_conversion:
        if detected_pack:
            qty = updated.get("menge") or 0
            try:
                qty_float = float(qty)
            except (TypeError, ValueError):
                qty_float = 0.0
            pack_value, pack_unit = detected_pack
            base_qty, base_unit, factor = pack_to_base(qty_float, f"{pack_value} {pack_unit}", pack_unit)
            updated["menge"] = base_qty
            updated["einheit"] = base_unit_hint or base_unit
            reasons.append("pack_to_base")
            if factor and qty_float:
                conversion_info = {
                    "factor": base_qty / qty_float if qty_float else factor,
                    "source_unit": normalized_unit or unit_raw,
                    "target_unit": updated["einheit"],
                }
        else:
            reasons.append("no_pack_detected")

    if base_unit_hint and updated.get("einheit") != base_unit_hint:
        updated["einheit"] = base_unit_hint
    return updated, reasons, conversion_info


def _detect_pack_from_name(name: str) -> Optional[Tuple[float, str]]:
    if not name:
        return None
    matches = list(_PACK_PATTERN.finditer(name))
    if not matches:
        return None
    match = matches[-1]
    value = float(match.group(1).replace(",", "."))
    unit = normalize_uom(match.group(2))
    return value, unit
