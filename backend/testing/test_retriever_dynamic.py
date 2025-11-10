import importlib
import os
from pathlib import Path

import pytest


def _reload_modules(tmp_path, monkeypatch):
    db_path = tmp_path / "catalog_dynamic.db"
    monkeypatch.setenv("KALKULAI_DB_URL", f"sqlite:///{db_path}")
    store = importlib.reload(__import__("backend.store.catalog_store", fromlist=["dummy"]))
    store.init_db()
    index_manager = importlib.reload(__import__("backend.retriever.index_manager", fromlist=["dummy"]))

    class DummyEmbedder:
        def encode(self, texts):
            return [[float(len(text) or 1.0)] for text in texts]

    index_manager._EMBEDDER = DummyEmbedder()
    return store, index_manager


def test_ensure_index_builds_from_db(tmp_path, monkeypatch):
    store, index_manager = _reload_modules(tmp_path, monkeypatch)
    store.upsert_product("demo", {"sku": "SKU-A", "name": "Innenfarbe Weiß", "description": "10 L"})
    store.upsert_product("demo", {"sku": "SKU-B", "name": "Putzgrund Fassade", "description": "Aussen"})

    idx = index_manager.ensure_index("demo")
    assert idx is not None
    stats = index_manager.get_index_stats("demo")
    assert stats["docs"] == 2

    hits = index_manager.search_index("demo", "Putzgrund", top_k=2)
    assert hits and hits[0]["sku"] in {"SKU-A", "SKU-B"}


def test_update_index_incremental_add_then_delete(tmp_path, monkeypatch):
    store, index_manager = _reload_modules(tmp_path, monkeypatch)
    store.upsert_product("demo", {"sku": "SKU-1", "name": "Haftgrund Holz"})
    index_manager.ensure_index("demo")

    store.upsert_product("demo", {"sku": "SKU-2", "name": "Tiefgrund Innen"})
    index_manager.update_index_incremental("demo", ["SKU-2"])
    assert index_manager.get_index_stats("demo")["docs"] == 2

    store.delete_product("demo", "SKU-1")
    index_manager.update_index_incremental("demo", ["SKU-1"])
    assert index_manager.get_index_stats("demo")["docs"] == 1


def test_rebuild_index_forces_fresh_state(tmp_path, monkeypatch):
    store, index_manager = _reload_modules(tmp_path, monkeypatch)
    store.upsert_product("demo", {"sku": "SKU-1", "name": "Innenfarbe"})
    index_manager.ensure_index("demo")

    store.upsert_product("demo", {"sku": "SKU-2", "name": "Fassadenfarbe"})
    stats_before = index_manager.get_index_stats("demo")
    assert stats_before["docs"] == 1

    index_manager.rebuild_index("demo")
    stats_after = index_manager.get_index_stats("demo")
    assert stats_after["docs"] == 2
