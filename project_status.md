# Carole.ai — Project Status Document

> Last updated: May 31, 2026

---

## 🎯 What Was Expected (Full Scope)

The goal was to build a **production-ready multi-agent AI platform** with:

1. Multi-tenant org structure (User → Project → Team → Agent)
2. A creative visual playground UI (org bubbles → project satellites → team conference table with bot avatars)
3. Custom agent creation with dynamic model selection, roles, skills, and instructions
4. Real-time group chat with @mention routing
5. Agent ReACT loop (Thought → Action → Observation) with streaming
6. Multi-model LLM routing (Claude, GPT, Gemini, Qwen)
7. Semantic long-term memory (pgvector)
8. Full tool suite (filesystem, shell, git, web, browser, coordination, tasks)
9. Human-in-the-loop approval gates for dangerous tools
10. Background Dream worker for memory consolidation
11. Knowledge base / learnings management
12. Voice + meeting integration (Whisper STT, OpenAI TTS)
13. Plugin system for custom tools

---

## ✅ What Is Done

### 🏗️ Infrastructure & Database
- [x] Next.js 15 + FastAPI monorepo structure
- [x] PostgreSQL with pgvector extension
- [x] Multi-tenant schema: `users → projects → teams → agents → messages → tasks → learnings`
- [x] Agent columns: `name, role, model, system_prompt, personality, custom_instructions, skills, tool_permissions, working_memory`
- [x] Message columns: `sender_id, sender_name, recipient_id, text, embedding` (pgvector)
- [x] `FORCE_DB_RECREATE` env flag for dev schema migration
- [x] Async SQLAlchemy session management + FastAPI dependency injection
- [x] Docker Compose with health checks

### 🤖 Agent Engine
- [x] **ReACT loop** — Thought → Action → Observation streaming
- [x] **Conversation history** — agents load last 20 messages from DB (context continuity)
- [x] **LLM retry/backoff** — 3 attempts with exponential backoff on API errors
- [x] **Agent status events** — `active`, `executing_tool`, `idle` broadcast to UI
- [x] **CoordinatorAgent** — delegates to workers, collects `<task-notification>` XML responses, synthesizes results
- [x] **Worker-to-Coordinator protocol** — `<task-notification>` XML with task_id, agent, status, result
- [x] **Semantic memory recall** — loads top 3 relevant learnings from pgvector before each loop
- [x] **MessageRouter** — parses `@name` and `/@name` (private) mentions, routes to correct agent

### 🧠 Multi-Model LLM Router
- [x] **Anthropic Claude** — Streaming via SSE (`claude-3-5-sonnet`, `claude-sonnet-4`, `claude-opus-4`, etc.)
- [x] **OpenAI GPT** — Streaming (`gpt-4o`, `gpt-4o-mini`, `o1`, `o3`, `o4-mini`)
- [x] **Google Gemini** — Streaming via SSE (`gemini-2.0-flash`, `gemini-2.5-pro`, etc.)
- [x] **Qwen** — OpenAI-compatible endpoint (DashScope or local)
- [x] **Retry/backoff** — Handles 429 rate limits and 5xx errors across all providers
- [x] **OpenAI Embeddings** — `text-embedding-3-small` (1536 dimensions)
- [x] **Gemini Embeddings fallback** — `text-embedding-004` (zero-padded to 1536)
- [x] **Zero-vector fallback** — when no API key configured, returns `[0.0] * 1536`

### 🛠️ Tool Suite (30 tools total)

| Category | Tools | Status |
|----------|-------|--------|
| Filesystem | `read_file`, `write_file`, `edit_file`, `append_file`, `list_directory`, `delete_file` | ✅ |
| Search | `grep_search`, `glob_search` | ✅ |
| Shell | `execute_command` (streaming stdout/stderr) | ✅ |
| Git | `git_status`, `git_diff`, `git_add`, `git_commit`, `git_log`, `git_checkout`, `git_push` | ✅ |
| Web | `web_search` (Tavily), `web_fetch` | ✅ |
| Browser | `browser_navigate`, `browser_screenshot`, `browser_click`, `browser_type`, `browser_extract_text` | ✅ |
| Coordination | `spawn_agent`, `send_message` | ✅ |
| Tasks | `create_task`, `list_tasks`, `update_task` | ✅ |
| Interaction | `ask_user` (blocks + waits for human reply), `sleep` | ✅ |

- [x] **Permission gating** — `safe` (instant), `judge` (LLM review), `human` (approval required)
- [x] **Judge AI** — LLM evaluates dangerous tool requests before execution
- [x] **Human-in-the-loop** — `POST /api/tools/approve/{tx_id}` REST endpoint
- [x] **Plugin system** — `@carole_tool` decorator + hot-reload from `/plugins/` directory
- [x] **File diff streaming** — writes/edits emit unified diffs to EventBus for live UI display

### 📡 Real-time Communication
- [x] **EventBus** — asyncio pub/sub with 100-event history buffer per topic
- [x] **WebSocket** — `/ws/chat/{team_id}` endpoint with reconnect support
- [x] **Event types**: `message`, `thought_delta`, `tool_start`, `tool_end`, `file_change`, `agent_status`, `typing`, `approval_request`, `agent_question`, `shell_output`, `browser_screenshot`, `task_update`, `transcription`, `meeting_notes`, `agent_audio`

