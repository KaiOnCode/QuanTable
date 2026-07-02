# Broker Plus 技术摘要

## 核心架构

```text
AgentState / PM decision
  -> agentgraph.execution_node
  -> BrokerGateway
  -> MockBrokerEngine
  -> BrokerEventSink + TradeLedger
  -> broker.views serializers
  -> ExecutionReportView / BacktestResultView / ExecutionOutcomeView
```

关键设计: broker 只负责执行域, 不拥有平台层。

- Broker 内: 订单、成交、账户、持仓、风险、事件、账本、执行结果、回测结果。
- Broker 外: FastAPI、React、ContextStore、MCP、通知渠道、完整 HITL manager、真实券商 SDK、权限系统。

## 身份字段

| 字段 | 含义 | 当前职责 |
| --- | --- | --- |
| `strategy_id` | 长期策略身份 | broker 接收、传播、过滤, 不生成 |
| `account_id` | 隔离交易账户 | mock engine 以此隔离现金、持仓、订单、成交、事件 |
| `session_id` | 一次 Agent graph run 或一次 execution turn | 回测和账本按 session 追踪 |
| `decision_id` | 一次 PM 决策 | 上游生成, broker 只传播和记录 |

这些字段贯穿 `Order`、`Fill`、`Position`、`AccountSnapshot`、`ExecutionReport`、ledger records 和 broker events。

## 账户隔离

`MockBrokerEngine` 维护按 `account_id` 划分的账户状态:

- cash
- positions
- orders
- fills
- event log

默认查询仍访问 `"default"` 账户, 兼容旧用法。需要跨账户查询时必须显式传 `account_id=None`。这让默认兼容和多账户隔离可以同时存在。

## 事件与账本边界

事件 sink 记录执行域事件, 账本只记录真实成交和账户快照。

| 类型 | 进入事件 sink | 进入 trade ledger |
| --- | --- | --- |
| 下单 | 是, `order_placed` | 否 |
| 成交 | 是, `order_filled` | 是 |
| 撤单 | 是, `order_canceled` | 否 |
| 风控拒单 | 是, `risk_check_failed` + `order_rejected` | 否 |
| 审批 pending/rejected/failed | 是, execution event | 否 |
| HOLD / skipped / target already satisfied | 返回 report, 默认不写事件 | 否 |

事件 vocabulary 固定为:

```text
order_placed
order_filled
order_canceled
risk_check_failed
order_rejected
execution_pending
execution_rejected
execution_failed
```

事件 sequence 按 `(strategy_id, account_id)` 单调递增。

## 执行报告

`ExecutionReportView.status` 的含义:

| Status | 语义 | 是否下单 |
| --- | --- | --- |
| `pending` | 等待审批, 或 broker 返回 pending order | 视分支而定 |
| `skipped` | caller 禁用 execution | 否 |
| `held` | PM HOLD 或目标仓位已满足 | 否 |
| `executed` | broker order 已成交 | 是 |
| `rejected` | 审批拒绝/超时或 broker 风控拒单 | 可能有 rejected order |
| `failed` | 缺价格等系统/数据前置条件失败 | 否 |

审批在 broker-plus 中只是执行报告里的 snapshot, 不是完整 HITL 系统:

```text
approval_id
approval_status
approval_reason
reviewer
reviewer_notes
original_target_pct
modified_target_pct
```

## Public Views

`broker/views.py` 把内部模型映射成 API/前端可消费形状:

- `OrderView`
- `FillView`
- `PositionView`
- `AccountView`
- `TradeView`
- `ApprovalSnapshotView`
- `ExecutionReportView`
- `ExecutionOutcomeView`
- `BrokerEventView`
- `PerformanceMetricsView`
- `BacktestConfigView`
- `BacktestSeriesPointView`
- `BacktestResultView`

关键 contract:

- 内部百分比用 decimal fraction, 例如 `0.1` 表示 10%。
- Public view 百分比用 percentage points, 例如 `10.0` 表示 10%。
- Public enum 用小写, 例如 `buy`、`sell`、`market`、`limit`、`pending`、`executed`。
- `TradeView` 来自 `LedgerFillRecord`, 不直接从裸 `Fill` 生成。
- `PositionView.current_price` 带 `price_source`: `market`、`last_close`、`avg_cost_fallback`。

## 回测合同

`BacktestRunner` 当前每次 run:

- 生成独立 `session_id`。
- 每个交易日传递 `as_of` 给 agent/harness。
- 支持 scoped agent factory, 让后续 no-lookahead data sandbox 有插入点。
- 回传 trades、portfolio、metrics 和 `BacktestResultView`。
- `BacktestResultView` 是同步 completed result, 异步 job id/status 属后续 API 层。

谨慎点: broker-plus 已有 `as_of` 和 harness contract, 但 data service 对历史数据可见性的强制门控仍是后续重点。

## Adapter Readiness

当前 adapter-ready 能力:

- `BrokerGateway` 作为真实 broker adapter 的协议边界。
- `client_order_id` 由调用方生成, broker 在 `(strategy_id, account_id)` 范围内做幂等。
- `execution_timing` 支持 `close_bar` 和 `next_open`, 让 mock 行为确定且可测试。

尚未完成:

- 外部券商 SDK。
- 异步订单生命周期。
- partial fills public contract。
- 真实交易日历、行情订阅、成交回报 replay。
