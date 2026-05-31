"use client";

import { Shell } from "@/components/layout/shell";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { EmptyState } from "@/components/shared/empty-state";
import { ActionBadge } from "@/components/shared/badges";
import { formatDateTime } from "@/lib/utils";
import { approvalsApi } from "@/lib/api/approvals";
import {
  CheckSquare,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ThumbsUp,
  ThumbsDown,
  Edit3,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";

import type { Approval } from "@/lib/types/models";

type ApprovalRow = Approval;

// ── Helpers ──────────────────────────────────────────────

function parseRules(jsonStr: string): string[] {
  try {
    const parsed = JSON.parse(jsonStr);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function statusBadgeVariant(status: string) {
  switch (status) {
    case "approved":
      return "default";
    case "rejected":
      return "destructive";
    case "modified":
      return "secondary";
    case "pending":
      return "outline";
    default:
      return "outline";
  }
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pending: "待审批",
    approved: "已通过",
    rejected: "已拒绝",
    modified: "已修改",
    timed_out: "已超时",
  };
  return map[status] || status;
}

// ── Components ───────────────────────────────────────────

function ApprovalCard({
  approval,
  onApprove,
  onReject,
  onModify,
  isPending,
}: {
  approval: ApprovalRow;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onModify: (id: string, action: string, pct: number, notes: string) => void;
  isPending: boolean;
}) {
  const rules = parseRules(approval.triggered_rules_json || "[]");
  const [showModify, setShowModify] = useState(false);
  const [modAction, setModAction] = useState(approval.original_action || "HOLD");
  const [modPct, setModPct] = useState(approval.original_target_position_pct || 0);
  const [modNotes, setModNotes] = useState("");

  return (
    <Card
      className={
        isPending
          ? rules.length > 1
            ? "border-destructive/50"
            : "border-yellow-500/30"
          : ""
      }
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold font-mono text-lg">
                ${approval.ticker}
              </span>
              <ActionBadge action={approval.original_action || "HOLD"} />
              <Badge variant={statusBadgeVariant(approval.status)}>
                {statusLabel(approval.status)}
              </Badge>
              {isPending && rules.length > 1 && (
                <Badge variant="destructive">
                  <AlertTriangle className="mr-1 h-3 w-3" />
                  高风险
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              置信度: {((approval.original_confidence || 0) * 100).toFixed(0)}%
              &middot; 目标仓位: {approval.original_target_position_pct || 0}%
            </p>
          </div>
          <div className="text-right text-xs text-muted-foreground">
            <div>创建于 {formatDateTime(approval.created_at)}</div>
            {approval.decided_at && (
              <div>处理于 {formatDateTime(approval.decided_at)}</div>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* PM Report */}
        {approval.pm_report && (
          <div className="p-3 rounded-lg bg-muted/50">
            <p className="text-xs text-muted-foreground mb-1">PM 决策理由:</p>
            <p className="text-sm">{approval.pm_report}</p>
          </div>
        )}

        {/* Triggered Rules */}
        {rules.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">触发规则:</p>
            <div className="flex gap-1 flex-wrap">
              {rules.map((r, i) => (
                <Badge key={i} variant="outline" className="text-xs">
                  {r}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Reviewer notes */}
        {approval.reviewer_notes && (
          <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/20">
            <p className="text-xs font-medium text-blue-600 mb-1">
              审批人备注 ({approval.reviewer}):
            </p>
            <p className="text-sm">{approval.reviewer_notes}</p>
          </div>
        )}

        {/* Modified info */}
        {approval.status === "modified" && approval.modified_action && (
          <div className="p-3 rounded-lg bg-purple-500/5 border border-purple-500/20">
            <p className="text-xs font-medium text-purple-600 mb-1">
              修改后执行:
            </p>
            <p className="text-sm">
              {approval.modified_action} {approval.modified_target_position_pct}%
              (原: {approval.original_action} {approval.original_target_position_pct}%)
            </p>
          </div>
        )}

        {/* Actions */}
        {isPending && (
          <>
            <Separator />
            {!showModify ? (
              <div className="flex items-center gap-3 flex-wrap">
                <Button
                  variant="default"
                  size="sm"
                  onClick={() => onApprove(approval.id)}
                >
                  <ThumbsUp className="mr-2 h-4 w-4" />
                  通过
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => onReject(approval.id)}
                >
                  <ThumbsDown className="mr-2 h-4 w-4" />
                  拒绝
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowModify(true)}
                >
                  <Edit3 className="mr-2 h-4 w-4" />
                  修改
                </Button>
              </div>
            ) : (
              <div className="space-y-3 p-3 border rounded-lg">
                <p className="text-sm font-medium">修改参数</p>
                <div className="flex gap-3 items-center">
                  <select
                    className="border rounded px-2 py-1 text-sm"
                    value={modAction}
                    onChange={(e) => setModAction(e.target.value)}
                  >
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                    <option value="HOLD">HOLD</option>
                  </select>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    className="border rounded px-2 py-1 text-sm w-24"
                    value={modPct}
                    onChange={(e) => setModPct(Number(e.target.value))}
                  />
                  <span className="text-sm text-muted-foreground">%</span>
                </div>
                <textarea
                  className="border rounded px-2 py-1 text-sm w-full"
                  rows={2}
                  placeholder="修改理由 (可选)"
                  value={modNotes}
                  onChange={(e) => setModNotes(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => {
                      onModify(approval.id, modAction, modPct, modNotes);
                      setShowModify(false);
                    }}
                  >
                    确认修改
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowModify(false)}
                  >
                    取消
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── Page ─────────────────────────────────────────────────

export default function ApprovalsPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState("pending");

  // Fetch pending approvals with polling
  const pendingQuery = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => approvalsApi.list({ status: "pending" }),
    refetchInterval: 10000, // 每 10 秒自动刷新
  });

  // Fetch resolved approvals
  const resolvedQuery = useQuery({
    queryKey: ["approvals", "resolved"],
    queryFn: () =>
      approvalsApi.list({ status: "approved,rejected,modified,timed_out" }),
    refetchInterval: 10000,
  });

  const approveMutation = useMutation({
    mutationFn: (id: string) =>
      approvalsApi.approve(id, { reviewer: "user", notes: "" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.refetchQueries({ queryKey: ["approvals", "resolved"] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) =>
      approvalsApi.reject(id, { reviewer: "user", notes: "" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.refetchQueries({ queryKey: ["approvals", "resolved"] });
    },
  });

  const modifyMutation = useMutation({
    mutationFn: ({
      id,
      action,
      pct,
      notes,
    }: {
      id: string;
      action: string;
      pct: number;
      notes: string;
    }) =>
      approvalsApi.modify(id, {
        reviewer: "user",
        modified_action: action,
        modified_target_position_pct: pct,
        notes,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.refetchQueries({ queryKey: ["approvals", "resolved"] });
    },
  });

  const pendingItems: ApprovalRow[] =
    (pendingQuery.data?.items as ApprovalRow[]) || [];
  const resolvedItems: ApprovalRow[] =
    (resolvedQuery.data?.items as ApprovalRow[]) || [];

  const isLoading = pendingQuery.isLoading || resolvedQuery.isLoading;

  return (
    <Shell>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <CheckSquare className="h-5 w-5" />
              人工审批 (HITL)
            </h2>
            <p className="text-sm text-muted-foreground">
              审核、通过或修改 AI 的交易决策
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ["approvals"] });
            }}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            刷新
          </Button>
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载中...
          </div>
        )}

        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="space-y-4"
        >
          <TabsList>
            <TabsTrigger value="pending" className="gap-2">
              <Clock className="h-4 w-4" />
              待审批
              {pendingItems.length > 0 && (
                <Badge variant="destructive" className="ml-1 h-5 px-1.5 text-xs">
                  {pendingItems.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="history" className="gap-2">
              <CheckCircle2 className="h-4 w-4" />
              历史记录
            </TabsTrigger>
          </TabsList>

          {/* Pending */}
          <TabsContent value="pending" className="space-y-4">
            {pendingItems.length === 0 ? (
              <Card>
                <CardContent className="pt-8">
                  <EmptyState
                    icon={<CheckCircle2 className="h-12 w-12" />}
                    title="暂无待审批"
                    description="所有 AI 决策均在安全范围内，无需人工审核。"
                  />
                </CardContent>
              </Card>
            ) : (
              pendingItems.map((a) => (
                <ApprovalCard
                  key={a.id}
                  approval={a}
                  isPending={true}
                  onApprove={(id) => approveMutation.mutate(id)}
                  onReject={(id) => rejectMutation.mutate(id)}
                  onModify={(id, action, pct, notes) =>
                    modifyMutation.mutate({ id, action, pct, notes })
                  }
                />
              ))
            )}
          </TabsContent>

          {/* History */}
          <TabsContent value="history" className="space-y-4">
            {resolvedItems.length === 0 ? (
              <Card>
                <CardContent className="pt-8">
                  <EmptyState
                    icon={<XCircle className="h-12 w-12" />}
                    title="暂无历史记录"
                    description="审批历史将显示在这里。"
                  />
                </CardContent>
              </Card>
            ) : (
              resolvedItems.map((a) => (
                <ApprovalCard
                  key={a.id}
                  approval={a}
                  isPending={false}
                  onApprove={() => {}}
                  onReject={() => {}}
                  onModify={() => {}}
                />
              ))
            )}
          </TabsContent>
        </Tabs>
      </div>
    </Shell>
  );
}
