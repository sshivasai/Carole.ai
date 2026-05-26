# Claude Code Architecture Analysis
## Complete Source Code Understanding from yasasbanukaofficial/claude-code

---

## 🏗️ High-Level Architecture

### Core Technologies
- **Language**: TypeScript (100%)
- **Runtime**: Bun/Node.js v18+
- **UI Framework**: React + Ink (terminal rendering)
- **CLI Framework**: Commander.js
- **Tool System**: 40+ integrated tools with permission gating

### Main Entry Point
`src/main.tsx` (803KB) - React terminal renderer with full agent orchestration

---

## 🔧 Core Agent System

### 1. Tool Architecture (`src/Tool.ts` - 29.5KB)

**Tool Definition Pattern:**
```typescript
interface Tool<Input, Output, Progress> {
  // Schema & Validation
  inputSchema: ZodSchema<Input>
  inputJSONSchema?: JSONSchema7  // For MCP tools
  outputSchema?: ZodSchema<Output>
  
  // Execution
  call(args, context, canUseTool, parentMessage, onProgress): ToolResult<Output>
  
  // Permissions & Safety
  checkPermissions(): PermissionLevel
  validateInput(args): ValidationResult
  isDestructive(): boolean
  isConcurrencySafe(): boolean
  
  // Behavior Flags
  interruptBehavior: 'cancel' | 'block'
  isSearchOrReadCommand(): boolean
  shouldDefer: boolean  // Requires ToolSearch lookup
  alwaysLoad: boolean   // Never deferred
  
  // Rendering Pipeline
  renderToolUseMessage(args): ReactNode
  renderToolResultMessage(result): ReactNode
  renderToolUseProgressMessage(progress): ReactNode
  renderGroupedToolUse(tools): ReactNode
}
```

**Tool Result Structure:**
```typescript
interface ToolResult<Output> {
  data: Output
  newMessages?: Message[]
  contextModifier?: ContextUpdate
  mcpMeta?: MCPMetadata
}
```

**Tool Registration:**
- Tools defined via `buildTool()` factory with sensible defaults
- Registered in `src/tools.ts` via `getAllBaseTools()`
- Filtered by permissions, mode, and feature flags
- Assembled with MCP tools in `assembleToolPool()`

---

### 2. Query Engine (`src/QueryEngine.ts` - 46.6KB)

**Core Responsibilities:**
- Manages conversation lifecycle (`mutableMessages`)
- Orchestrates LLM interactions
- Executes tool calls with permission checks
- Streams responses and tracks usage/costs

**Main Loop (`submitMessage()` generator):**
```
1. Initialization
   ├─ Build system prompts
   ├─ Load plugins & skills
   └─ Yield system init message

2. User Input Processing
   ├─ Slash command handling
   └─ Attachment processing

3. Query Execution
   ├─ Call query() with wrapped permissions
   └─ Stream events (stream_event)

4. Response Handling
   ├─ Assistant messages (streamed)
   ├─ Tool execution results
   └─ Usage metrics & summaries
```

**Permission Wrapping:**
- `canUseTool` callback validates permissions before execution
- Tracks denials for SDK reporting
- Returns "allow" | "deny" decisions

**Budget Enforcement:**
- Turn limits (`maxTurns`)
- USD budgets (`maxBudgetUsd`)
- Structured output retry limits

---

### 3. Query Loop (`src/query.ts` - 68.7KB)

**Infinite State Machine:**
```
┌─────────────────────────────────────┐
│ Setup & Compaction                  │
├─────────────────────────────────────┤
│ - Extract messages after boundaries │
│ - Apply snipping (history removal)  │
│ - Microcompaction (optimize storage)│
│ - Context collapse (summarization)  │
│ - Autocompaction (token thresholds) │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│ Model Invocation                    │
├─────────────────────────────────────┤
│ - Call LLM with system + tools      │
│ - Stream responses                  │
│ - Extract tool use blocks           │
│ - Withhold recoverable errors       │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│ Error Recovery                      │
├─────────────────────────────────────┤
│ - Context collapse drain            │
│ - Reactive compaction               │
│ - Max-output-tokens escalation      │
│ - Model fallback                    │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│ Tool Execution                      │
├─────────────────────────────────────┤
│ - Streaming or batch execution      │
│ - Accumulate results                │
│ - Generate summaries (async)        │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│ Attachment Processing               │
├─────────────────────────────────────┤
│ - Inject queued commands            │
│ - Memory prefetch results           │
│ - Skill discovery                   │
└──────────────┬──────────────────────┘
               │
               └──────► Loop back
```

