from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


def _setup_app(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "company.db"
    monkeypatch.setenv("KALKULAI_DB_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("SKIP_LLM_SETUP", "1")
    store = importlib.reload(__import__("backend.store.catalog_store", fromlist=["dummy"]))
    store.init_db()
    store.upsert_product("acme", {"sku": "acme-dsp-10l", "name": "Innenfarbe Weiß 10 L", "description": "Acme"})
    store.upsert_product("beta", {"sku": "beta-tiefgrund-10l", "name": "Tiefengrund 10 L", "description": "Beta"})

    index_manager = importlib.reload(__import__("backend.retriever.index_manager", fromlist=["dummy"]))

    class DummyEmbedder:
        def encode(self, texts):
            return [[float(len(text) or 1.0)] for text in texts]

    index_manager._EMBEDDER = DummyEmbedder()
    index_manager._INDEX_CACHE.clear()
    index_manager.rebuild_index("acme")
    index_manager.rebuild_index("beta")

    main = importlib.reload(__import__("backend.main", fromlist=["app"]))

    class StubRetriever:
        class Doc:
            def __init__(self, text):
                self.page_content = text
                self.metadata = {"name": text, "sku": "legacy"}

        def get_relevant_documents(self, query):
            return [self.Doc(query)]

    main.RETRIEVER = StubRetriever()

    last_company = {"value": None}

    def fake_rank_main(query, retriever, top_k=5, business_cfg=None, company_id=None):
        last_company["value"] = company_id
        sku = "beta-tiefgrund-10l" if company_id == "beta" else "acme-dsp-10l"
        return [{"sku": sku, "name": f"Result {sku}"}]

    backend_retriever_main = importlib.import_module("backend.retriever.main")
    backend_retriever_main.rank_main = fake_rank_main
    main.rank_main = fake_rank_main
    main._ensure_llm_enabled = lambda *args, **kwargs: None
    main.chain2 = object()

    class DummyLLM:
        def invoke(self, formatted):
            company = last_company["value"] or "acme"
            sku = "beta-tiefgrund-10l" if company == "beta" else "acme-dsp-10l"
            content = (
                f'[{{"nr":1,"name":"{sku}","menge":1,"einheit":"stk","sku":"{sku}","epreis":0,"gesamtpreis":0}}]'
            )
            return SimpleNamespace(content=content)

    main.llm2 = DummyLLM()

    class DummyPrompt:
        def format(self, **kwargs):
            return ""

    main.PROMPT2 = DummyPrompt()
    main.memory1 = SimpleNamespace(load_memory_variables=lambda _: {"chat_history": ""})
    main.chain1 = SimpleNamespace(run=lambda **kwargs: None)

    return TestClient(main.app)


def test_company_specific_catalog_search(monkeypatch, tmp_path):
    client = _setup_app(monkeypatch, tmp_path)

    resp = client.get("/api/catalog/search", params={"q": "Innenfarbe Weiß", "company_id": "acme"})
    assert resp.status_code == 200
    names = [item["sku"] for item in resp.json()["results"]]
    assert names and names[0] == "acme-dsp-10l"

    resp = client.get("/api/catalog/search", params={"q": "Tiefgrund 10 L", "company_id": "beta"})
    assert resp.status_code == 200
    names = [item["sku"] for item in resp.json()["results"]]
    assert names and names[0] == "beta-tiefgrund-10l"

    resp = client.get("/api/catalog/search", params={"q": "Innenfarbe Weiß"})
    assert resp.status_code == 200


def test_company_specific_offer(monkeypatch, tmp_path):
    client = _setup_app(monkeypatch, tmp_path)
    payload = {"message": "Bitte Angebot", "products": ["Tiefgrund 10 L"]}
    resp = client.post("/api/offer", params={"company_id": "beta"}, json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "beta-tiefgrund-10l" in data["positions"][0]["name"]
