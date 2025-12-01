from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from jinja2 import Environment

import backend.app.services.quote_service as qs
import backend.app.services.quote_service as qs
from backend.app.services.quote_service import (
    QuoteServiceContext,
    ServiceError,
    chat_turn,
    generate_offer_positions,
    render_offer_or_invoice_pdf,
    run_revenue_guard,
    search_catalog,
    wizard_finalize,
    wizard_next_step,
)


class FakeChain:
    def __init__(self, reply: str):
        self.reply = reply
        self.run_calls: list[str] = []

    def run(self, human_input: str) -> str:
        self.run_calls.append(human_input)
        return self.reply


class FakeChatMemory:
    def __init__(self, owner: "FakeMemory"):
        self.messages: list[str] = []
        self._owner = owner

    def add_ai_message(self, content: str) -> None:
        self.messages.append(content)
        prefix = "\n" if self._owner._history else ""
        self._owner._history += f"{prefix}Assistent:\n{content}"


class FakeMemory:
    def __init__(self, history: str = ""):
        self._history = history
        self.chat_memory = FakeChatMemory(self)

    def load_memory_variables(self, _: Dict[str, Any]) -> Dict[str, str]:
        return {"chat_history": self._history}


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.invocations: list[str] = []

    def invoke(self, prompt: str):
        self.invocations.append(prompt)
        return SimpleNamespace(content=self.response)


class EmptyRetriever:
    def get_relevant_documents(self, query: str):  # pragma: no cover - interface stub
        return []


def _default_catalog_entry() -> Dict[str, Any]:
    return {
        "sku": "sku-001",
        "name": "Premiumfarbe weiß 10L",
        "unit": "L",
        "pack_sizes": ["10L"],
        "synonyms": ["Innenfarbe"],
        "category": "Farbe",
        "brand": "Kalkulai",
        "description": "Hochwertige Dispersionsfarbe",
        "raw": "Produkt: Premiumfarbe weiß 10L",
    }


def _override_catalog_entries() -> List[Dict[str, Any]]:
    return [
        {
            "sku": "sku-farbe",
            "name": "Innenfarbe weiß",
            "unit": "L",
            "pack_sizes": ["10 L"],
            "synonyms": ["Wandfarbe"],
            "category": "Farbe",
            "brand": "Test",
            "description": "Innenanstrich",
            "raw": "Produkt: Innenfarbe weiß",
        },
        {
            "sku": "sku-folie",
            "name": "Abdeckfolie 20 m²",
            "unit": "m²",
            "pack_sizes": ["20 m²"],
            "synonyms": [],
            "category": "Zubehör",
            "brand": "Test",
            "description": "Folie",
            "raw": "Produkt: Abdeckfolie 20 m²",
        },
        {
            "sku": "sku-band",
            "name": "Abklebeband 19 mm 25 m",
            "unit": "m",
            "pack_sizes": ["25 m"],
            "synonyms": ["Kreppband"],
            "category": "Zubehör",
            "brand": "Test",
            "description": "Band",
            "raw": "Produkt: Abklebeband 19 mm 25 m",
        },
        {
            "sku": "sku-holz",
            "name": "Holzschutzgrund honigfarben 5 L",
            "unit": "L",
            "pack_sizes": ["5 L"],
            "synonyms": ["Holzschutz"],
            "category": "Holzschutz",
            "brand": "Test",
            "description": "Holzschutzgrund für Außen",
            "raw": "Produkt: Holzschutzgrund honigfarben 5 L",
        },
        {
            "sku": "sku-roller",
            "name": "Farbroller 25 cm",
            "unit": "Stück",
            "pack_sizes": ["1 Stück"],
            "synonyms": ["Rolle"],
            "category": "Werkzeug",
            "brand": "Test",
            "description": "Werkzeug",
            "raw": "Produkt: Farbroller 25 cm",
        },
    ]


def make_context(tmp_path, **overrides) -> QuoteServiceContext:
    entry = overrides.pop("catalog_entry", _default_catalog_entry())
    catalog_items = overrides.pop("catalog_items", [entry])
    catalog_by_name = overrides.pop(
        "catalog_by_name",
        {(entry["name"] or "").lower(): entry},
    )
    catalog_by_sku = overrides.pop(
        "catalog_by_sku",
        {entry["sku"]: entry},
    )
    catalog_text_by_name = overrides.pop(
        "catalog_text_by_name",
        {(entry["name"] or "").lower(): entry.get("raw", "")},
    )
    catalog_text_by_sku = overrides.pop(
        "catalog_text_by_sku",
        {entry["sku"]: entry.get("raw", "")},
    )
    ctx = QuoteServiceContext(
        chain1=overrides.pop("chain1", None),
        chain2=overrides.pop("chain2", None),
        llm1=overrides.pop("llm1", None),
        llm2=overrides.pop("llm2", None),
        prompt2=overrides.pop("prompt2", "{context}\n{question}"),
        memory1=overrides.pop("memory1", FakeMemory()),
        retriever=overrides.pop("retriever", EmptyRetriever()),
        reset_callback=overrides.pop("reset_callback", None),
        documents=overrides.pop("documents", [object()]),
        catalog_items=catalog_items,
        catalog_by_name=catalog_by_name,
        catalog_by_sku=catalog_by_sku,
        catalog_text_by_name=catalog_text_by_name,
        catalog_text_by_sku=catalog_text_by_sku,
        catalog_search_cache=overrides.pop("catalog_search_cache", {}),
        wizard_sessions=overrides.pop("wizard_sessions", {}),
        env=overrides.pop("env", Environment()),
        output_dir=overrides.pop("output_dir", tmp_path),
        vat_rate=overrides.pop("vat_rate", 0.19),
        synonyms_path=overrides.pop(
            "synonyms_path",
            Path(__file__).resolve().parents[1] / "shared" / "normalize" / "synonyms.yaml",
        ),
        logger=overrides.pop("logger", logging.getLogger("test-quote-service")),
        llm1_mode=overrides.pop("llm1_mode", "merge"),
        adopt_threshold=overrides.pop("adopt_threshold", 0.8),
        business_scoring=overrides.pop("business_scoring", []),
        llm1_thin_retrieval=overrides.pop("llm1_thin_retrieval", False),
        catalog_top_k=overrides.pop("catalog_top_k", 5),
        catalog_cache_ttl=overrides.pop("catalog_cache_ttl", 60),
        catalog_queries_per_turn=overrides.pop("catalog_queries_per_turn", 2),
        skip_llm_setup=overrides.pop("skip_llm_setup", False),
        default_company_id=overrides.pop("default_company_id", "default"),
        debug=overrides.pop("debug", True),
    )
    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


