"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import {
  nextStoredBacktestId,
  parseBacktestId,
  persistedBacktestRoute,
  resolveBacktestId,
  type BacktestJobStatus,
  type BacktestPersistenceStatus,
} from "@/lib/backtest-id";

const LAST_BACKTEST_ID_KEY = "agentic-quant:last-backtest-id";
const BACKTEST_ID_CHANGED_EVENT = "agentic-quant:backtest-id-changed";

function subscribeToSessionStorage(onStoreChange: () => void): () => void {
  window.addEventListener(BACKTEST_ID_CHANGED_EVENT, onStoreChange);
  return () => window.removeEventListener(BACKTEST_ID_CHANGED_EVENT, onStoreChange);
}

function getStoredBacktestId(): string | null {
  return parseBacktestId(sessionStorage.getItem(LAST_BACKTEST_ID_KEY));
}

function setStoredBacktestId(backtestId: string | null): void {
  if (backtestId) {
    sessionStorage.setItem(LAST_BACKTEST_ID_KEY, backtestId);
  } else {
    sessionStorage.removeItem(LAST_BACKTEST_ID_KEY);
  }
  window.dispatchEvent(new Event(BACKTEST_ID_CHANGED_EVENT));
}

function getServerBacktestId(): null {
  return null;
}

function getClientReady(): true {
  return true;
}

function getServerReady(): false {
  return false;
}

export function usePersistedBacktestId(queryBacktestId: string | null) {
  const storedBacktestId = useSyncExternalStore(
    subscribeToSessionStorage,
    getStoredBacktestId,
    getServerBacktestId,
  );
  const isRestored = useSyncExternalStore(
    subscribeToSessionStorage,
    getClientReady,
    getServerReady,
  );
  const [createdBacktestId, setCreatedBacktestId] = useState<string | null>(null);

  useEffect(() => {
    const rawStoredBacktestId = sessionStorage.getItem(LAST_BACKTEST_ID_KEY);
    if (rawStoredBacktestId !== null && !parseBacktestId(rawStoredBacktestId)) {
      setStoredBacktestId(null);
    }
  }, []);

  useEffect(() => {
    const restoredRoute = persistedBacktestRoute(queryBacktestId, storedBacktestId);
    if (restoredRoute) {
      window.history.replaceState(null, "", restoredRoute);
    }
  }, [queryBacktestId, storedBacktestId]);

  const persistBacktestId = useCallback(
    (backtestId: string, status: BacktestJobStatus) => {
      const parsedBacktestId = parseBacktestId(backtestId);
      if (!parsedBacktestId) {
        throw new Error("Invalid backtest ID returned by the server.");
      }
      const nextBacktestId = nextStoredBacktestId(
        getStoredBacktestId(),
        parsedBacktestId,
        status,
      );
      setStoredBacktestId(nextBacktestId);
      setCreatedBacktestId(parsedBacktestId);
      window.history.replaceState(
        null,
        "",
        `/backtest?backtest_id=${encodeURIComponent(parsedBacktestId)}`,
      );
    },
    [],
  );

  const syncBacktestStatus = useCallback((
    backtestId: string,
    status: BacktestPersistenceStatus,
  ) => {
    const parsedBacktestId = parseBacktestId(backtestId);
    if (!parsedBacktestId) return;
    if (status === "completed" || status === "failed") {
      setCreatedBacktestId(parsedBacktestId);
    }
    const currentStoredBacktestId = getStoredBacktestId();
    const nextBacktestId = nextStoredBacktestId(
      currentStoredBacktestId,
      parsedBacktestId,
      status,
    );
    if (nextBacktestId !== currentStoredBacktestId) {
      setStoredBacktestId(nextBacktestId);
    }
  }, []);

  return {
    backtestId: resolveBacktestId(queryBacktestId, createdBacktestId, storedBacktestId),
    isRestored,
    persistBacktestId,
    syncBacktestStatus,
  } as const;
}
