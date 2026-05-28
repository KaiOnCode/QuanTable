"use client";

import { useState } from "react";
import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
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
import { formatPercent, formatDate } from "@/lib/utils";
import {
  Plus,
  Search,
  MoreHorizontal,
  Play,
  Pause,
  Square,
  Copy,
  Trash2,
  TrendingUp,
  ArrowUpRight,
} from "lucide-react";
import Link from "next/link";

// Mock data for UI development (backend not running)
const MOCK_STRATEGIES = [
  {
    id: "1",
    name: "Tech Momentum",
    description: "Momentum-based strategy focused on tech stocks",
    type: "agent" as const,
    status: "active" as const,
    tickers: ["AAPL", "MSFT", "NVDA"],
    created_at: "2026-05-01T09:00:00Z",
    updated_at: "2026-05-28T06:00:00Z",
  },
  {
    id: "2",
    name: "Value Hunter",
    description: "Deep value with PE/PB filters",
    type: "quant" as const,
    status: "active" as const,
    tickers: ["BRK.B", "JPM", "XOM"],
    created_at: "2026-04-15T09:00:00Z",
    updated_at: "2026-05-27T06:00:00Z",
  },
  {
    id: "3",
    name: "HITL Safe Harbor",
    description: "Conservative strategy with human oversight",
    type: "hitl" as const,
    status: "draft" as const,
    tickers: ["SPY", "BND", "GLD"],
    created_at: "2026-05-20T09:00:00Z",
    updated_at: "2026-05-25T06:00:00Z",
  },
];

export default function StrategiesPage() {
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const strategies = MOCK_STRATEGIES;

  const filtered = strategies.filter((s) => {
    if (search && !s.name.toLowerCase().includes(search.toLowerCase()))
      return false;
    if (typeFilter !== "all" && s.type !== typeFilter) return false;
    if (statusFilter !== "all" && s.status !== statusFilter) return false;
    return true;
  });

  return (
    <Shell>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
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
            </div>
          </CardContent>
        </Card>

        {/* Table */}
        {filtered.length === 0 ? (
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
        ) : (
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Tickers</TableHead>
                  <TableHead>Return</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((s) => (
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
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="uppercase text-xs">
                        {s.type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={s.status} />
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1 flex-wrap">
                        {s.tickers.map((t) => (
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
                    <TableCell className="font-mono text-sm">
                      <span className="text-green-500">+0.00%</span>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(s.created_at)}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger className="hover:bg-muted rounded-md">
                          <div className="h-8 w-8 flex items-center justify-center">
                            <MoreHorizontal className="h-4 w-4" />
                          </div>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem>
                            <Play className="mr-2 h-4 w-4" />
                            {s.status === "active" ? "Restart" : "Start"}
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            <Pause className="mr-2 h-4 w-4" />
                            Pause
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            <Square className="mr-2 h-4 w-4" />
                            Stop
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem>
                            <Copy className="mr-2 h-4 w-4" />
                            Clone
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem className="text-destructive">
                            <Trash2 className="mr-2 h-4 w-4" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </div>
    </Shell>
  );
}
