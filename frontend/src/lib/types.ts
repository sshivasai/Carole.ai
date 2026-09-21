/**
 * Shared TypeScript types for the Carole.ai frontend.
 * Used by page.tsx, useWebSocket.ts, and useApi.ts.
 */

// ---- Chat Messages ----
export interface ChatMessage {
  id: string;
  sender_id: string;
  sender_name?: string;
  recipient_id?: string;
  text: string;
  role?: string;
  type: string;
  timestamp?: string | number;

  // Tool execution fields
  tool_name?: string;
  arguments?: Record<string, any>;
  observation?: string;

  // File change fields
  path?: string;
  action?: string;
  diff?: string;

  // Approval fields
  tx_id?: string;
  status?: string;
  pending_approval?: {
    tx_id: string;
    tool_name: string;
    arguments: Record<string, any>;
    text: string;
    status?: string;
  };

  // Agent question & browser intervention fields
  question_id?: string;
  question?: string;
  options?: string[];  // multiple-choice options for ask_user tool
  questions?: Array<{
    id?: string;
    question: string;
    options?: string[];
    is_multi_select?: boolean;
  }>;
  is_answered?: boolean;
  answer?: string;
  reason?: string;
  captcha_image?: string;

  // Browser fields
  image_base64?: string;

  // Shell fields
  stream?: "stdout" | "stderr";

  // Thoughts / reasoning trace (from LLM thinking + tool calls)
  reasoning?: string;
  has_reasoning?: boolean;

  // Intermediate trace rows (tool calls inside a loop iteration).
  // When true, the UI should render this as a compact collapsed trace row, not a full chat bubble.
  is_intermediate?: boolean;

  // BYOK LLM Error details
  llm_error?: {
    error_type: string;
    provider: string;
    model: string;
    message: string;
    status_code?: number;
    action_hint: string;
    env_key_name: string;
  };
  attachments?: any[];
}

// ---- Compaction Events ----
// Represents a conversation compaction checkpoint rendered as a visible divider in the chat.
export interface CompactionEvent {
  id: string;
  triggered_by: 'auto' | 'manual' | 'emergency';
  message_count_before?: number;
  summary_preview?: string;
  created_at?: string;
}


// ---- Scheduled Task ----
export interface ScheduledTask {
  id: string;
  team_id: string;
  agent_id: string;
  name: string;
  cron_expression: string;
  prompt: string;
  is_active: boolean;
  last_run_at?: string;
  created_at: string;
}

// ---- Notification ----
export interface Notification {
  id: string;
  title: string;
  message: string;
  type: "info" | "success" | "warning" | "error";
  is_read: boolean;
  created_at: string;
}

// ---- Access Control ----

export type PermissionLevel = "allow" | "block" | "always_ask" | "judge";

export type ActionCategory =
  | "view" | "edit" | "create" | "delete"
  | "execute" | "git" | "web" | "browser"
  | "subagents" | "scheduler";

export interface SkipJudgeRules {
  file_patterns: string[];
  command_prefixes: string[];
}

export interface AccessControlConfig {
  /** Master on/off for the Judge LLM */
  enable_judge: boolean;
  /** Fallback gate when judge is disabled: "always_ask" | "allow" */
  judge_fallback: "always_ask" | "allow";
  /** Per-category permissions */
  categories: Record<ActionCategory, PermissionLevel>;
  /** Per-tool overrides (highest priority after runtime context) */
  overrides: Record<string, PermissionLevel>;
  /** Whitelist to skip judge without human review */
  custom_skip_judge: SkipJudgeRules;
}

// ---- Agent Configuration ----
export interface AgentConfig {
  id: string;
  name: string;
  role: string;
  role_template?: string;
  model: string;
  fallback_model?: string;
  reasoning_effort?: string;
  personality?: string;
  /** Structured AccessControlConfig or legacy flat {tool: level} map */
  tool_permissions?: AccessControlConfig | Record<string, string>;
  custom_instructions?: string;
  skills?: string[];
  /** If true, implementation plans written by this agent are auto-approved without admin review */
  auto_approve_plans?: boolean;
}

// ---- Task Board ----
export interface TaskItem {
  id: string;
  title: string;
  description?: string;
  status: string;
  priority: string;
  assigned_to?: string;
  assigned_agent_id?: string | null;
  parent_task_id?: string | null;
  blocked_by_task_id?: string | null;
  depends_on?: string[];
  created_by?: string;
  created_at?: string;
  // Implementation plan
  implementation_plan?: string;
  plan_file_path?: string;
  plan_status?: "draft" | "awaiting_approval" | "approved" | "revision_requested";
  plan_feedback?: string;
  todo_list?: TodoItem[];
  revision?: number;
  unread_comments_count?: number;
  is_watching?: boolean;
  watcher_count?: number;
}

