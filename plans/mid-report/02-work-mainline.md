# 已完成工作主线

## 1. 基础多智能体分析系统

已有基础能力:

- 5 个 Agent: 市场、新闻、基本面、风险、PM。
- CLI 和 Streamlit 入口。
- Yahoo Finance、Google News、技术指标和基础图表。
- PM 输出 `Action`、`Target_position_pct` 和分析报告。

这部分是项目原型的分析能力底座。当前中期汇报可以简要带过, 重点转向执行闭环。

## 2. Broker 基线: `feat/broker`

`feat/broker` 完成了从"PM 只给建议"到"PM 决策可以进入本地模拟执行"的第一轮落地。

| 模块 | 已完成内容 | 关键文件 |
| --- | --- | --- |
| 数据模型 | `Order`、`Fill`、`Position`、`AccountSnapshot`、`ExecutionReport` | `broker/models.py` |
| 配置 | 初始资金、手续费、滑点、执行时机、仓位限制、做空开关 | `broker/config.py` |
| 事件 | broker 事件模型和默认事件日志 | `broker/events.py` |
| Gateway | 可替换 broker 接口协议 | `broker/gateway.py` |
| Mock engine | 市价/限价单、成交、撤单、多空、账户/持仓查询 | `broker/engine.py` |
| 风控 | 资金、做空、单票仓位限制 | `broker/risk_checks.py` |
| 账本 | fills、daily snapshots、CSV、核心绩效指标 | `broker/ledger.py` |
| 主流程接入 | PM -> execution node -> broker -> execution report | `agentgraph/execution_node.py`, `agentgraph/orchestrator.py` |
| 回测 | broker-backed backtest runner, trades/portfolio/metrics | `broker/backtest_runner.py` |
| UI 验证 | Streamlit 回测展示和浏览器 smoke | `streamlit_app.py`, `test/streamlit/` |

可讲口径:

> 这一阶段先把交易执行域从脚本原型抽成正式模块, 让订单、成交、账户、持仓、风控、账本和 PM 执行结果都有公共接口和测试覆盖。

## 3. Broker Plus: 执行域契约增强

`feat/broker-plus` 的重点不是多做一个页面, 而是把 broker 做成未来平台层可以消费的 contract。

| 方向 | 已完成内容 | 价值 |
| --- | --- | --- |
| 身份字段 | `strategy_id`、`account_id`、`session_id`、`decision_id` 进入订单、成交、持仓、快照、报告、事件 | 支持多策略、多账户、多会话追踪 |
| 账户隔离 | `MockBrokerEngine` 按 `account_id` 隔离 cash、positions、orders、fills、events | 避免多个策略或账户互相污染 |
| 事件 sink | `BrokerEventSink` 协议和 `InMemoryBrokerEventSink` | 为后续事件持久化和审计留边界 |
| 账本 backend | `TradeLedgerBackend` 协议和 identity filters | 为后续 SQLite/ContextStore 适配留边界 |
| Public views | 新增 `broker/views.py` | API/前端/审计消费统一 DTO, 不直接依赖内部模型 |
| Execution report | `ExecutionReportView` 固定 `pending/skipped/held/executed/rejected/failed` | 所有执行分支都有结构化 JSON |
| Backtest view | `BacktestResultView` 包含 config、summary、series、trades | 回测结果可序列化、可展示、可对接 API |
| Orchestrator hook | `on_execution_complete` | 为后续通知、memory、审计回调预留 |

可讲口径:

> Broker-plus 把执行域从"能跑"推进到"能被未来平台可靠消费": 它固定了身份、状态、事件、账本和 public view 的语义, 同时明确不把 FastAPI、React、ContextStore、完整 HITL 或真实券商 SDK 混进 broker 内核。

## 4. Integration-Owned 增强

2026-06-02 的 `plans/broker-plus-integration/*` 和对应实现, 进一步把后续集成风险前置到 broker contract 内:

- 回测 `as_of` 合同: 每个交易日把可见时间传给 agent/harness, 为 no-lookahead 打基础。
- Scoped agent factory: 回测时可以按 `as_of` 构造受限 agent 或工具沙盒。
- Identity filters: event 和 ledger 可按 strategy/account/session/decision 过滤。
- `client_order_id` 幂等: 在 `(strategy_id, account_id)` 范围内避免重复下单。
- Event vocabulary: 固定 broker-owned 事件类型和最小 payload 字段。
- `ExecutionOutcomeView`: 为未来 memory/reflection 消费单次执行结果预留统一形状。
- Deterministic execution timing: `close_bar` 与 `next_open` 两种可测试撮合时机。

## 5. 工程卫生

- 测试按域组织到 `test/broker`、`test/agentgraph`、`test/dataflow`、`test/agents`、`test/streamlit`。
- `properties.env` 已从 Git 跟踪中移出, 本地仍可存在, 由 `.gitignore` 忽略。
- 两个 broker-plus 远端跟踪引用已对齐当前 HEAD。
- 当前工作区在写本文档前为干净状态。

## 可引用提交

| 范围 | SHA | 日期 | 汇报证据点 |
| --- | --- | --- | --- |
| broker | `dc51bc8` | 2026-04-13 | broker domain models/events/config |
| broker | `2d09080` | 2026-04-13 | mock broker engine + pre-trade risk |
| broker | `6980742` | 2026-04-13 | TradeLedger fills/snapshots/metrics |
| broker | `236a63a` | 2026-04-13 | execution node + backtest runner + tests |
| broker | `f998860` | 2026-04-13 | HITL approval workflow mapping |
| broker | `3ff07c8` | 2026-04-13 | benchmark metrics, drawdown, visualization tabs |
| broker-plus plan | `69ea315` | 2026-05-30 | frozen contract / premerge phase docs |
| broker-plus | `a19fcb7` | 2026-05-30 | execution identity fields |
| broker-plus | `b2995d1` | 2026-05-30 | public view serializers |
| broker-plus | `c278585` | 2026-05-30 | structured execution reports |
| broker-plus | `10f2ca5` | 2026-05-30 | test suites organized by domain |
| broker-plus | `5f99eac` | 2026-06-02 | broker identity filters |
| broker-plus | `f7ea2ac` | 2026-06-02 | client order id idempotency |
| broker-plus | `d905b6a` | 2026-06-02 | deterministic execution timing |
| broker-plus | `8988e4b` | 2026-06-02 | integration-owned contract mapping |
