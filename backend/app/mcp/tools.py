"""Public MCP tools wrapping quote service logic with guardrails.

These functions adapt QuoteServiceContext operations into Model Context Protocol
tools (chat, wizard, catalog search). They enforce company scoping, readiness,
and publish metadata consumed by the MCP server. See docs/mcp-overview.md for
end-to-end guidance and usage recipes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import backend.app.services.quote_service as qs
from backend.app.services.quote_service import QuoteServiceContext

_CONTEXT: QuoteServiceContext | None = None
_STATE: Dict[str, Any] = {
    "ready_for_offer": False,
    "company_id_lock": None,
}


def configure_tools(context: QuoteServiceContext) -> None:
    """Configure the MCP tools module with a shared service context."""
    global _CONTEXT
    _CONTEXT = context
    _reset_guard_state()


def _require_context() -> QuoteServiceContext:
    if _CONTEXT is None:
        raise RuntimeError("MCP tools are not configured. Call configure_tools() first.")
    return _CONTEXT


def _reset_guard_state() -> None:
    _STATE["ready_for_offer"] = False
    _STATE["company_id_lock"] = None


def _resolve_company_id(explicit: Optional[str], ctx: QuoteServiceContext) -> str:
    candidate = (explicit or ctx.default_company_id or "").strip()
    if not candidate:
        raise ValueError("company_id is required but missing.")
    lock = _STATE.get("company_id_lock")
    if lock is None:
        _STATE["company_id_lock"] = candidate
        return candidate
    if candidate != lock:
        raise ValueError("company_id mismatch detected for this session.")
    return lock


def reset_session(reason: Optional[str] = None) -> Dict[str, Any]:
    """
    Reset server-side wizard sessions and (if available) rebuild the LLM chains.

    Args:
        reason: Optional explanation for auditing purposes.
    """
    ctx = _require_context()
    result = qs.reset_session(ctx=ctx, reason=reason)
    _reset_guard_state()
    return result


def chat_turn(message: str) -> Dict[str, Any]:
    """
    Run a single LLM1 chat turn and return the assistant reply plus readiness flag.
    """
    ctx = _require_context()
    result = qs.chat_turn(message=message, ctx=ctx)
    _STATE["ready_for_offer"] = bool(result.get("ready_for_offer"))
    return {
        "reply_markdown": result.get("reply", ""),
        "ready_for_offer": bool(result.get("ready_for_offer")),
    }


def generate_offer_positions(
    message: Optional[str] = None,
    products: Optional[List[str]] = None,
    company_id: Optional[str] = None,
    business_cfg: Optional[Dict[str, Any]] = None,
    confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Run the LLM2 pipeline to convert confirmed materials into structured offer lines.
    """
    ctx = _require_context()
    if not (confirmed or _STATE.get("ready_for_offer")):
        return {
            "positions": [],
            "raw_llm": "",
            "error": "offer_not_ready",
            "message": "The conversation is not ready for offer generation. Confirm materials first.",
        }
    payload: Dict[str, Any] = {}
    if message is not None:
        payload["message"] = message
    if products is not None:
        payload["products"] = products

    result = qs.generate_offer_positions(
        payload=payload,
        ctx=ctx,
        company_id=_resolve_company_id(company_id, ctx),
        business_cfg=business_cfg,
    )
    _STATE["ready_for_offer"] = False
    return {
        "positions": result.get("positions", []),
        "raw_llm": result.get("raw", ""),
        "error": None,
        "message": None,
    }


def render_pdf(
    *,
    positions: List[Dict[str, Any]],
    kunde: Optional[str] = None,
    angebot_nr: Optional[str] = None,
    datum: Optional[str] = None,
    doc_type: str = "offer",
) -> Dict[str, Any]:
    """
    Render an offer/invoice PDF from structured positions and metadata.
    Use only after the customer explicitly confirms the document is final.
    """
    ctx = _require_context()
    payload: Dict[str, Any] = {"positions": positions, "doc_type": doc_type}
    if kunde is not None:
        payload["kunde"] = kunde
    if angebot_nr is not None:
        payload["angebot_nr"] = angebot_nr
    if datum is not None:
        payload["datum"] = datum

    return qs.render_offer_or_invoice_pdf(payload=payload, ctx=ctx)


