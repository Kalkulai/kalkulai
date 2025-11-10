import importlib
import os
from pathlib import Path

import pytest

import backend.store.catalog_store as catalog_store


def _reload_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DB_URL", f"sqlite:///{db_path}")
    return importlib.reload(catalog_store)


def test_product_crud(tmp_path, monkeypatch):
    store = _reload_store(tmp_path, monkeypatch)
    store.init_db()

    result = store.upsert_product(
        "demo",
        {"sku": "SKU-1", "name": "Innenfarbe Weiß", "description": "Deckend"},
    )
    assert result["sku"] == "SKU-1"
    assert result["name"] == "Innenfarbe Weiß"
    assert result["is_active"] is True

    products = store.list_products("demo", include_deleted=True)
    assert len(products) == 1
    assert products[0]["description"] == "Deckend"

    deleted = store.delete_product("demo", "SKU-1")
    assert deleted is True
    products_after = store.list_products("demo", include_deleted=True)
    assert products_after[0]["is_active"] is False


def test_synonym_flow(tmp_path, monkeypatch):
    store = _reload_store(tmp_path, monkeypatch)
    store.init_db()

    store.add_synonym("demo", "tiefgrund", "tief grund")
    store.add_synonym("demo", "tiefgrund", "tief-grund", confidence=0.8)
    store.add_synonym("demo", "putzgrund", "putz-grund")

    mapping = store.list_synonyms("demo")
    assert "tiefgrund" in mapping
    assert set(mapping["tiefgrund"]) == {"tief grund", "tief-grund"}
    assert mapping["putzgrund"] == ["putz-grund"]
