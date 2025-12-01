"""Minimal JSON-over-stdio MCP server exposing public Kalkulai tools.

It wires the shared QuoteServiceContext into the MCP tool registry, validates
requests, and streams responses for Model Context Protocol hosts. Guardrails
(company scoping, readiness, public-only tools) match those documented in
docs/mcp-overview.md. HTTP/FastAPI behavior remains unchanged.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Optional

from app.mcp.tools import (
    TOOL_REGISTRY,
    ToolDefinition,
    configure_tools,
    list_tools as registry_list_tools,
)
from app.services.quote_service import QuoteServiceContext

logger = logging.getLogger("mcp.server")

_CONTEXT_INITIALIZED = False


def initialize_context(context: Optional[QuoteServiceContext] = None) -> QuoteServiceContext:
    """
    Ensure the MCP tools are wired to a fully initialized service context.

    When no context is supplied, the existing FastAPI initialization path is
    reused by importing backend.main and reading its service context.
    """
    global _CONTEXT_INITIALIZED
    if _CONTEXT_INITIALIZED and context is None:
        # Already configured via a previous call.
        from app.mcp.tools import _CONTEXT as _TOOLS_CONTEXT  # type: ignore

        if _TOOLS_CONTEXT is not None:
            return _TOOLS_CONTEXT

    if context is None:
        from main import _get_service_context  # type: ignore

        context = _get_service_context()

    configure_tools(context)
    _CONTEXT_INITIALIZED = True
    return context


def _validate_args(schema: Dict[str, Any], args: Any) -> None:
    if schema.get("type") != "object":
        return
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")

    properties = schema.get("properties") or {}
    required_fields = schema.get("required") or []

    for field in required_fields:
        if field not in args:
            raise ValueError(f"missing required argument '{field}'")

    for name, value in args.items():
        if name not in properties:
            continue  # allow forwards compatibility
        expected = properties[name]
        _validate_type(name, value, expected)


def _validate_type(name: str, value: Any, schema: Dict[str, Any]) -> None:
    expected_type = schema.get("type")
    if expected_type is None:
        return

    type_checks = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    py_type = type_checks.get(expected_type)
    if py_type is None:
        return

    if not isinstance(value, py_type):
        raise ValueError(f"argument '{name}' must be of type {expected_type}")


def list_tools() -> Dict[str, Any]:
    """Return a JSON-serializable listing of all registered tools."""
    tools_payload = [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.input_schema,
            "output_schema": spec.output_schema,
            "usage_hint": spec.usage_hint,
            "scoped_to_company": spec.scoped_to_company,
            "example_flow": spec.example_flow,
        }
        for spec in registry_list_tools()
    ]
    return {"tools": tools_payload}


def call_tool(tool_name: str, args: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Execute a tool by name with validated arguments."""
    if tool_name not in TOOL_REGISTRY:
        raise KeyError(f"unknown tool '{tool_name}'")
    tool_def = TOOL_REGISTRY[tool_name]
    args_obj = args or {}
    _validate_args(tool_def.input_schema, args_obj)
    result = tool_def.function(**args_obj)
    return {"tool": tool_name, "result": result}


def dispatch_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a single MCP request dictionary and return the response dictionary.
    """
    req_id = request.get("id")
    req_type = request.get("type")
    response: Dict[str, Any] = {"id": req_id, "type": "response"}

    try:
        if req_type == "list_tools":
            response["success"] = True
            response["result"] = list_tools()
        elif req_type == "call_tool":
            tool_name = request.get("tool")
            args = request.get("args")
            if not isinstance(tool_name, str):
                raise ValueError("field 'tool' must be a string")
            response["success"] = True
            response["result"] = call_tool(tool_name, args)
        else:
            raise ValueError(f"unsupported request type '{req_type}'")
    except KeyError as exc:
        response["success"] = False
        response["error"] = {"code": "not_found", "message": str(exc)}
    except ValueError as exc:
        response["success"] = False
        response["error"] = {"code": "invalid_request", "message": str(exc)}
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("MCP tool execution failed")
        response["success"] = False
        response["error"] = {"code": "tool_error", "message": str(exc)}

    return response


def run_mcp_server(context: Optional[QuoteServiceContext] = None) -> None:
    """
    Run a simple JSON-over-stdio loop that exposes the MCP tools registry.
    """
    initialize_context(context)
    logger.info("MCP server started (stdio mode)")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON input: %s", exc)
            continue

        response = dispatch_request(request)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    run_mcp_server()
