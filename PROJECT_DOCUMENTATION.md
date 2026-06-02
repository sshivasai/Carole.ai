# Carole.ai Project Documentation

## 1. Executive Summary & Core Purpose

**Carole.ai** is a next-generation, collaborative multi-agent platform meticulously designed to simulate a fully autonomous, highly skilled engineering and operations team. Operating through a modern, glass-morphic Web UI, human users can collaborate directly with a spectrum of customizable AI agents within a shared, real-time group chat environment.

The primary objective of Carole.ai is to transcend standard single-agent chat paradigms by establishing a dynamic multi-agent ecosystem. These agents can write and review code, perform complex web research, execute terminal commands, participate in virtual meetings, and dynamically learn from their mistakes over time. By combining advanced Large Language Model (LLM) orchestration with an asynchronous EventBus and a robust PostgreSQL-backed hierarchical memory system, Carole.ai provides a continuous, highly observable, and intelligent software development lifecycle.

---

## 2. High-Level Architectural Overview

Carole.ai is partitioned into a resilient, event-driven backend and a highly responsive, high-performance frontend.

### 2.1 Backend Architecture (Agent Engine)
- **Framework & Language:** Python leveraging FastAPI for RESTful endpoints.
- **Communication Layer:** Bi-directional asynchronous `EventBus` using WebSockets. This streams agent thoughts, tool execution progress, and live browser captures directly to the UI.
- **Multi-Model Routing:** A `MultiModelRouter` dynamically routes requests to various LLM providers (e.g., Claude 3.5, GPT-4o-mini, Qwen) based on task complexity and agent role.
- **Tool Execution Engine:** A comprehensive `ToolExecutor` that manages over 40+ specialized tools gated by configurable Team Permissions (Safe, Judge-Approvable, Human-Only).

### 2.2 Frontend Architecture (Web UI)
- **Framework:** Next.js (React) utilizing TypeScript.
- **Styling:** Vanilla CSS tailored for a premium, glass-morphic user experience.
- **Core Components:** Real-time Chat Interface, Live Browser View (for rendering streamed Playwright screenshots), and Team/Agent Configuration dashboards.

### 2.3 Database & Memory Persistence
- **RDBMS:** PostgreSQL serving as the foundational state store.
- **Vector Database:** Integration with `pgvector` for semantic long-term memory, enabling similarity searches over historical chat logs and "Lessons Learned".
- **ORM:** SQLAlchemy (Async) with Alembic for migrations.

---

## 3. Unique Value Proposition

Carole.ai significantly differentiates itself functionally and technically from standard agent approaches through the following key innovations:

### 3.1 The Hierarchical Memory System (Continuous Learning)
Most AI platforms rely on stateless, flat-file contexts. Carole.ai introduces a tri-layered memory architecture:
1. **Short-Term Memory:** Relational tables holding active, real-time chat logs and threads.
2. **Working Memory:** Fast JSONB scratchpads where active agents store in-progress states, task metadata, and intermediate thoughts.
3. **Long-Term Memory ("Lessons Learned" Ledger):** A background worker (`AutoDreamWorker`) periodically summarizes completed tasks, extracts actionable lessons and rules, and embeds them into `pgvector`. Agents query this ledger before commencing new tasks, allowing the system to genuinely learn from its mistakes and self-correct over time.

### 3.2 True Multi-Agent Orchestration
Instead of a monolithic agent attempting to perform all tasks linearly, Carole.ai simulates a real engineering team:
- **Coordinator Agent:** The primary human interface. It breaks down complex requests, delegates sub-tasks to workers, and synthesizes results. Crucially, the coordinator *never delegates understanding*.
- **Worker Agents:** Isolated execution specialists (e.g., Coder, Reviewer) that perform pure tasks to prevent token bloat, communicating via a structured `<task-notification>` XML protocol.
- **Judge AI:** A passive, invisible guardian monitoring the `EventBus` that intercepts hallucinations, provides real-time coaching, and autonomously approves or denies potentially dangerous tool executions based on risk assessment.
- **Utility Bots:** Specialized, lightweight bots designated for precise micromanagement tasks like meeting summarization.