def test_chat_turn_sets_ready_flag(tmp_path):
    reply = (
        "Gerne!\n---\nstatus: bestätigt\nmaterialien:\n"
        "- name=Dispersionsfarbe, menge=10, einheit=L\n---"
    )
    entry = {
        "sku": "sku-xyz",
        "name": "Dispersionsfarbe",
        "unit": "L",
        "pack_sizes": ["10L"],
        "synonyms": ["Innenfarbe"],
        "category": "Farbe",
        "brand": "Test",
        "description": "Farbton",
        "raw": "Produkt: Dispersionsfarbe 10L",
    }
    ctx = make_context(
        tmp_path,
        chain1=FakeChain(reply),
        memory1=FakeMemory(),
        llm1_thin_retrieval=False,
        catalog_entry=entry,
        catalog_items=[entry],
        catalog_by_name={entry["name"].lower(): entry},
        catalog_by_sku={entry["sku"]: entry},
    )
    result = chat_turn(message="Bitte Angebot", ctx=ctx)

    assert result["ready_for_offer"] is True
    assert "**Zusammenfassung**" in result["reply"]
    assert ctx.memory1.chat_memory.messages  # type: ignore[union-attr]


def test_chat_turn_requests_details_when_no_data(tmp_path):
    ctx = make_context(
        tmp_path,
        chain1=FakeChain("Gerne, ich helfe Ihnen weiter."),
        memory1=FakeMemory(),
    )
    result = chat_turn(message="Ich brauche ein Angebot.", ctx=ctx)

    assert result["ready_for_offer"] is False
    assert "Es liegen noch keine Angebotsdaten vor." in result["reply"]
    assert "Passen die Mengen" not in result["reply"]


def test_generate_offer_positions_uses_llm2_and_catalog(tmp_path):
    llm_response = '[{"nr": 1, "name": "Premiumfarbe weiß 10L", "menge": 10, "einheit": "L", "epreis": 5, "gesamtpreis": 50}]'
    memory = FakeMemory("Assistent:\n---\nstatus: bestätigt\nmaterialien:\n- name=Premiumfarbe weiß 10L, menge=10, einheit=L\n---")
    ctx = make_context(
        tmp_path,
        llm2=FakeLLM(llm_response),
        prompt2="CTX:{context}\nQ:{question}",
        memory1=memory,
        retriever=None,
    )
    payload = {"products": ["Premiumfarbe weiß 10L"]}

    result = generate_offer_positions(payload=payload, ctx=ctx, company_id=None)

    assert result["positions"][0]["name"] == "Premiumfarbe weiß 10L"
    assert result["positions"][0]["gesamtpreis"] == 50
    assert json.loads(result["raw"]) == result["positions"]


def test_generate_offer_positions_adjusts_price_for_pack_conversion(tmp_path):
    llm_response = (
        '[{"nr": 1, "name": "Premiumfarbe weiß 10L", "menge": 1, '
        '"einheit": "Eimer", "epreis": 29.9, "gesamtpreis": 29.9}]'
    )
    memory = FakeMemory("Assistent:\n---\nstatus: bestätigt\nmaterialien:\n- name=Premiumfarbe weiß 10L, menge=1, einheit=Eimer\n---")
    ctx = make_context(
        tmp_path,
        llm2=FakeLLM(llm_response),
        prompt2="CTX:{context}\nQ:{question}",
        memory1=memory,
        retriever=None,
    )
    payload = {"products": ["Premiumfarbe weiß 10L"]}

    result = generate_offer_positions(payload=payload, ctx=ctx, company_id=None)

    pos = result["positions"][0]
    assert pos["einheit"] == "L"
    assert pos["menge"] == 10
    assert pytest.approx(pos["epreis"], rel=1e-6) == 2.99
    assert pytest.approx(pos["gesamtpreis"], rel=1e-6) == 29.9
    assert json.loads(result["raw"]) == result["positions"]


