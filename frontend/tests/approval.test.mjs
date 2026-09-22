import test from "node:test";
import assert from "node:assert/strict";
import { approvalStatus, isPendingApproval } from "../src/features/chat/approval.ts";

const request = { id: "request", sender_id: "agent", text: "Run check", type: "approval_request" };
test("unresolved requests require attention but ordinary messages do not", () => {
  assert.equal(isPendingApproval(request), true);
  assert.equal(isPendingApproval({ ...request, type: "message" }), false);
});
for (const status of ["approved", "denied", "expired", "cancelled", "superseded"]) {
  test(`${status} receipts resolve both flat and nested approval messages`, () => {
    const message = { ...request, status, pending_approval: { tx_id: "tx", tool_name: "run", arguments: {}, text: "", status: "pending" } };
    assert.equal(approvalStatus(message), status);
    assert.equal(isPendingApproval(message), false);
    assert.equal(isPendingApproval({ ...request, status }), false);
    assert.equal(isPendingApproval({ ...message, status: "pending", pending_approval: { ...message.pending_approval, status } }), false);
  });
}
