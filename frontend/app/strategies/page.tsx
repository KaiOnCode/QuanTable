"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/badges";
import { formatDate } from "@/lib/utils";
import { strategiesApi } from "@/lib/api/strategies";
import type { StrategyConfig } from "@/lib/types/models";
import {
  Plus,
  Search,
  MoreHorizontal,
  Play,
  Pause,
  Square,
  Copy,
  Trash2,
  Loader2,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

type LifecycleAction = "start" | "pause" | "stop";

type RowAction = {
  readonly strategyId: string;
  readonly action: LifecycleAction;
};

type RowError = {
  readonly strategyId: string;
  readonly message: string;
};

const lifecycleLabel = (action: LifecycleAction) => {
  switch (action) {
    case "start":
      return "active";
    case "pause":
      return "paused";
    case "stop":
      return "stopped";
  }
};

export default function StrategiesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [rowError, setRowError] = useState<RowError | null>(null);
  const [pendingRowCounts, setPendingRowCounts] = useState<Record<string, number>>({});

  const updatePendingRow = (strategyId: string, delta: 1 | -1) => {
    setPendingRowCounts((current) => {
      const nextCount = Math.max(0, (current[strategyId] ?? 0) + delta);
      if (nextCount === 0) {
        const remaining = { ...current };
        delete remaining[strategyId];
        return remaining;
      }
      return { ...current, [strategyId]: nextCount };
    });
  };

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["strategies", typeFilter, statusFilter],
    queryFn: () =>
      strategiesApi.list({
        type: typeFilter !== "all" ? typeFilter : undefined,
        status: statusFilter !== "all" ? statusFilter : undefined,
      }),
  });

  const strategies = data?.items ?? [];

  const deleteMutation = useMutation({
    mutationFn: (id: string) => strategiesApi.delete(id, true),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["strategies"] }),
  });

  const lifecycleMutation = useMutation({
    mutationFn: ({ strategyId, action }: RowAction) => {
      switch (action) {
        case "start":
          return strategiesApi.start(strategyId);
        case "pause":
          return strategiesApi.pause(strategyId);
        case "stop":
          return strategiesApi.stop(strategyId);
      }
    },
    onMutate: (variables) => updatePendingRow(variables.strategyId, 1),
    onSuccess: async (_result, variables) => {
      setRowError(null);
      toast.success(`Strategy marked ${lifecycleLabel(variables.action)}.`);
      await queryClient.invalidateQueries({ queryKey: ["strategies"] });
    },
    onError: (mutationError: Error, variables) => {
      setRowError({ strategyId: variables.strategyId, message: mutationError.message });
      toast.error(`Strategy update failed: ${mutationError.message}`);
    },
    onSettled: (_result, _error, variables) => updatePendingRow(variables.strategyId, -1),
  });

  const cloneMutation = useMutation({
    mutationFn: (strategy: StrategyConfig) =>
      strategiesApi.clone(strategy.id, `${strategy.name.slice(0, 195)} Copy`),
    onMutate: (strategy) => updatePendingRow(strategy.id, 1),
    onSuccess: async (clone) => {
      setRowError(null);
      toast.success(`Cloned as ${clone.name}.`);
      await queryClient.invalidateQueries({ queryKey: ["strategies"] });
    },
    onError: (mutationError: Error, strategy) => {
      setRowError({ strategyId: strategy.id, message: mutationError.message });
      toast.error(`Clone failed: ${mutationError.message}`);
    },
    onSettled: (_clone, _error, strategy) => updatePendingRow(strategy.id, -1),
  });

  const filtered = strategies.filter((s) => {
    if (search && !s.name.toLowerCase().includes(search.toLowerCase()))
      return false;
    return true;
  });

  return (
    <Shell>
      <div className="p-4 sm:p-6 space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold">Strategies</h2>
            <p className="text-sm text-muted-foreground">
              Manage your trading strategies — create, run, and monitor.
            </p>
          </div>
          <Link href="/strategies/new" className={buttonVariants()}>
            <Plus className="mr-2 h-4 w-4" />
            New Strategy
          </Link>
        </div>

        {/* Filters */}
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3 flex-wrap">
              <div className="relative flex-1 min-w-[200px] max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search strategies..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9"
                />
              </div>
              <Select value={typeFilter} onValueChange={(v) => v && setTypeFilter(v)}>
                <SelectTrigger className="w-32">
                  <SelectValue placeholder="Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="agent">Agent</SelectItem>
                  <SelectItem value="quant">Quant</SelectItem>
                  <SelectItem value="hitl">HITL</SelectItem>
                </SelectContent>
              </Select>
              <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
                <SelectTrigger className="w-36">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="paused">Paused</SelectItem>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="stopped">Stopped</SelectItem>
                </SelectContent>
              </Select>
              {isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
            </div>
          </CardContent>
        </Card>

        {/* Error state */}
        {isError && (
          <Card className="border-destructive">
            <CardContent className="pt-6 text-sm text-destructive">
              Failed to load strategies: {error?.message ?? "Unknown error"}
            </CardContent>
          </Card>
        )}

        {/* Empty state */}
        {!isLoading && !isError && filtered.length === 0 ? (
          <Card>
            <CardContent className="pt-8">
              <EmptyState
                title="No strategies found"
                description={
                  search || typeFilter !== "all" || statusFilter !== "all"
                    ? "Try adjusting your filters."
                    : "Create your first trading strategy to get started."
                }
                action={
                  !search &&
                  typeFilter === "all" &&
                  statusFilter === "all" ? (
                    <Link href="/strategies/new" className={buttonVariants()}>
                      <Plus className="mr-2 h-4 w-4" />
                      Create Strategy
                    </Link>
                  ) : undefined
                }
              />
            </CardContent>
          </Card>
        ) : null}

        {/* Table */}
        {!isLoading && !isError && filtered.length > 0 ? (
          <Card className="overflow-x-auto">
            <Table className="min-w-[760px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Tickers</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((s) => {
                  const isRowPending = (pendingRowCounts[s.id] ?? 0) > 0;
                  return (
                    <TableRow key={s.id}>
                    <TableCell>
                      <Link
                        href={`/strategies/${s.id}`}
                        className="font-medium hover:text-primary transition-colors"
                      >
                        {s.name}
                      </Link>
                      <p className="text-xs text-muted-foreground truncate max-w-[200px]">
                        {s.description}
                      </p>
                      {rowError?.strategyId === s.id ? (
                        <p className="mt-1 max-w-[280px] text-xs text-destructive" role="alert">
                          {rowError.message}
                        </p>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="uppercase text-xs">
                        {s.type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={s.status ?? "draft"} />
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1 flex-wrap">
                        {(s.tickers ?? []).map((t) => (
                          <Badge
                            key={t}
                            variant="secondary"
                            className="text-xs font-mono"
                          >
                            ${t}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(s.created_at)}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          className="hover:bg-muted rounded-md"
                          disabled={isRowPending}
                          aria-label={`Actions for ${s.name}`}
                        >
                          <div className="h-8 w-8 flex items-center justify-center">
                            {isRowPending ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <MoreHorizontal className="h-4 w-4" />
                            )}
                          </div>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            disabled={s.status === "active" || s.status === "archived"}
                            onClick={() =>
                              lifecycleMutation.mutate({ strategyId: s.id, action: "start" })
                            }
                          >
                            <Play className="mr-2 h-4 w-4" />
                            Mark Active
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            disabled={
                              !["active", "paused"].includes(s.status) || s.status === "paused"
                            }
                            onClick={() =>
                              lifecycleMutation.mutate({ strategyId: s.id, action: "pause" })
                            }
                          >
                            <Pause className="mr-2 h-4 w-4" />
                            Mark Paused
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            disabled={s.status === "stopped" || s.status === "archived"}
                            onClick={() =>
                              lifecycleMutation.mutate({ strategyId: s.id, action: "stop" })
                            }
                          >
                            <Square className="mr-2 h-4 w-4" />
                            Mark Stopped
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => cloneMutation.mutate(s)}>
                            <Copy className="mr-2 h-4 w-4" />
                            Clone
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() => {
                              if (confirm(`Delete "${s.name}"?`)) {
                                deleteMutation.mutate(s.id);
                              }
                            }}
                          >
                            <Trash2 className="mr-2 h-4 w-4" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Card>
        ) : null}
      </div>
    </Shell>
  );
}
