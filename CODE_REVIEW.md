# Carole.ai — Code Review & Feature Map

**Scope:** Full-stack review (FastAPI backend + Next.js frontend), ~20k LOC across ~100 files.
**Date:** 2026-06-22
**Status:** This pass delivered the **Scratchpad feature end-to-end** and a set of **top
high-impact fixes** (marked ✅ below). Remaining findings are documented for follow-up passes
— the codebase is mid-refactor (52 modified + 24 untracked files at review time), so a single
giant rewrite was intentionally avoided in favor of verifiable, incremental change.

---

## 1. Feature → Code Map

### Backend (`backend/core/`)

| Feature | Primary files |
|---|---|
| App bootstrap, lifespan, WebSocket gateway, router mounting | `main.py` |
| ReACT agent loop, system-prompt assembly, scratchpad awareness | `agent/react_agent.py`, `agent/coordinator.py`, `agent/role_templates.py` |
| Tool registry, gated execution, human-in-the-loop approvals | `tools/tool_registry.py`, `tools/tool_executor.py`, `tools/context.py` |
| Built-in tools (file/shell/git/web/browser/code/memory/meeting/voice/interaction) | `tools/file_tools.py`, `shell_tools.py`, `git_tools.py`, `web_tools.py`, `browser_tool.py`, `browser_pool.py`, `code_analysis_tools.py`, `memory_tools.py`, `meeting_tool.py`, `google_meet_tool.py`, `google_workspace_tools.py`, `interaction_tools.py`, `agent_tools.py` |
| MCP client | `tools/mcp_client.py` |
| Plugin system | `tools/plugin_decorator.py`, `plugins/` |
| Skills system | `skills/skill_manager.py`, `api/skill_routes.py` |
| **Scratchpad store (NEW)** | `memory/scratchpad.py` |
| **Scratchpad REST API (NEW)** | `api/scratchpad_routes.py` |
| CRUD (agents, teams, projects, tasks, messages, learnings) | `api/crud_routes.py` |
| Cost / model catalog / plugin routes | `api/cost_routes.py`, `api/model_routes.py`, `api/plugin_routes.py` |
| Auth (JWT, middleware, OAuth) | `auth/auth_service.py`, `auth/auth_middleware.py`, `api/auth_routes.py`, `api/google_auth_routes.py` |
| Files / git / search / terminal REST | `api/file_routes.py`, `api/git_routes.py`, `api/search_routes.py`, `api/terminal_routes.py`, `api/terminal_ws.py` |
| Chat routing, EventBus pub/sub | `chat/message_router.py`, `chat/event_bus.py` |
| Memory: SQLite models, LanceDB vectors, auto-dream consolidation | `memory/database.py`, `memory/models.py`, `memory/lancedb_client.py`, `memory/auto_dream.py` |
| Hybrid GraphRAG: code graph + ingestor | `knowledge/code_graph.py`, `knowledge/knowledge_ingestor.py` |
| LLM multi-model router, config manager, model catalog | `llm/multi_model_router.py`, `llm/config_manager.py`, `llm/model_catalog.py` |
| Judge evaluator (tool safety gate) | `judge/judge_evaluator.py` |
| Prompts (defaults + user overrides) | `defaults/prompts.json`, `prompts.py`, `config.py` |

### Frontend (`frontend/src/`)

| Feature | Primary files |
|---|---|
| App shell, state, WS event processing, panel routing | `app/page.tsx` |
| Sidebar / nav / project+team switcher | `components/Sidebar.tsx` |
| Chat (streaming, reasoning, mentions, approvals) | `components/ChatInterface.tsx` |
| Agent management | `components/AgentPanel.tsx` |
| Native Kanban task board + task detail | `components/KanbanBoard.tsx`, `components/TaskDetailModal.tsx` |
| Long-term memory / learnings | `components/MemoryView.tsx` |
| **Scratchpad panel (NEW)** | `components/ScratchpadPanel.tsx` |
| File explorer / diff viewer | `components/FileExplorerPanel.tsx`, `components/DiffViewer.tsx` |
| Git panel (via Next API route) | `components/GitPanel.tsx`, `app/api/git/[...action]/route.ts` |
| Terminal | `components/TerminalPanel.tsx` |
| Browser view (live screenshots) | `components/BrowserView.tsx` |
| Settings, model catalog editor, prompts editor | `components/SettingsPanel.tsx`, `components/settings/ModelCatalogEditor.tsx`, `components/settings/PromptsEditor.tsx` |
| Plugin studio / skills studio / MCP | `components/PluginStudio.tsx`, `components/SkillsStudio.tsx`, `components/McpIntegration.tsx` |
| Hooks: API, WebSocket, auth, toast | `hooks/useApi.ts`, `useWebSocket.ts`, `useAuth.tsx`, `useToast.ts` |
| Shared types | `lib/types.ts` |

