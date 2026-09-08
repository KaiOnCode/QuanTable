import assert from "node:assert/strict";
import test from "node:test";

import {
  encodeBacktestIdPathSegment,
  persistedBacktestRoute,
  nextStoredBacktestId,
  parseBacktestId,
  resolveBacktestId,
} from "../lib/backtest-id.ts";

const ACTIVE_ID = "0123456789abcdef0123456789abcdef";
const OTHER_ID = "fedcba9876543210fedcba9876543210";

test("accepts only server-shaped backtest IDs", () => {
  assert.equal(parseBacktestId(ACTIVE_ID), ACTIVE_ID);
  assert.equal(parseBacktestId("../../settings"), null);
  assert.equal(parseBacktestId(ACTIVE_ID.toUpperCase()), null);
  assert.equal(parseBacktestId("a".repeat(10_000)), null);
  assert.equal(parseBacktestId(null), null);
});

test("an explicit valid URL ID is authoritative", () => {
  assert.equal(resolveBacktestId(OTHER_ID, ACTIVE_ID, ACTIVE_ID), OTHER_ID);
  assert.equal(resolveBacktestId("../../settings", null, ACTIVE_ID), ACTIVE_ID);
});

test("only an active job replaces the persisted running pointer", () => {
  assert.equal(nextStoredBacktestId(ACTIVE_ID, OTHER_ID, "running"), OTHER_ID);
  assert.equal(nextStoredBacktestId(ACTIVE_ID, OTHER_ID, "pending"), OTHER_ID);
  assert.equal(nextStoredBacktestId(ACTIVE_ID, OTHER_ID, undefined), ACTIVE_ID);
});

test("terminal jobs clear only their matching persisted pointer", () => {
  assert.equal(nextStoredBacktestId(ACTIVE_ID, ACTIVE_ID, "completed"), null);
  assert.equal(nextStoredBacktestId(ACTIVE_ID, ACTIVE_ID, "failed"), null);
  assert.equal(nextStoredBacktestId(ACTIVE_ID, OTHER_ID, "failed"), ACTIVE_ID);
  assert.equal(nextStoredBacktestId(ACTIVE_ID, ACTIVE_ID, "not_found"), null);
});

test("a restored active pointer is promoted into the URL", () => {
  assert.equal(persistedBacktestRoute(null, ACTIVE_ID), `/backtest?backtest_id=${ACTIVE_ID}`);
  assert.equal(
    persistedBacktestRoute("../../settings", ACTIVE_ID),
    `/backtest?backtest_id=${ACTIVE_ID}`,
  );
  assert.equal(persistedBacktestRoute(ACTIVE_ID, OTHER_ID), null);
  assert.equal(persistedBacktestRoute(null, null), null);
});

test("API path segments reject traversal and oversized values", () => {
  assert.equal(encodeBacktestIdPathSegment(ACTIVE_ID), ACTIVE_ID);
  assert.throws(() => encodeBacktestIdPathSegment("../../settings"), /Invalid backtest ID/);
  assert.throws(() => encodeBacktestIdPathSegment("a".repeat(10_000)), /Invalid backtest ID/);
});
