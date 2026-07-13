"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import {
  activeInsightGenerationId,
  parseInsightGenerationId,
  type InsightGenerationPersistenceStatus,
} from "@/lib/insight-generation-state";

const LAST_GENERATION_ID_KEY = "agentic-quant:last-insight-generation-id";
const GENERATION_ID_CHANGED_EVENT = "agentic-quant:insight-generation-id-changed";

function subscribeToSessionStorage(onStoreChange: () => void): () => void {
  window.addEventListener(GENERATION_ID_CHANGED_EVENT, onStoreChange);
  return () => window.removeEventListener(GENERATION_ID_CHANGED_EVENT, onStoreChange);
}

function getStoredGenerationId(): string | null {
  return parseInsightGenerationId(sessionStorage.getItem(LAST_GENERATION_ID_KEY));
}

function getServerGenerationId(): null {
  return null;
}

function setStoredGenerationId(generationId: string | null): void {
  if (generationId === null) {
    sessionStorage.removeItem(LAST_GENERATION_ID_KEY);
  } else {
    sessionStorage.setItem(LAST_GENERATION_ID_KEY, generationId);
  }
  window.dispatchEvent(new Event(GENERATION_ID_CHANGED_EVENT));
}

export function usePersistedInsightGenerationId() {
  const storedGenerationId = useSyncExternalStore(
    subscribeToSessionStorage,
    getStoredGenerationId,
    getServerGenerationId,
  );
  const [createdGenerationId, setCreatedGenerationId] = useState<string | null>(
    null,
  );

  useEffect(() => {
    const rawGenerationId = sessionStorage.getItem(LAST_GENERATION_ID_KEY);
    if (
      rawGenerationId !== null &&
      parseInsightGenerationId(rawGenerationId) === null
    ) {
      setStoredGenerationId(null);
    }
  }, []);

  const persistGenerationId = useCallback(
    (generationId: string, status: InsightGenerationPersistenceStatus) => {
      const parsedGenerationId = parseInsightGenerationId(generationId);
      if (parsedGenerationId === null) {
        throw new Error("Invalid insight generation ID returned by the server.");
      }
      setCreatedGenerationId(parsedGenerationId);
      setStoredGenerationId(
        activeInsightGenerationId(parsedGenerationId, status),
      );
    },
    [],
  );

  const syncGenerationStatus = useCallback(
    (generationId: string, status: InsightGenerationPersistenceStatus) => {
      const parsedGenerationId = parseInsightGenerationId(generationId);
      if (parsedGenerationId === null) return;
      if (status === "completed" || status === "failed") {
        setCreatedGenerationId(parsedGenerationId);
      }
      const nextStoredGenerationId = activeInsightGenerationId(
        parsedGenerationId,
        status,
      );
      if (nextStoredGenerationId !== getStoredGenerationId()) {
        setStoredGenerationId(nextStoredGenerationId);
      }
    },
    [],
  );

  return {
    generationId: createdGenerationId ?? storedGenerationId,
    persistGenerationId,
    syncGenerationStatus,
  } as const;
}