**Recovery Mechanisms:**

1. **Prompt Too Long (413)**
   - Context-collapse drain (preserves granular context)
   - Reactive compaction (full summarization)

2. **Max Output Tokens**
   - Escalating retry: 8k → 64k
   - Multi-turn continuation nudges

3. **Model Fallback**
   - Orphan messages tombstoned
   - Tool results discarded
   - Fresh executor initialized

**Termination Conditions:**
- No tool use blocks (natural completion)
- Max turns exceeded
- Stop hooks prevent continuation
- Token budget depleted
- User abort signal
- Unrecoverable API errors

---

## 🤝 Multi-Agent Orchestration

### Coordinator Mode (`src/coordinator/coordinatorMode.ts` - 19KB)

**Hierarchical Agent System:**
```
┌──────────────────────────────┐
│   COORDINATOR (Primary)      │
│   - Synthesis & planning     │
│   - Worker management        │
│   - Context routing          │
└───────────┬──────────────────┘
            │
            ├─────► Worker 1 (Research)
            ├─────► Worker 2 (Research)
            └─────► Worker 3 (Implementation)
```

**Worker Tool Access:**
- **Simple Mode**: Bash + file read/write
- **Full Mode**: Standard tools + MCP integration
- **Restricted**: Team management, messaging (coordinator only)

**Communication Pattern:**
- Workers send `<task-notification>` XML messages
- Messages contain: task ID, status, results, token usage
- Arrive as user-role messages

**Coordination Tools:**
1. `AgentTool` - Spawn new workers with fresh context
2. `SendMessageTool` - Continue existing workers (preserves context)

**Coordination Strategy:**
> "The coordinator never delegates understanding. After workers complete research, the coordinator must synthesize findings into specific prompts proving understanding by including file paths, line numbers, and exactly what to change."

**Concurrency Pattern:**
- Parallel: Read-only research tasks
- Serial: Write operations (per file set)
- Context reuse: High-overlap → continuation, Low-overlap → fresh spawn

---

## 🛠️ Available Tools (40+)

### Tool Categories

**File & Code Operations:**
- FileReadTool, FileWriteTool, FileEditTool
- GlobTool, GrepTool
- NotebookEditTool

**Execution & Shell:**
- BashTool, PowerShellTool
- REPLTool

**Web & External:**
- WebSearchTool, WebFetchTool
- MCPTool, ListMcpResourcesTool, ReadMcpResourceTool, McpAuthTool

**Task & Workflow:**
- TaskCreateTool, TaskGetTool, TaskListTool, TaskUpdateTool, TaskStopTool, TaskOutputTool
- ScheduleCronTool, RemoteTriggerTool

**Development & Analysis:**
- LSPTool (Language Server Protocol)
- AgentTool (spawn subagents)
- BriefTool

**Configuration & Planning:**
- ConfigTool
- EnterPlanModeTool, ExitPlanModeTool
- EnterWorktreeTool, ExitWorktreeTool

**Communication:**
- AskUserQuestionTool
- SendMessageTool (inter-agent)
- SyntheticOutputTool
- TodoWriteTool

**Utility:**
- SkillTool
- ToolSearchTool (deferred tool loading)
- SleepTool
- TeamCreateTool, TeamDeleteTool

### Tool Loading Mechanism (`src/tools.ts` - 17.3KB)

**Registration:**
```typescript
getAllBaseTools(): Tool[] {
  // Static imports
  const tools = [BashTool, FileReadTool, FileEditTool, ...]
  
  // Conditional imports (feature flags)
  if (process.env.USER_TYPE === 'ant') {
    tools.push(REPLTool)
  }
  
  // Lazy loading (circular dependency resolution)
  tools.push(getTeamCreateTool())
  
  return tools
}
```

**Discovery:**
```typescript
getTools(context): Tool[] {
  const base = getAllBaseTools()
  
  // 1. Permission filtering
  const filtered = filterToolsByDenyRules(base, context.denyRules)
  
  // 2. Mode filtering (REPL hides primitives)
  const modeFiltered = applyModeFilters(filtered, context.mode)
  
  // 3. Enablement checks
  return modeFiltered.filter(t => t.isEnabled())
}
```

**Assembly for LLM:**
```typescript
assembleToolPool(builtInTools, mcpTools): Tool[] {
  // Combine built-in + MCP (dedupe by name, built-ins win)
  const combined = [...builtInTools, ...mcpTools]
  const deduped = deduplicateByName(combined)
  
  // Sort alphabetically for prompt-cache stability
  return sortAlphabetically(deduped)
}
```

---

