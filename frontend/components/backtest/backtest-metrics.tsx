import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { PerformanceMetricsView } from "@/lib/types/models";
import { formatPercent } from "@/lib/utils";

function MetricCard({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-xl font-mono tabular-nums">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}

export function BacktestMetrics({ summary }: { readonly summary: PerformanceMetricsView }) {
  return (
    <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
      <MetricCard label="Cumulative Return" value={formatPercent(summary.cumulative_return_pct)} />
      <MetricCard label="Benchmark Return" value={formatPercent(summary.benchmark_return_pct)} />
      <MetricCard label="Excess Return" value={formatPercent(summary.excess_return_pct)} />
      <MetricCard label="Max Drawdown" value={formatPercent(summary.max_drawdown_pct)} />
      <MetricCard label="Sharpe Ratio" value={summary.sharpe_ratio.toFixed(2)} />
      <MetricCard label="Win Rate" value={formatPercent(summary.win_rate_pct)} />
      <MetricCard label="Trades" value={String(summary.number_of_trades)} />
      <MetricCard label="Avg Holding Period" value={`${summary.avg_holding_period_days.toFixed(1)} days`} />
    </div>
  );
}