### 🗄️ REST API
- [x] `POST/GET /api/users`, `DELETE /api/users/{id}`
- [x] `POST/GET /api/projects`, `GET /api/projects/single/{id}`, `DELETE /api/projects/{id}`
- [x] `POST /api/teams`, `GET /api/teams/{project_id}`, `GET /api/teams/single/{id}`, `DELETE /api/teams/{id}`
- [x] `POST/GET /api/agents/{team_id}`, `PUT /api/agents/{id}`, `DELETE /api/agents/{id}`
- [x] `GET /api/messages/{team_id}`, `GET /api/messages/search/{team_id}` (semantic vector search)
- [x] `POST/GET /api/tasks/{team_id}`, `PUT /api/tasks/{id}`
- [x] `GET /api/tools` (dynamic tool registry list)
- [x] `POST /api/tools/approve/{tx_id}` (human approval gate)
- [x] `POST /api/agent/answer/{question_id}` (answer agent's `ask_user`)
- [x] `POST /api/audio/transcribe/{team_id}` (Whisper STT upload)
- [x] `POST /api/learnings`, `GET /api/learnings/{project_id}`
- [x] `POST /api/seed` (demo data bootstrapping)

### 🧠 Memory System
- [x] **Short-term memory** — messages table with pgvector embeddings
- [x] **Long-term memory** — learnings table with semantic embeddings
- [x] **Dream Worker** — background task (every 15 min) consolidates conversation logs into learnings
- [x] **Semantic search** — cosine distance search over pgvector for message recall and lesson retrieval
- [x] **Working memory** — JSONB scratchpad per agent for active task state

### 🎨 Frontend / UI
- [x] **Visual Playground Canvas** — 2D interactive board with three drill-down levels
  - Level 1: Floating org bubbles (tenants)
  - Level 2: Project satellite cards with animated SVG connector lines
  - Level 3: Glassmorphic oval conference table with bot avatars positioned trigonometrically
- [x] **Agent hover cards** — frosted-glass overlays showing role, model, skills
- [x] **Slide-out console drawer** — right-panel showing chat, tasks, file diffs, memory ledger
- [x] **WebSocket hook** — auto-reconnect, event streaming, `thought_delta` aggregation
- [x] **API client** — full REST coverage with typed methods
- [x] **TypeScript types** — `AgentConfig`, `TaskItem`, `WSEvent`, `ChatMessage`, `LearningItem`, `ProjectItem`, `TeamItem`, `UserItem`

### 🎤 Voice & Meeting
- [x] `voice_stt_tts.py` — OpenAI Whisper STT + TTS-1 synthesis
- [x] `meeting_tool.py` — transcribe audio, generate structured meeting notes (LLM), TTS agent voice
- [x] `browser_pool.py` — Playwright Chromium per-agent isolated contexts

---

## 🔴 What Is Pending

### High Priority
- [ ] **Alembic migrations** — currently using `FORCE_DB_RECREATE` (drops data). Need proper versioned migrations for production
- [ ] **Authentication** — no login/signup. The API has no auth guards. Anyone can access any tenant's data
- [ ] **WebSocket auth** — WS connections are unauthenticated
- [ ] **End-to-end test suite** — no automated tests exist

### Medium Priority
- [ ] **Agent drag-and-drop** — moving agents between teams via the playground UI
- [ ] **Avatar customization** — agent avatar skins/colors in the conference table
- [ ] **Role template library** — pre-built roles (Senior Dev, QA, Designer) that auto-fill skills/prompt when selected in the agent creation form
- [ ] **Live agent status badge** on conference table avatars (connected to `agent_status` WebSocket events)
- [ ] **Task Kanban board** — visual drag-and-drop board for tasks in the console drawer
- [ ] **File diff viewer** — proper syntax-highlighted diff display in the console drawer
- [ ] **Browser live view** — render Playwright screenshots in the chat as a live widget

### Low Priority / Future
- [ ] **Git PR creation** — push a branch and open a GitHub PR automatically
- [ ] **Multi-user real-time** — multiple human users in the same team room simultaneously
- [ ] **Agent marketplace** — share/publish custom agent templates
- [ ] **Cost tracking** — token usage and cost per agent/project
- [ ] **Webhook integrations** — Slack, Linear, GitHub event triggers
- [ ] **Local LLM support** — Ollama integration for fully offline agents
- [ ] **Knowledge file upload** — drag-and-drop PDFs/docs into a project knowledge base

---

## 📊 Feature Completion Summary

| Area | Expected | Done | Pending |
|------|----------|------|---------|
| Database schema | 7 tables | 7 ✅ | Migrations |
| LLM providers | 4 (Claude, GPT, Gemini, Qwen) | 4 ✅ | — |
| Tool suite | 49 (inventory doc) | 30 ✅ | 19 (code analysis, advanced search) |
| REST API endpoints | ~25 | 24 ✅ | — |
| Agent ReACT loop | Full loop | ✅ | — |
| Coordinator pattern | Multi-worker | ✅ | — |
| Memory (short+long term) | Both | ✅ | — |
| Dream consolidation | Auto-background | ✅ | — |
| Real-time WebSocket | Full event bus | ✅ | Multi-user |
| Visual Playground UI | 3-level canvas | ✅ | Drag-and-drop |
| Authentication | Login/JWT | ❌ | Full auth system |
| Voice/Meeting | STT+TTS | ✅ | WebRTC live join |
| Plugin system | Decorator + hot-load | ✅ | Plugin marketplace |
| Tests | Unit + e2e | ❌ | Full test suite |

**Overall: ~75% complete** toward a production-ready system. Core agent infrastructure is solid. Main gaps are auth, migrations, and UI polish.