def test_generate_offer_positions_adjusts_price_for_roll_conversion(tmp_path):
    llm_response = (
        '[{"nr": 1, "name": "Kreppband 50 m", "menge": 1, '
        '"einheit": "Rolle", "epreis": 2.9, "gesamtpreis": 2.9}]'
    )
    tape_entry = {
        "sku": "sku-band-50",
        "name": "Kreppband 50 m",
        "unit": "m",
        "pack_sizes": ["50 m"],
        "synonyms": ["Abklebeband"],
        "category": "Zubehör",
        "brand": "Test",
        "description": "Klebeband",
        "raw": "Produkt: Kreppband 50 m",
    }
    ctx = make_context(
        tmp_path,
        llm2=FakeLLM(llm_response),
        prompt2="CTX:{context}\nQ:{question}",
        memory1=FakeMemory(),
        retriever=None,
        catalog_entry=tape_entry,
        catalog_items=[tape_entry],
        catalog_by_name={tape_entry["name"].lower(): tape_entry},
        catalog_by_sku={tape_entry["sku"]: tape_entry},
        catalog_text_by_name={tape_entry["name"].lower(): tape_entry["raw"]},
        catalog_text_by_sku={tape_entry["sku"]: tape_entry["raw"]},
    )
    payload = {"products": ["Kreppband 50 m"]}

    result = generate_offer_positions(payload=payload, ctx=ctx, company_id=None)

    pos = result["positions"][0]
    assert pos["einheit"] == "m"
    assert pos["menge"] == 50
    assert pytest.approx(pos["epreis"], rel=1e-6) == 2.9 / 50
    assert pytest.approx(pos["gesamtpreis"], rel=1e-6) == 2.9
    assert json.loads(result["raw"]) == result["positions"]


def test_generate_offer_positions_without_context_raises(tmp_path):
    ctx = make_context(tmp_path, memory1=None, llm2=FakeLLM("[]"))
    with pytest.raises(ServiceError) as exc:
        generate_offer_positions(payload={}, ctx=ctx)
    assert exc.value.status_code == 400


def test_generate_offer_positions_accepts_annotated_products(tmp_path):
    llm_response = '[{"nr": 1, "name": "Premiumfarbe weiß 10L", "menge": 10, "einheit": "L", "epreis": 5, "gesamtpreis": 50}]'
    memory = FakeMemory("Assistent:\n---\nstatus: bestätigt\nmaterialien:\n- name=Premiumfarbe weiß 10L, menge=10, einheit=L\n---")
    ctx = make_context(
        tmp_path,
        llm2=FakeLLM(llm_response),
        prompt2="CTX:{context}\nQ:{question}",
        memory1=memory,
        retriever=None,
    )
    payload = {"products": ["Premiumfarbe weiß 10L: 15 L (Reserve 5 L)"]}

    result = generate_offer_positions(payload=payload, ctx=ctx, company_id=None)

    assert result["positions"][0]["name"] == "Premiumfarbe weiß 10L"


def test_generate_offer_positions_prefers_machine_block(tmp_path):
    llm_response = (
        '[{"nr": 1, "name": "Premiumfarbe weiß 10L", "menge": 12, "einheit": "L", "epreis": 5, "gesamtpreis": 60}]'
    )
    history = (
        "Assistent:\n- Innenanstrich einer Wandfläche von 20 m².\n"
        "- Der Tiefengrund wird mit einem Verbrauch von ca. 75 ml/m² kalkuliert.\n"
        "---\nstatus: schätzung\nmaterialien:\n"
        "- name=Premiumfarbe weiß 10L, menge=12, einheit=L\n"
        "- name=Tiefgrund 10 L, menge=2, einheit=L\n---"
    )
    entry = {
        "sku": "sku-123",
        "name": "Dispersionsfarbe weiß, matt, 10 L",
        "unit": "L",
        "pack_sizes": ["10L"],
        "synonyms": ["Innenfarbe"],
        "category": "Farbe",
        "brand": "Kalkulai",
        "description": "Dispersionsfarbe",
        "raw": "Produkt: Dispersionsfarbe weiß, matt, 10 L",
    }
    entry2 = dict(entry)
    entry2["sku"] = "sku-002"
    entry2["name"] = "Tiefgrund 10 L"
    entry2["raw"] = "Produkt: Tiefgrund 10 L"
    ctx = make_context(
        tmp_path,
        llm2=FakeLLM(llm_response),
        prompt2="CTX:{context}\nQ:{question}",
        memory1=FakeMemory(history),
        retriever=None,
        catalog_items=[entry, entry2],
        catalog_by_name={
            entry["name"].lower(): entry,
            entry2["name"].lower(): entry2,
        },
        catalog_by_sku={
            entry["sku"]: entry,
            entry2["sku"]: entry2,
        },
        catalog_text_by_name={
            entry["name"].lower(): entry.get("raw", ""),
            entry2["name"].lower(): entry2.get("raw", ""),
        },
        catalog_text_by_sku={
            entry["sku"]: entry.get("raw", ""),
            entry2["sku"]: entry2.get("raw", ""),
        },
    )
    payload = {
        "message": "Innenanstrich einer Wandfläche von 20 m²: Der Tiefengrund wird mit 75 ml/m² kalkuliert.",
    }

    result = generate_offer_positions(payload=payload, ctx=ctx, company_id=None)

    assert result["positions"][0]["name"] == "Premiumfarbe weiß 10L"