export interface TodoItem {
  id: string;
  text: string;
  done: boolean;
}

export interface PlanInlineComment {
  id: string;
  line_index: number;
  author_id: string;
  author_name: string;
  text: string;
  resolved: boolean;
  created_at?: string;
}

export interface TaskComment {
  id: string;
  task_id?: string;
  author_id: string;
  author_name: string;
  text: string;
  created_at?: string;
}

export interface TaskActivity {
  id: string;
  task_id: string;
  team_id: string;
  actor_id: string;
  actor_name: string;
  activity_type: string;
  details: string;
  old_value?: any;
  new_value?: any;
  created_at?: string;
}

export interface TaskWatcher {
  id: string;
  task_id: string;
  user_id: string;
  created_at?: string;
}

export interface TaskReadCursor {
  id: string;
  task_id: string;
  user_id: string;
  last_read_at?: string;
}

export interface AgentNotificationPreference {
  agent_id: string;
  notify_on_assignment: boolean;
  notify_on_mention: boolean;
  notify_on_all_comments: boolean;
  muted_task_ids: string[];
}

export interface TaskMetricItem {
  id: string;
  task_id?: string;
  team_id: string;
  metric_name: string;
  metric_value: number;
  tags?: Record<string, any>;
  created_at?: string;
}

export interface TaskMetricsSummary {
  team_id: string;
  queue_delay_avg_seconds: number;
  duplicate_suppressions: number;
  task_completions: number;
  task_failures: number;
  wake_reason_distribution: Record<string, number>;
}

// ---- WebSocket Events ----
export interface WSEvent {
  type: string;
  sender_id?: string;
  sender_name?: string;
  role?: string;
  text?: string;
  delta?: string;
  status?: string;
  tool_name?: string;
  arguments?: Record<string, any>;
  observation?: string;
  tx_id?: string;
  question_id?: string;
  question?: string;
  options?: string[]; // multiple-choice options for ask_user
  task?: any;
  action?: string;
  // plan lifecycle
  plan_status?: string;
  plan_feedback?: string;
  // message_deleted
  message_id?: string;
  // message_rewind
  from_message_id?: string;
  from_timestamp?: string;
  restored_files?: string[];
  deleted_files?: string[];

  // stream_reasoning
  chunk?: string;
  has_reasoning?: boolean;

  // legacy/compatibility
  is_private?: boolean;
  recipient_id?: string;
  stream?: string;

  // File/browser/approval fields
  [key: string]: any;
}

// ---- Specialized Event Subtypes ----
export interface FileChangeEvent extends WSEvent {
  type: "file_change";
  path: string;
  action: string;
  diff: string;
  before_content?: string;
  after_content?: string;
}

export interface ApprovalRequestEvent extends WSEvent {
  type: "approval_request";
  tx_id: string;
  agent_id: string;
  agent_name: string;
  tool_name: string;
  arguments: Record<string, any>;
}

export interface BrowserScreenshotEvent extends WSEvent {
  type: "browser_screenshot";
  url: string;
  image_base64: string;
}

// ---- Agent Scratchpads ----
export interface ScratchpadItem {
  target: "team" | "personal";
  agent_name: string;
  agent_id?: string;
  label: string;
  content: string;
  updated_at?: string;
  size_bytes?: number;
}

// ---- Knowledge base Learnings ----
export interface LearningItem {
  id: string;
  task_summary: string;
  lesson_rule: string;
  team_id?: string;
  project_id?: string | null;
  created_at?: string;
}

// ---- Project / Team / User ----
export interface ProjectItem {
  id: string;
  name: string;
  owner_id: string;
  description?: string;
}

export interface TeamItem {
  id: string;
  name: string;
  project_id: string;
  description?: string;
}

export interface UserItem {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
}

// ---- Role Templates ----
export interface RoleTemplate {
  role: string;
  display_name: string;
  description: string;
  suggested_names: string[];
  personality: string;
  skills: string[];
  custom_instructions: string;
  recommended_model: string;
  recommended_permissions: Record<string, string>;
}

// ---- Auth ----
export interface AuthResponse {
  user: UserItem;
  token: string;
}

// ---- Notifications ----
export interface NotificationItem {
  id: string;
  user_id: string;
  title: string;
  message: string;
  type: string;
  is_read: boolean;
  created_at: string;
}

// ---- Prompt Blocks ----
export interface PromptBlock {
  key: string;
  display_name: string;
  description: string;
  category: string;
  enabled: boolean;
  content: string;
  default_content: string;
  is_customized: boolean;
}