### 3.3 Multi-Modal Environmental Interaction
Carole.ai agents are not trapped in a text box. They interact with the external world vividly:
- **Live Browser Streaming:** Using headless Playwright (Chromium), agents surf the web while the backend streams live screenshots of their viewport directly into the chat UI for human observation.
- **Voice & Meeting Participation:** Utilizing STT (Speech-to-Text via Whisper) and TTS (Text-to-Speech via OpenAI), agents can actively "listen" to virtual meetings and "speak" responses, bridging the gap between text-based bots and active team participants.

---

## 4. Current State of Implementation

The core foundation and primary feature sets of Carole.ai have been successfully built and integrated. The current state reflects a highly functional prototype nearing production readiness.

### 4.1 Completed Infrastructure & Core Systems
- **Next.js Frontend & FastAPI Backend:** Fully established repository structure, CORS configurations, and containerization (`docker-compose.yml`).
- **PostgreSQL & pgvector:** Database initialized with comprehensive schemas (`Users`, `Projects`, `Teams`, `Agents`, `Messages`, `Learnings`, `Tasks`).
- **EventBus:** Robust WebSocket implementation for real-time bi-directional messaging, capable of handling `@name` group broadcasts and `/@name` direct messages.

### 4.2 Completed Agent Engine & Tooling
- **ReACT Loop & Routing:** Full implementation of the Thought-Action-Observation loop, `MultiModelRouter`, and prompt-assembly engine incorporating active learnings.
- **Agent Roles:** `CoordinatorAgent`, `ReACTAgent` (Workers), and `JudgeEvaluator` are fully operational and integrated with the `<task-notification>` communication protocol.
- **Tool Suite (`ToolExecutor`):** Successfully implemented filesystem operations (sandboxed), shell command execution (async streaming), Git workflows, web research (Tavily), browser automation (Playwright), and Voice integrations (STT/TTS).
- **Background Processes:** The `AutoDreamWorker` is fully implemented and successfully extracts and embeds lessons into the database.

### 4.3 Completed Web Interface
- **Chat Experience:** Real-time typing indicators, tool-execution streaming, and semantic pgvector search capabilities.
- **Agent Management:** Sidebar UI for team creation, agent configuration, and role/model assignments.
- **Observability:** "Live Browser View" component rendering headless browser sessions in real-time.

---

## 5. Roadmap & Technical Debt (Pending Features)

While the architecture is heavily solidified, the following integrations, end-to-end validations, and technical debt require resolution to reach full production maturity.

### 5.1 End-to-End Validation & Testing
- **Lessons Learned Feedback Loop:** Comprehensive end-to-end testing is required to verify that the `AutoDreamWorker`'s extracted lessons are actively retrieved and successfully influence an agent's future decision-making process in subsequent chat threads.
- **Autonomous Git Workflows:** End-to-end validation of a Coder agent autonomously writing, reviewing, committing, and pushing code to a remote GitHub repository.
- **Voice Meeting Verification:** Live environment testing of the STT/TTS integration to ensure agents can successfully join a virtual meeting (Google Meet/Zoom), transcribe audio in real-time, and synthetically speak back into the call.

### 5.2 Pending Features & Developer Experience
- **Setup & Execution Documentation:** The `README.md` is currently missing concrete instructions for initializing the PostgreSQL database, installing Python dependencies, and running the development servers.
- **Model Context Protocol (MCP) Expansion:** Although planned in the architecture, dynamic on-the-fly capability expansion via external MCP servers requires further robust implementation and testing.
- **Comprehensive Unit Testing:** The test suite (`backend/tests/`) requires expansion to increase coverage across multi-agent concurrent interactions, ensuring race conditions are mitigated in the `working_memory` and `EventBus`.

### 5.3 Technical Debt
- **Error Recovery Chains:** Refinement of LLM error handling (e.g., token limit breaches, API timeouts). The system requires a more robust fallback mechanism comparable to advanced context-compaction strategies to maintain stability during prolonged agent tasks.
- **Database Indexing:** As the `messages` and `learnings` tables grow, performance tuning and proper index optimization on PostgreSQL vector columns will be necessary to ensure real-time query latency remains low.

---

## 6. Conclusion

Carole.ai stands as an ambitious and technically sophisticated multi-agent platform. By tightly coupling an event-driven architecture, hierarchical memory consolidation, and distinct multi-agent orchestration, the system reliably mimics human team dynamics. Addressing the pending end-to-end testing and system documentation will solidify Carole.ai as a premier, production-ready solution in the autonomous AI engineering space.