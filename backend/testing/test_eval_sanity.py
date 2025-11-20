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

import backend.eval.eval_thin as eval_thin  # noqa: E402
import backend.eval.eval_main as eval_main  # noqa: E402


@pytest.fixture()
def gold_data():
    sample_path = Path(__file__).resolve().parents[1] / "eval" / "goldset.sample.yaml"
    return eval_thin.load_goldset(sample_path)


def test_eval_thin_run(monkeypatch, gold_data):
    dummy_hits = [
        {"name": "Haftgrund Innen 10 L"},
        {"name": "Abklebeband Premium"},
    ]

    def _fake_search(query, top_k, catalog_items, synonyms_path=None):
        return dummy_hits

    monkeypatch.setattr(eval_thin, "search_catalog_thin", _fake_search)
    monkeypatch.setattr(eval_thin.backend_main, "CATALOG_ITEMS", [])

    result = eval_thin.evaluate_thin(gold_data["thin"], top_k=2)
    assert result.recall_at_k == pytest.approx(1.0)
    assert result.latencies_ms


def _build_query2sku(gold_main):
    return {case["query"]: case["ideal_sku"] for case in gold_main if case.get("query") and case.get("ideal_sku")}


def _fake_rank_factory(gold_main):
    q2sku = _build_query2sku(gold_main)

    def _fake_rank(query, retriever, top_k=5, business_cfg=None):
        sku = q2sku.get(query)
        if not sku:
            sku = next(iter(q2sku.values()))
        return [{"sku": sku, "name": f"{query} Premium"}]

    return _fake_rank


def test_eval_main_run(monkeypatch, gold_data):
    class _DummyRetriever:
        pass

    monkeypatch.setattr(eval_main.backend_main, "RETRIEVER", _DummyRetriever())
    monkeypatch.setattr(eval_main, "rank_main", _fake_rank_factory(gold_data["main"]))

    result = eval_main.evaluate_main(gold_data["main"], top_k=1)
    assert result.precision_at_1 == pytest.approx(1.0)
    assert result.latencies_ms
