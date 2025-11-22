from __future__ import annotations

import logging
from pathlib import Path

import pytest
from jinja2 import Environment

from backend.app.mcp import server as mcp_server
from backend.app.services.quote_service import QuoteServiceContext


@pytest.fixture
def context_fixture(tmp_path: Path):
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
        logger=logging.getLogger("test-mcp-docs"),
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


def test_list_tools_contains_doc_metadata(context_fixture):
    response = mcp_server.list_tools()
    assert response["tools"]
    for tool in response["tools"]:
        assert tool["usage_hint"]
        assert "example_flow" in tool
