import test from "node:test";
import assert from "node:assert/strict";
import { agentContext } from "../src/features/chat/contextUsage.ts";

test("unknown context is not invented", () => {
  const result = agentContext();
  assert.equal(result.tokens, undefined);
  assert.equal(result.limit, undefined);
  assert.equal(result.percent, undefined);
});
test("provider input replaces the estimate for the same request only", () => {
  const snapshot = {call_id: "new", estimated_tokens: 200, context_window: 1000};
  const usage = {call_id: "new", prompt_tokens: 150, input_source: "provider"};
  assert.deepEqual(agentContext(snapshot, usage), {tokens: 150, limit: 1000, source: "reported", percent: 15});
  assert.equal(agentContext(snapshot, {...usage, call_id: "old"}).tokens, 200);
  assert.equal(agentContext(snapshot, {...usage, call_id: "old"}).source, "estimated");
  const missing = agentContext({call_id: "new"}, {...usage, call_id: "old", context_window: 1000});
  assert.equal(missing.tokens, undefined);
  assert.equal(missing.limit, undefined);
});
test("agent snapshots are independent and zero is a valid measurement", () => {
  assert.equal(agentContext({estimated_tokens: 0, context_window: 1000}).percent, 0);
  assert.equal(agentContext({estimated_tokens: 200, context_window: 1000}).percent, 20);
  assert.equal(agentContext({estimated_tokens: 500, context_window: 10000}).percent, 5);
});
