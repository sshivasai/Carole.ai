# Carole.ai frontend improvement plan

## Direction and scope

Create a spacious, conversation-first coding workspace. The user's selected reference is a Claude-style spacious conversation, with the request handling and code review clarity expected of a capable coding assistant. Treat those products as inspiration, not as a verified feature comparison or a pixel-copy specification.

The primary job: submit a request, understand progress, answer or approve when necessary, inspect the resulting changes, and continue confidently. Keep Carole's multi-agent, project/team, browser, memory, plugin, and scheduling capabilities available without making every capability compete for attention in chat.

This is an implementation plan based on source inspection, not a completed visual redesign. It covers the 12 views selected in `frontend/src/app/page.tsx`, the landing/auth experience, supporting work panes and dialogs, and all eight settings sections. Runtime screenshots, measured contrast, performance profiling, and end-to-end behavior have not been verified. Findings below distinguish observable code behavior from proposed improvements. Existing uncommitted application work was not modified.

## 1. Findings that should set the priorities

| Priority | Source evidence | Consequence | Required change |
| --- | --- | --- | --- |
| P0 | `hooks/useWebSocket.ts`: `sendMessage` silently returns unless the socket is open; `ChatInterface.tsx:1362` clears input and attachments after calling a void callback. | A disconnected send can erase the user's draft without delivering it. | Return an explicit submission result; preserve drafts until durable acceptance; show sending, failed, and retry states. |
| P0 | `app/page.tsx:118`: approvals attach to `streaming-${agentId}`; final message replacement at line 93 retains reasoning but does not carry `pending_approval`. | A final message event can remove an unresolved approval from the transcript. | Store approvals independently, keyed by transaction ID, and reference them from the turn. |
| P0 | `ChatInterface.tsx:141`: approval wrapper catches failures without rethrowing; `AgentPermissionCard.tsx` sets a local decision before awaiting it. | An HTTP failure can leave the card appearing successfully approved or denied. | Use one shared mutation state and authoritative server resolution; display retryable errors inline. |
| P0 | `backend/main.py:686`: an unknown approval transaction returns `already_resolved` with an action inferred from the submitted decision. | The client cannot reliably distinguish missing/expired work from an accepted decision. | Return actual recorded resolution or explicit unknown/expired status; never infer historical success from a new request. |
| P0 | `ChatInterface.tsx:220` mutates the message object and marks questions answered before the API call; `AskUserQuestionCard.tsx` also has optimistic local answer state. | Failed answers can appear complete with no usable retry path. | Controlled question state, retained answer draft, acknowledgment, failure, and retry. |
| P0 | `app/page.tsx:869` and `:880`: deletion/rollback remove messages before API completion, without restoration in the catch path. | The visible history can disagree with files and server state after failure. | Preview rollback scope; commit UI changes after success or restore a precise optimistic snapshot. |
| P1 | `app/page.tsx:61–91`: tool start/progress/end become Markdown in `reasoning`; results are sliced to 1,000 characters. | Tool identity, lifecycle, full output, and parallel execution are difficult to represent accurately. | Structured tool calls and output references; concise rows with expandable details. |
| P1 | `ChatInterface.tsx:1200`: every `approval_request` qualifies for forced bottom scrolling, regardless of resolution; question check uses `ask_user`, while the reducer emits `agent_question`. | Reading position is disrupted and request detection is inconsistent. | Derive an explicit pending-action list; notify without taking over scroll position. |
| P1 | `AgentPermissionCard.tsx`: countdown assumes 60 seconds; risk falls back to substring checks; dark gradients and fixed colors are inline. | Expiry and risk labels can mislead; light theme cannot consistently apply. | Server expiry/policy metadata, neutral unknown state, semantic theme tokens. |
| P1 | `FileChangeCard.tsx:83`: content-only changes are presented as additions; missing content/diff gets a fabricated “created” line. | A preview can look like a real patch even when no patch exists. | Distinguish genuine patch, full content preview, binary change, and unavailable diff. |
| P1 | `DiffViewer.tsx`: line counters start at zero and do not initialize from hunk headers. | Displayed source line numbers can be incorrect. | Parse unified patches correctly or use a tested diff renderer. |
| P1 | `app/page.tsx`: history hydration replaces message state; pending approvals are restored from local storage then reconciled separately. | Event/history races and context switching need explicit handling. | Merge snapshots and live events using stable IDs, sequence boundaries, and context generation guards. |
| P1 | `hooks/useWebSocket.ts`: ticket-fetch failure returns without scheduling retry. | Initial connection failure can remain disconnected with little explanation. | Include authentication/ticket failure in the transport state machine and retry policy. |
| P1 | `Modal.tsx` has Escape and dialog roles, but no focus trap, return-focus behavior, or title association. | Keyboard users can lose context or tab behind a dialog. | Shared accessible dialog primitive with labeled content and managed focus. |
| P2 | `Sidebar.tsx` presents 12 top-level destinations; `page.tsx` uses local `activeView` and eager component imports. | Navigation competes with the core workflow; refresh/deep linking and feature loading need improvement. | Group navigation, persist URL state, and load heavy work panes on demand. |
| P2 | `globals.css` duplicates font imports and mixes font families/legacy aliases; chat cards use bespoke dark surfaces and small text. | Visual identity and density vary across surfaces. | Consolidate typography, spacing, color, and component primitives. |
| P2 | Agent, task, and plan editors contain swallowed errors; graph fetch failures are console-only. | Some operations appear inert or fail without a recovery path. | Form-level errors and retry states; preserve local work. |

