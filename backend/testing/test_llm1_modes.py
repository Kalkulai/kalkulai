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

import backend.main as main  # noqa: E402


def _sample_items():
    return [{"name": "Tiefgrund", "einheit": "L"}]


def _hit(
    score: float,
    *,
    hard_filters: bool = True,
    name: str = "Haftgrund 10 L",
    sku: str = "SKU-1",
    unit: str = "L",
):
    return {
        "sku": sku,
        "name": name,
        "unit": unit,
        "category": "primer",
        "brand": "Favorit",
        "score_final": score,
        "hard_filters_passed": hard_filters,
    }


@pytest.fixture(autouse=True)
def _enable_thin(monkeypatch):
    monkeypatch.setattr(main, "LLM1_THIN_RETRIEVAL", True)
    monkeypatch.setattr(main, "CATALOG_QUERIES_PER_TURN", 5)
    yield


def _patch_search(monkeypatch, hits):
    def _fake_search(**kwargs):  # pragma: no cover - helper shim
        return hits

    monkeypatch.setattr(main, "search_catalog_thin", _fake_search)


def test_assistive_shows_candidates_only(monkeypatch):
    _patch_search(monkeypatch, [_hit(0.9)])
    monkeypatch.setattr(main, "LLM1_MODE", "assistive")
    candidates = main._build_catalog_candidates(_sample_items())
    assert candidates
    cand = candidates[0]
    assert cand["adoptable"] is False
    assert cand["selected_catalog_item_id"] is None


def test_strict_marks_adoptable_when_title_contains_canonical(monkeypatch):
    _patch_search(monkeypatch, [_hit(0.9)])
    monkeypatch.setattr(main, "LLM1_MODE", "strict")
    candidates = main._build_catalog_candidates(_sample_items())
    cand = candidates[0]
    assert cand["adoptable"] is True
    assert cand["selected_catalog_item_id"] is None


def test_merge_autoselects_when_above_threshold(monkeypatch):
    _patch_search(monkeypatch, [_hit(0.93)])
    monkeypatch.setattr(main, "LLM1_MODE", "merge")
    monkeypatch.setattr(main, "ADOPT_THRESHOLD", 0.82)
    candidates = main._build_catalog_candidates(_sample_items())
    cand = candidates[0]
    assert cand["selected_catalog_item_id"] == "SKU-1"
    assert cand["selection_reason"] == "rule"
    assert cand["adoptable"] is True
    assert cand["unit"] == "L"


def test_merge_does_not_autoselect_below_threshold(monkeypatch):
    _patch_search(monkeypatch, [_hit(0.8)])
    monkeypatch.setattr(main, "LLM1_MODE", "merge")
    monkeypatch.setattr(main, "ADOPT_THRESHOLD", 0.82)
    candidates = main._build_catalog_candidates(_sample_items())
    cand = candidates[0]
    assert cand["selected_catalog_item_id"] is None
    assert cand["adoptable"] is False


def test_strict_requires_hard_filters_passed(monkeypatch):
    _patch_search(monkeypatch, [_hit(0.95, hard_filters=False)])
    monkeypatch.setattr(main, "LLM1_MODE", "strict")
    candidates = main._build_catalog_candidates(_sample_items())
    cand = candidates[0]
    assert cand["adoptable"] is False
