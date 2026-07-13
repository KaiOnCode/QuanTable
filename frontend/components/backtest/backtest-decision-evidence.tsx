import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { BacktestDecisionView, BacktestOrderEvidenceView } from "@/lib/types/models";
import { formatDate, formatPercent } from "@/lib/utils";

type BacktestDecisionEvidenceProps = {
  readonly decisions: readonly BacktestDecisionView[];
  readonly orders: readonly BacktestOrderEvidenceView[];
};

function numberOrUnavailable(value: number | null, formatter: (value: number) => string): string {
  return value === null ? "Unavailable" : formatter(value);
}

function orderVariant(status: BacktestOrderEvidenceView["status"]): "destructive" | "outline" | "secondary" {
  switch (status) {
    case "rejected":
      return "destructive";
    case "pending":
    case "unfilled":
      return "secondary";
    case "executed":
    case "cancelled":
      return "outline";
  }
}

function DecisionRows({ decisions }: { readonly decisions: readonly BacktestDecisionView[] }) {
  if (decisions.length === 0) return <p className="py-8 text-center text-sm text-muted-foreground">No decision evidence was returned.</p>;
  return <>
    <div className="space-y-3 md:hidden">{decisions.map((decision) => <article key={decision.sequence} className="space-y-2 rounded-lg border border-input p-3"><div className="flex items-start justify-between gap-3"><span className="font-mono text-sm">#{decision.sequence}</span><Badge variant={decision.status === "failed" ? "destructive" : "outline"}>{decision.status}</Badge></div><dl className="grid grid-cols-2 gap-2 text-xs"><div><dt className="text-muted-foreground">Signal</dt><dd>{formatDate(decision.signal_date)}</dd></div><div><dt className="text-muted-foreground">Execution</dt><dd>{decision.execution_date ? formatDate(decision.execution_date) : "Not executed"}</dd></div><div><dt className="text-muted-foreground">Target</dt><dd>{numberOrUnavailable(decision.target_position_pct, formatPercent)}</dd></div><div><dt className="text-muted-foreground">Attempts</dt><dd>{decision.attempts}</dd></div></dl>{decision.error_code ? <p className="text-xs text-destructive">{decision.error_stage ?? "decision"}: {decision.error_code}</p> : null}</article>)}</div>
    <div className="hidden md:block"><Table><TableHeader><TableRow><TableHead>Sequence</TableHead><TableHead>Signal</TableHead><TableHead>Execution</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Target</TableHead><TableHead className="text-right">Attempts</TableHead><TableHead>Error</TableHead></TableRow></TableHeader><TableBody>{decisions.map((decision) => <TableRow key={decision.sequence}><TableCell className="font-mono">#{decision.sequence}</TableCell><TableCell>{formatDate(decision.signal_date)}</TableCell><TableCell>{decision.execution_date ? formatDate(decision.execution_date) : "Not executed"}</TableCell><TableCell><Badge variant={decision.status === "failed" ? "destructive" : "outline"}>{decision.status}</Badge></TableCell><TableCell className="text-right font-mono">{numberOrUnavailable(decision.target_position_pct, formatPercent)}</TableCell><TableCell className="text-right font-mono">{decision.attempts}</TableCell><TableCell className="text-xs text-muted-foreground">{decision.error_code ?? "—"}</TableCell></TableRow>)}</TableBody></Table></div>
  </>;
}

function OrderRows({ orders }: { readonly orders: readonly BacktestOrderEvidenceView[] }) {
  if (orders.length === 0) return <p className="py-8 text-center text-sm text-muted-foreground">No order evidence was returned.</p>;
  return <>
    <div className="space-y-3 md:hidden">{orders.map((order) => <article key={order.order_id} className="space-y-2 rounded-lg border border-input p-3"><div className="flex items-start justify-between gap-3"><span className="truncate font-mono text-xs">{order.order_id}</span><Badge variant={orderVariant(order.status)}>{order.status}</Badge></div><dl className="grid grid-cols-2 gap-2 text-xs"><div><dt className="text-muted-foreground">Signal</dt><dd>{formatDate(order.signal_date)}</dd></div><div><dt className="text-muted-foreground">Execution</dt><dd>{order.execution_date ? formatDate(order.execution_date) : "Not executed"}</dd></div></dl>{order.reason ? <p className="text-xs text-muted-foreground">{order.reason}</p> : null}</article>)}</div>
    <div className="hidden md:block"><Table><TableHeader><TableRow><TableHead>Order</TableHead><TableHead>Signal</TableHead><TableHead>Execution</TableHead><TableHead>Status</TableHead><TableHead>Reason</TableHead></TableRow></TableHeader><TableBody>{orders.map((order) => <TableRow key={order.order_id}><TableCell className="font-mono text-xs">{order.order_id}</TableCell><TableCell>{formatDate(order.signal_date)}</TableCell><TableCell>{order.execution_date ? formatDate(order.execution_date) : "Not executed"}</TableCell><TableCell><Badge variant={orderVariant(order.status)}>{order.status}</Badge></TableCell><TableCell className="text-muted-foreground">{order.reason || "—"}</TableCell></TableRow>)}</TableBody></Table></div>
  </>;
}

export function BacktestDecisionEvidence({ decisions, orders }: BacktestDecisionEvidenceProps) {
  return <div className="space-y-6"><Card><CardHeader><CardTitle className="text-base">Decisions</CardTitle><CardDescription>Persisted decision evidence, including typed readiness and failures.</CardDescription></CardHeader><CardContent><DecisionRows decisions={decisions} /></CardContent></Card><Card><CardHeader><CardTitle className="text-base">Order Evidence</CardTitle><CardDescription>Orders remain distinct from fill-level executions and closed trades.</CardDescription></CardHeader><CardContent><OrderRows orders={orders} /></CardContent></Card></div>;
}