## 2. Conversation layout and visual system

### Proposed desktop composition

```text
Projects / teams      Project / conversation title        Review changes
Recent conversations  -------------------------------------------------
                      User request
Workspace             Assistant response in readable prose
  Tasks               > Working · 4 actions · 2 files changed
  Agents              > Changes · 2 files                       [Review]
  Browser
                      Approval or question card when relevant
Knowledge             Assistant result and validation summary
  Memory              -------------------------------------------------
  Scratchpad          Needs your input · 1                     [View]
  Code graph          [Attached files / selected context]
                      [Message composer                         Send]
Extensions            Model / mode / context usage
Settings
```

The review pane opens beside chat only on user action or an explicit navigation request. It contains Changes, Files, and supporting output as appropriate. Preserve the existing resizable-panel capability. On smaller widths, switch to a full-width pane with a clear Back to conversation action rather than squeezing three columns together.

### Design specifications for the first implementation

- Conversation column: approximately 760–840px maximum width, centered with generous gutters when review is closed. Let tables and code blocks scroll within their own containers.
- Body copy: 15–16px with approximately 1.6 line height; metadata 12–13px; code 12–13px. Avoid using tiny text for decisions or primary actions.
- User messages: a subtle surface with moderate padding. Assistant prose: largely unboxed. Tool activity: compact bordered disclosure rows. Action requests: one clear card with a modest accent.
- Use neutral light and dark surfaces with one restrained Carole accent. Status colors communicate pending/error/success and always have a text label or icon.
- Replace competing glow, glass, gradient, and animated-background treatments in the workspace with quiet surfaces and clear boundaries. Marketing can retain its own expressive treatment.
- Standardize spacing around a 4px scale and shared control sizes. Keep primary buttons easy to target; use roughly 44px touch targets on touch layouts.
- Composer grows to a bounded height, supports multiline input, and keeps attachments and submission status visible. Put secondary actions in a menu rather than a permanent icon wall.
- Use one typography source and verify rendered font loading. Create tokens for canvas, panel, hover, selection, border, text, focus, status, and diff colors in both themes.
- Build shared Button/IconButton, Field, Select/Combobox, Tabs, Disclosure, Dialog, Menu, EmptyState, InlineError, StatusBadge, and PageHeader components.

## 3. Chat and request handling: implementation specification

### 3.1 Make conversations, turns, and events explicit

Split transport, state reduction, and presentation. `page.tsx` should assemble the shell, not own every chat lifecycle transition.

Suggested structure:

```text
src/features/chat/
  types.ts                 discriminated event and entity types
  eventAdapter.ts          runtime validation and legacy normalization
  reducer.ts               deterministic event transitions
  selectors.ts             turns, pending actions, changes, run state
  useConversation.ts       snapshots, reconnect, mutations, context scope
  components/
    ConversationHeader.tsx
    ConversationTimeline.tsx
    Turn.tsx
    AssistantMessage.tsx
    ToolCallRow.tsx
    ApprovalRequest.tsx
    QuestionRequest.tsx
    PendingActionsBar.tsx
    Composer.tsx
    ChangeSummary.tsx
    RunStatus.tsx
src/features/review/
  ReviewPane.tsx
  ChangedFileList.tsx
  PatchView.tsx
```

Proposed event envelope: `event_id`, `schema_version`, `project_id`, `team_id`, `conversation_id`, `run_id`, `turn_id`, `sequence`, `timestamp`, `type`, and typed payload. Tool events add `tool_call_id`; approval events use `tx_id`; questions use stable question IDs. These are contract additions where the backend does not currently provide them.

Normalize server entities separately: messages, runs, tool calls, approvals, questions, file changes, and plan revisions. Rendering an assistant's final response must not delete outstanding actions. Multiple calls from the same agent must coexist. Unknown event types should degrade gracefully with diagnostics, rather than corrupting a turn.

Compatibility: adapt existing events at the boundary; do not manufacture certainty about run identity for old history. Show a legacy activity group when a reliable relationship is unavailable. Migrate in one surface at a time behind a frontend feature flag.

### 3.2 Sending, queueing, stopping, and recovery

| State | User-facing behavior |
| --- | --- |
| Draft | Persist per conversation/team; show attachment validation and selected context. |
| Sending | Show an optimistic user message keyed by a client ID; retain the recoverable draft. |
| Accepted | Deduplicate server echo by client ID; clear only the submitted draft revision. |
| Queued | Explain which run it follows; support removal/editing only if backed by the queue API. |
| Running | Show a plain progress label and elapsed time; Stop targets the correct run. |
| Waiting for input | Name the approval/question and agent; keep the composer available for steering. |
| Stopping | Disable repeated stop clicks; wait for server confirmation. |
| Failed/interrupted | Retain partial output and files; offer a concrete retry/resume path. |
| Completed | Show result, changes, and actual verification outcome; avoid conflating completion with all checks passing. |

