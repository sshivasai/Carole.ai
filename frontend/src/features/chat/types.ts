/**
 * Normalized Chat Domain Types (Section 3.1 of Frontend Improvement Plan)
 */

export interface ToolCallRecord {
  id: string;
  tool_name: string;
  arguments?: Record<string, any>;
  status: "pending_approval" | "running" | "completed" | "failed" | "cancelled";
  started_at?: number;
  completed_at?: number;
  duration_ms?: number;
  observation?: string;
  error?: string;
  tx_id?: string;
}

export interface ApprovalRecord {
  tx_id: string;
  agent_id: string;
  agent_name?: string;
  tool_name: string;
  arguments?: Record<string, any>;
  text?: string;
  reason?: string;
  status: "pending" | "submitting" | "approved" | "denied" | "expired";
  feedback?: string;
  created_at: number;
  expires_at?: number;
  resolved_at?: number;
  error?: string;
}

export interface QuestionRecord {
  question_id: string;
  agent_id?: string;
  agent_name?: string;
  question: string;
  options?: string[];
  questions?: Array<{
    id?: string;
    question: string;
    options?: string[];
    is_multi_select?: boolean;
  }>;
  status: "pending" | "submitting" | "answered" | "skipped";
  answer?: string;
  created_at: number;
  error?: string;
}

export interface BackgroundJobRecord {
  id: string;
  name: string;
  type: "command" | "agent" | "browser" | "indexing" | "scheduled";
  agent_id?: string;
  agent_name?: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  started_at: number;
  completed_at?: number;
  elapsed_s?: number;
  output_summary?: string;
  turn_id?: string;
}

export interface FileChangeRecord {
  id: string;
  path: string;
  action: "create" | "modify" | "delete" | "rollback_restore";
  diff?: string;
  content?: string;
  additions?: number;
  deletions?: number;
  timestamp: number;
}