def wizard_next_step(session_id: Optional[str] = None, answers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Advance the painter wizard by one step, returning the next prompt and suggestions.
    """
    ctx = _require_context()
    payload = {
        "session_id": session_id,
        "answers": answers or {},
    }
    return qs.wizard_next_step(payload=payload, ctx=ctx)


def wizard_finalize(session_id: str) -> Dict[str, Any]:
    """
    Finalize the painter wizard and return the summary plus material positions.
    """
    ctx = _require_context()
    return qs.wizard_finalize(payload={"session_id": session_id}, ctx=ctx)


def revenue_guard_check(positions: List[Dict[str, Any]], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Run deterministic revenue-guard rules against the provided offer positions/context.
    """
    return qs.run_revenue_guard(payload={"positions": positions, "context": context or {}}, debug=False)


def search_catalog(q: str, top_k: Optional[int] = None, company_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Search the catalog via thin-retrieval and return scored product candidates.
    """
    ctx = _require_context()
    limit = top_k if top_k is not None else ctx.catalog_top_k
    resolved_company = _resolve_company_id(company_id, ctx)
    return qs.search_catalog(query=q, limit=limit, company_id=resolved_company, ctx=ctx)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    function: Callable[..., Any]
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    usage_hint: Optional[str] = None
    scoped_to_company: bool = False
    example_flow: Optional[str] = None


PUBLIC_TOOL_NAMES = [
    "reset_session",
    "chat_turn",
    "generate_offer_positions",
    "render_pdf",
    "wizard_next_step",
    "wizard_finalize",
    "revenue_guard_check",
    "search_catalog",
]


TOOL_REGISTRY: Dict[str, ToolDefinition] = {
    "reset_session": ToolDefinition(
        name="reset_session",
        description="Reset wizard sessions and rebuild LLM chains/memory if available.",
        function=reset_session,
        input_schema={
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}, "message": {"type": "string"}},
            "required": ["ok", "message"],
        },
        usage_hint="Only use when you need a clean slate; warn the user about losing progress.",
        example_flow="Before starting a new user conversation: reset_session → chat_turn/wizard_next_step",
    ),
    "chat_turn": ToolDefinition(
        name="chat_turn",
        description="Execute one chat turn via LLM1 and extract readiness for offer generation.",
        function=chat_turn,
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "reply_markdown": {"type": "string"},
                "ready_for_offer": {"type": "boolean"},
            },
            "required": ["reply_markdown", "ready_for_offer"],
        },
        usage_hint="Natural-language path: gather requirements here until ready_for_offer becomes true.",
        example_flow="chat_turn (repeat until ready) → generate_offer_positions → revenue_guard_check → render_pdf",
    ),
    "generate_offer_positions": ToolDefinition(
        name="generate_offer_positions",
        description="Invoke the offer-generation pipeline to produce structured positions.",
        function=generate_offer_positions,
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "products": {"type": "array", "items": {"type": "string"}},
                "company_id": {"type": "string"},
                "business_cfg": {"type": "object"},
                "confirmed": {"type": "boolean"},
            },
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "positions": {"type": "array"},
                "raw_llm": {"type": "string"},
                "error": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["positions", "raw_llm"],
        },
        usage_hint="Use after chat_turn reports ready_for_offer (or confirmed=true) to obtain offer positions, then run revenue_guard_check.",
        scoped_to_company=True,
        example_flow="chat_turn → generate_offer_positions → revenue_guard_check → render_pdf",
    ),
    "render_pdf": ToolDefinition(
        name="render_pdf",
        description="Render offer/invoice PDFs from structured positions.",
        function=render_pdf,
        input_schema={
            "type": "object",
            "properties": {
                "positions": {"type": "array"},
                "kunde": {"type": "string"},
                "angebot_nr": {"type": "string"},
                "datum": {"type": "string"},
                "doc_type": {"type": "string", "enum": ["offer", "invoice"]},
            },
            "required": ["positions"],
        },
        output_schema={
            "type": "object",
            "properties": {"pdf_url": {"type": "string"}, "context": {"type": "object"}},
            "required": ["pdf_url", "context"],
        },
        usage_hint="Finalization step – only after the user explicitly requests a PDF; run revenue_guard_check first.",
        example_flow="... → revenue_guard_check → render_pdf",
    ),
    "wizard_next_step": ToolDefinition(
        name="wizard_next_step",
        description="Advance the painter wizard and return the next question plus suggestions.",
        function=wizard_next_step,
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "answers": {"type": "object"},
            },
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "step": {"type": "string"},
                "question": {"type": "string"},
                "ui": {"type": "object"},
                "context_partial": {"type": "object"},
                "done": {"type": "boolean"},
                "suggestions": {"type": "array"},
            },
            "required": ["session_id", "done", "context_partial", "suggestions"],
        },
        usage_hint="Structured alternative to chat_turn: call repeatedly, passing answers, until done=true before finalizing.",
        example_flow="reset_session → wizard_next_step (loop) → wizard_finalize → revenue_guard_check → render_pdf",
    ),
    "wizard_finalize": ToolDefinition(
        name="wizard_finalize",
        description="Finalize the painter wizard and return summary plus positions.",
        function=wizard_finalize,
        input_schema={
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "positions": {"type": "array"},
                "done": {"type": "boolean"},
            },
            "required": ["summary", "positions", "done"],
        },
        usage_hint="Call once wizard_next_step signals done=true to obtain baseline positions for revenue_guard_check or render_pdf.",
    ),
    "revenue_guard_check": ToolDefinition(
        name="revenue_guard_check",
        description="Run deterministic revenue-guard checks on offer positions.",
        function=revenue_guard_check,
        input_schema={
            "type": "object",
            "properties": {
                "positions": {"type": "array"},
                "context": {"type": "object"},
            },
            "required": ["positions"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "missing": {"type": "array"},
                "rules_fired": {"type": "array"},
            },
            "required": ["passed", "missing", "rules_fired"],
        },
        usage_hint="Use after generate_offer_positions or wizard_finalize to suggest missing items before render_pdf.",
    ),
    "search_catalog": ToolDefinition(
        name="search_catalog",
        description="Search catalog entries using thin retrieval for product candidates.",
        function=search_catalog,
        input_schema={
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "top_k": {"type": "integer"},
                "company_id": {"type": "string"},
            },
            "required": ["q"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "results": {"type": "array"},
                "count": {"type": "integer"},
                "limit": {"type": "integer"},
                "took_ms": {"type": "integer"},
            },
            "required": ["query", "results", "count"],
        },
        usage_hint="Use to fetch catalog details scoped to the active company context.",
        scoped_to_company=True,
    ),
}

# Ensure registry only contains public tools (no admin/ops functions here).
assert set(TOOL_REGISTRY.keys()) <= set(PUBLIC_TOOL_NAMES)


def list_tools() -> List[ToolDefinition]:
    """Return all registered MCP tool definitions."""
    return list(TOOL_REGISTRY.values())


def get_tool(name: str) -> ToolDefinition:
    """Look up a tool definition by name."""
    return TOOL_REGISTRY[name]