Use a client message ID and server idempotency handling so a retry cannot create duplicate work. If acknowledgment is uncertain, reconcile first. Until that contract exists, preserve the draft and show “Delivery not confirmed”; do not promise reliable automatic resend.

Represent connection as connecting, connected, reconnecting, offline, and authentication-required. Retry transient ticket failures; stop retrying invalid authentication until reauthentication. Reconcile active runs and pending actions after reconnect. Ignore stale socket callbacks and aborted history loads when the selected team changes.

Preserve typed input when attachment upload fails. Support cancel/retry/removal per attachment. Model file references as chips carrying the exact path, including spaces and Unicode; do not rely on `/@file:(\S+)/` parsing. Guard Enter submission during IME composition. Make Plan and other modes visible structured choices rather than opaque prompt rewrites where backend support is available.

### 3.3 Tool activity timeline

Each tool call gets a stable row: icon, readable verb, target, agent, state, duration, and expansion control. Examples: “Reading 3 files”, “Running frontend checks”, “Updating ChatInterface.tsx”. Keep the original command and arguments inspectable.

Group related completed actions under a single disclosure such as “Explored 8 files”. Keep running calls and unresolved requests visible. Preserve order within each run while allowing parallel agents to have separate activity groups. Avoid turning every agent status update into a new chat bubble.

Expanded details include exact command, working directory, arguments, stdout/stderr, exit code, and cancellation/error information where supplied. Store large output separately with explicit truncation and a fetch-more/download action if supported. Never silently throw away output after 1,000 characters.

Keep provider-supplied reasoning separate from tool records and user-facing progress. Render only data actually supplied; no fabricated reasoning. The normal view should remain understandable with reasoning collapsed.

### 3.4 Approval cards and pending-action queue

Card anatomy: action title; agent; exact target and scope; reason approval is required; inspectable command or genuine proposed diff; decision controls; resolution/error text.

Default actions: **Approve once** and **Deny**, with optional feedback. Additional persistent approval scopes appear only when the backend enforces their exact meaning and can describe/revoke them. Do not add a broad “always allow” button merely for parity with another product.

Lifecycle: `pending → submitting → approved | denied | expired | cancelled | superseded`, with retryable mutation failure returning to a pending card that retains feedback. The HTTP acknowledgment and subsequent event must reconcile to the same entity. An approved tool can still fail execution; show those as separate states.

Send feedback as part of the decision payload. The current approval API only sends a Boolean, and the nested card can be rendered without `onFeedback`; a feedback box must not silently discard its contents or rely on an unrelated chat message.

Use backend-provided `created_at`, `expires_at`, policy source, and scope. If expiry is unavailable, omit the countdown. If policy classification is unavailable, say that explicitly instead of labeling an unknown action “Safe”. Show meaningful rationale rather than numeric risk tiers alone.

Maintain one pending-action queue across the active workspace, with team/conversation attribution and a count. The transcript card and the pinned “Needs your input” bar reference the same record. Resolution collapses the card to a receipt while retaining what was approved, when, and by whom when available.

Acceptance examples:

- Two approvals from one agent remain independently actionable.
- A final assistant message arriving before the decision does not remove the request.
- HTTP failure leaves the request actionable and feedback intact.
- A second browser tab resolving the request updates the first tab to the actual outcome.
- An expired or unknown request never appears approved merely because Approve was clicked.
- Scrolling upward remains stable when a request arrives; the pending-action bar offers navigation.

### 3.5 Questions, plans, and browser intervention

Questions use explicit stable IDs, labels, required/optional status, and answer types: single choice, multiple choice, or free text. For multiple questions, retain answers by ID rather than question text so duplicate labels cannot overwrite each other. Validate required answers and preserve the answer draft on failure. Skip is available only when the workflow permits it.

Plan approval is a separate domain from tool permission. Unify `InChatPlanCard`, `ImplementationPlanModal`, task detail, and task board around the same plan revision/status. Show Approve plan, Request changes, and Open full plan. Bind decisions/comments to a revision; newer revisions invalidate stale decisions as defined by the server. “Proceed” should target the approved task/run through a structured action when supported.

Browser intervention cards show the owning agent/session and a direct Open browser action. Explain whether the user is viewing a snapshot or controlling a live session. On completion, require server acknowledgment before marking intervention resolved. Preserve the interrupted run while the user takes over.

### 3.6 File changes and checkpoint restoration

Separate proposed changes awaiting approval from already-applied changes. Group applied changes by turn/run, with a compact count and additions/deletions only when known. Retain individual change IDs even when a file is edited repeatedly.

Open Review into a file list and diff pane. Provide file path, change type, old/new line numbers, next/previous file, unified/split views, and Open file. Handle created/deleted/renamed/binary/large files and missing snapshots explicitly. A full content preview must be labeled as such.

Use stored before/after revisions or snapshots for the selected change. Fetching Git HEAD is not necessarily the original content for that turn. Distinguish turn changes, all conversation changes, and working-tree changes; do not silently mix user edits into the agent's summary.

Checkpoint restore shows affected messages, tasks, and files before execution. Detect user edits since the checkpoint and surface conflicts. Use transactional server results where possible, then refresh all affected state. Disable repeated restore clicks and retain history if restore fails. Hunk-level accept/revert is a later feature requiring patch validation and conflict handling.

