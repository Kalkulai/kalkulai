from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import time

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.retriever.main import rank_main  # noqa: E402


@dataclass
class FakeDocument:
    page_content: str
    metadata: dict


class MockRetriever:
    def __init__(self, documents):
        self.documents = documents

    def get_relevant_documents(self, query):  # pragma: no cover - simple shim
        return self.documents


DOCS_FIXTURE = [
    FakeDocument(
        "Haftgrund Produkt",
        {
            "sku": "SKU-1",
            "name": "Haftgrund Innen 10 L",
            "unit": "L",
            "category": "primer",
            "brand": "Favorit",
            "synonyms": ["Haftgrundierung", "Tiefgrund"],
        },
    ),
    FakeDocument(
        "Dispersionsfarbe weiß",
        {
            "sku": "SKU-2",
            "name": "Dispersionsfarbe Premium 12 L",
            "unit": "L",
            "category": "paint",
            "brand": "StandardCo",
        },
    ),
    FakeDocument(
        "Malerkrepp",
        {
            "sku": "SKU-3",
            "name": "Malerkrepp 50 m",
            "unit": "m",
            "category": "tape",
            "brand": "FixIt",
        },
    ),
    FakeDocument(
        "Grundierung",
        {
            "sku": "SKU-4",
            "name": "Tiefgrund LF 5 L",
            "unit": "L",
            "category": "primer",
            "brand": "Budget",
        },
    ),
    FakeDocument(
        "Innenfarbe",
        {
            "sku": "SKU-5",
            "name": "Innenfarbe Matt 10 L",
            "unit": "L",
            "category": "paint",
            "brand": "Favorit",
        },
    ),
    FakeDocument(
        "Reiniger",
        {
            "sku": "SKU-6",
            "name": "Neutralreiniger 1 L",
            "unit": "L",
            "category": "cleaner",
            "brand": "StandardCo",
        },
    ),
]


BASE_BUSINESS_CFG = {
    "availability": {"SKU-1": 1, "SKU-2": 0, "SKU-3": 1, "SKU-4": 0, "SKU-5": 1},
    "price": {"SKU-1": 32.5, "SKU-2": 45.0, "SKU-3": 9.5, "SKU-4": 18.0, "SKU-5": 38.0},
    "margin": {"SKU-1": 0.18, "SKU-2": 0.12, "SKU-3": 0.25, "SKU-5": 0.2},
    "brand_boost": {"favorit": 0.05},
}


def test_main_returns_topk_and_schema() -> None:
    retriever = MockRetriever(DOCS_FIXTURE)
    results = rank_main("Haftgrund weiß Innen", retriever, top_k=4, business_cfg=BASE_BUSINESS_CFG)
    assert 1 <= len(results) <= 4
    first = results[0]
    for field in {"sku", "name", "unit", "category", "brand", "score_main", "score_business", "reasons"}:
        assert field in first
    assert isinstance(first["reasons"], list)
    assert 0.0 <= first["score_main"] <= 1.0


def test_main_deterministic_ties() -> None:
    retriever = MockRetriever(DOCS_FIXTURE)
    run_one = rank_main("Innenfarbe", retriever, top_k=5, business_cfg=BASE_BUSINESS_CFG)
    run_two = rank_main("Innenfarbe", retriever, top_k=5, business_cfg=BASE_BUSINESS_CFG)
    assert [item["sku"] for item in run_one] == [item["sku"] for item in run_two]


def test_main_business_layer_effects() -> None:
    retriever = MockRetriever(DOCS_FIXTURE)
    results = rank_main("Kreppband", retriever, top_k=3, business_cfg=BASE_BUSINESS_CFG)
    assert results
    assert results[0]["sku"] == "SKU-3"  # availability + margin
    assert "availability" in results[0]["reasons"]
    assert "margin" in results[0]["reasons"]


def test_main_respects_brand_boost() -> None:
    retriever = MockRetriever(DOCS_FIXTURE)
    cfg = BASE_BUSINESS_CFG | {"brand_boost": {"favorit": 0.1}}
    boosted = rank_main("Innenfarbe", retriever, top_k=3, business_cfg=cfg)
    assert boosted
    assert boosted[0]["brand"].lower() == "favorit"


def test_main_latency_budget() -> None:
    retriever = MockRetriever(DOCS_FIXTURE * 30)
    start = time.perf_counter()
    for _ in range(10):
        rank_main("Innenfarbe weiß", retriever, top_k=5, business_cfg=BASE_BUSINESS_CFG)
    duration = time.perf_counter() - start
    assert duration < 1.5  # generous upper bound for CI
