/**
 * Chat Selectors: Derives pending actions, active jobs, and summaries.
 */

import type { ChatState } from "./reducer";
import type { ApprovalRecord, QuestionRecord, BackgroundJobRecord } from "./types";

export function selectPendingApprovals(state: ChatState): ApprovalRecord[] {
  return Object.values(state.approvals).filter(a => a.status === "pending" || a.status === "submitting");
}

export function selectPendingQuestions(state: ChatState): QuestionRecord[] {
  return Object.values(state.questions).filter(q => q.status === "pending" || q.status === "submitting");
}

export function selectPendingActionCount(state: ChatState): number {
  return selectPendingApprovals(state).length + selectPendingQuestions(state).length;
}

export function selectActiveBackgroundJobs(state: ChatState): BackgroundJobRecord[] {
  return Object.values(state.jobs).filter(j => j.status === "running" || j.status === "queued");
}