### 3.7 Scrolling, long histories, and accessible interaction

Follow streaming only while the user is near the bottom. Never force scrolling merely because an old request exists. Show “New activity” and “Needs your input” separately. Preserve scroll anchors when loading older history or expanding tool output.

Add pagination and profile long transcripts before selecting virtualization. Keep the streaming turn and pending interactions mounted. Cache completed Markdown rendering and isolate token updates to the active turn. Lazy-load editors and heavy graph/browser surfaces.

Use semantic transcript structure, accessible names for all icon actions, and polite announcements for major state changes. Do not announce each token. Manage focus after sending, opening/closing review, submitting a question, and resolving a dialog. Respect reduced motion and make hover actions available to keyboard users.

### 3.8 Background work: first-class, persistent activity

Background work is part of the core chat redesign and must ship with M2–M3, not as a later task-manager enhancement. A response finishing, a tool returning, and a background job finishing are separate events.

Additional source findings: `ChatInterface.tsx` extracts a process ID by matching “launched in background with PID” from result text. `TaskManagerPanel.tsx` independently polls every three seconds and uses a separate API-base/auth wrapper. `AgentActivityStream.tsx` derives past-tense tool titles and edit counts from arguments. Replace these assumptions with structured execution records and shared transport/state. A launch acknowledgment does not establish successful completion, and proposed file content does not establish actual changed-line counts.

#### Three coordinated places to see activity

1. **Within the originating turn:** one compact live summary, such as “Running checks · 2 jobs”, expands into its tool calls and child workers. When the assistant responds while jobs continue, retain a visible “Checks still running” row beneath that turn.
2. **Workspace activity indicator:** a quiet header control such as “3 running · 1 needs input” remains available on other pages. Counts come from the same job/request store. Show scope explicitly; switching teams must not mix their records.
3. **Activity drawer:** opens on demand with Running, Needs input, and Recent filters. Each row shows a meaningful job name, agent, originating conversation/task, state, elapsed time, and available actions. Selecting a job opens its details and output; selecting its origin returns to the exact turn.

Do not repeat full logs in all three places. They are views of one record. Pending approvals/questions remain actionable from the drawer using the same request components as chat. Closing the drawer or leaving the page does not cancel work.

#### Job types and lifecycle

| Work type | Presentation | Completion meaning |
| --- | --- | --- |
| Finite command or test | Command summary, output, elapsed time, exit status | Process exit plus actual result; failed assertions remain failures. |
| Persistent service/watch process | “Starting”, then “Running”; “Ready” only with an explicit readiness signal | Continues until stopped/exited; launch success is not task completion. |
| Delegated agent | Task goal, owner, concise current activity, child tool disclosure | Agent outcome with remaining work, files, and verification state. |
| Browser job | Session/agent, current action, Open browser, intervention state | Server-confirmed result or handoff requirement. |
| Indexing, ingestion, memory maintenance | Named operation, scope, progress when available | Backend-confirmed operation result; upload is separate from ingestion. |
| Scheduled execution | Schedule name, current run, next occurrence separately | Each execution has its own result; schedule remains enabled independently. |

Shared lifecycle: `queued → starting → running → succeeded | failed | cancelled`, with explicit `waiting_for_approval`, `waiting_for_answer`, and `stopping` states where applicable. Model connection freshness separately (`live`, `stale`, `reconnecting`, `unknown`); losing connection must not convert a running process into success or failure. Record readiness separately for services.

Use stable server job IDs, not PID alone: PIDs can be reused. A job record carries project/team/conversation/run/parent IDs, kind, timestamps, current state, output cursor, result/exit code, and supported actions. Parent/child links connect agents, tool calls, and launched processes. Derive displayed counts without double-counting a tool and the process it launched.

#### Controls, output, and notifications

- View output, Open origin, Open file/browser, and Stop appear where supported. Retry creates a new attempt linked to the old one and is an explicit user action; do not automatically rerun side effects.
- Stop job, stop agent/run, and stop all work are different scopes. Name the actual scope on the control. A stopped parent must report whether its children continue; never assume cancellation propagated.
- Show stop progress and server-confirmed outcome; retain logs and partial file changes. If a stop fails, keep the job visible with an inline error.
- Stream output incrementally with a bounded client buffer and server pagination/cursor for older output. Provide stdout/stderr distinction, search, copy, and supported download; display truncation explicitly. Treat terminal escapes and tool text as untrusted display data.
- Auto-follow logs only while the user is at their end. Pausing to read preserves position; “New output” restores following. Avoid a separate spinner for every line or repeated chat messages for heartbeat events.
- Use determinate progress only when actual units/total are reported. Otherwise show a plain running label and elapsed time. Show last update separately so quiet long-running work is not automatically declared stuck.
- Ordinary progress stays quiet. Completion produces one compact result at the origin and updates Recent activity. Notify for work completed while the user is elsewhere, actionable failure, or required input; deduplicate by event/job ID. Persistent services do not repeatedly announce that they are still running.
- On reconnect/reload, reconcile an authoritative job snapshot and events after its cursor. For backend restart without durable job recovery, show “Status unavailable after restart” and offer supported reconciliation; no endless invented spinner.