---

## 2. Scratchpad feature — what was built this pass

**Problem:** scratchpad was half-built — backend had read/write only, with path logic
duplicated across 4 sites; no update/delete/list; no realtime; zero frontend UI.

**Delivered:**
- `backend/core/memory/scratchpad.py` — `ScratchpadStore`: single source of truth.
  Workspace-aware path `~/.carole/workspaces/{project_slug}/{team_slug}/scratchpads/`.
  CRUD: `list_pads` (team + every agent, empty pads included), `read`, `write` (append/overwrite),
  `update` (full replace), `delete` (clear). Per-pad `asyncio.Lock` prevents torn writes from
  concurrent agents. Broadcasts `scratchpad_updated` on the EventBus for live UI updates.
  Slug resolution mirrors `file_tools.get_workspace_root` with graceful raw-id fallback.
- `backend/core/api/scratchpad_routes.py` — clean router: `GET` list, `GET /{target}`,
  `POST` write, `PUT` update, `DELETE` clear. Mounted in `main.py`. The old inline endpoints
  were removed from `crud_routes.py` (no frontend consumer existed).
- `backend/core/tools/tool_executor.py` — `read/write/update/clear_scratchpad` tools, all
  delegating to the store (4× duplication removed). `datetime.utcnow()` → `datetime.now(timezone.utc)`.
- `backend/core/agent/react_agent.py` + `defaults/prompts.json` — agent awareness of all four ops.
- Frontend: `ScratchpadItem` type, 5 `useApi` methods, Sidebar nav entry, `ScratchpadPanel`
  (team + per-agent rail, view/edit/append/clear, stale-remote-update banner so edits are never
  clobbered), wired into `page.tsx` (load on team change + `scratchpad_updated` WS handling).

**Verified:** backend CRUD smoke test at correct path; `npx tsc --noEmit` clean;
`npm run build` clean; `pytest` 14/14 green.

---

## 3. Findings

Severity: **P0** critical/security/data-loss · **P1** bugs/perf/architecture · **P2** maintainability.
Each finding is marked **[confirmed]** (verified directly) or **[reported]** (from review pass,
worth verifying before acting). ✅ = fixed this pass; 📋 = documented for follow-up.

### P0

| # | Finding | Location | Status |
|---|---|---|---|
| P0-1 | **JWT in localStorage** — token stealable via any XSS. Move to httpOnly cookies. [reported] | `frontend/src/hooks/useAuth.tsx`, `useApi.ts` | 📋 |
| P0-2 | **Hardcoded default JWT secret** — `carole-ai-dev-secret-change-in-production`. Refuse to boot in prod without `JWT_SECRET`. [confirmed] | `backend/core/auth/auth_service.py` | 📋 |
| P0-3 | **Git clone SSRF / URL validation** — user-supplied git URL unvalidated; could target internal hosts. [reported] | `backend/core/tools/git_tools.py` `clone()` | 📋 |
| P0-4 | **Markdown XSS surface** — agent/user text rendered via ReactMarkdown; ensure HTML is disabled (default-safe, but lock it down explicitly). [reported] | `frontend/src/components/ChatInterface.tsx` (~604-626) | 📋 |

> Note: two review-pass P0s were **rejected as false positives** after verification:
> - "Global approval dict never cleaned up" — it IS cleaned on both timeout (`tool_executor.py:436-437`) and resolution (`:444-445`). (Minor residual leak only if the agent task is *cancelled* mid-await — see P2-3.)
> - "LanceDB SQL injection" — LanceDB uses vector + filter APIs, not raw SQL string interpolation; lower risk than claimed. Still worth UUID-validating ids (P2-2).

### P1

