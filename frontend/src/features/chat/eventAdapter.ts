/**
 * Event Adapter: Normalizes raw WebSocket events into clean domain records.
 */

import type { WSEvent, ChatMessage } from "@/lib/types";
import type { ApprovalRecord, QuestionRecord, ToolCallRecord, BackgroundJobRecord } from "./types";

export function normalizeApprovalEvent(evt: WSEvent): ApprovalRecord {
  return {
    tx_id: evt.tx_id || `tx_${Date.now()}`,
    agent_id: evt.agent_id || evt.sender_id || "agent",
    agent_name: evt.agent_name || evt.sender_name || "Agent",
    tool_name: evt.tool_name || "action",
    arguments: evt.arguments || {},
    text: evt.text || "",
    reason: evt.reason || "",
    status: "pending",
    created_at: typeof evt.timestamp === "number" ? evt.timestamp : Date.now(),
    expires_at: evt.expires_at ? (typeof evt.expires_at === "number" ? evt.expires_at : new Date(evt.expires_at).getTime()) : undefined,
  };
}

export function normalizeQuestionEvent(evt: WSEvent): QuestionRecord {
  return {
    question_id: evt.question_id || evt.id || `q_${Date.now()}`,
    agent_id: evt.sender_id || "agent",
    agent_name: evt.sender_name || "Agent",
    question: evt.question || evt.text || "",
    options: evt.options || [],
    questions: evt.questions,
    status: "pending",
    created_at: typeof evt.timestamp === "number" ? evt.timestamp : Date.now(),
  };
}

export function normalizeToolCall(evt: WSEvent): ToolCallRecord {
  return {
    id: evt.tool_call_id || evt.tx_id || `${evt.tool_name}_${Date.now()}`,
    tool_name: evt.tool_name || "unknown_tool",
    arguments: evt.arguments,
    status: "running",
    started_at: Date.now(),
  };
}
