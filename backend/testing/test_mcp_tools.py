from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from jinja2 import Environment

from backend.app.mcp import tools as mcp_tools
from backend.app.services.quote_service import QuoteServiceContext


@pytest.fixture
def configured_context(tmp_path: Path) -> QuoteServiceContext:
    ctx = QuoteServiceContext(
        chain1=None,
        chain2=None,
        llm1=None,
        llm2=None,
        prompt2=None,
        memory1=None,
        retriever=None,
        reset_callback=lambda: None,
        documents=[],
        catalog_items=[],
        catalog_by_name={},
        catalog_by_sku={},
        catalog_text_by_name={},
        catalog_text_by_sku={},
        catalog_search_cache={},
        wizard_sessions={},
        env=Environment(),
        output_dir=tmp_path,
        vat_rate=0.19,
        synonyms_path=tmp_path / "synonyms.yaml",
        logger=logging.getLogger("test-mcp-tools"),
        llm1_mode="assistive",
        adopt_threshold=0.8,
        business_scoring=[],
        llm1_thin_retrieval=False,
        catalog_top_k=5,
        catalog_cache_ttl=60,
        catalog_queries_per_turn=2,
        skip_llm_setup=True,
        default_company_id="default",
        debug=True,
    )
    mcp_tools.configure_tools(ctx)
    return ctx


def test_reset_session_tool_calls_service(monkeypatch, configured_context):
    captured: Dict[str, Any] = {}

    def fake_reset(*, ctx, reason=None):
        captured["ctx"] = ctx
        captured["reason"] = reason
        return {"ok": True, "message": "done"}

    monkeypatch.setattr(mcp_tools.qs, "reset_session", fake_reset)
    result = mcp_tools.reset_session(reason="maintenance")
    assert result["message"] == "done"
    assert captured == {"ctx": configured_context, "reason": "maintenance"}


def test_chat_turn_tool_maps_output(monkeypatch, configured_context):
    def fake_chat(*, message, ctx):
        assert ctx is configured_context
        return {"reply": f"Echo: {message}", "ready_for_offer": True}

    monkeypatch.setattr(mcp_tools.qs, "chat_turn", fake_chat)
    result = mcp_tools.chat_turn("Hallo")
    assert result == {"reply_markdown": "Echo: Hallo", "ready_for_offer": True}
    assert mcp_tools._STATE["ready_for_offer"] is True


def test_generate_offer_positions_tool_forwards_payload(monkeypatch, configured_context):
    captured: Dict[str, Any] = {}

    def fake_generate(*, payload, ctx, company_id, business_cfg=None):
        captured["payload"] = payload
        captured["ctx"] = ctx
        captured["company_id"] = company_id
        captured["business_cfg"] = business_cfg
        return {"positions": [{"nr": 1}], "raw": "[]"}

    monkeypatch.setattr(mcp_tools.qs, "generate_offer_positions", fake_generate)
    mcp_tools._STATE["ready_for_offer"] = True
    result = mcp_tools.generate_offer_positions(
        message="Bitte Angebot",
        products=["Farbe"],
        company_id="comp-1",
        business_cfg={"price": {"max": 100}},
    )
    assert result["error"] is None
    assert result["positions"] == [{"nr": 1}]
    assert captured["payload"] == {"message": "Bitte Angebot", "products": ["Farbe"]}
    assert captured["company_id"] == "comp-1"
    assert captured["business_cfg"] == {"price": {"max": 100}}
    assert mcp_tools._STATE["ready_for_offer"] is False


def test_generate_offer_positions_requires_readiness(monkeypatch, configured_context):
    monkeypatch.setattr(
        mcp_tools.qs,
        "generate_offer_positions",
        lambda *, payload, ctx, company_id, business_cfg=None: {"positions": [], "raw": "[]"},
    )
    result = mcp_tools.generate_offer_positions(message="now")
    assert result["error"] == "offer_not_ready"

    # Mark ready via chat_turn response
    monkeypatch.setattr(
        mcp_tools.qs,
        "chat_turn",
        lambda *, message, ctx: {"reply": message, "ready_for_offer": True},
    )
    mcp_tools.chat_turn("prep")
    mcp_tools._STATE["company_id_lock"] = None
    result_ready = mcp_tools.generate_offer_positions(message="go", confirmed=True, company_id="tenant-a")
    assert result_ready["error"] is None


def test_render_pdf_tool_passes_metadata(monkeypatch, configured_context):
    payloads: List[Dict[str, Any]] = []

    def fake_render(*, payload, ctx):
        payloads.append(payload)
        return {"pdf_url": "/outputs/a.pdf", "context": payload}

    monkeypatch.setattr(mcp_tools.qs, "render_offer_or_invoice_pdf", fake_render)
    positions = [{"name": "Farbe"}]
    result = mcp_tools.render_pdf(
        positions=positions,
        kunde="Test GmbH",
        angebot_nr="A-1",
        datum="2024-01-01",
        doc_type="invoice",
    )
    assert result["pdf_url"] == "/outputs/a.pdf"
    assert payloads[0]["doc_type"] == "invoice"
    assert payloads[0]["kunde"] == "Test GmbH"


