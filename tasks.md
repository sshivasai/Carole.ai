# Execution Tasks: Carole.ai Platform

## 1. Foundation & Infrastructure
- [x] Setup Next.js monolithic repository structure.
- [x] Initialize PostgreSQL database with `pgvector` extension.
- [x] Implement robust WebSocket `EventBus` for real-time bi-directional communication.
- [x] Add `__init__.py` package files for all Python modules.
- [x] Fix `.env` credentials to match `docker-compose.yml`.
- [x] Fix `docker-compose.yml` healthcheck user mismatch.
- [x] Add CORS middleware for frontend-backend communication.

## 2. Memory & Database Layer
- [x] Create schema for `Users`, `Projects`, `Teams`, and `Agents`.
- [x] Create schema for `messages` (Short-Term Memory with vector embeddings).
- [x] Create `learnings` table in `pgvector` for the "Lessons Learned" ledger.
- [x] Implement `working_memory` JSONB scratchpads for active agents.
- [x] Build the background "Dream" worker to auto-consolidate logs into semantic embeddings.

## 3. The Core Tool Suite
- [x] Implement `ToolExecutor` with Team-level permission gating (Safe, Judge-Approvable, Human-Only).
- [x] **Filesystem**: Implement `file_tools.py` (Safe sandboxing / Workspace locked).
- [x] **Shell**: Implement `shell_tools.py` (Asynchronous streaming process execution).
- [x] **Git**: Implement `git_tools.py` (status, diff, add, commit, log, checkout, push).
- [x] **Web Research**: Implement `web_tools.py` (Tavily search + URL text extraction).
- [ ] **Browser**: Integrate Headless Playwright Chromium with screenshot capturing to the EventBus.
- [ ] **Voice**: Integrate STT (Speech-to-Text) and TTS (Text-to-Speech) APIs for meeting participation.
- [ ] **Coordination**: Implement `AgentTool` (Spawn) and `SendMessageTool` (Continue).

## 4. Multi-Model Orchestrator & Agent Engine
- [x] Build `MultiModelRouter` to route requests to Claude 3.5, GPT-4o-mini, and Qwen dynamically.
- [x] Build prompt-assembly engine (incorporating system prompts, active learnings from DB, and tool rules).
- [x] Implement the core `ReACT` Thought-Action-Observation loop.
- [x] Build `MessageRouter` with @mention parsing, DB persistence, and async agent triggering.
- [x] Build Human-In-The-Loop approval API endpoint (`POST /api/tools/approve/{tx_id}`).
- [ ] Implement the `<task-notification>` XML protocol for Worker-to-Coordinator communication.

## 5. Specialized Agents & Roles
- [ ] **Coordinator Agent**: The primary interface that synthesizes plans and manages workers.
- [ ] **Worker Agents**: Specialized in execution without delegating understanding.
- [ ] **Judge AI**: Passively monitors `EventBus`, detects hallucinations, provides real-time coaching, and autonomously approves safe tools.
- [ ] **Utility Bots**: Implement the Meeting Assistant (consumes STT, produces notes) and Daily Email/Summarizer bots.

## 6. Web Interface (Next.js/React)
- [ ] Build Team Creation & Agent Configuration UI (Assigning models, roles, tool permissions).
- [ ] Build the main Chat Interface with `@name` and `/@name` mentions.
- [ ] Implement real-time typing indicators and tool-execution streaming.
- [ ] Build the "Live Browser View" component to render Playwright screenshots in-chat.

## 7. Polish & Verification
- [ ] End-to-end test of the "Lessons Learned" feedback loop.
- [ ] End-to-end test of a Coder agent writing and pushing to GitHub.
- [ ] Verify Voice Meeting integration.
