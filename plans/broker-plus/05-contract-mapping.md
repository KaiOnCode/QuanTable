# Broker Plus Contract Mapping

This document maps the frozen broker-plus contract to the implemented broker
surface. It is an execution-domain contract only; platform integration remains
outside this branch.

## Identity Fields

- `strategy_id`: long-lived strategy owner. Broker receives and propagates it;
  broker does not generate it.
- `account_id`: isolated trading account. First-stage default is `"default"`;
  execution-node input can override it and otherwise derives it from
  `strategy_id` when present.
- `session_id`: one Agent graph run / execution turn. It is used for run-scoped
  ledger/backtest reads, not as account or strategy identity.
- `decision_id`: upstream PM decision identity. Broker receives, propagates,
  records, and serializes it, but does not create it.

These fields are present on broker models, fills, positions, account snapshots,
execution reports, ledger records, and broker events.

## Percent Units

- Internal broker math uses decimal fractions, for example `0.1` means 10%.
- AgentState target inputs stay as percentage points, for example `50.0`.
- Public view output uses percentage points:
  - `PositionView.weight_pct`
  - `PerformanceMetricsView.cumulative_return_pct`
  - `PerformanceMetricsView.annualized_return_pct`
  - `PerformanceMetricsView.benchmark_return_pct`
  - `PerformanceMetricsView.excess_return_pct`
  - `PerformanceMetricsView.max_drawdown_pct`
  - `PerformanceMetricsView.win_rate_pct`

## Enum Mapping

- `OrderSide.BUY` -> `"buy"`
- `OrderSide.SELL` -> `"sell"`
- `OrderType.MARKET` -> `"market"`
- `OrderType.LIMIT` -> `"limit"`
- `OrderStatus.NEW` -> `"pending"`
- `OrderStatus.FILLED` -> `"executed"`
- `OrderStatus.CANCELED` -> `"cancelled"`
- `OrderStatus.REJECTED` -> `"rejected"`
- `Position.side == "LONG"` -> `"long"`
- `Position.side == "SHORT"` -> `"short"`
- `Position.side == "FLAT"` -> `"flat"`

`OrderStatus.PARTIALLY_FILLED` is not exposed as `"executed"` in this
first-stage contract.

## Execution Report Statuses

`ExecutionReportView.status` can be:

- `"pending"`: waiting for approval or a broker-returned pending order.
- `"skipped"`: execution disabled by caller; no broker event is written.
- `"held"`: PM held or target already satisfied; no broker event is written.
- `"executed"`: broker order is filled.
- `"rejected"`: approval rejection, timeout, or broker risk rejection.
- `"failed"`: data/system precondition failure such as missing market price.

Approval details live in `ApprovalSnapshotView` inside the report. The broker
does not own approval workflow policy.

## Event And Ledger Boundary

- Trade ledger stores fills/trades and daily snapshots.
- Failed execution preconditions and risk rejections do not become trade ledger
  rows.
- Broker event sink records execution-domain events:
  - `order_placed`
  - `order_filled`
  - `order_canceled`
  - `risk_check_failed`
  - `order_rejected`
  - `execution_pending`
  - `execution_rejected`
  - `execution_failed`
- Event sequence is monotonic per `(strategy_id, account_id)`.
- In-memory event and ledger backends are first-stage validation boundaries.
  SQLite and ContextStore adapters are out of scope.

## Backtest JSON Shape

`BacktestResultView` is synchronous and completed:

```text
status = "completed"
config
summary
series
trades
```

`BacktestConfigView.benchmark_symbol` defaults to `"SPY"`. Series points expose
portfolio-level `strategy_equity` and `benchmark_equity`. Trades are serialized
from `LedgerFillRecord` through `TradeView`, not from naked fills.

The serializer supports multi-ticker config as one shared strategy account. The
current runner still executes one ticker per call and returns a single
portfolio-level result.

## Non-Goals

- No React/Next.js pages, routes, components, or API client.
- No FastAPI routes or full FastAPI app.
- No ContextStore, MCP, memory/reflection, or notification channels.
- No SQLite adapter or production audit store.
- No full HITL manager, approval policy engine, interrupt/resume flow, or
  front-end approval page.
- No user/permission system.
- No async backtest job queue or prediction-accuracy backtest contract.
- No README merge on broker-plus.
