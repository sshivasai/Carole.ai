# Execution Tasks: Carole.ai Platform

## 1. Foundation & Infrastructure
- [x] Setup Next.js monolithic repository structure.
- [x] Initialize PostgreSQL database with `pgvector` extension.
- [x] Implement robust WebSocket `EventBus` for real-time bi-directional communication.

## 2. Memory & Database Layer
- [x] Create schema for `Teams`, `Agents`, and `Users`.
- [x] Create schema for `conversations` and `messages` (Short-Term Memory).
- [ ] Implement `working_memory` JSONB scratchpads for active agents.
- [x] Create `learnings` table in `pgvector` for the "Lessons Learned" ledger.
- [ ] Build the background "Dream" worker to auto-consolidate logs into semantic embeddings.

## 3. The Core Tool Suite
- [ ] Port existing `core/tools` into the new architecture.
- [ ] Implement `ToolExecutor` with Team-level permission gating (Safe, Judge-Approvable, Human-Only).
- [ ] **File & Shell**: Implement `Bash`, `FileRead`, `FileWrite`, `FileEdit`, `Glob`, `Grep`.
- [ ] **Git**: Implement `GitCommit`, `GitPush`, `GitDiff`.
- [ ] **Voice**: Integrate STT (Speech-to-Text) and TTS (Text-to-Speech) APIs for meeting participation.
- [ ] **Browser**: Integrate Headless Playwright Chromium with screenshot capturing to the EventBus.
- [ ] **Coordination**: Implement `AgentTool` (Spawn) and `SendMessageTool` (Continue).

## 4. Multi-Model Orchestrator & Agent Engine
- [ ] Build `MultiModelRouter` to route requests to Claude 3.5, GPT-4o-mini, and Qwen dynamically.
- [ ] Build prompt-assembly engine (incorporating system prompts, active learnings from DB, and tool rules).
- [ ] Implement the core `ReACT` Thought-Action-Observation loop.
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