## 🎯 Advanced Features

### 1. BUDDY System (`src/buddy/`)

**Files:**
- `CompanionSprite.tsx` (45.9KB) - Visual rendering
- `companion.ts` (3.7KB) - Core logic
- `sprites.ts` (9.8KB) - 18 species variants
- `types.ts` (3.8KB) - Type definitions
- `useBuddyNotification.tsx` (10KB) - Notification hooks
- `prompt.ts` (1.5KB) - Buddy personality prompts

**Features:**
- Tamagotchi-style companion
- Deterministic character generation (user ID-based)
- Personality stats: debugging level, chaos level
- 18 species with unique sprites

---

### 2. Background Services (`src/services/`)

**Major Services:**

**Memory Management:**
- `SessionMemory/` - Context tracking
- `extractMemories/` - Memory extraction
- `teamMemorySync/` - Multi-agent memory sync
- `autoDream/` - Memory consolidation (runs in background)

**API & Integration:**
- `api/` - External API clients
- `oauth/` - Authentication
- `mcp/` - Model Context Protocol integration
- `lsp/` - Language Server Protocol

**Analytics & Monitoring:**
- `analytics/` - Usage tracking
- `diagnosticTracking.ts` - Error reporting
- `internalLogging.ts` - Debug logs
- `rateLimitMessages.ts` - Rate limit handling

**AI Services:**
- `AgentSummary/` - Conversation summarization
- `PromptSuggestion/` - Smart suggestions
- `MagicDocs/` - Auto-documentation
- `toolUseSummary/` - Tool usage analysis

**Advanced Features:**
- `awaySummary.ts` - Summary when user away
- `compact/` - Context compaction algorithms
- `preventSleep.ts` - Keep system awake during tasks
- `voice.ts` / `voiceStreamSTT.ts` - Voice input

**Utility:**
- `claudeAiLimits.ts` - API rate limits
- `tokenEstimation.ts` - Token counting
- `notifier.ts` - System notifications
- `settingsSync/` - Settings synchronization
- `remoteManagedSettings/` - Remote config
- `policyLimits/` - Policy enforcement

---

### 3. Dream Service (Auto Memory Consolidation)

**Purpose:**
- Runs in background during idle time
- Organizes conversation logs
- Updates memory files
- Maintains efficient context

**Pattern:**
```
Active Session → Idle Detection → Dream Service
                                      ├─ Analyze logs
                                      ├─ Extract key info
                                      ├─ Update memory
                                      └─ Compact context
```

---

### 4. KAIROS (Proactive Assistant)

**Always-On Monitoring:**
- Watches for patterns requiring assistance
- Suggests actions proactively
- Monitors system state

---

### 5. ULTRAPLAN (Remote Task Offloading)

**Purpose:**
- Offload complex planning to remote Opus 4.6 instance
- Extended planning periods without blocking main session
- Return results when ready

**Architecture:**
```
Local Agent → Detects complex task
              ↓
           ULTRAPLAN trigger
              ↓
Remote Opus 4.6 → Deep planning session
              ↓
Results returned → Local agent continues
```

---

### 6. Undercover Mode (Security)

**Purpose:**
- Prevents internal information leakage
- Filters Anthropic codenames (e.g., "Tengu")
- Protects proprietary information in public repos

**Pattern:**
- Detects Anthropic employee contributions
- Scrubs internal references
- Maintains operational security

---

## 📁 Project Structure

```
claude-code/
├── src/
│   ├── main.tsx (803KB)           # Entry point
│   ├── QueryEngine.ts (46KB)      # LLM orchestration
│   ├── query.ts (68KB)            # Query loop
│   ├── Tool.ts (29KB)             # Tool framework
│   ├── tools.ts (17KB)            # Tool registration
│   ├── commands.ts (25KB)         # CLI commands
│   ├── history.ts (14KB)          # Session history
│   ├── context.ts (6KB)           # Context management
│   │
│   ├── tools/                     # 40+ individual tools
│   │   ├── FileReadTool/
│   │   ├── FileWriteTool/
│   │   ├── BashTool/
│   │   ├── GlobTool/
│   │   ├── GrepTool/
│   │   ├── AgentTool/
│   │   └── ...
│   │
│   ├── coordinator/               # Multi-agent orchestration
│   │   └── coordinatorMode.ts
│   │
│   ├── services/                  # Background services
│   │   ├── autoDream/            # Memory consolidation
│   │   ├── SessionMemory/        # Context tracking
│   │   ├── analytics/            # Usage tracking
│   │   ├── mcp/                  # Model Context Protocol
│   │   ├── lsp/                  # Language Server
│   │   └── ...
│   │
│   ├── buddy/                     # Companion system
│   │   ├── CompanionSprite.tsx
│   │   ├── companion.ts
│   │   └── sprites.ts
│   │
│   ├── bridge/                    # IDE integration
│   ├── skills/                    # Custom skills
│   ├── components/                # React components
│   ├── screens/                   # UI screens
│   ├── hooks/                     # React hooks
│   ├── state/                     # State management
│   ├── schemas/                   # Validation schemas
│   └── utils/                     # Utilities
│
└── assets/                        # Documentation assets
```