def test_generate_offer_positions_deduplicates_machine_items(tmp_path):
    llm_response = (
        '[{"nr": 1, "name": "Dispersionsfarbe weiß, matt, 10 L", "menge": 12, '
        '"einheit": "L", "epreis": 5, "gesamtpreis": 60}]'
    )
    history = (
        "Assistent:\n---\nstatus: schätzung\nmaterialien:\n"
        "- name=Dispersionsfarbe weiß (für die ganze Fläche), menge=12, einheit=L\n---"
    )
    entry = {
        "sku": "sku-123",
        "name": "Dispersionsfarbe weiß, matt, 10 L",
        "unit": "L",
        "pack_sizes": ["10L"],
        "synonyms": ["Innenfarbe"],
        "category": "Farbe",
        "brand": "Test",
        "description": "Farbton",
        "raw": "Produkt: Dispersionsfarbe weiß, matt, 10 L",
    }
    ctx = make_context(
        tmp_path,
        llm2=FakeLLM(llm_response),
        prompt2="CTX:{context}\nQ:{question}",
        memory1=FakeMemory(history),
        retriever=None,
        catalog_items=[entry],
        catalog_by_name={entry["name"].lower(): entry},
        catalog_by_sku={entry["sku"]: entry},
        catalog_text_by_name={entry["name"].lower(): entry.get("raw", "")},
        catalog_text_by_sku={entry["sku"]: entry.get("raw", "")},
    )

    result = generate_offer_positions(payload={"products": ["Dispersionsfarbe weiß, matt, 10 L"]}, ctx=ctx, company_id=None)

    assert len(result["positions"]) == 1
    assert result["positions"][0]["menge"] == 12


def test_render_offer_or_invoice_pdf(monkeypatch, tmp_path):
    saved_path = tmp_path / "outputs" / "angebot.pdf"
    saved_path.parent.mkdir(parents=True, exist_ok=True)

    def fake_render(env, template_file, context, output_dir):  # pragma: no cover - patched
        assert template_file.endswith(".html")
        saved_path.write_text("pdf")
        return saved_path

    fake_module = SimpleNamespace(
        render_pdf_from_template=fake_render,
        DEFAULT_OFFER_TEMPLATE_ID="classic",
        resolve_offer_template=lambda tpl_id: {"id": "classic", "file": "offer.html"},
    )
    monkeypatch.setitem(sys.modules, "backend.app.pdf", fake_module)
    ctx = make_context(tmp_path)
    payload = {
        "positions": [{"menge": 2, "einheit": "L", "epreis": 5.0, "gesamtpreis": 0.0}],
        "kunde": "Test GmbH",
    }

    result = render_offer_or_invoice_pdf(payload=payload, ctx=ctx)

    assert result["pdf_url"].endswith("angebot.pdf")
    assert result["context"]["brutto_summe"] == 11.9  # 19 % VAT
    assert result["template_id"] == "classic"


def test_wizard_flow_produces_suggestions(tmp_path):
    wizard_sessions: dict[str, dict] = {}
    llm1 = FakeLLM(
        "---\nstatus: schätzung\nmaterialien:\n- name=Dispersionsfarbe, menge=7, einheit=L\n---"
    )
    ctx = make_context(
        tmp_path,
        llm1=llm1,
        wizard_sessions=wizard_sessions,
        skip_llm_setup=False,
    )

    first = wizard_next_step(payload={}, ctx=ctx)
    assert first["done"] is False

    second = wizard_next_step(
        payload={
            "session_id": first["session_id"],
            "answers": {"flaeche_m2": 80, "anzahl_schichten": 2},
        },
        ctx=ctx,
    )
    assert second["suggestions"], "expected suggestions once enough context is present"

    final = wizard_finalize(payload={"session_id": first["session_id"]}, ctx=ctx)
    assert final["positions"]
    assert final["done"] is True


def test_wizard_finalize_missing_session(tmp_path):
    ctx = make_context(tmp_path, wizard_sessions={})
    with pytest.raises(ServiceError):
        wizard_finalize(payload={"session_id": "missing"}, ctx=ctx)


def test_revenue_guard_detects_missing_primer(tmp_path):
    result = run_revenue_guard(
        payload={"positions": [{"name": "Abdeckfolie", "menge": 1, "einheit": "Rolle"}], "context": {"untergrund": "Putz"}},
        debug=True,
    )
    assert result["passed"] is False
    assert any(sug["name"].startswith("Tiefgrund") for sug in result["missing"])


def test_search_catalog_returns_match(tmp_path):
    entry = _default_catalog_entry()
    entry["raw"] = "Produkt: Premiumfarbe weiß 10L"
    ctx = make_context(
        tmp_path,
        catalog_entry=entry,
        retriever=EmptyRetriever(),
    )
    result = search_catalog(query="Premiumfarbe", limit=3, company_id=None, ctx=ctx)

    assert result["count"] == 1
    assert result["results"][0]["sku"] == "sku-001"


def test_custom_guard_materials_roundtrip(tmp_path, monkeypatch):
    # Ensure a clean config path per test
    from backend.app.services import quote_service as qs

    config_path = tmp_path / "guard.json"
    monkeypatch.setattr(qs, "REVENUE_GUARD_CONFIG_PATH", config_path)
    qs.GUARD_CONFIG_CACHE = None

    payload = {
        "items": [
            {
                "id": "brandschutz",
                "name": "Brandschutzfarbe",
                "keywords": ["brandschutz", "f90"],
                "reason": "Brandschutzklasse laut Kundenvorgabe.",
                "default_menge": 5,
                "einheit": "Eimer",
                "severity": "high",
                "category": "Brandschutz",
                "origin": "custom",
            },
            {
                "id": "primer_tiefgrund",
                "name": "Spezialgrundierung",
                "keywords": [],
                "reason": "Eigene Beschreibung",
                "default_menge": 3,
                "einheit": "L",
                "severity": "low",
                "category": "Vorarbeiten",
                "origin": "builtin",
                "enabled": False,
            }
        ],
    }

    saved = qs.save_revenue_guard_materials(payload=payload)
    assert any(item["id"] == "brandschutz" for item in saved["items"])
    assert config_path.exists()

    result = qs.run_revenue_guard(
        payload={"positions": [{"name": "Innenanstrich Standard", "menge": 10}], "context": {}},
        debug=False,
    )
    assert any(s["id"] == "brandschutz" for s in result["missing"])
    # Override disabled builtin should suppress the default suggestion
    assert not any(s["id"] == "primer_tiefgrund" for s in result["missing"])

    loaded = qs.get_revenue_guard_materials()
    brandschutz = next(item for item in loaded["items"] if item["id"] == "brandschutz")
    assert brandschutz["keywords"] == ["brandschutz", "f90"]
    primer = next(item for item in loaded["items"] if item["id"] == "primer_tiefgrund")
    assert primer["name"] == "Spezialgrundierung"


