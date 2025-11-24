import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("SKIP_LLM_SETUP", "1")

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.uom_convert import harmonize_material_line  # noqa: E402
import backend.main as main  # noqa: E402


def _apply_offer_postprocess(positions):
    business_cfg = {"availability": {}, "price": {}, "margin": {}, "brand_boost": {}}
    if main.RETRIEVER is not None:
        for pos in positions:
            if pos.get("matched_sku"):
                continue
            query_name = pos.get("name") or ""
            if not query_name:
                continue
            ranked = main.rank_main(query_name, main.RETRIEVER, top_k=5, business_cfg=business_cfg)
            if not ranked:
                continue
            top = ranked[0]
            if top.get("sku"):
                pos["matched_sku"] = top["sku"]
            if top.get("name"):
                pos["name"] = top["name"]
            pos.setdefault("reasons", []).append("rank_main_top1")

    harmonized = []
    for pos in positions:
        pos2, reasons, _ = harmonize_material_line(pos)
        if reasons:
            pos2.setdefault("reasons", []).extend(reasons)
        try:
            menge_val = float(pos2.get("menge", 0))
            pos2["menge"] = int(menge_val) if menge_val.is_integer() else round(menge_val, 3)
        except (TypeError, ValueError):
            pass
        harmonized.append(pos2)
    return harmonized


def test_harmonize_paint_pack_to_base():
    line = {"name": "Dispersionsfarbe weiß 10 L", "menge": 3, "einheit": "Eimer"}
    updated, reasons, conversion = harmonize_material_line(line)
    assert updated["menge"] == 30.0
    assert updated["einheit"] == "L"
    assert "pack_to_base" in reasons
    assert conversion and conversion["factor"] == pytest.approx(10.0)


def test_harmonize_tape_roll_to_meters():
    line = {"name": "Malerkrepp 50 m", "menge": 2, "einheit": "Rolle"}
    updated, reasons, conversion = harmonize_material_line(line)
    assert pytest.approx(updated["menge"], rel=1e-6) == 100.0
    assert updated["einheit"] == "m"
    assert "pack_to_base" in reasons
    assert conversion and conversion["factor"] == pytest.approx(50.0)


def test_harmonize_primer_single_pack():
    line = {"name": "Tiefgrund 10 L", "menge": 1, "einheit": "Eimer"}
    updated, reasons, conversion = harmonize_material_line(line)
    assert updated["menge"] == 10.0
    assert updated["einheit"] == "L"
    assert "pack_to_base" in reasons
    assert conversion and conversion["factor"] == pytest.approx(10.0)


def test_rank_main_fallback_assigns_sku(monkeypatch):
    main.RETRIEVER = object()

    def _fake_rank(name, retriever, top_k=5, business_cfg=None):
        return [
            {
                "sku": "SKU123",
                "name": "Haftgrund Innen 10 L",
                "unit": "L",
            }
        ]

    monkeypatch.setattr(main, "rank_main", _fake_rank, raising=False)

    positions = [
        {"name": "Haftgrund", "menge": 1, "einheit": "Eimer", "epreis": 0.0, "gesamtpreis": 0.0},
    ]

    processed = _apply_offer_postprocess(positions)
    assert processed[0]["matched_sku"] == "SKU123"
    assert processed[0]["name"] == "Haftgrund Innen 10 L"
    assert processed[0]["einheit"] == "L"
    assert processed[0]["menge"] == 10
    assert "rank_main_top1" in processed[0]["reasons"]