### 3.9 Thoughts, progress, tool calls, and results: one presentation language

| Content | Default UI | Expanded UI / rules |
| --- | --- | --- |
| User-facing progress | Brief text such as “Checking the request flow” within the active turn | Keep useful updates; coalesce repetitive progress. Do not create a new large message for each tick. |
| Thinking without supplied text | Quiet “Thinking” activity state | No fabricated explanation or percentage; transition according to real events. |
| Provider-supplied reasoning summary | Collapsed “Reasoning summary” disclosure | Show only content provided and intended for display; keep separate from progress and tool output. No inferred hidden reasoning. |
| Tool awaiting permission | Pending tool row linked to an approval card | Clearly proposed, with exact payload available; not yet executed. |
| Running tool | Present-tense row, target, elapsed time | Arguments, working directory, live output, child job link, supported stop action. |
| Successful tool | Compact completed row with actual result summary | Full details on demand; derive success and counts from results, not input or optimistic titles. |
| Failed/cancelled tool | Distinct text/icon state that remains discoverable | Error, partial output, exit code, affected files, and available recovery. Do not hide failures inside a success-only group. |
| Delegation | “Agent name · task · state” disclosure | Child activity and outcome; independent agents do not flood the main prose stream. |
| File mutation | Concise linked change row | Actual diff in review; proposed/applied/failed/reverted state remains explicit. |
| Final assistant response | Spacious readable prose | Tool history remains attached to the turn; background work and unverified checks remain visibly unresolved. |

Use a small shared family: `ActivityGroup`, `ActivityRow`, `ReasoningDisclosure`, `JobSummary`, `JobDetails`, and `OutputViewer`, alongside the approval/question/change components. Consolidate existing `ThoughtsPanel`, reasoning parsers, `AgentActivityStream`, and process cards into these renderers. Keep legacy parsing only in the compatibility adapter; new UI should not detect execution state from emoji, prose fragments, regex-stripped JSON, or words such as “Executed”.

Default hierarchy: assistant prose first; one compact activity group per turn; unresolved requests visibly available; logs and supplied reasoning behind disclosures. Active state uses a modest indicator and completed state uses subdued text/icons. Reserve stronger color for actionable errors or pending decisions. Preserve expansion choices while streaming and when changing panes; never auto-collapse content the user is reading.

Suggested interaction example:

```text
I’m checking how requests are handled.

▾ Working · 2 tools complete · 1 background job
  ✓ Read ChatInterface.tsx
  ✓ Read useWebSocket.ts
  ◌ Running frontend checks · 34s                 [View output]
  ▸ Reasoning summary                            (if supplied)

The request handling changes are ready to review.
▸ Changes · 3 files                               [Review]
◌ Checks still running                            [View job]

After the job actually completes:
✓ Frontend checks passed · 52s                     [View output]
```

The example is a proposed state fixture, not a claim that changes or checks have been run. If checks fail, the last row must instead show failure and a linked result; the earlier response cannot override the job outcome.

### 3.10 Additional acceptance checks for background activity

- A command launches a child process and returns: child remains Running until its own terminal event.
- A final assistant response arrives while two workers continue: both remain visible and independently stoppable where supported.
- A development server is ready and stays alive: UI shows Ready/Running without claiming the server has completed.
- A background job requests approval while the user is in Settings: workspace indicator exposes the request and links to its origin without forcing navigation.
- A parent is cancelled while a child continues: each state and cancellation scope is displayed accurately.
- A process exits between snapshot fetch and subscription: cursor reconciliation captures the terminal event exactly once.
- A PID is reused: the prior job is not updated or stopped by mistake.
- Output arrives quickly or has long lines/terminal escapes: UI remains responsive, bounded, and safe to render; scroll position is preserved.
- A failed command with partial file changes retains both error and review links.
- A quiet service, stale connection, failed job, and waiting-for-input job have distinct labels.
- Opening/closing activity and switching views never starts, stops, or repeats work by itself.
- Tool titles use “Reading/Running/Updating” during execution and accurate past-tense results only after acknowledgment; unknown changed-line counts remain unknown.

## 4. Page-by-page work plan

All pages receive consistent loading, empty, error/retry, permission-denied, stale-data, and success states. Maintain project/team scope visibly and preserve drafts during navigation.