def test_chat_turn_blocks_unknown_materials(tmp_path):
    reply = (
        "Alles klar.\n---\nstatus: schätzung\nmaterialien:\n"
        "- name=Fantasieprodukt, menge=5, einheit=Stück\n---"
    )
    ctx = make_context(
        tmp_path,
        chain1=FakeChain(reply),
        memory1=FakeMemory(),
        catalog_items=[],
        catalog_by_name={},
        catalog_by_sku={},
        catalog_text_by_name={},
        catalog_text_by_sku={},
    )
    result = chat_turn(message="Bitte Angebot", ctx=ctx)

    assert result["ready_for_offer"] is False
    assert "Hinweis zur Produktprüfung" in result["reply"]
    assert "- Fantasieprodukt" in result["reply"]


def test_missing_catalog_handles_colon_annotations(tmp_path):
    ctx = make_context(tmp_path)
    materials = [{"name": "Premiumfarbe weiß 10L: 15 L (Reserve)", "menge": 15, "einheit": "L"}]

    matches, unknown = qs._validate_materials(materials, ctx, company_id=None)

    assert matches and not unknown


def test_validate_materials_accepts_generic_kreppband(tmp_path):
    entries = [
        {
            "sku": "sku_kb25",
            "name": "Kreppband 25 m",
            "unit": "m",
            "pack_sizes": ["25"],
            "synonyms": [],
            "category": "Zubehör",
            "brand": "Test",
            "description": "Abdeckband schmal",
            "raw": "Produkt: Kreppband 25 m",
        },
        {
            "sku": "sku_kb50",
            "name": "Kreppband 50 m",
            "unit": "m",
            "pack_sizes": ["50"],
            "synonyms": [],
            "category": "Zubehör",
            "brand": "Test",
            "description": "Abdeckband breit",
            "raw": "Produkt: Kreppband 50 m",
        },
    ]
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    matches, unknown = qs._validate_materials(
        [{"name": "Kreppband", "menge": 1, "einheit": "Rolle"}],
        ctx,
        company_id=None,
    )

    assert matches and not unknown
    assert matches[0]["matched"] is True
    assert matches[0]["canonical_name"].startswith("Kreppband")


def test_validate_materials_accepts_generic_abdeckfolie(tmp_path):
    entries = [
        {
            "sku": "sku_folie20",
            "name": "Abdeckfolie 20 m²",
            "unit": "m²",
            "pack_sizes": ["20"],
            "synonyms": [],
            "category": "Zubehör",
            "brand": "Test",
            "description": "Folie klein",
            "raw": "Produkt: Abdeckfolie 20 m²",
        },
        {
            "sku": "sku_folie50",
            "name": "Abdeckfolie 50 m²",
            "unit": "m²",
            "pack_sizes": ["50"],
            "synonyms": [],
            "category": "Zubehör",
            "brand": "Test",
            "description": "Folie groß",
            "raw": "Produkt: Abdeckfolie 50 m²",
        },
    ]
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    matches, unknown = qs._validate_materials(
        [{"name": "Abdeckfolie", "menge": 1, "einheit": "Rolle"}],
        ctx,
        company_id=None,
    )

    assert matches and not unknown
    assert matches[0]["matched"] is True
    assert matches[0]["canonical_name"].startswith("Abdeckfolie")


def test_validate_materials_still_flags_unknown_products(tmp_path):
    entries = [
        {
            "sku": "sku_kb25",
            "name": "Kreppband 25 m",
            "unit": "m",
            "pack_sizes": ["25"],
            "synonyms": [],
            "category": "Zubehör",
            "brand": "Test",
            "description": "Abdeckband schmal",
            "raw": "Produkt: Kreppband 25 m",
        }
    ]
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    matches, unknown = qs._validate_materials(
        [{"name": "SuperDeko Farbe 3000", "menge": 1, "einheit": "L"}],
        ctx,
        company_id=None,
    )

    assert matches and unknown
    assert unknown[0]["query"] == "SuperDeko Farbe 3000"


