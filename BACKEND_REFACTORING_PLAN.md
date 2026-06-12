# Backend Architectural Refactoring Plan

## 1. Architectural Analysis (Current State)

### Logical Flow & Structure
The current backend is a FastAPI application orchestrating real-time AI agents. The workflow follows:
1. **Entrypoints:** WebSockets handle bidirectional communication (`EventBus`), while REST APIs manage CRUD and human approvals.
2. **Routing:** `MessageRouter` parses incoming text, resolves `@mentions`, and triggers target Agents as background `asyncio.create_task` jobs.
3. **Agent Loop:** The core `ReACTAgent` implements a custom Thought-Action-Observation `while`-loop, calling LLMs and executing tools until completion.
4. **Tools & Execution:** The `ToolExecutor` gates operations via permissions (safe, judge, human) and maps string-based actions to registered callbacks.
5. **Background Workers:** An `AutoDreamWorker` periodically runs an infinite loop `asyncio.sleep()` mechanism to consolidate conversation memory into LanceDB.

### Key Architectural Smells
- **Fragile In-Memory State:** Human-in-the-loop approvals rely on global memory dictionaries (`pending_approvals: Dict[str, asyncio.Event]`). If the server restarts, pending approval states are permanently lost, and blocking agent loops crash.
- **Unbounded Task Spawning:** Using `asyncio.create_task` for long-running Agent loops lacks durability. There is no job queue, meaning crashes cause total data loss of the current execution state, and high load will lead to Out-Of-Memory (OOM) failures.
- **Regex-Based Tool Parsing:** The `ReACTAgent` extracts tools using custom string matching (`[ACTION]tool(args)[/ACTION]`). This is outdated and brittle compared to modern API-enforced structured outputs.
- **Reinventing the Wheel:** The `MultiModelRouter` hand-rolls SSE parsing and retry logic for different LLM providers instead of leveraging robust community standards. Inefficient HTTP client usage exists (instantiating `httpx.AsyncClient` dynamically per request).
- **Monolithic Singletons:** The heavy reliance on global singletons (`event_bus`, `tool_executor`, `message_router`, `llm_router`) violates SOLID dependency inversion, severely complicating unit testing and preventing horizontal scaling (e.g., the `EventBus` only works on a single backend instance).

---

## 2. Competitive Industry Analysis

When benchmarking Carole.ai against industry-standard frameworks like **LangGraph**, **CrewAI**, or **AutoGen**, several high-value feature gaps emerge:

| Feature Area | Industry Standard (LangGraph/CrewAI) | Current Carole.ai Implementation |
| :--- | :--- | :--- |
| **Workflow State** | Graph-based Directed Acyclic Graphs (DAGs) allowing state checkpoints, rewinds, and pause/resume logic. | Imperative Python `while` loops containing tightly coupled text generation and parsing. |
| **Tool Calling** | Native JSON Schema Function Calling (OpenAI spec) inherently supported by modern model weights. | Custom Regex XML/Bracket parsing prone to formatting hallucinations. |
| **Execution Persistence** | Durable execution (Temporal, Postgres checkpointer) backing all steps so agents can pause indefinitely. | Volatile memory (`asyncio.Event` blocks) that terminate upon process exit. |
| **Pub/Sub Scaling** | Distributed message brokers (Redis, RabbitMQ, Kafka) natively integrated for horizontal scaling. | Local `asyncio.Queue` preventing multi-node deployments. |

---

## 3. Refactoring Strategy

To modernize the implementation, adhere to SOLID principles, DRY methodologies, and ensure fault tolerance, the following refactoring steps must be executed:

### Phase 1: State Persistence & Fault Tolerance
- **Durable Task Queue:** Replace raw `asyncio.create_task` with a robust task queue (e.g., **ARQ** or **Celery** via Redis). Agent runs must be serializable background jobs.
- **Persistent Human-in-the-Loop:** Move `pending_approvals` into the database (or Redis). Agents should suspend execution completely, store their exact state checkpoint, and be awoken by a Webhook trigger rather than blocking a thread indefinitely on an `asyncio.Event`.
- **Distributed Event Bus:** Refactor `EventBus` behind an Abstract Base Class (ABC). Implement a `RedisEventBus` adapter so Websocket messages sync across multiple horizontally-scaled API nodes.

### Phase 2: Modernizing LLM Interactions (DRY)
- **Replace Custom LLM Router:** Deprecate the hand-rolled `MultiModelRouter`. Integrate **LiteLLM**, which natively unifies Anthropic, OpenAI, Gemini, and local models under the standard OpenAI API specification, automatically handling streaming, retries, and token logging.
- **Native Tool Calling:** Refactor the `ReACTAgent` to utilize native Function Calling. Expose `ToolRegistry` elements as OpenAPI JSON schemas. Replace `_parse_action` regex matching with native provider structured outputs.

### Phase 3: SOLID Component Decoupling
- **Dependency Injection:** Migrate singletons (e.g., `llm_router`, `tool_executor`) to FastAPI's `Depends()` injection pattern or a dedicated IoC container framework, allowing modular test mocking.
- **Decouple Dream Worker:** Extract the `AutoDreamWorker` from an in-process infinite loop into a cron-triggered headless script or standard Celery Beat schedule to separate API load from background batch processing.

---

## 4. Optimization & Telemetry

### Telemetry (Observability)
- **Structured Logging:** Migrate standard `logging` to **Structlog** or **Loguru**. Output logs in JSON format for ingestion into Datadog, ELK, or Grafana.
- **OpenTelemetry (OTel):** Instrument the application with OpenTelemetry traces. Bind incoming WebSocket connections -> `MessageRouter` -> `ReACTAgent` -> `LiteLLM` -> `ToolExecutor`. This provides a visual waterfall of agent latency and failure cascades.

### Performance & Optimization
- **HTTP Connection Pooling:** Refactor all external API calls (e.g., vector embeddings, LLMs) to utilize a globally shared, long-lived `httpx.AsyncClient` pool per the FastAPI lifespan context manager. Destroying and recreating SSL handshakes per token stream causes massive latency.
- **Semantic Caching:** Introduce a Redis-backed semantic cache (e.g., `redisvl` or `gptcache`) to bypass LLM generation and embedding calculations for identical downstream tool questions.
- **Streaming Context Management:** Optimize the Agent's memory loader. Instead of full string concatenation (`\n.join(history)`), utilize a sliding window Tokenizer count limit, dropping older unstructured messages dynamically before hitting provider token caps.

*Prepared by Carole.ai Architectural Review System.*