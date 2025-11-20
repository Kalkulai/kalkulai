import os
import sys
from pathlib import Path

os.environ.setdefault("SKIP_LLM_SETUP", "1")

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
for path in (REPO_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from fastapi.testclient import TestClient
import pytest

import backend.main as main


class _DummyRetriever:
    def get_relevant_documents(self, query):  # pragma: no cover - helper
        return []


SAMPLE_ITEMS = [
    {
        "sku": "SKU-1",
        "name": "Haftgrund Innen 10 L",
        "unit": "L",
        "pack_sizes": None,
        "synonyms": ["Haftgrundierung"],
        "category": "primer",
        "brand": "Favorit",
        "description": "Haftgrund für Innen",
        "raw": "Haftgrund Innen 10 L",
    },
    {
        "sku": "SKU-2",
        "name": "Tiefgrund LF 5 L",
        "unit": "L",
        "pack_sizes": None,
        "synonyms": ["Tiefgrund"],
        "category": "primer",
        "brand": "Budget",
        "description": "Tiefgrund",
        "raw": "Tiefgrund LF 5 L",
    },
    {
        "sku": "SKU-3",
        "name": "Malerkrepp 50 m",
        "unit": "m",
        "pack_sizes": None,
        "synonyms": ["Kreppband"],
        "category": "tape",
        "brand": "FixIt",
        "description": "Malerkrepp",
        "raw": "Malerkrepp 50 m",
    },
]


def _reset_catalog(items):
    main.CATALOG_ITEMS = items
    main.CATALOG_BY_NAME = {
        (item["name"] or "").lower(): item for item in items if item.get("name")
    }
    main.CATALOG_BY_SKU = {item["sku"]: item for item in items if item.get("sku")}
    main.CATALOG_TEXT_BY_NAME = {
        (item["name"] or "").lower(): item.get("raw", "") for item in items if item.get("name")
    }
    main.CATALOG_TEXT_BY_SKU = {item["sku"]: item.get("raw", "") for item in items if item.get("sku")}
    main.CATALOG_SEARCH_CACHE.clear()


@pytest.fixture(autouse=True)
def _setup_environment():
    _reset_catalog(list(SAMPLE_ITEMS))
    main.RETRIEVER = _DummyRetriever()
    yield
    main.CATALOG_SEARCH_CACHE.clear()


@pytest.fixture()
def client():
    return TestClient(main.app)


def test_catalog_search_200_and_shape(client):
    resp = client.get("/api/catalog/search", params={"q": "Tiefgrund", "top_k": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] <= 5
    assert data["results"]
    first = data["results"][0]
    for key in ("sku", "name", "confidence"):
        assert key in first
    assert "took_ms" in data


def test_catalog_search_fallback_on_error(client, monkeypatch):
    def _boom(**kwargs):  # pragma: no cover - injected failure
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "search_catalog_thin", _boom)
    resp = client.get("/api/catalog/search", params={"q": "Haftgrund", "top_k": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0
    assert data["results"][0]["name"]


def test_catalog_search_logs_timing(client, caplog):
    caplog.set_level("INFO", logger="kalkulai")
    client.get("/api/catalog/search", params={"q": "Malerkrepp", "top_k": 2})
    assert any("catalog.search" in record.getMessage() for record in caplog.records)
