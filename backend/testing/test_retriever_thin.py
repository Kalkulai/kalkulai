from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.retriever.thin import search_catalog_thin  # noqa: E402

SYN_PATH = BACKEND_ROOT / "shared" / "normalize" / "synonyms.yaml"

CATALOG_FIXTURE = [
    {"sku": "SKU-1", "name": "Haftgrund LF weiß 5 L", "unit": "L", "category": "primer"},
    {"sku": "SKU-2", "name": "Dispersionsfarbe weiß 10 L", "unit": "L", "category": "paint"},
    {"sku": "SKU-3", "name": "Abdeckband Premium 50 m", "unit": "m", "category": "tape"},
    {"sku": "SKU-4", "name": "Spachtelmasse Innen 5 kg", "unit": "kg", "category": "filler"},
    {"sku": "SKU-5", "name": "Grundierung Universal 5 L", "unit": "L", "category": "primer"},
    {"sku": "SKU-6", "name": "Neutralreiniger 1 L", "unit": "L", "category": "cleaner"},
]


def test_thin_returns_at_most_topk() -> None:
    results = search_catalog_thin(
        "Haftgrundierung weiß",
        top_k=2,
        catalog_items=CATALOG_FIXTURE,
        synonyms_path=str(SYN_PATH),
    )
    assert len(results) <= 2
    if len(results) == 2:
        assert results[0]["score_final"] >= results[1]["score_final"]


def test_thin_schema_fields_present() -> None:
    results = search_catalog_thin(
        "Dispersionsfarbe",
        top_k=3,
        catalog_items=CATALOG_FIXTURE,
        synonyms_path=str(SYN_PATH),
    )
    assert results
    first = results[0]
    for field in {"sku", "name", "unit", "category", "score_final", "hard_filters_passed", "reasons"}:
        assert field in first
    assert isinstance(first["reasons"], list)


def test_thin_hard_filter_excludes_irrelevants() -> None:
    results = search_catalog_thin(
        "Edelstahl Schraube",
        top_k=5,
        catalog_items=CATALOG_FIXTURE,
        synonyms_path=str(SYN_PATH),
    )
    assert results == []


def test_thin_synonym_expansion_hits() -> None:
    results = search_catalog_thin(
        "Tiefgrund",
        top_k=3,
        catalog_items=CATALOG_FIXTURE,
        synonyms_path=str(SYN_PATH),
    )
    assert results
    assert results[0]["sku"] == "SKU-1"
    reason_blob = " ".join(results[0]["reasons"])
    assert "synonym bonus" in reason_blob


def test_thin_deterministic_ordering() -> None:
    local_catalog = [
        {"sku": "A", "name": "Farbe A Innen", "unit": "L", "category": "paint"},
        {"sku": "B", "name": "Farbe B Innen", "unit": "L", "category": "paint"},
    ]
    results = search_catalog_thin(
        "Farbe Innen",
        top_k=5,
        catalog_items=local_catalog,
        synonyms_path=str(SYN_PATH),
    )
    assert [item["name"] for item in results] == ["Farbe A Innen", "Farbe B Innen"]
