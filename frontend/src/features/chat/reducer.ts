/**
 * Deterministic Chat Reducer (Section 3.1 & P0/P1 of Plan)
 * Stores approvals, questions, and background jobs independently of message text arrays.
 */

import type { ChatMessage, WSEvent } from "@/lib/types";
import type { ApprovalRecord, QuestionRecord, BackgroundJobRecord, ToolCallRecord } from "./types";
import { normalizeApprovalEvent, normalizeQuestionEvent, normalizeToolCall } from "./eventAdapter";

export interface ChatState {
  messages: ChatMessage[];
  approvals: Record<string, ApprovalRecord>;
  questions: Record<string, QuestionRecord>;
  jobs: Record<string, BackgroundJobRecord>;
}

export const initialChatState: ChatState = {
  messages: [],
  approvals: {},
  questions: {},
  jobs: {},
};

export type ChatAction =
  | { type: "WS_EVENT"; event: WSEvent }
  | { type: "SET_MESSAGES"; messages: ChatMessage[] }
  | { type: "ROLLBACK_MESSAGES"; targetId: string }
  | { type: "RESOLVE_APPROVAL"; tx_id: string; status: "approved" | "denied" | "expired"; feedback?: string }
  | { type: "RESOLVE_QUESTION"; question_id: string; answer: string }
  | { type: "CLEAR_CHAT" };

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "SET_MESSAGES": {
      // Reconcile messages while preserving outstanding independent approvals and questions
      return {
        ...state,
        messages: action.messages,
      };
    }

    case "RESOLVE_APPROVAL": {
      const existing = state.approvals[action.tx_id];
      if (!existing) return state;
      return {
        ...state,
        approvals: {
          ...state.approvals,
          [action.tx_id]: {
            ...existing,
            status: action.status,
            feedback: action.feedback,
            resolved_at: Date.now(),
          },
        },
      };
    }

    case "RESOLVE_QUESTION": {
      const existing = state.questions[action.question_id];
      if (!existing) return state;
      return {
        ...state,
        questions: {
          ...state.questions,
          [action.question_id]: {
            ...existing,
            status: "answered",
            answer: action.answer,
          },
        },
      };
    }

    case "CLEAR_CHAT": {
      return {
        ...state,
        messages: [],
        approvals: {},
        questions: {},
        jobs: {},
      };
    }

    case "WS_EVENT": {
      const evt = action.event;
      const ts = typeof evt.timestamp === "number" ? evt.timestamp : Date.now();

      switch (evt.type) {
        case "approval_request": {
          if (!evt.tx_id) return state;
          const approval = normalizeApprovalEvent(evt);
          return {
            ...state,
            approvals: {
              ...state.approvals,
              [evt.tx_id]: approval,
            },
          };
        }

        case "approval_resolved": {
          if (!evt.tx_id) return state;
          const existing = state.approvals[evt.tx_id];
          if (!existing) return state;
          return {
            ...state,
            approvals: {
              ...state.approvals,
              [evt.tx_id]: {
                ...existing,
                status: evt.approved ? "approved" : "denied",
                resolved_at: ts,
              },
            },
          };
        }

        case "agent_question":
        case "ask_user": {
          const qRecord = normalizeQuestionEvent(evt);
          return {
            ...state,
            questions: {
              ...state.questions,
              [qRecord.question_id]: qRecord,
            },
          };
        }

        case "agent_question_answered": {
          const qId = evt.question_id;
          if (!qId || !state.questions[qId]) return state;
          return {
            ...state,
            questions: {
              ...state.questions,
              [qId]: {
                ...state.questions[qId],
                status: "answered",
                answer: evt.answer,
              },
            },
          };
        }

        default:
          return state;
      }
    }

    default:
      return state;
  }
}
