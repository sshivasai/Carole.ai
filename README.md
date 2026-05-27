# Carole.ai 🚀

Carole.ai is a next-generation collaborative multi-agent platform designed to simulate a fully autonomous, highly skilled engineering and operations team. 

Operating through a modern, glass-morphic Web UI, human users can collaborate directly with customizable AI agents (ReACT, Utility Bots, and Judge AI) inside a shared, real-time group chat environment. Agents can write code, surf the web, participate in virtual meetings, and dynamically learn from their mistakes over time.

---

## 🏗️ High-Level Architecture

Carole.ai is split into a robust, event-driven backend and a highly responsive frontend.

- **Backend (Agent Engine):** Python, FastAPI, and WebSockets.
- **Frontend (Web UI):** Next.js (React) and Vanilla CSS for a premium, high-performance user experience.
- **Database & Memory:** PostgreSQL enhanced with `pgvector` for semantic long-term memory and retrieval.
- **Communication:** A bi-directional asynchronous `EventBus` that streams agent thoughts, tool execution, and live browser captures directly to the UI.

---

## 🤖 The Multi-Agent Ecosystem

The platform orchestrates multiple types of agents, each with specific roles, permissions, and toolsets:

1. **Coordinator Agent:** The primary interface that communicates with the human user. It breaks down complex requests into sub-tasks and delegates them to specialized workers. It synthesizes results but *never delegates understanding*.
2. **Worker Agents:** Specialized in pure execution (e.g., Code Reviewer, Researcher). They operate on isolated contexts to prevent token bloat and communicate back via the `<task-notification>` protocol.
3. **Judge AI:** A passive, invisible guardian that monitors the EventBus. It detects hallucinations, provides real-time coaching, and autonomously approves "Judge-Approvable" tool executions.
4. **Utility Bots:** Lightweight, specialized bots (e.g., Meeting Summarizer, Daily Emailer) designed for micromanagement and automation.

---

## 🧠 Hierarchical Memory System

Carole.ai moves away from flat file memory in favor of a robust database architecture:

- **Short-Term Memory:** Standard relational tables holding active chat logs and threads.
- **Working Memory:** Fast JSONB scratchpads where active agents store in-progress states and thoughts.
- **Long-Term Memory (The "Lessons Learned" Ledger):** The background `AutoDreamWorker` periodically summarizes completed tasks and mistakes, embedding them into `pgvector`. Agents query this ledger before beginning new tasks to proactively avoid past errors.

---

## 🛠️ The 40+ Tool Ecosystem

Agents are empowered with an extensive suite of specialized tools, gated by configurable Team Permissions (Safe, Judge-Approvable, Human-Only).

- **File & Shell Operations:** `FileRead`, `FileWrite`, `FileEdit`, `Glob`, `Bash`, `REPL`. Secure, sandboxed execution with live stdout streaming.
- **Git Workflows:** `GitCommit`, `GitPush`, `GitDiff`, `GitStatus`. Agents can branch, commit, and push PRs autonomously.
- **Browser Automation:** Headless Chromium via **Playwright**. Agents can surf the web while the backend streams live screenshots of their viewport directly into the chat UI.
- **Voice & Meetings:** Integration with STT (e.g., Deepgram) and TTS (e.g., ElevenLabs) APIs allows agents to join Google Meet/Zoom calls, listen to conversations, and speak out loud.
- **Dynamic Expansion:** Seamlessly connect to external Model Context Protocol (MCP) servers for on-the-fly capability expansion.

---

## 🚀 Setup & Execution (Coming Soon)

*(Instructions for initializing the PostgreSQL database, installing Python dependencies for the backend, and running the Next.js development server will be added here once implementation is complete.)*
