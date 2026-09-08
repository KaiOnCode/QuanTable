"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { strategiesApi } from "@/lib/api/strategies";

export const DEFAULT_STRATEGY_ID = "default";

const EMPTY_STRATEGIES = [] as const;

export function useStrategyIdentity() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [selectedStrategyId, setSelectedStrategyId] = useState(DEFAULT_STRATEGY_ID);
  const [historicalStrategyId, setHistoricalStrategyId] = useState<string | null>(null);
  const initialized = useRef(false);
  const strategiesQuery = useQuery({
    queryKey: ["strategies"],
    queryFn: () => strategiesApi.list(),
  });
  const strategies = strategiesQuery.data?.items ?? EMPTY_STRATEGIES;
  const realStrategyIds = useMemo(
    () => new Set(strategies.map((strategy) => strategy.id)),
    [strategies],
  );
  const urlStrategyId = searchParams.get("strategy_id");
  const validatedUrlStrategyId =
    urlStrategyId === DEFAULT_STRATEGY_ID ||
    (urlStrategyId !== null && realStrategyIds.has(urlStrategyId))
      ? urlStrategyId
      : null;

  const replaceUrlIdentity = useCallback(
    (strategyId: string) => {
      if (searchParams.get("strategy_id") === strategyId) return;
      const params = new URLSearchParams(searchParams.toString());
      params.set("strategy_id", strategyId);
      router.replace(`/quick-ask?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  useEffect(() => {
    if (!strategiesQuery.isSuccess || initialized.current) return;
    initialized.current = true;
    setSelectedStrategyId(
      validatedUrlStrategyId ?? strategies[0]?.id ?? DEFAULT_STRATEGY_ID,
    );
  }, [strategies, strategiesQuery.isSuccess, validatedUrlStrategyId]);

  const selectStrategy = useCallback(
    (strategyId: string) => {
      setHistoricalStrategyId(null);
      setSelectedStrategyId(strategyId);
      replaceUrlIdentity(strategyId);
    },
    [replaceUrlIdentity],
  );

  const restoreStrategy = useCallback(
    (snapshotStrategyId?: string) => {
      initialized.current = true;
      const restoredId =
        validatedUrlStrategyId ??
        snapshotStrategyId ??
        strategies[0]?.id ??
        DEFAULT_STRATEGY_ID;
      setHistoricalStrategyId(
        restoredId !== DEFAULT_STRATEGY_ID && !realStrategyIds.has(restoredId)
          ? restoredId
          : null,
      );
      setSelectedStrategyId(restoredId);
      replaceUrlIdentity(restoredId);
    },
    [realStrategyIds, replaceUrlIdentity, strategies, validatedUrlStrategyId],
  );

  const selectedStrategyLabel =
    selectedStrategyId === DEFAULT_STRATEGY_ID
      ? "Default"
      : strategies.find((strategy) => strategy.id === selectedStrategyId)?.name ??
        `Deleted strategy (${selectedStrategyId})`;

  return {
    strategies,
    strategiesQuery,
    selectedStrategyId,
    selectedStrategyLabel,
    historicalStrategyId,
    selectStrategy,
    restoreStrategy,
  };
}
