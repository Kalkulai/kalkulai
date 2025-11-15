from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from jinja2 import Environment

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
    def __init__(self):
        self.messages: list[str] = []

    def add_ai_message(self, content: str) -> None:
        self.messages.append(content)


class FakeMemory:
    def __init__(self, history: str = ""):
        self._history = history
        self.chat_memory = FakeChatMemory()

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
    ctx = make_context(
        tmp_path,
        chain1=FakeChain(reply),
        memory1=FakeMemory(),
        llm1_thin_retrieval=False,
    )
    result = chat_turn(message="Bitte Angebot", ctx=ctx)

    assert result["ready_for_offer"] is True
    assert "**Zusammenfassung**" in result["reply"]
    assert ctx.memory1.chat_memory.messages  # type: ignore[union-attr]


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
    assert result["raw"] == llm_response


def test_generate_offer_positions_without_context_raises(tmp_path):
    ctx = make_context(tmp_path, memory1=None, llm2=FakeLLM("[]"))
    with pytest.raises(ServiceError) as exc:
        generate_offer_positions(payload={}, ctx=ctx)
    assert exc.value.status_code == 400


def test_render_offer_or_invoice_pdf(monkeypatch, tmp_path):
    saved_path = tmp_path / "outputs" / "angebot.pdf"
    saved_path.parent.mkdir(parents=True, exist_ok=True)

    def fake_render(env, context, output_dir):  # pragma: no cover - patched
        saved_path.write_text("pdf")
        return saved_path

    fake_module = SimpleNamespace(render_pdf_from_template=fake_render)
    monkeypatch.setitem(sys.modules, "backend.app.pdf", fake_module)
    ctx = make_context(tmp_path)
    payload = {
        "positions": [{"menge": 2, "einheit": "L", "epreis": 5.0, "gesamtpreis": 10.0}],
        "kunde": "Test GmbH",
    }

    result = render_offer_or_invoice_pdf(payload=payload, ctx=ctx)

    assert result["pdf_url"].endswith("angebot.pdf")
    assert result["context"]["brutto_summe"] == 11.9  # 19 % VAT


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
