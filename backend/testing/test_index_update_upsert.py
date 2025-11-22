import importlib
import os
from pathlib import Path


def test_update_index_in_place(tmp_path):
    db_path = tmp_path / "catalog.db"
    os.environ["KALKULAI_DB_URL"] = f"sqlite:///{db_path}"

    store = importlib.reload(__import__("backend.store.catalog_store", fromlist=["dummy"]))
    store.init_db()
    store.upsert_product("demo", {"sku": "sku_dsp_10", "name": "Dispersionsfarbe weiß"})
    store.upsert_product("demo", {"sku": "sku_tg_10", "name": "Tiefengrund"})

    index_manager = importlib.reload(__import__("backend.retriever.index_manager", fromlist=["dummy"]))

    index_manager.rebuild_index("demo")
    assert index_manager.index_stats("demo")["docs"] == 2

    store.upsert_product("demo", {"sku": "sku_dsp_10", "name": "Dispersionsfarbe neu"})

    index_manager.update_index("demo", ["sku_dsp_10"])
    stats = index_manager.index_stats("demo")
    assert stats["docs"] == 2

    idx = index_manager.ensure_company_index("demo")
    docs = getattr(idx, "docs", None)
    if not docs:
        mapping = getattr(idx, "_map", None)
        if isinstance(mapping, dict):
            docs = mapping.values()
        else:
            stored = getattr(idx, "_docs", None)
            if isinstance(stored, dict):
                docs = stored.values()
    docs = docs or []
    names = {getattr(doc, "tags", {}).get("sku"): getattr(doc, "tags", {}).get("name") for doc in docs}
    assert names.get("sku_dsp_10") == "Dispersionsfarbe neu"


def test_update_index_refreshes_fallback_map(monkeypatch):
    monkeypatch.setenv("KALKULAI_DB_URL", "sqlite:///:memory:")
    store = importlib.reload(__import__("backend.store.catalog_store", fromlist=["dummy"]))
    store.init_db()
    store.upsert_product("acme", {"sku": "sku_dsp_10", "name": "Fassadenfarbe Grau 5L"})
    store.upsert_product(
        "acme",
        {
            "sku": "sku_dsp_10_weiss",
            "name": "Dispersionsfarbe Weiß Innen 10L",
        },
    )

    index_manager = importlib.reload(__import__("backend.retriever.index_manager", fromlist=["dummy"]))

    class DummyEmbedder:
        def encode(self, texts):
            return [[float(len(text) or 1.0)] for text in texts]

    dummy = DummyEmbedder()
    monkeypatch.setattr(index_manager, "_get_embedder", lambda: dummy)
    index_manager._EMBEDDER = dummy
    monkeypatch.setattr(index_manager, "_DOCARRAY_AVAILABLE", False, raising=False)

    index_manager.rebuild_index("acme")
    assert index_manager.index_stats("acme")["docs"] == 2

    store.upsert_product("acme", {"sku": "sku_dsp_10_weiss", "name": "Innenfarbe Premium Weiß 10L"})

    stats = index_manager.update_index("acme", ["sku_dsp_10_weiss"])
    assert stats["docs"] == 2

    hits = index_manager.search_index("acme", "Innenfarbe", top_k=5)
    doc = next((hit for hit in hits if hit["sku"] == "sku_dsp_10_weiss"), None)
    assert doc is not None
    assert doc["name"] == "Innenfarbe Premium Weiß 10L"


