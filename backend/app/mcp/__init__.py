"""
Model Context Protocol (MCP) helpers wrapping internal service-layer logic.

These helpers allow future MCP servers to configure shared context and access
the tool registry without depending on FastAPI-specific wiring.
"""

from .tools import (  # noqa: F401
    TOOL_REGISTRY,
    ToolDefinition,
    chat_turn,
    configure_tools,
    generate_offer_positions,
    get_tool,
    list_tools,
    render_pdf,
    reset_session,
    revenue_guard_check,
    search_catalog,
    wizard_finalize,
    wizard_next_step,
)