def test_wizard_tools_delegate(monkeypatch, configured_context):
    state = {"calls": 0}

    def fake_next_step(*, payload, ctx):
        state["calls"] += 1
        if payload["session_id"] is None:
            return {
                "session_id": "sess-1",
                "step": "flaeche_m2",
                "question": "How big?",
                "ui": {"type": "number"},
                "context_partial": {},
                "done": False,
                "suggestions": [],
            }
        return {
            "session_id": payload["session_id"],
            "step": "",
            "question": "",
            "ui": {"type": "info"},
            "context_partial": payload["answers"],
            "done": True,
            "suggestions": [{"nr": 1, "name": "Farbe", "menge": 5, "einheit": "L"}],
        }

    monkeypatch.setattr(mcp_tools.qs, "wizard_next_step", fake_next_step)
    first = mcp_tools.wizard_next_step()
    assert first["done"] is False and first["session_id"] == "sess-1"
    second = mcp_tools.wizard_next_step(session_id="sess-1", answers={"flaeche_m2": 80})
    assert second["done"] is True

    monkeypatch.setattr(
        mcp_tools.qs,
        "wizard_finalize",
        lambda *, payload, ctx: {
            "session_id": payload["session_id"],
            "summary": "Projekt",
            "positions": [{"nr": 1, "name": "Basis", "menge": 10, "einheit": "L"}],
            "done": True,
        },
    )
    final_resp = mcp_tools.wizard_finalize(session_id="sess-1")
    assert final_resp["positions"]


def test_revenue_guard_tool(monkeypatch):
    def fake_guard(*, payload, debug=False):
        assert payload["positions"]
        assert payload["context"] == {"untergrund": "Putz"}
        assert debug is False
        return {"passed": False, "missing": [], "rules_fired": []}

    monkeypatch.setattr(mcp_tools.qs, "run_revenue_guard", fake_guard)
    # No context needed for this tool
    result = mcp_tools.revenue_guard_check([{"name": "Test"}], {"untergrund": "Putz"})
    assert result["passed"] is False


def test_wizard_flow_with_revenue_guard(monkeypatch, configured_context):
    # stub wizard responses
    monkeypatch.setattr(
        mcp_tools.qs,
        "wizard_next_step",
        lambda *, payload, ctx: {
            "session_id": payload["session_id"] or "wiz-1",
            "step": "" if payload["session_id"] else "flaeche_m2",
            "question": "" if payload["session_id"] else "How big?",
            "ui": {"type": "info"},
            "context_partial": payload["answers"] or {},
            "done": bool(payload["session_id"]),
            "suggestions": [{"nr": 1, "name": "Wizard Farbe", "menge": 7, "einheit": "L"}],
        },
    )
    monkeypatch.setattr(
        mcp_tools.qs,
        "wizard_finalize",
        lambda *, payload, ctx: {
            "session_id": payload["session_id"],
            "summary": "Wizard summary",
            "positions": [{"nr": 1, "name": "Wizard Farbe", "menge": 7, "einheit": "L"}],
            "done": True,
        },
    )

    captured_positions = {}

    def fake_guard(*, payload, debug=False):
        captured_positions["positions"] = payload["positions"]
        return {"passed": True, "missing": [], "rules_fired": []}

    monkeypatch.setattr(mcp_tools.qs, "run_revenue_guard", fake_guard)

    step_one = mcp_tools.wizard_next_step()
    assert step_one["done"] is False
    step_two = mcp_tools.wizard_next_step(session_id=step_one["session_id"], answers={"flaeche_m2": 50})
    assert step_two["done"] is True
    final_payload = mcp_tools.wizard_finalize(session_id=step_one["session_id"])
    assert final_payload["positions"][0]["name"] == "Wizard Farbe"
    guard_result = mcp_tools.revenue_guard_check(final_payload["positions"], {})
    assert guard_result["passed"] is True
    assert captured_positions["positions"] == final_payload["positions"]


def test_search_catalog_tool(monkeypatch, configured_context):
    def fake_search(*, query, limit, company_id, ctx):
        assert query == "farbe"
        assert limit == 3
        assert company_id == "comp-1"
        assert ctx is configured_context
        return {"query": query, "results": [], "count": 0, "limit": limit, "took_ms": 1}

    monkeypatch.setattr(mcp_tools.qs, "search_catalog", fake_search)
    resp = mcp_tools.search_catalog("farbe", top_k=3, company_id="comp-1")
    assert resp["limit"] == 3


def test_search_catalog_enforces_company_lock(monkeypatch, configured_context):
    monkeypatch.setattr(
        mcp_tools.qs,
        "search_catalog",
        lambda *, query, limit, company_id, ctx: {"query": query, "results": [], "count": 0, "limit": limit, "took_ms": 1},
    )
    mcp_tools.search_catalog("farbe", top_k=2, company_id="tenant-a")
    with pytest.raises(ValueError):
        mcp_tools.search_catalog("farbe", top_k=2, company_id="tenant-b")
    # Reset guard state by simulating server reset
    monkeypatch.setattr(mcp_tools.qs, "reset_session", lambda *, ctx, reason=None: {"ok": True, "message": "reset"})
    mcp_tools.reset_session()
    assert mcp_tools._STATE["company_id_lock"] is None


def test_tool_registry_metadata():
    expected = {
        "reset_session",
        "chat_turn",
        "generate_offer_positions",
        "render_pdf",
        "wizard_next_step",
        "wizard_finalize",
        "revenue_guard_check",
        "search_catalog",
    }
    assert set(mcp_tools.TOOL_REGISTRY.keys()) == expected
    for name, spec in mcp_tools.TOOL_REGISTRY.items():
        assert spec.name == name
        assert callable(spec.function)
        assert isinstance(spec.input_schema, dict)
        assert isinstance(spec.output_schema, dict)
        assert spec.usage_hint is not None
        if spec.scoped_to_company:
            assert name in {"generate_offer_positions", "search_catalog"}
