# Implementation Plan: Group Chat Multi-Agent Platform

## Goal Description

Build a collaborative, Web UI-based application where customizable AI agents (ReACT, Utility Bots) work simultaneously on tasks alongside human users. Communication supports group broadcasts (`@name`) and private direct messages (`/@name`). A background "Judge AI" continuously provides real-time feedback, and a robust **PostgreSQL** memory system ensures long-term context retention and continuous learning. Agents can perform complex real-world tasks including writing/reviewing code via Git, browsing the web via headless Playwright, and even joining virtual meetings using Voice (STT/TTS) integrations.

## Proposed Architecture & Changes

### 1. Context, Memory Persistence & PostgreSQL
We will use **PostgreSQL + pgvector** as the foundational database for all state.
- **Short-Term Context (Chat History)**: Stored in standard relational tables.
- **Working Memory (Task Scratchpad)**: Active tasks stored in a `working_memory` JSONB column.
- **Long-Term Memory (Semantic)**: Chat summaries, completed code files, and key decisions are embedded and stored in `pgvector`.
- **Memory Consolidation**: A background "Dream" worker summarizes raw logs into canonical knowledge.

### 2. Feedback Loops, Corrections, & Learnings
- **Real-Time Feedback (Judge AI)**: The Judge AI monitors the `EventBus` to intercept hallucinations or incorrect tool usage and provides real-time coaching.
- **The "Lessons Learned" Ledger**: Mistakes and corrections are summarized as rules and embedded into `pgvector`.
- **Future Application**: Agents query the `learnings` table before starting a task to apply past lessons to new situations.

### 3. Voice, Meetings & Browser Automation
- **Meeting Participation**: Agents can join meetings using Browser Automation or WebRTC APIs. 
  - *Hearing*: Speech-to-Text (STT) models (e.g., Deepgram/Whisper) transcribe meeting audio and pipe it into the `EventBus`.
  - *Speaking*: Text-to-Speech (TTS) models (e.g., ElevenLabs/OpenAI) allow agents to speak their text responses out loud into the meeting.
- **Browser Automation**: We use headless **Playwright** (Chromium). While running invisibly on the backend, the browser will periodically send screenshots over the WebSocket `EventBus` so humans can watch the agents surf the web live in the Web UI.
- **Git Workflows**: Complete parity with advanced agent Git tools allowing Coder agents to `GitCommit` and `GitPush`, while Reviewer agents use `GitDiff` and `FileEdit` to review and amend code.

### 4. Comprehensive Tool Suite
Managed via our `ToolExecutor` with configurable team permissions (Safe, Judge-Approvable, Human-Only).
- **File & Code**: `FileRead`, `FileWrite`, `FileEdit`, `Glob`, `Grep`, `NotebookEdit`
- **Execution & Shell**: `Bash`, `PowerShell`, `REPL`
- **Web & External**: `WebSearch`, `WebFetch`, `MCPTool` (Dynamic Tool Expansion)
- **Task & Workflow**: `TaskCreate`, `TaskList`, `TaskUpdate`, `ScheduleCron`, `RemoteTrigger`
- **Development**: `LSPTool`, `AgentTool` (Spawn sub-agents), `BriefTool`
- **Git**: `GitCommit`, `GitPush`, `GitDiff`, `GitStatus`

### 5. Core System & Orchestration
- **Dynamic Model Selection**: Agents use configurable models (e.g. Sonnet, 4o-mini, Qwen) routed dynamically via API providers.
- **`MessageRouter` & `EventBus`**: Handles `@name` and `/@name` routing concurrently using WebSockets.
- **Utility Bots**: Specialized bots for summarization, email drafting, and meeting transcription.

## Verification Plan
- **Persistence Test**: Shut down PostgreSQL, bring it back up, and ensure agents retain their "Lessons Learned" and chat history.
- **Browser Streaming Test**: Assign an agent to summarize a Wikipedia page and verify that screenshots of the headless browser stream successfully to the chat UI.
- **Git Workflow Test**: Have a Coder agent write a script and a Reviewer agent approve and push it to a test branch.
