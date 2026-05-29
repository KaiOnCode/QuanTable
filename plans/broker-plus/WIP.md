# WIP

## 已锁定决策

- Backtest JSON contract 第一阶段采用同步完成态结果视图：
  `BacktestResultView(status="completed", summary, series, trades, config)`。
- 当前阶段不在 broker runner 内模拟异步 job queue。
- 未来 FastAPI 层可以在 `BacktestResultView` 外再包装 `backtest_id` 与 job 状态，
  例如 `BacktestJobView(backtest_id, status, submitted_at, completed_at, result)`。
- SQLite / event sink 第一阶段只固定 protocol 边界并提供 in-memory 实现。
  SQLite 与 ContextStore adapter 留给后续计划，不和 broker-plus 第一阶段混在一起。