def test_validate_materials_accepts_kreppband_via_thin_candidates(tmp_path, monkeypatch):
    entry = {
        "sku": "sku_abkl_standard",
        "name": "Abklebeband 19 mm, Standard",
        "unit": "m",
        "pack_sizes": ["19"],
        "synonyms": [],
        "category": "Zubehör",
        "brand": "Test",
        "description": "Standard Abklebeband",
        "raw": "Produkt: Abklebeband 19 mm, Standard",
    }
    ctx = make_context(
        tmp_path,
        catalog_entry=entry,
        catalog_items=[entry],
        catalog_by_name={entry["name"].lower(): entry},
        catalog_by_sku={entry["sku"]: entry},
        catalog_text_by_name={entry["name"].lower(): entry["raw"]},
        catalog_text_by_sku={entry["sku"]: entry["raw"]},
    )
    monkeypatch.setattr(
        qs,
        "_run_thin_catalog_search",
        lambda **kwargs: [{"name": entry["name"], "sku": entry["sku"], "confidence": 0.32}],
    )

    matches, unknown = qs._validate_materials(
        [{"name": "Kreppband", "menge": 1, "einheit": "Rolle"}],
        ctx,
        company_id=None,
    )

    assert matches and not unknown
    assert matches[0]["match_type"] in {"vector", "type_generic"}
    assert matches[0]["canonical_name"].startswith("Abklebeband")


def test_generate_offer_positions_requires_known_products(tmp_path):
    llm_response = '[{"nr": 1, "name": "Fantasieprodukt", "menge": 5, "einheit": "Stück", "epreis": 10, "gesamtpreis": 50}]'
    ctx = make_context(
        tmp_path,
        llm2=FakeLLM(llm_response),
        prompt2="{context}\n{question}",
        retriever=EmptyRetriever(),
        catalog_items=[],
        catalog_by_name={},
        catalog_by_sku={},
        catalog_text_by_name={},
        catalog_text_by_sku={},
    )
    with pytest.raises(ServiceError) as exc:
        generate_offer_positions(payload={"products": ["Fantasieprodukt"]}, ctx=ctx)
    detail = exc.value.message
    assert isinstance(detail, dict)
    assert detail["unknown_products"] == ["Fantasieprodukt"]
    assert detail["message"].startswith("Angebot kann noch nicht erstellt werden")


def test_generate_offer_positions_accepts_synonym(tmp_path, monkeypatch):
    entry = _default_catalog_entry()
    ctx = make_context(
        tmp_path,
        llm2=FakeLLM(
            '[{"nr":1,"name":"Premiumfarbe weiß 10L","menge":5,"einheit":"L","epreis":5,"gesamtpreis":25}]'
        ),
        prompt2="{context}\n{question}",
        catalog_entry=entry,
    )

    from backend.store import catalog_store

    monkeypatch.setattr(catalog_store, "get_active_products", lambda company_id: [])
    monkeypatch.setattr(
        catalog_store,
        "list_synonyms",
        lambda company_id: {"premiumfarbe weiß 10l": ["premium tone 10l"]},
    )

    result = generate_offer_positions(
        payload={"products": ["Premium Tone 10L"]},
        ctx=ctx,
        company_id="demo",
    )
    assert result["positions"]


def test_generate_offer_positions_accepts_vector_match(tmp_path, monkeypatch):
    entry = _default_catalog_entry()
    ctx = make_context(
        tmp_path,
        llm2=FakeLLM(
            '[{"nr":1,"name":"Premiumfarbe weiss matt","menge":5,"einheit":"L","epreis":5,"gesamtpreis":25}]'
        ),
        prompt2="{context}\n{question}",
        catalog_entry=entry,
    )

    monkeypatch.setattr(
        qs,
        "_run_thin_catalog_search",
        lambda **kwargs: [{"name": entry["name"], "sku": entry["sku"], "confidence": 0.9}],
    )
    from backend.store import catalog_store

    monkeypatch.setattr(catalog_store, "get_active_products", lambda company_id: [])
    monkeypatch.setattr(catalog_store, "list_synonyms", lambda company_id: {})

    payload = {"products": ["Premiumfarbe matt extra"]}
    result = generate_offer_positions(payload=payload, ctx=ctx, company_id="demo")
    assert result["positions"]


def test_offer_positions_use_quantity_override(tmp_path):
    entries = _override_catalog_entries()
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    initial_reply = (
        "Start.\n---\nstatus: schätzung\nmaterialien:\n"
        "- name=Innenfarbe weiß, menge=4, einheit=L\n"
        "- name=Abdeckfolie 20 m², menge=18, einheit=m²\n"
        "- name=Abklebeband 19 mm, menge=25, einheit=m\n---"
    )
    override_reply = (
        "Mehr Band.\n---\nstatus: update\nmaterialien:\n"
        "- name=Kreppband, menge=40, einheit=m\n---"
    )
    ctx.chain1 = FakeChain(initial_reply)
    chat_turn(message="Schlafzimmer", ctx=ctx)
    ctx.chain1 = FakeChain(override_reply)
    chat_turn(message="Bitte mehr Band", ctx=ctx)
    llm_response = json.dumps(
        [
            {"nr": 1, "name": "Innenfarbe weiß", "menge": 4, "einheit": "L", "epreis": 10, "gesamtpreis": 40},
            {
                "nr": 2,
                "name": "Abklebeband 19 mm 25 m Rolle",
                "menge": 1,
                "einheit": "Rolle",
                "epreis": 30,
                "gesamtpreis": 30,
            },
        ]
    )
    ctx.llm2 = FakeLLM(llm_response)
    result = generate_offer_positions(payload={}, ctx=ctx)
    tape = next(pos for pos in result["positions"] if "Abklebeband" in pos["name"])
    assert tape["menge"] == 50