def test_update_index_removes_inactive_products(tmp_path, monkeypatch):
    db_path = tmp_path / "catalog_remove.db"
    monkeypatch.setenv("KALKULAI_DB_URL", f"sqlite:///{db_path}")
    store = importlib.reload(__import__("backend.store.catalog_store", fromlist=["dummy"]))
    store.init_db()
    store.upsert_product("acme", {"sku": "sku_dsp_10", "name": "Dispersionsfarbe Innen 10L"})
    store.upsert_product("acme", {"sku": "sku_tg_10", "name": "Tiefgrund 10 L"})

    index_manager = importlib.reload(__import__("backend.retriever.index_manager", fromlist=["dummy"]))

    class DummyEmbedder:
        def encode(self, texts):
            return [[float(len(text) or 1.0)] for text in texts]

    dummy = DummyEmbedder()
    monkeypatch.setattr(index_manager, "_get_embedder", lambda: dummy)
    index_manager._EMBEDDER = dummy
    monkeypatch.setattr(index_manager, "_DOCARRAY_AVAILABLE", False, raising=False)

    index_manager.rebuild_index("acme")
    hits_before = index_manager.search_index("acme", "Farbe", top_k=5)
    assert {hit["sku"] for hit in hits_before} == {"sku_dsp_10", "sku_tg_10"}

    store.upsert_product("acme", {"sku": "sku_tg_10", "name": "Tiefgrund 10 L", "is_active": False})

    stats = index_manager.update_index("acme", ["sku_tg_10"])
    assert stats["docs"] == 1

    hits_after = index_manager.search_index("acme", "Tiefgrund", top_k=5)
    skus_after = {hit["sku"] for hit in hits_after}
    assert "sku_dsp_10" in skus_after
    assert "sku_tg_10" not in skus_after


def test_update_index_reactivates_products(tmp_path, monkeypatch):
    db_path = tmp_path / "catalog_reactivate.db"
    monkeypatch.setenv("KALKULAI_DB_URL", f"sqlite:///{db_path}")
    store = importlib.reload(__import__("backend.store.catalog_store", fromlist=["dummy"]))
    store.init_db()
    store.upsert_product("acme", {"sku": "sku_dsp_10", "name": "Dispersionsfarbe Weiß 10L"})
    store.upsert_product("acme", {"sku": "sku_dsp_10_weiss", "name": "Innenfarbe Premium Weiß 10L"})
    store.upsert_product("acme", {"sku": "sku_tg_10", "name": "Tiefgrund Spezial 10 L"})

    index_manager = importlib.reload(__import__("backend.retriever.index_manager", fromlist=["dummy"]))

    class DummyEmbedder:
        def encode(self, texts):
            return [[float(len(text) or 1.0)] for text in texts]

    dummy = DummyEmbedder()
    monkeypatch.setattr(index_manager, "_get_embedder", lambda: dummy)
    index_manager._EMBEDDER = dummy
    monkeypatch.setattr(index_manager, "_DOCARRAY_AVAILABLE", False, raising=False)

    index_manager.rebuild_index("acme")
    initial_hits = index_manager.search_index("acme", "10 L", top_k=5)
    assert {hit["sku"] for hit in initial_hits} == {"sku_dsp_10", "sku_dsp_10_weiss", "sku_tg_10"}
    assert index_manager.index_stats("acme")["docs"] == 3

    store.upsert_product("acme", {"sku": "sku_tg_10", "name": "Tiefgrund Spezial 10 L", "is_active": False})
    stats_after_deactivate = index_manager.update_index("acme", ["sku_tg_10"])
    assert stats_after_deactivate["docs"] == 2
    hits_after_deactivate = index_manager.search_index("acme", "10 L", top_k=5)
    assert {hit["sku"] for hit in hits_after_deactivate} == {"sku_dsp_10", "sku_dsp_10_weiss"}

    store.upsert_product("acme", {"sku": "sku_tg_10", "name": "Tiefgrund Spezial 10 L", "is_active": True})
    stats_after_reactivate = index_manager.update_index("acme", ["sku_tg_10"])
    assert stats_after_reactivate["docs"] == 3
    hits_after_reactivate = index_manager.search_index("acme", "10 L", top_k=5)
    assert {hit["sku"] for hit in hits_after_reactivate} == {
        "sku_dsp_10",
        "sku_dsp_10_weiss",
        "sku_tg_10",
    }