| Surface and source | Planned changes | Acceptance condition |
| --- | --- | --- |
| Workspace shell — `app/page.tsx`, `Sidebar.tsx` | Group navigation into Workspace, Knowledge, Extensions, Settings; make project/team switchers searchable; show recent conversations when supported; move floating fullscreen control into a predictable header; reflect view and context in the URL. | Back/forward and refresh restore selection; a team switch cannot display the previous team's late response; narrow layout has a usable navigation drawer. |
| Chat — `ChatInterface.tsx` and request cards | Implement section 3; spacious prose, subdued activity, independent requests, reliable composer, contextual review. | User can send, approve/answer, inspect changes, and continue with reconnect/failure recovery. |
| Tasks — `KanbanBoard.tsx`, `TaskDetailModal.tsx` | Add list/board switch, filtering by agent/status/priority, explicit blockers, direct links to originating conversation and plan; provide keyboard status movement; replace ignored save/comment errors with retained drafts. | Create/edit/move failures are visible and reversible; plan state agrees with chat. |
| Scheduled tasks — `CronTaskModal.tsx`, scheduling portion of Kanban | Human-readable schedule with timezone, next run, enabled state, last outcome; guided common schedules and an advanced cron editor; separate immediate execution from saving a schedule. | Preview uses server schedule semantics, including timezone/DST; failed save retains form values. |
| Agents — `AgentPanel.tsx`, `AccessControlMatrix.tsx`, avatar/hover components | Prefer scannable roster rows with role/model/status/current task; details in a drawer; distinguish configuration from live runtime; explain inherited versus overridden permissions; expose save failures. | Agent state and stop actions agree with chat; edits retain values and show validation errors. |
| Swarm topology — `WorkflowDAGCanvas.tsx` | Place under Agents as an advanced view or grouped destination; add legend, fit/zoom, selected-agent detail, last updated status, and accessible list alternative; integrate live state or label snapshots. | Large teams remain navigable; loading failure is distinct from no agents; graph selection opens useful task/activity context. |
| Code graph — `CodeGraphVisualizer.tsx` | Search paths/symbols, filter node types, reveal dependencies for selection, fit/zoom, Open file action, indexing/refresh status, list fallback. | Selection can navigate to source; empty project, indexing, stale data, and request error are distinguishable. |
| Browser — `BrowserView.tsx` | Distinguish live view from history; show agent/session owner, URL, connection state, and timestamp; consolidate controls; explicit Take control/Return to agent flow; show action errors near controls. | User never sends input believing a historical screenshot is live; failed takeover does not appear active. |
| Memory — `MemoryView.tsx` | Separate learnings, entity memory, and maintenance; searchable scope/source/updated information; readable detail drawer; explain Dream action and show operation outcome; clear targeted delete/purge scope. | Project/team memory boundaries are clear; empty results differ from failed load; edits and purge results reconcile. |
| Scratchpad — `ScratchpadPanel.tsx` | Keep existing shared/personal organization and remote-edit detection; add clear draft/saving/saved/conflict states, compare remote version, and preserve draft on switch. | Agent updates cannot silently overwrite a user draft; save conflict offers a recovery choice. |
| Plugins — `PluginStudio.tsx` | Library/editor split; explicit built-in read-only versus custom editable tools; unsaved indicator and draft protection; generated code preview; distinguish saving from runtime loading. | Switching files retains or explicitly discards edits; load failures are visible even if writing the file succeeded. |
| Skills — `SkillsStudio.tsx` | Unified searchable list with source/scope/enabled badges; clear discovered versus team-custom distinction; preview instructions and tools; consistent builder/raw editor; upload validation and draft preservation. | User knows whether edits affect team, project, or global skill; failed toggle restores prior state. |
| MCP — `McpIntegration.tsx`, `McpStatusIndicator.tsx` | Server rows with scope, connection state, tool count, last error; details for configuration and diagnostics; one shared status source; clear inherited/global versus team ownership. | Connect/reload/remove has acknowledged progress and retry; stale status is labeled; secrets are not shown in routine diagnostics. |
| Settings — `SettingsPanel.tsx`, `settings/*` | Search actual fields, retain URL section, use consistent save bar and dirty state; separate account/global/project/team scopes; follow subsection plan below. | Deep links open the requested section; failed loads cannot be mistaken for saved defaults. |
| Landing — `LandingPage.tsx`, showcase/animation components, CSS module | Establish one primary launch CTA; favor an actual product workflow demonstration; reduce competing animation and content density; align with new workspace identity; audit claims against implemented behavior before changing copy. | Keyboard/touch navigation works, reduced-motion mode is calm, and marketing assets do not load in the signed-in workspace unnecessarily. |
| Authentication — `AuthModal.tsx`, `AuthPage.tsx`, `hooks/useAuth.tsx` | Consolidate active login/signup experience; clear validation and submission states, password manager support, retained fields, focus management, session-expired recovery; establish whether standalone AuthPage is still needed. | Login failure preserves input; dialog closes/returns focus correctly; expired sessions return users to their work after authentication. |

### Supporting work panes and overlays