def test_latest_override_wins(tmp_path):
    entries = _override_catalog_entries()
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    initial_reply = (
        "Start.\n---\nstatus: schätzung\nmaterialien:\n"
        "- name=Innenfarbe weiß, menge=4, einheit=L\n"
        "- name=Abdeckfolie 20 m², menge=18, einheit=m²\n"
        "- name=Abklebeband 19 mm, menge=25, einheit=m\n---"
    )
    override_reply_40 = (
        "Mehr Band.\n---\nstatus: update\nmaterialien:\n"
        "- name=Kreppband, menge=40, einheit=m\n---"
    )
    override_reply_35 = (
        "Doch etwas weniger.\n---\nstatus: update\nmaterialien:\n"
        "- name=Abklebeband 19 mm, menge=35, einheit=m\n---"
    )
    ctx.chain1 = FakeChain(initial_reply)
    chat_turn(message="Projektstart", ctx=ctx)
    ctx.chain1 = FakeChain(override_reply_40)
    chat_turn(message="Mehr Band", ctx=ctx)
    ctx.chain1 = FakeChain(override_reply_35)
    chat_turn(message="Doch weniger", ctx=ctx)
    llm_response = json.dumps(
        [
            {"nr": 1, "name": "Innenfarbe weiß", "menge": 4, "einheit": "L", "epreis": 10, "gesamtpreis": 40},
            {
                "nr": 2,
                "name": "Abklebeband 19 mm 25 m Rolle",
                "menge": 1,
                "einheit": "Rolle",
                "epreis": 30,
                "gesamtpreis": 30,
            },
        ]
    )
    ctx.llm2 = FakeLLM(llm_response)
    result = generate_offer_positions(payload={}, ctx=ctx)
    tape = next(pos for pos in result["positions"] if "Abklebeband" in pos["name"])
    assert tape["menge"] == 50


def test_override_with_unknown_product_is_blocked(tmp_path):
    entries = _override_catalog_entries()
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    initial_reply = (
        "Start.\n---\nstatus: schätzung\nmaterialien:\n"
        "- name=Innenfarbe weiß, menge=4, einheit=L\n"
        "- name=Abdeckfolie 20 m², menge=18, einheit=m²\n"
        "- name=Abklebeband 19 mm, menge=25, einheit=m\n---"
    )
    unknown_reply = (
        "Neues Produkt.\n---\nstatus: update\nmaterialien:\n"
        "- name=SuperDeko Farbe 3000, menge=5, einheit=L\n---"
    )
    ctx.chain1 = FakeChain(initial_reply)
    chat_turn(message="Start", ctx=ctx)
    ctx.chain1 = FakeChain(unknown_reply)
    result = chat_turn(message="Unbekanntes Produkt", ctx=ctx)
    assert result["ready_for_offer"] is False
    assert "Hinweis zur Produktprüfung" in result["reply"]
    history = ctx.memory1.load_memory_variables({}).get("chat_history", "")
    latest = qs._extract_last_machine_items(history, prefer_status="bestätigt")
    assert latest
    assert not any("SuperDeko" in item.get("name", "") for item in latest)


def test_locked_override_applies_to_paint(tmp_path):
    entries = _override_catalog_entries()
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    initial_reply = (
        "Start.\n---\nstatus: schätzung\nmaterialien:\n"
        "- name=Innenfarbe weiß, menge=4, einheit=L\n"
        "- name=Abdeckfolie 20 m², menge=18, einheit=m²\n"
        "- name=Abklebeband 19 mm, menge=25, einheit=m\n---"
    )
    override_reply = (
        "Mehr Farbe.\n---\nstatus: update\nmaterialien:\n"
        "- name=Innenfarbe weiß, menge=6, einheit=L\n---"
    )
    ctx.chain1 = FakeChain(initial_reply)
    chat_turn(message="Los", ctx=ctx)
    ctx.chain1 = FakeChain(override_reply)
    chat_turn(message="Mehr Farbe", ctx=ctx)
    llm_response = json.dumps(
        [
            {"nr": 1, "name": "Innenfarbe weiß", "menge": 5, "einheit": "L", "epreis": 12, "gesamtpreis": 60},
            {"nr": 2, "name": "Abdeckfolie 20 m²", "menge": 18, "einheit": "m²", "epreis": 2, "gesamtpreis": 36},
        ]
    )
    ctx.llm2 = FakeLLM(llm_response)
    result = generate_offer_positions(payload={}, ctx=ctx)
    paint = next(pos for pos in result["positions"] if "Innenfarbe" in pos["name"])
    assert paint["einheit"] == "L"
    assert paint["menge"] >= 6


def test_pack_conversion_keeps_base_units_for_tape(tmp_path):
    entries = _override_catalog_entries()
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    initial_reply = (
        "Start.\n---\nstatus: schätzung\nmaterialien:\n"
        "- name=Abklebeband 19 mm 25 m, menge=25, einheit=m, sku=sku-band\n---"
    )
    ctx.chain1 = FakeChain(initial_reply)
    chat_turn(message="Tape", ctx=ctx)
    llm_response = json.dumps(
        [
            {"nr": 1, "name": "Abklebeband 19 mm, Standard", "menge": 1, "einheit": "Stück", "epreis": 5, "gesamtpreis": 5}
        ]
    )
    ctx.llm2 = FakeLLM(llm_response)
    result = generate_offer_positions(payload={}, ctx=ctx)
    tape_positions = [pos for pos in result["positions"] if "Abklebeband" in pos["name"]]
    assert len(tape_positions) == 1
    tape = tape_positions[0]
    assert tape["einheit"] == "m"
    assert tape["menge"] >= 25


