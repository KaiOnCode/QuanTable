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
  const unavailable = "Unavailable";
  const percent = (value: number | null): string =>
    value === null ? unavailable : formatPercent(value);
  const decimal = (value: number | null): string =>
    value === null ? unavailable : value.toFixed(2);
  return (
    <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
      <MetricCard label="Cumulative Return" value={percent(summary.cumulative_return_pct)} />
      <MetricCard label="Benchmark Return" value={percent(summary.benchmark_return_pct)} />
      <MetricCard label="Excess Return" value={percent(summary.excess_return_pct)} />
      <MetricCard label="Max Drawdown" value={percent(summary.max_drawdown_pct)} />
      <MetricCard label="Sharpe Ratio" value={decimal(summary.sharpe_ratio)} />
      <MetricCard label="Win Rate" value={percent(summary.win_rate_pct)} />
      <MetricCard label="Trades" value={String(summary.number_of_trades)} />
      <MetricCard label="Avg Holding Period" value={`${summary.avg_holding_period_days.toFixed(1)} days`} />
    </div>
  );
}
