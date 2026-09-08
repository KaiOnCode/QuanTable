import assert from "node:assert/strict";
import test from "node:test";

import {
  displayBacktestError,
  isBacktestNotFoundError,
} from "../lib/backtest-api-error.ts";

test("projects a typed backtest API failure without exposing its raw JSON body", () => {
  const error = new Error(
    'HTTP 503: {"detail":{"code":"provider_capability_unsupported","message":"Experimental provider capability is unavailable"}}',
  );

  assert.equal(
    displayBacktestError(error),
    "Experimental provider capability is unavailable (provider_capability_unsupported)",
  );
  assert.doesNotMatch(displayBacktestError(error), /HTTP 503|\{"detail"/);
});

test("falls back safely for an untyped HTTP response while preserving not-found detection", () => {
  const error = new Error("HTTP 500: provider response body must not reach the UI");

  assert.equal(displayBacktestError(error), "The request could not be completed.");
  assert.equal(isBacktestNotFoundError(new Error("HTTP 404: {\"detail\":{}}")), true);
});
