import csv
import importlib
import json
from pathlib import Path

import pytest

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    yaml = None


def _reload_modules(monkeypatch):
    monkeypatch.setenv("KALKULAI_DB_URL", "sqlite:///:memory:")
    store_module = importlib.import_module("backend.store.catalog_store")
    index_module = importlib.import_module("backend.retriever.index_manager")
    cli_module = importlib.import_module("backend.cli.catalog_cli")

    store = importlib.reload(store_module)
    store.init_db()
    index_manager = importlib.reload(index_module)

    class DummyEmbedder:
        def encode(self, texts):
            return [[float(len(text) or 1.0)] for text in texts]

    index_manager._EMBEDDER = DummyEmbedder()
    cli = importlib.reload(cli_module)
    cli.index_manager._EMBEDDER = DummyEmbedder()
    return store, index_manager, cli


def _write_csv(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sku", "name", "description", "unit", "volume_l", "price_eur", "active"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_import_export_products_roundtrip_csv(tmp_path, monkeypatch):
    store, index_manager, cli = _reload_modules(monkeypatch)
    csv_path = tmp_path / "acme.csv"
    _write_csv(
        csv_path,
        [
            {"sku": "SKU-1", "name": "Innenfarbe Weiß", "description": "Deckend", "unit": "l", "volume_l": "10", "price_eur": "49.0", "active": "true"},
            {"sku": "SKU-2", "name": "Putzgrund Fassade", "description": "Außen", "unit": "l", "volume_l": "5", "price_eur": "29.0", "active": "true"},
        ],
    )

    exit_code = cli.main(
        [
            "import-products",
            "--company-id",
            "acme",
            "--path",
            str(csv_path),
            "--format",
            "csv",
        ]
    )
    assert exit_code == 0
    assert len(store.get_active_products("acme")) == 2
    assert index_manager.index_stats("acme")["docs"] == 2

    json_path = tmp_path / "acme.json"
    exit_code = cli.main(
        [
            "export-products",
            "--company-id",
            "acme",
            "--path",
            str(json_path),
            "--format",
            "json",
        ]
    )
    assert exit_code == 0
    exported = json.loads(json_path.read_text())
    assert len(exported) == 2

    csv_out = tmp_path / "acme.out.csv"
    exit_code = cli.main(
        [
            "export-products",
            "--company-id",
            "acme",
            "--path",
            str(csv_out),
            "--format",
            "csv",
        ]
    )
    assert exit_code == 0
    content = csv_out.read_text().strip().splitlines()
    assert len(content) == 3  # header + 2 rows


@pytest.mark.skipif(yaml is None, reason="PyYAML is required")
def test_import_export_synonyms_yaml(tmp_path, monkeypatch):
    store, _, cli = _reload_modules(monkeypatch)
    yaml_path = tmp_path / "synonyms.yaml"
    yaml_path.write_text("tiefgrund:\n  - Grundierung Tief\n  - Haftgrundierung\n", encoding="utf-8")

    exit_code = cli.main(
        [
            "import-synonyms",
            "--company-id",
            "acme",
            "--path",
            str(yaml_path),
            "--clear-existing",
        ]
    )
    assert exit_code == 0

    mapping = store.list_synonyms("acme")
    assert "tiefgrund" in mapping
    assert sorted(mapping["tiefgrund"]) == ["grundierung tief", "haftgrundierung"]

    export_path = tmp_path / "synonyms.out.yaml"
    exit_code = cli.main(
        [
            "export-synonyms",
            "--company-id",
            "acme",
            "--path",
            str(export_path),
        ]
    )
    assert exit_code == 0
    data = yaml.safe_load(export_path.read_text(encoding="utf-8"))
    assert data == {"tiefgrund": ["grundierung tief", "haftgrundierung"]}


def test_update_index_partial(tmp_path, monkeypatch):
    store, index_manager, cli = _reload_modules(monkeypatch)
    csv_path = tmp_path / "bulk.csv"
    _write_csv(
        csv_path,
        [
            {"sku": "SKU-1", "name": "Innenfarbe", "description": "Matt", "unit": "", "volume_l": "", "price_eur": "", "active": "true"},
            {"sku": "SKU-2", "name": "Tiefgrund", "description": "Innen", "unit": "", "volume_l": "", "price_eur": "", "active": "true"},
            {"sku": "SKU-3", "name": "Putzgrund", "description": "Außen", "unit": "", "volume_l": "", "price_eur": "", "active": "true"},
        ],
    )

    assert cli.main(["import-products", "--company-id", "acme", "--path", str(csv_path), "--format", "csv"]) == 0
    assert index_manager.index_stats("acme")["docs"] == 3

    store.upsert_product("acme", {"sku": "SKU-2", "name": "Tiefgrund Neu", "description": "Updated"})

    rebuild_calls = {"count": 0}
    original_rebuild = cli.index_manager.rebuild_index

    def _tracking(company_id: str):
        rebuild_calls["count"] += 1
        return original_rebuild(company_id)

    cli.index_manager.rebuild_index = _tracking

    try:
        assert (
            cli.main(
                [
                    "update-index",
                    "--company-id",
                    "acme",
                    "--skus",
                    "SKU-2",
                ]
            )
            == 0
        )
    finally:
        cli.index_manager.rebuild_index = original_rebuild

    assert rebuild_calls["count"] == 0
    stats = index_manager.index_stats("acme")
    assert stats["docs"] == 3
