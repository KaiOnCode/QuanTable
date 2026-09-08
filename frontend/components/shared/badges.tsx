import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function DirectionBadge({
  direction,
  className,
}: {
  direction: string;
  className?: string;
}) {
  const variants: Record<string, { label: string; variant: "default" | "destructive" | "secondary" }> = {
    Bullish: { label: "Bullish", variant: "default" },
    Bearish: { label: "Bearish", variant: "destructive" },
    Neutral: { label: "Neutral", variant: "secondary" },
  };
  const v = variants[direction] || variants.Neutral;
  return (
    <Badge variant={v.variant} className={cn("font-medium", className)}>
      {v.label}
    </Badge>
  );
}

export function ActionBadge({
  action,
  className,
}: {
  action: string;
  className?: string;
}) {
  const variants: Record<string, { label: string; variant: "default" | "destructive" | "secondary" }> = {
    BUY: { label: "BUY", variant: "default" },
    SELL: { label: "SELL", variant: "destructive" },
    HOLD: { label: "HOLD", variant: "secondary" },
  };
  const v = variants[action] || variants.HOLD;
  return (
    <Badge variant={v.variant} className={cn("font-bold", className)}>
      {v.label}
    </Badge>
  );
}

export function StatusBadge({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  const variants: Record<string, "default" | "destructive" | "secondary" | "outline"> = {
    active: "default",
    completed: "default",
    paused: "secondary",
    stopped: "destructive",
    archived: "outline",
    draft: "outline",
    pending: "secondary",
    approved: "default",
    rejected: "destructive",
    timed_out: "destructive",
    running: "default",
    failed: "destructive",
    error: "destructive",
  };
  const variant = variants[status] || "outline";
  return (
    <Badge variant={variant} className={cn("capitalize", className)}>
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 rounded-full bg-muted overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground w-9 text-right">
        {pct}%
      </span>
    </div>
  );
}

export function TickerBadge({
  ticker,
  className,
}: {
  ticker: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-mono font-bold bg-primary/10 text-primary",
        className
      )}
    >
      ${ticker}
    </span>
  );
}
