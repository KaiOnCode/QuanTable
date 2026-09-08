import assert from "node:assert/strict";
import test from "node:test";

import {
  activeInsightGenerationId,
  createInsightGenerationId,
  parseInsightGenerationId,
} from "../lib/insight-generation-state.ts";

test("restores only a valid active insight generation id", () => {
  // Given: a persisted generation id and each backend lifecycle state.
  const id = "0123456789abcdef0123456789abcdef";

  // When: the frontend reconciles storage with backend status.
  const pending = activeInsightGenerationId(id, "pending");
  const running = activeInsightGenerationId(id, "running");
  const completed = activeInsightGenerationId(id, "completed");
  const failed = activeInsightGenerationId(id, "failed");

  // Then: active work survives remount while terminal work is cleared.
  assert.equal(pending, id);
  assert.equal(running, id);
  assert.equal(completed, null);
  assert.equal(failed, null);
  assert.equal(parseInsightGenerationId("../../etc/passwd"), null);
});

test("creates a client-owned generation id before the starting request", () => {
  // Given: generation has not yet received a server response.

  // When: the click handler allocates the reconnect identifier locally.
  const id = createInsightGenerationId();

  // Then: it is immediately valid for pending-state persistence and API use.
  assert.match(id, /^[0-9a-f]{32}$/);
  assert.equal(activeInsightGenerationId(id, "pending"), id);
});
