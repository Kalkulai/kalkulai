from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _reload_env(monkeypatch, tmp_path: Path, admin_key: str | None):
    db_path = tmp_path / "admin_api.db"
    monkeypatch.setenv("KALKULAI_DB_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("SKIP_LLM_SETUP", "1")
    if admin_key is None:
        monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ADMIN_API_KEY", admin_key)

    store = importlib.reload(__import__("backend.store.catalog_store", fromlist=["dummy"]))
    store.init_db()

    index_manager = importlib.reload(__import__("backend.retriever.index_manager", fromlist=["dummy"]))

    class DummyEmbedder:
        def encode(self, texts):
            return [[float(len(text) or 1.0)] for text in texts]

    index_manager._EMBEDDER = DummyEmbedder()
    index_manager._INDEX_CACHE.clear()

    importlib.reload(__import__("backend.app.admin_api", fromlist=["router"]))
    main = importlib.reload(__import__("backend.main", fromlist=["app"]))
    return main, index_manager


def _build_client(monkeypatch, tmp_path, admin_key=None):
    main, _ = _reload_env(monkeypatch, tmp_path, admin_key)
    return TestClient(main.app)


def test_admin_requires_key(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path, admin_key="secret")
    resp = client.post(
        "/api/admin/products",
        json={"company_id": "acme", "sku": "SKU-1", "name": "Test"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unauthorized"


def test_admin_optional_without_key(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path, admin_key=None)
    resp = client.get("/api/admin/products", params={"company_id": "acme"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_admin_product_synonym_index_flow(monkeypatch, tmp_path):
    main, index_manager = _reload_env(monkeypatch, tmp_path, admin_key="secret")
    client = TestClient(main.app)
    headers = {"X-Admin-Key": "secret"}

    # Create products
    p1 = {
        "company_id": "acme",
        "sku": "SKU-1",
        "name": "Innenfarbe Weiß",
        "description": "10 L",
    }
    p2 = {
        "company_id": "acme",
        "sku": "SKU-2",
        "name": "Putzgrund Fassade",
        "description": "Außen",
    }
    assert client.post("/api/admin/products", json=p1, headers=headers).status_code == 200
    assert client.post("/api/admin/products", json=p2, headers=headers).status_code == 200

    resp = client.get("/api/admin/products", params={"company_id": "acme"}, headers=headers)
    assert len(resp.json()) == 2

    resp = client.put(
        "/api/admin/products/SKU-1",
        params={"company_id": "acme"},
        json={"description": "12 L"},
        headers=headers,
    )
    assert resp.json()["description"] == "12 L"

    resp = client.delete(
        "/api/admin/products/SKU-2",
        params={"company_id": "acme"},
        headers=headers,
    )
    assert resp.json()["deleted"] is True

    resp = client.get("/api/admin/products", params={"company_id": "acme"}, headers=headers)
    assert len(resp.json()) == 1

    syn_payload = {"company_id": "acme", "canon": "Tiefgrund", "synonyms": ["Tief Grund", "Tief-Grund"]}
    resp = client.post("/api/admin/synonyms", json=syn_payload, headers=headers)
    data = resp.json()
    assert "tiefgrund" in data

    resp = client.get("/api/admin/synonyms", params={"company_id": "acme"}, headers=headers)
    assert "tiefgrund" in resp.json()

    # Index rebuild & stats
    resp = client.post("/api/admin/index/rebuild", json={"company_id": "acme"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["docs"] == 1

    stats = client.get("/api/admin/index/stats", params={"company_id": "acme"}, headers=headers).json()
    assert stats["docs"] == 1

    # Add new product and update incrementally
    client.post(
        "/api/admin/products",
        json={"company_id": "acme", "sku": "SKU-3", "name": "Tiefgrund Innen"},
        headers=headers,
    )
    client.post(
        "/api/admin/index/update",
        json={"company_id": "acme", "changed_skus": ["SKU-3"]},
        headers=headers,
    )
    stats = client.get("/api/admin/index/stats", params={"company_id": "acme"}, headers=headers).json()
    assert stats["docs"] == 2

    # Delete product and update index
    client.delete("/api/admin/products/SKU-1", params={"company_id": "acme"}, headers=headers)
    client.post(
        "/api/admin/index/update",
        json={"company_id": "acme", "changed_skus": ["SKU-1"]},
        headers=headers,
    )
    stats = client.get("/api/admin/index/stats", params={"company_id": "acme"}, headers=headers).json()
    assert stats["docs"] == 1

    # CORS preflight
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == "*"