| Surface | Planned changes and validation |
| --- | --- |
| File explorer/editor — `FileExplorerPanel.tsx` | Searchable tree, clear project root, keyboard navigation, predictable tabs, dirty indicators, save/conflict state, external change reconciliation, large/binary handling. Preserve open files and drafts while toggling review. Validate concurrent agent/user edits. |
| Git — `GitPanel.tsx` | Distinguish staged/unstaged/untracked; inspect diffs before destructive discard; clear repository identity, commit validation, progress/errors for remote operations. Refresh status after successful mutations. Label working-tree changes separately from turn changes. |
| Search — `SearchPanel.tsx` | Visible search action, keyboard navigation, highlighted matches, result counts and query scope; pass line information when opening a result, not only file path. Guard late responses from previous queries/projects. |
| Terminal — `TerminalPanel.tsx` | Session/working-directory identity, connection status, reconnect and session-ended states, accessible fallback output, predictable resize and focus. Distinguish stop process from closing the pane. |
| Processes — `TaskManagerPanel.tsx`, `AgentActivityStream.tsx` | Stable process/run identity, elapsed time and exit status; acknowledgment for kill/stop actions; avoid independent polling sources disagreeing with chat state. |
| File activity — `ActivityLogPanel.tsx` | Scope/time/actor filtering, details linked to a change or file, visible load/delete errors, empty state. Keep audit history separate from user-facing conversation summaries. |
| Plan review — `ImplementationPlanModal.tsx`, `InChatPlanCard.tsx` | Shared revision state, readable Markdown, comments tied to revisions, clear errors, retained feedback, consistent approval status in every entry point. |
| Notifications — `NotificationBell.tsx`, `Toast.tsx` | Actionable notifications link to their subject; derive pending counts from actual request state; toasts supplement inline errors; manage announcement priority and avoid duplicate notices. |
| Context/cost — `ContextUsageGauge.tsx` | Compact default, details on demand; distinguish context occupancy from billed usage; display unknown/stale rather than zero; explain compaction with its acknowledged outcome. |
| Loading/errors/shortcuts — `LoadingScreen.tsx`, `ErrorBoundary.tsx`, `KeyboardShortcutsModal.tsx`, `Modal.tsx` | Real loading phases rather than timer-based claims; route/pane-level recovery; one shortcut registry; focus-safe dialogs, Escape handling, and consistent help. |

### Settings subsection detail

1. **General & Health:** separate profile/account connection tasks from diagnostics. Display backend/WebSocket health and last check independently; failed health requests must not look healthy. Preserve Google connection feedback.
2. **API Keys & Providers:** masked values, explicit configured/missing status, provider-specific validation, retained edits on failure. Connection testing requires an actual endpoint; distinguish key saved from provider reachable. Do not interpret failed configuration loading as blank saved credentials.
3. **Models & Catalog:** searchable provider/model selector, clear role defaults and fallback order, unavailable model handling, validated catalog edits. Confirm reset scope and show a before/after preview where practical.
4. **Observability:** separate high-level health/latency from trace inspection; add run/agent/time filters and links to conversation/tool activity. Show unavailable telemetry explicitly; distinguish clear-data progress from completion.
5. **Safety & Runtime:** explain policy inheritance and effective behavior with concrete action examples; separate access decisions from limits/compaction. Show which scope is being saved; keep independent save failures visible.
6. **Prompts & Capabilities:** readable preview plus source editing, per-block dirty indicators, targeted reset, revision/conflict support when available. Maintain drafts when switching roles or blocks.
7. **Browser Automation:** group connection, engine, and advanced settings; show effective configuration, test result if supported, and field errors. Replace internal jargon in primary labels with task-oriented language.
8. **Project, Cost & Danger:** separate Usage & budget, Knowledge files, and Deletion into clear subsections. Show upload/ingestion states separately; use server budget enforcement status; deletion describes exact project/team/content scope.

## 5. Backend dependencies and boundaries

| Contract | Why it is needed | Frontend fallback before delivery |
| --- | --- | --- |
| Message acknowledgment and idempotent client IDs | Reliable retry without duplicate execution. | Preserve draft; expose unconfirmed delivery; no automatic replay. |
| Stable run/turn/tool/event IDs and replay cursor | Parallel execution, deduplication, reconnect recovery. | Adapt legacy events with documented limitations; reconcile snapshots. |
| Authoritative approval outcomes, expiry, scope, feedback | Accurate decisions, recovery, and expiry display. | Approve once/Deny only; no invented countdown or persistent permission scope. |
| Pending-question snapshot and structured answers | Reload recovery and multi-question correctness. | Retain local answer draft, but do not claim restart recovery without server state. |
| File before/after snapshots or revision IDs | Accurate per-turn diffs and conflict-aware restore. | Label available working-tree/full-content previews honestly. |
| Plan revision and structured proceed action | Approval applies to exactly the reviewed plan. | Show current plan status; avoid pretending a generic message is a transactional start. |
| Run-specific cancellation and queue actions | Stop/steer/queue semantics users can trust. | Expose only supported stop scope and avoid unsupported queue controls. |
| Durable conversation identity/history | Recent conversations and per-conversation drafts beyond team rooms. | Keep the current team-room model explicit; do not invent sessions only in the sidebar. |
| Stable background-job identity, parent links, snapshots, output cursor, readiness and cancellation scope | Jobs outlive tool calls and pages; process IDs and result-text parsing cannot guarantee lifecycle correctness. | Display known running work with freshness labels; no inferred completion/readiness or unsupported cancellation controls. |

Audit and reuse existing backend behavior before adding endpoints. Approval persistence currently includes in-memory structures; frontend local storage alone cannot guarantee recovery after a backend restart. Decide retention and restart semantics as part of the protocol work.

## 6. Delivery sequence and reviewable milestones

