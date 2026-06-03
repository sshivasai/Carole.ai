# Carole.ai Project Documentation

## Master Architectural Document

Carole.ai is designed as a modular, scalable, and highly context-aware AI assistant system. This document outlines the core architectural components and their interplay.

### 1. Hybrid GraphRAG

The memory and context retrieval system of Carole.ai relies on a custom Hybrid GraphRAG architecture. It fuses multiple retrieval mechanisms to ensure the AI has precise and broad context simultaneously.

- **Dense Retrieval (pgvector)**: Uses embedding-based cosine similarity to find semantically related memories, code snippets, and conversational history.
- **Sparse Retrieval (ts_rank)**: Utilizes traditional keyword-based text search with term frequency-inverse document frequency ranking to ensure exact matches are not lost in vector space.
- **Code Graph (networkx)**: A real-time, dynamically updated representation of the codebase. It maps dependencies, function calls, and file relationships, providing the LLM with structural awareness of the project.

This triad ensures that memory retrieval is both semantically rich and structurally accurate.

### 2. Zero-Cost Meeting Integration

Carole.ai integrates with virtual meetings without relying on expensive official API bots. 

- **Playwright DOM Scraping**: The system uses headless (or headed) browser automation via Playwright to join Google Meet sessions. It scrapes live captions directly from the DOM, providing a real-time transcription feed to the agent.
- **Native Chat Injection**: The agent can respond and interact within the meeting by injecting messages natively into the Google Meet chat interface via DOM manipulation.

### 3. MCP Expansion (Model Context Protocol)

To maintain flexibility and security when integrating various models and tools, Carole.ai employs an expanded MCP architecture.

- **Dynamic ToolRegistry**: Tools are registered dynamically, allowing plugins and external scripts to be loaded at runtime without core system modifications.
- **Universal MCP Firewall**: A strict validation and permission layer that sits between the LLM and the ToolRegistry. It ensures that any code execution, file modification, or API call requested by the model is authenticated, authorized, and safe to execute, preventing malicious or runaway actions.

### 4. Native Real-Time Kanban

Project management is built directly into the agent's workflow.

- **EventBus-Driven Updates**: The backend utilizes an EventBus architecture to broadcast state changes instantly.
- **Split-Screen Interface**: The frontend features a native Kanban board that operates alongside the chat interface. When the agent plans tasks or updates progress, the EventBus pushes these changes via WebSockets to the React frontend, updating the Kanban board in real-time without requiring a page refresh.

---
*End of Document*
