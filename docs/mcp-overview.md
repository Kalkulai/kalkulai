# Kalkulai MCP Overview

## 1. What is the MCP Layer?
The Model Context Protocol (MCP) is a lightweight contract for invoking tools from LLM hosts. Kalkulai exposes its quoting workflows through MCP so assistants can call structured functions (chat, wizard, revenue guard, PDF rendering) without new HTTP endpoints. The FastAPI app continues to serve Web clients; the MCP layer reuses the same service logic with additional guardrails.

```
LLM Host ── JSON/stdio ──> MCP Server ──> MCP Tools ──> Quote Service Layer ──> FastAPI / DB / LLMs
```

## 2. Architecture Overview
- **Service layer (`backend/app/services/quote_service.py`)** – source of truth for chat, offer generation, PDF rendering, wizard logic, revenue guard.
- **MCP tools (`backend/app/mcp/tools.py`)** – typed wrappers that enforce company scoping, readiness gating, and publish metadata.
- **MCP server (`backend/app/mcp/server.py`)** – JSON-over-stdio dispatcher that exposes only the public tools. HTTP routes remain unchanged.
- **QuoteServiceContext** – shared object containing LLM clients, retriever, catalog data, wizard sessions, etc. FastAPI and MCP both use it.

## 3. Public MCP Tools
| Tool | Description | Inputs | Outputs | usage_hint | example_flow | scoped_to_company | Finalizing? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `reset_session` | Reset wizard sessions & rebuild chains | reason?: string | {ok: bool, message: str} | Warn users before wiping state | reset_session → chat_turn/wizard_next_step | false | No |
| `chat_turn` | LLM1 chat step | message: string | {reply_markdown, ready_for_offer} | Gather requirements until ready_for_offer=true | chat_turn loop → generate_offer_positions | false | No |
| `generate_offer_positions` | LLM2 offer generation | message?, products?, company_id?, business_cfg?, confirmed? | {positions[], raw_llm, error?, message?} | Only call after ready_for_offer or confirmed=true | chat_turn → generate_offer_positions → revenue_guard_check → render_pdf | true | No |
| `render_pdf` | Render offer/invoice PDF | positions[], kunde?, angebot_nr?, datum?, doc_type? | {pdf_url, context} | Final step; run revenue_guard_check first | … → revenue_guard_check → render_pdf | false | Yes |
| `search_catalog` | Thin retrieval for catalog items | q: string, top_k?, company_id? | {query, results[], count, limit, took_ms} | Scoped to active company | chat_turn/wizard → search_catalog for references | true | No |
| `wizard_next_step` | Structured wizard question | session_id?, answers? | {session_id, step, question, ui, context_partial, done, suggestions[]} | Form-based alternative; loop until done=true | reset_session → wizard_next_step loop → wizard_finalize | false | No |
| `wizard_finalize` | Finish wizard & get positions | session_id: string | {summary, positions[], done} | Call after wizard reports done | wizard flow → wizard_finalize → revenue_guard_check → render_pdf | false | No |
| `revenue_guard_check` | Deterministic missing-item checker | positions[], context? | {passed, missing[], rules_fired[]} | Run before render_pdf to suggest upsells | … → revenue_guard_check → render_pdf | false | No |

## 4. Guardrails & Safety
- **Company scoping** – `_resolve_company_id` locks the first company_id per session; subsequent calls must match.
- **Readiness gating** – `chat_turn` sets `ready_for_offer`; `generate_offer_positions` refuses to run until ready or `confirmed=true`.
- **Public vs admin** – only public tools appear in `TOOL_REGISTRY`; admin/ops tools require a separate registry/server.
- **Finalizing operations** – `render_pdf` is considered final; only call after explicit confirmation and revenue guard.
- **Session reset** – `reset_session` clears wizard sessions and guard state; warn the user beforehand.

## 5. Workflows / Recipes
### a. Chat-first offer flow
1. `chat_turn` (loop) until `ready_for_offer=true`.
2. `generate_offer_positions` (set `confirmed=true` if forcing early).
3. `revenue_guard_check` with returned positions.
4. `render_pdf` to produce the offer PDF.

### b. Wizard-first offer flow
1. `reset_session` (optional).
2. `wizard_next_step` (loop, passing answers) until response indicates `done=true`.
3. `wizard_finalize` for summary + baseline positions.
4. `revenue_guard_check` on wizard positions.
5. `render_pdf` for the final PDF.

### c. Invoice generation flow
1. Reuse stored positions or regenerate them via chat/wizard.
2. `render_pdf` with `doc_type="invoice"` plus metadata.

## 6. How to Run the MCP Server
```
python -m backend.app.mcp.server
```
Protocol: one JSON object per line on stdin.
- Request fields: `id`, `type` (`list_tools` or `call_tool`), `tool`, `args`.
- Example request:
```
{"id": 1, "type": "call_tool", "tool": "chat_turn", "args": {"message": "Hallo"}}
```
- Example response:
```
{"id": 1, "type": "response", "success": true, "result": {"tool": "chat_turn", "result": {"reply_markdown": "...", "ready_for_offer": false}}}
```

## 7. Testing MCP
```
cd backend
python3 -m pytest testing/test_mcp_tools.py testing/test_mcp_server.py
```
Tests rely on `SKIP_LLM_SETUP=1` (default) and stubbed service functions so no live LLM calls occur.

## 8. Future Extensions
- Add tools by extending `TOOL_REGISTRY` with usage hints, guardrails, and tests.
- Provide an admin-only registry/server for ops workflows (index rebuilds, catalog edits) if needed.
- Versioning: bump metadata/schema when inputs/outputs change to keep LLM hosts in sync.