| # | Finding | Location | Status |
|---|---|---|---|
| P1-1 | **Zombie process leak on shell timeout** — `process.kill()` not followed by `await process.wait()` in the `TimeoutError` branch (happy path reaps correctly). [confirmed] | `backend/core/tools/shell_tools.py:108-113` | ✅ Fixed |
| P1-2 | **Unbounded `messages` array growth** — WS events append indefinitely over long sessions (screenshots are capped at 50; messages are not). Cap or window the in-memory list. [confirmed] | `frontend/src/app/page.tsx` (`messages` state + `applyWSEvent`) | 📋 |
| P1-3 | **Rollback optimistic-update race** — UI state updated before the API confirms; on API failure UI shows rolled-back state while server retains old data. Await API, revert + toast on failure. [confirmed] | `frontend/src/app/page.tsx:344-356` | 📋 |
| P1-4 | **N+1 in editor-conflict check** — one DB query per conflicting agent. Batch with `Agent.name.in_(...)`. [reported] | `backend/core/tools/tool_executor.py` (`_check_active_editor_conflicts`) | 📋 |
| P1-5 | **Browser context unbounded** — no per-agent/global cap on Playwright contexts; a runaway agent can exhaust memory. [reported] | `backend/core/tools/browser_pool.py` | 📋 |
| P1-6 | **EventBus history dict unbounded** — per-topic deques are capped (maxlen=100) but the *dict* of topics grows with team churn. Add a TTL sweep. [confirmed] | `backend/core/chat/event_bus.py:31-34` | 📋 |
| P1-7 | **Terminal WS uses `threading.Thread`** — background reader thread can outlive a disconnect; race with `active_sessions`. Prefer `asyncio` task or a shutdown flag. [reported] | `backend/core/api/terminal_ws.py` | 📋 |
| P1-8 | **Stale closure / missing deps in `useEffect`/`useCallback`** — e.g. FileExplorer `loadChildren` not re-run on path change; ChatInterface keydown handler missing `agents` dep. [reported] | `FileExplorerPanel.tsx`, `ChatInterface.tsx` | 📋 |
| P1-9 | **API inflight-dedup deletes key before retry decision** — can double-fire a GET on retry failure. [reported] | `frontend/src/hooks/useApi.ts:37-46` | 📋 |
| P1-10 | **Blocking `print()` in async paths** — `print()` in shell/judge/browser code is sync IO on the event loop; also leaks potentially sensitive LLM responses. Use `logger`. [confirmed] | `shell_tools.py`, `judge/judge_evaluator.py`, `browser_tool.py` | 📋 |

### P2

| # | Finding | Location | Status |
|---|---|---|---|
| P2-1 | **Stray debug `console.log`** in ThoughtsPanel (no longer needed). [confirmed] | `frontend/src/components/ChatInterface.tsx:141` | ✅ Fixed |
| P2-2 | **Overly broad `except Exception`** swallows `CancelledError`/`SystemExit`; DB migration `except: pass` hides non-"already exists" errors. Catch specific exceptions. [confirmed] | `memory/database.py`, `lancedb_client.py`, others | 📋 |
| P2-3 | **Approval dict leak on task cancellation** — if the agent loop is cancelled while awaiting approval, `pending_approvals[tx_id]` is not popped. Wrap await in try/finally. [confirmed] | `backend/core/tools/tool_executor.py:433-445` | 📋 |
| P2-4 | **No ErrorBoundary** — a single component throw crashes the whole app. [reported] | `frontend/src/app/page.tsx` `AppContent` | 📋 |
| P2-5 | **File backup naming O(N) loop + collision risk** — use timestamp+uuid instead of `@v{N}` scan. [reported] | `backend/core/tools/tool_executor.py` (`~663-669`) | 📋 |
| P2-6 | **Implicit numeric coercion can raise** — `float(args.get("timeout"))` / `int(args.get("count"))` without try/except. [confirmed] | `backend/core/tools/tool_executor.py` | 📋 |
| P2-7 | **Delete file without dirty-state check** — can delete a file with unsaved editor changes. [reported] | `frontend/src/components/FileExplorerPanel.tsx` | 📋 |
| P2-8 | **Magic numbers / a11y gaps** — `slice(-50)` constants, missing ARIA on mention dropdown. [reported] | `page.tsx`, `ChatInterface.tsx` | 📋 |
| P2-9 | **No audit log** for sensitive ops (file writes/deletes, tool executions). [reported] | backend API layer | 📋 |
| P2-10 | **`datetime.utcnow()` deprecation** — remaining call sites beyond scratchpad (Py3.12). [reported] | backend-wide grep | 📋 |

---

## 4. Top fixes applied this pass ✅

1. **Scratchpad feature fully implemented** (end-to-end) — the explicit user ask. See §2.
2. **Shell zombie-process leak** (P1-1) — `await process.wait()` added in the timeout branch.
3. **Stray debug `console.log`** (P2-1) — removed from `ThoughtsPanel`.
4. **4× duplicated scratchpad path logic consolidated** into `ScratchpadStore` (maintainability).
5. **Deprecated `datetime.utcnow()`** replaced in scratchpad code.

## 5. Recommended next passes (priority order)

1. **P0-1 / P0-2** — auth hardening (httpOnly cookies + refuse-to-boot without `JWT_SECRET`).
2. **P1-2 / P1-3** — frontend memory + rollback-correctness (user-visible reliability).
3. **P1-5 / P1-6 / P1-7** — resource-leak cluster (browser pool, EventBus TTL, terminal WS).
4. **P1-4 / P1-10** — backend perf + logging hygiene.
5. **P2-4** — ErrorBoundary (cheap, high resilience payoff).
