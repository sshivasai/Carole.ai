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
- [x] **Browser**: Integrate Headless Playwright Chromium with screenshot capturing to the EventBus.
- [x] **Voice**: OpenAI Whisper STT + OpenAI TTS-1 implemented in `voice_stt_tts.py`.
- [x] **Interaction**: `ask_user` (blocks agent, human replies via REST) and `sleep` tools.
- [x] **Coordination**: Implement `AgentTool` (Spawn) and `SendMessageTool` (Continue).

## 4. Multi-Model Orchestrator & Agent Engine
- [x] Build `MultiModelRouter` to route requests to Claude 3.5, GPT-4o-mini, and Qwen dynamically.
- [x] Build prompt-assembly engine (incorporating system prompts, active learnings from DB, and tool rules).
- [x] Implement the core `ReACT` Thought-Action-Observation loop.
- [x] Build `MessageRouter` with @mention parsing, DB persistence, and async agent triggering.
- [x] Build Human-In-The-Loop approval API endpoint (`POST /api/tools/approve/{tx_id}`).
- [x] Implement the `<task-notification>` XML protocol for Worker-to-Coordinator communication.

## 5. Specialized Agents & Roles
- [x] **Coordinator Agent**: CoordinatorAgent with team roster injection, task tracking, and worker notification collection.
- [x] **Worker Agents**: ReACTAgent with parent_coordinator_id and task-notification emission.
- [x] **Judge AI**: LLM-powered tool safety evaluator wired into ToolExecutor judge gate.
- [x] **Utility Bots**: MeetingTool (transcribe, notes, TTS) wired with VoiceService.

## 6. Web Interface (Next.js/React)
- [x] Build Team Creation & Agent Configuration UI (sidebar Add Agent form with role/model pickers).
- [x] Build the main Chat Interface with `@name` and `/@name` mentions.
- [x] Implement real-time typing indicators and tool-execution streaming.
- [x] Build the "Live Browser View" component to render Playwright screenshots in-chat.

## 7. Polish & Verification
- [x] Create `frontend/src/lib/types.ts` (was missing — frontend would not compile).
- [x] Fix `auto_dream.py` pgvector NULL comparison (`== None` → `.is_(None)`).
- [x] Add `POST /api/agent/answer/{question_id}` endpoint + frontend question card UI.
- [x] Add `GET /api/messages/search/{team_id}` semantic pgvector search endpoint.
- [x] Add `POST /api/audio/transcribe/{team_id}` Whisper transcription upload endpoint.
- [ ] End-to-end test of the "Lessons Learned" feedback loop.
- [ ] End-to-end test of a Coder agent writing and pushing to GitHub.
- [ ] Verify Voice Meeting integration.