def test_pack_conversion_rounds_up_for_foil(tmp_path):
    entries = _override_catalog_entries()
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    initial_reply = (
        "Start.\n---\nstatus: schätzung\nmaterialien:\n"
        "- name=Abdeckfolie 20 m², menge=20, einheit=m², sku=sku-folie\n---"
    )
    override_reply = (
        "Mehr Folie.\n---\nstatus: update\nmaterialien:\n"
        "- name=Abdeckfolie 20 m², menge=30, einheit=m², sku=sku-folie\n---"
    )
    ctx.chain1 = FakeChain(initial_reply)
    chat_turn(message="Projekt", ctx=ctx)
    ctx.chain1 = FakeChain(override_reply)
    chat_turn(message="Mehr Folie", ctx=ctx)
    llm_response = json.dumps(
        [
            {"nr": 1, "name": "Abdeckfolie 20 m²", "menge": 1, "einheit": "Rolle", "epreis": 8, "gesamtpreis": 8},
        ]
    )
    ctx.llm2 = FakeLLM(llm_response)
    result = generate_offer_positions(payload={}, ctx=ctx)
    foil = next(pos for pos in result["positions"] if "Abdeckfolie" in pos["name"])
    assert foil["einheit"] == "m²"
    assert foil["menge"] == 40
    assert "locked_quantity" in foil.get("reasons", [])


def test_pack_conversion_for_paint_bucket(tmp_path):
    entries = _override_catalog_entries()
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    initial_reply = (
        "Start.\n---\nstatus: schätzung\nmaterialien:\n"
        "- name=Innenfarbe weiß, menge=5, einheit=L, sku=sku-farbe\n---"
    )
    override_reply = (
        "Mehr Farbe.\n---\nstatus: update\nmaterialien:\n"
        "- name=Innenfarbe weiß, menge=6, einheit=L, sku=sku-farbe\n---"
    )
    ctx.chain1 = FakeChain(initial_reply)
    chat_turn(message="Start", ctx=ctx)
    ctx.chain1 = FakeChain(override_reply)
    chat_turn(message="Mehr Farbe", ctx=ctx)
    llm_response = json.dumps(
        [
            {"nr": 1, "name": "Innenfarbe weiß 10L Eimer", "menge": 1, "einheit": "Eimer", "epreis": 60, "gesamtpreis": 60},
        ]
    )
    ctx.llm2 = FakeLLM(llm_response)
    result = generate_offer_positions(payload={}, ctx=ctx)
    paint = next(pos for pos in result["positions"] if "Innenfarbe" in pos["name"])
    assert paint["einheit"] == "L"
    assert paint["menge"] == 10


def test_piece_based_unit_stays_stueck(tmp_path):
    entries = _override_catalog_entries()
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    initial_reply = (
        "Start.\n---\nstatus: schätzung\nmaterialien:\n"
        "- name=Farbroller 25 cm, menge=2, einheit=Stück, sku=sku-roller\n---"
    )
    ctx.chain1 = FakeChain(initial_reply)
    chat_turn(message="Werkzeug", ctx=ctx)
    llm_response = json.dumps(
        [
            {"nr": 1, "name": "Farbroller 25 cm", "menge": 1, "einheit": "Pack", "epreis": 8, "gesamtpreis": 8},
        ]
    )
    ctx.llm2 = FakeLLM(llm_response)
    result = generate_offer_positions(payload={}, ctx=ctx)
    roller = next(pos for pos in result["positions"] if "Farbroller" in pos["name"])
    assert roller["einheit"] == "Stück"
    assert roller["menge"] >= 2


def test_wall_paint_prefers_interior_product(tmp_path):
    entries = _override_catalog_entries()
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    matches, unknown = qs._validate_materials(
        [{"name": "Innenwände streichen, weiße Wandfarbe"}],
        ctx,
        company_id=None,
    )
    assert not unknown
    entry = ctx.catalog_by_sku.get(matches[0]["sku"])
    product_type = qs._classify_product_entry(entry)
    assert product_type in {"wall_paint_interior", "ceiling_paint_interior"}


def test_wood_preserver_selected_for_wood_context(tmp_path):
    entries = _override_catalog_entries()
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    matches, unknown = qs._validate_materials(
        [{"name": "Holzschutz für Gartenzaun"}],
        ctx,
        company_id=None,
    )
    assert not unknown
    entry = ctx.catalog_by_sku.get(matches[0]["sku"])
    product_type = qs._classify_product_entry(entry)
    assert product_type in {"wood_preserver", "wood_paint"}


def test_tape_and_foil_classifications(tmp_path):
    entries = _override_catalog_entries()
    ctx = make_context(
        tmp_path,
        catalog_entry=entries[0],
        catalog_items=entries,
        catalog_by_name={entry["name"].lower(): entry for entry in entries},
        catalog_by_sku={entry["sku"]: entry for entry in entries},
        catalog_text_by_name={entry["name"].lower(): entry["raw"] for entry in entries},
        catalog_text_by_sku={entry["sku"]: entry["raw"] for entry in entries},
    )
    tape_matches, tape_unknown = qs._validate_materials([{"name": "Kreppband"}], ctx, company_id=None)
    assert not tape_unknown
    entry = ctx.catalog_by_sku.get(tape_matches[0]["sku"])
    assert qs._classify_product_entry(entry) == "tape"

    foil_matches, foil_unknown = qs._validate_materials([{"name": "Abdeckfolie für Boden"}], ctx, company_id=None)
    assert not foil_unknown
    entry = ctx.catalog_by_sku.get(foil_matches[0]["sku"])
    assert qs._classify_product_entry(entry) == "foil"
