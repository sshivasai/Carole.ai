import type { ChatMessage } from "../../lib/types";

const resolvedStatuses = new Set(["approved", "denied", "expired", "cancelled", "superseded"]);

/** Receipts may update the outer message before the nested request is replaced. */
export function approvalStatus(message: ChatMessage): string {
  const nested = message.pending_approval?.status;
  if (nested && resolvedStatuses.has(nested)) return nested;
  if (message.status && resolvedStatuses.has(message.status)) return message.status;
  return nested || message.status || "pending";
}

export function isPendingApproval(message: ChatMessage): boolean {
  return Boolean(message.pending_approval || message.type === "approval_request") && !resolvedStatuses.has(approvalStatus(message));
}
