from __future__ import annotations

import logging
from pathlib import Path

import pytest
from jinja2 import Environment

from backend.app.mcp import tools as mcp_tools
from backend.app.mcp import server as mcp_server
from backend.app.services.quote_service import QuoteServiceContext


@pytest.fixture
def context(tmp_path: Path) -> QuoteServiceContext:
    ctx = QuoteServiceContext(
        chain1=None,
        chain2=None,
        llm1=None,
        llm2=None,
        prompt2=None,
        memory1=None,
        retriever=None,
        reset_callback=lambda: None,
        documents=[object()],
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
        logger=logging.getLogger("test-mcp-server"),
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
    mcp_server.initialize_context(ctx)
    return ctx


@pytest.fixture(autouse=True)
def patch_service_functions(monkeypatch):
    monkeypatch.setattr(
        mcp_tools.qs,
        "chat_turn",
        lambda *, message, ctx: {"reply": f"Echo: {message}", "ready_for_offer": True},
    )
    monkeypatch.setattr(
        mcp_tools.qs,
        "generate_offer_positions",
        lambda *, payload, ctx, company_id, business_cfg=None: {
            "positions": [{"nr": 1, "name": payload.get("message", "auto")}],
            "raw": "[]",
        },
    )
    monkeypatch.setattr(
        mcp_tools.qs,
        "render_offer_or_invoice_pdf",
        lambda *, payload, ctx: {"pdf_url": "/outputs/test.pdf", "context": payload},
    )
    monkeypatch.setattr(
        mcp_tools.qs,
        "search_catalog",
        lambda *, query, limit, company_id, ctx: {
            "query": query,
            "results": [],
            "count": 0,
            "limit": limit,
            "took_ms": 1,
        },
    )


def test_list_tools_contains_expected_entries(context):
    response = mcp_server.list_tools()
    names = {tool["name"] for tool in response["tools"]}
    assert {"chat_turn", "generate_offer_positions", "render_pdf", "search_catalog"}.issubset(names)
    for tool in response["tools"]:
        assert tool["usage_hint"]
        assert "example_flow" in tool


def test_call_tool_success(context):
    chat = mcp_server.call_tool("chat_turn", {"message": "Hallo"})
    assert chat["result"]["reply_markdown"].startswith("Echo")

    offer = mcp_server.call_tool("generate_offer_positions", {"message": "Farbe"})
    assert offer["result"]["positions"][0]["name"] == "Farbe"

    pdf = mcp_server.call_tool("render_pdf", {"positions": [{"name": "Test"}]})
    assert pdf["result"]["pdf_url"] == "/outputs/test.pdf"


def test_call_tool_errors(context):
    with pytest.raises(KeyError):
        mcp_server.call_tool("unknown", {})
    with pytest.raises(ValueError):
        mcp_server.call_tool("chat_turn", {})


def test_generate_offer_requires_ready_flag(context):
    # reset readiness state
    mcp_tools._STATE["ready_for_offer"] = False
    resp = mcp_server.call_tool("generate_offer_positions", {"message": "Too soon"})
    assert resp["result"]["error"] == "offer_not_ready"


def test_call_tool_company_lock(context):
    mcp_tools._STATE["company_id_lock"] = None
    mcp_server.call_tool("search_catalog", {"q": "farbe", "company_id": "tenant-a"})
    with pytest.raises(ValueError):
        mcp_server.call_tool("search_catalog", {"q": "farbe", "company_id": "tenant-b"})


def test_dispatch_request_success(context):
    req = {"id": 1, "type": "call_tool", "tool": "chat_turn", "args": {"message": "Hi"}}
    resp = mcp_server.dispatch_request(req)
    assert resp["success"] is True
    assert resp["result"]["result"]["reply_markdown"].startswith("Echo")


def test_dispatch_request_errors(context):
    resp = mcp_server.dispatch_request({"id": "a", "type": "call_tool", "tool": "chat_turn"})
    assert resp["success"] is False
    assert resp["error"]["code"] == "invalid_request"

    resp_unknown = mcp_server.dispatch_request({"id": "b", "type": "call_tool", "tool": "missing", "args": {}})
    assert resp_unknown["success"] is False
    assert resp_unknown["error"]["code"] == "not_found"