| Milestone | Work | Dependencies | Exit criteria |
| --- | --- | --- | --- |
| M0 — Baseline and fixtures | Record current routes/states; capture desktop and narrow screenshots; create representative event fixtures; agree tokens and conversation composition. | None. | Reviewed spacious-chat mock/state fixture, inventory, and contract gap list. |
| M1 — Reliability fixes | Fix send loss, false approval success, question acknowledgment, rollback recovery, pending detection, ticket retry, and context-switch races. | Minimal API outcome fixes for authoritative approvals. | All failure/reconnect request scenarios below pass in the existing UI. |
| M2 — Chat foundation | Extract typed adapter/reducer/selectors; stable turn/tool/request/background-job state; parent-child identity; snapshot merge; feature flag and legacy-history support. | IDs/acknowledgment/job contracts where needed. | Recorded interleaved events replay deterministically without lost requests, orphaned jobs, false completion, or duplicate sends. |
| M3 — Spacious chat | Build conversation header, prose timeline, grouped tools, supplied-reasoning disclosure, composer, pending bar, approval/question cards, run status, workspace activity indicator and job drawer. | M1/M2 and shared tokens/primitives. | Main coding workflow and continuing background work are readable and fully keyboard usable in both themes and narrow layouts. |
| M4 — Review and plans | Correct diff parsing, immutable change references, review pane, plan revision flow, restore preview and reconciliation. | File/plan/restore contracts. | Displayed diff matches selected change; failed restore leaves a truthful recoverable UI. |
| M5 — Shell and daily work | Navigation/URL state, tasks/schedules, agents, files/Git/search/terminal, browser. | Shared primitives; chat navigation links. | Navigation preserves drafts and context; all daily-work mutations expose outcome and recovery. |
| M6 — Knowledge and configuration | Memory, scratchpad, skills/plugins/MCP, all settings sections, graphs. | Shared forms and async state conventions. | Scope, dirty state, stale state, save errors, and recovery work consistently. |
| M7 — Public experience and final validation | Landing/auth, reduced-motion behavior, long-history profiling, accessibility and visual regression pass. | Stable application direction. | Acceptance matrix passes; measured regressions resolved; feature flag rollout decision documented. |

Use milestone-sized changes rather than a whole-frontend rewrite. Reserve the greatest implementation effort for M1–M4. Timing should be estimated after M0 confirms protocol gaps; the current code review does not justify a precise calendar promise.

Suggested first three implementation changes:

1. **Prevent false request outcomes:** acknowledged submission interface, retained drafts, surfaced approval errors, controlled question responses, authoritative missing-approval status.
2. **Separate durable chat state from message rendering:** reducer fixtures, independent approvals/questions/tool calls, correct pending selector, snapshot reconciliation and context guards.
3. **Ship the spacious conversation surface:** common tokens, narrow readable column, compact activity, pending-action bar, composer, and review entry point.

## 7. Verification and definition of done

Add a frontend behavioral test setup: reducer tests, component interaction tests, and browser integration tests. The inspected `package.json` provides dev/build/start/lint scripts but no frontend test script. Select tools during implementation; run existing lint/build and establish pre-existing failures before attributing regressions.

Required scenarios:

- Offline send, dropped acknowledgment, reconnect, duplicate server echo, delayed old-team response, and history/live-event interleaving.
- Approval while streaming, two approvals from the same agent, failure/timeout/denial, resolution in another tab, server restart, and final-message replacement.
- Single/multiple/free-text question answers, duplicate question labels, failed submission, skip, refresh, and agent cancellation while input is open.
- Tool start/progress/end interleaving, out-of-order events, unavailable output, command failure, and cancellation acknowledgment.
- Added/modified/deleted/renamed/binary files, multiple diff hunks, paths with spaces/Unicode, repeated edits, missing base, and user changes after checkpoint.
- Plan edited after approval, failed plan save/comment, stale revision approval, and task/chat state agreement.
- Attachment failure, draft navigation, IME Enter, large paste, expired authentication, settings load failure, and editor conflict.
- Keyboard-only send/approve/deny/answer/review; focus containment/return; meaningful screen-reader announcements; reduced motion and both themes.

Proposed performance/visual targets, to measure rather than assume:

- Fixture with 1,000 historical messages, 100 tool events, and 50 changed files remains usable while streaming; active typing should not wait on full-history Markdown rendering.
- Test 1440px desktop, 1024px compact desktop, and 390px narrow layout, plus 200% zoom. No page-level horizontal clipping; code and diff regions may scroll internally.
- Measure input latency, stream commit cost, and bundle loading against M0. Aim for under 100ms local interaction response on the agreed test machine, separating backend/network wait.
- No fake success, invented diff, hidden actionable request, or lost draft in the required scenarios.
- A user can answer four questions from the main conversation: What is happening? Does it need me? What changed? Did verification succeed?

Review the finished implementation in one batched desktop/narrow visual pass, fix the collected defects together, then run one confirmation pass. Validate behavior with targeted automated checks rather than repeated cosmetic review.

## 8. Decisions to preserve during implementation

- Selected direction: spacious conversation first; review and tools remain readily accessible through progressive disclosure.
- Preserve the multi-agent/team model unless a separate product decision changes it.
- Preserve real existing capabilities, including scratchpad conflict detection and current resizable panes; consolidate rather than duplicate them.
- No UI-only claims about reliable delivery, durable approvals, persistent permissions, exact diffs, or transactional rollback.
- Open product decisions: team room versus multiple durable conversations; approval retention after restart; supported review/restore granularity; scope of mobile editing. Use the fallbacks in section 5 until those are settled.

This plan is ready for review and implementation in milestone order. No application behavior has been changed by this planning deliverable.
