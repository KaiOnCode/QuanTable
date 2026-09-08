const BACKTEST_ID_PATTERN = /^[0-9a-f]{32}$/;

export type BacktestJobStatus = "pending" | "running" | "completed" | "failed";
export type BacktestPersistenceStatus = BacktestJobStatus | "not_found";

export function parseBacktestId(value: string | null | undefined): string | null {
  return value !== null && value !== undefined && BACKTEST_ID_PATTERN.test(value)
    ? value
    : null;
}

export function resolveBacktestId(
  queryBacktestId: string | null,
  createdBacktestId: string | null,
  storedBacktestId: string | null,
): string | null {
  return (
    parseBacktestId(queryBacktestId) ??
    parseBacktestId(createdBacktestId) ??
    parseBacktestId(storedBacktestId)
  );
}

export function nextStoredBacktestId(
  storedBacktestId: string | null,
  selectedBacktestId: string,
  status: BacktestPersistenceStatus | undefined,
): string | null {
  if (status === "pending" || status === "running") {
    return selectedBacktestId;
  }
  if (
    (status === "completed" || status === "failed" || status === "not_found") &&
    storedBacktestId === selectedBacktestId
  ) {
    return null;
  }
  return storedBacktestId;
}

export function persistedBacktestRoute(
  queryBacktestId: string | null,
  storedBacktestId: string | null,
): string | null {
  if (parseBacktestId(queryBacktestId)) return null;
  const parsedStoredBacktestId = parseBacktestId(storedBacktestId);
  if (parsedStoredBacktestId) {
    return `/backtest?backtest_id=${encodeURIComponent(parsedStoredBacktestId)}`;
  }
  return queryBacktestId === null ? null : "/backtest";
}

export function encodeBacktestIdPathSegment(backtestId: string): string {
  const parsedBacktestId = parseBacktestId(backtestId);
  if (!parsedBacktestId) {
    throw new Error("Invalid backtest ID.");
  }
  return encodeURIComponent(parsedBacktestId);
}