---

## 🔑 Key Design Patterns

### 1. Tool Pattern
```typescript
// Define tool with schema
const MyTool = buildTool({
  name: 'my_tool',
  inputSchema: z.object({ path: z.string() }),
  call: async (args, context) => {
    // Execute logic
    return { data: result }
  },
  checkPermissions: () => 'allow',
  isConcurrencySafe: false
})
```

### 2. Permission Gating
```typescript
// Three-level system
type Permission = 'allow' | 'deny' | 'ask'

// Context-aware checking
canUseTool(tool, args, context) => {
  const permission = tool.checkPermissions(args, context)
  if (permission === 'ask') {
    return await promptUser()
  }
  return permission
}
```

### 3. Lazy Tool Loading
```typescript
// Deferred tools loaded on demand
if (tool.shouldDefer) {
  // Use ToolSearchTool to load schema
  const schema = await ToolSearchTool.call({ query: tool.name })
  tool.schema = schema
}
```

### 4. Context Compaction
```typescript
// Multi-stage compression
Messages → Snipping → Microcompaction → Context Collapse → Autocompaction
           (trim)     (optimize)        (summarize)       (threshold)
```

### 5. Error Recovery Chain
```typescript
try {
  result = await callModel(prompt)
} catch (error) {
  if (error.type === 'prompt_too_long') {
    // Try context collapse drain
    return await retryWithCollapsedrain()
  } else if (error.type === 'max_output_tokens') {
    // Escalate limit
    return await retryWithHigherLimit()
  } else if (error.type === 'model_overload') {
    // Fallback to different model
    return await retryWithFallbackModel()
  }
  throw error
}
```

---

## 💡 Key Learnings for Battlefield

### 1. Tool System
✅ Use Zod schemas for validation  
✅ Permission checking before execution  
✅ Concurrent execution when safe  
✅ Lazy loading for large tool sets  
✅ Render methods for UI feedback  

### 2. Agent Loop
✅ Generator pattern for streaming  
✅ Context compaction at multiple stages  
✅ Error recovery with fallbacks  
✅ Budget tracking (turns, tokens, cost)  
✅ Session persistence for resumability  

### 3. Multi-Agent Coordination
✅ Coordinator never delegates understanding  
✅ Workers communicate via structured messages  
✅ Context reuse for high-overlap tasks  
✅ Parallel execution for read-only operations  
✅ Synthesis before implementation  

### 4. Background Services
✅ Memory consolidation during idle  
✅ Proactive monitoring (KAIROS)  
✅ Remote task offloading (ULTRAPLAN)  
✅ Analytics and diagnostics  

### 5. UI/UX
✅ Terminal rendering with React + Ink  
✅ Progress streaming during tool execution  
✅ Grouped rendering for parallel tools  
✅ Companion system for engagement  
✅ Voice input support  

---

## 🎯 Implementation Priority for Battlefield

**Phase 1: Core Agent Loop** ✅ Tools built
1. Tool registry with permission system
2. Query loop with LLM integration
3. Basic error recovery
4. Message streaming

**Phase 2: Multi-Agent**
1. Coordinator mode
2. Worker spawning
3. Inter-agent messaging
4. Context routing

**Phase 3: 3D Visualization**
1. WebSocket event streaming
2. React Three Fiber battlefield
3. Agent avatars with movement
4. Tool execution visualization

**Phase 4: Advanced Features**
1. Memory consolidation service
2. Context compaction
3. Proactive assistance
4. Voice integration

---

## 📊 Statistics

- **Total Source Size**: ~1.2MB TypeScript
- **Main Entry Point**: 803KB (main.tsx)
- **Tools**: 40+ integrated
- **Services**: 36 background services
- **Key Files**: 
  - QueryEngine.ts: 46.6KB
  - query.ts: 68.7KB
  - Tool.ts: 29.5KB
  - coordinatorMode.ts: 19KB

---

*Analysis completed: 2026-04-27*
*Source: yasasbanukaofficial/claude-code (GitHub)*
