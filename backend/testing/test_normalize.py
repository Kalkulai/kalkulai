from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.shared.normalize.text import (
    apply_synonyms,
    lemmatize_decompound,
    load_synonyms,
    normalize_query,
    tokenize,
)


SYN_PATH = BACKEND_ROOT / "shared" / "normalize" / "synonyms.yaml"


def test_umlaut_and_sz_normalization() -> None:
    assert normalize_query("HÄFTGRÜND ßuper") == "haeftgruend ssuper"


def test_tokenize_with_stemming() -> None:
    tokens = tokenize("Grundierungen Haftgrundierung")
    expected = {"grundierung", "haftgrundierung", "haftgrund", "grund"}
    assert expected.issubset(tokens)


def test_decompound_simple() -> None:
    parts = lemmatize_decompound("Haftgrundierung")
    assert "haft" in parts
    assert "grundierung" in parts

    parts_tief = lemmatize_decompound("Tiefgrund")
    assert "tief" in parts_tief
    assert "grund" in parts_tief


def test_synonym_loading_and_application() -> None:
    synonyms = load_synonyms(str(SYN_PATH))
    tokens = apply_synonyms({"tiefgrund"}, synonyms)
    assert "haftgrund" in tokens


def test_token_pipeline_integration() -> None:
    synonyms = load_synonyms(str(SYN_PATH))
    tokens = tokenize("Bitte einmal Tiefgrund liefern")
    enriched = apply_synonyms(tokens, synonyms)
    assert "haftgrund" in enriched


def test_compound_with_space_maps_to_compound() -> None:
    synonyms = load_synonyms(str(SYN_PATH))
    tokens = tokenize("abdeck band")
    enriched = apply_synonyms(tokens, synonyms)
    assert "abdeckband" in enriched or "abklebeband" in enriched
