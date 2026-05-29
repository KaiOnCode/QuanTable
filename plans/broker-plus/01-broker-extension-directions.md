# feat/broker 后续扩展方向

> 记录日期：2026-05-29
> 目的：沉淀 `feat/broker` 为适配 `feat/frontend-foundation` 架构构想所需的扩展方向。本文是后续深入讨论与实现计划的输入，不是最终实现方案。

## 1. 背景判断

当前 `feat/broker` 已经完成模拟券商内核与 Agent 执行闭环：

- `broker/` 已有订单、成交、持仓、账户快照、执行报告、事件、风控、账本、回测 runner。
- `agentgraph/execution_node.py` 已能把 PM 决策转成市场单，并将执行报告写回 `AgentState`。
- `TradeLedgerBackend` 已经抽象出账本后端，为后续 SQLite 或 ContextStore 接入留了接口。
- `BacktestRunner` 已能产出 trades、portfolio、metrics，Streamlit 侧已有最小展示。

上游 `feat/frontend-foundation` 提出的目标不是简单替换 UI，而是把系统升级为：

- React/Next.js 独立前端。
- FastAPI REST + SSE 后端。
- Strategy 为中心的多策略运行模型。
- Broker 作为统一执行网关。
- per-strategy SQLite 持久化。
- 审计、审批、记忆、回测、绩效都可被前端消费。

因此，`feat/broker` 不需要接管前端、MCP、15-agent pipeline、完整 ContextStore 或通知系统，但需要把 broker 从“本地模拟执行内核”扩展为“可被后端 API、策略账户、审计持久化和 React 前端稳定消费的执行域服务”。

## 2. 扩展方向一：Broker API DTO 与序列化层

### 目标

在不破坏现有 broker 内部模型的前提下，新增一层面向 API/前端的只读数据视图。

### 原因

当前内部模型更贴近撮合与账本：

- `Position` 使用 `shares`、`avg_cost`、`unrealized_pnl`。
- `Fill` 只含 `order_id`、`fill_price`、`fill_qty`、`fee`、`slippage`。
- `TradeLedger` 才补齐 ticker、side、realized_pnl 等交易展示字段。
- `BacktestRunner` 输出 DataFrame，不适合直接作为 HTTP response contract。

而上游前端契约期望的是：

- `Account`：账户资源，而不是单次快照。
- `Position`：`quantity`、`avg_entry_price`、`current_price`、`market_value`、`weight_pct`。
- `Order`：`order_type`、`filled_quantity`、`filled_avg_price`、`commission`、`decision_id`。
- `Trade`：带 ticker、side、quantity、price、commission、timestamp。
- `PerformanceMetrics`：total return、benchmark return、excess return、equity curve 等。

### 建议产物

- 新增 broker-facing 的 view/DTO 模型或 serializer 函数，例如：
  - `AccountView`
  - `PositionView`
  - `OrderView`
  - `TradeView`
  - `PerformanceMetricsView`
  - `BacktestResultView`
- 明确这些 DTO 是 API contract adapter，不参与撮合核心计算。
- 给每个 DTO 写单元测试，固定字段名、单位、百分比口径和空值行为。

### 非目标

- 不在本方向内实现 FastAPI 路由。
- 不要求 React 前端直接接入。
- 不把内部 `Order`、`Fill`、`Position` 全量改名为前端字段。

### 需要重点讨论的问题

- DTO 应该放在 `broker/views.py`、`broker/api_models.py`，还是未来 `server/schemas/broker.py`？
- 百分比字段统一用 `0-1` 还是 `0-100`？
- `/trades` 应暴露 ledger trade record，还是裸 `Fill`？

## 3. 扩展方向二：strategy/account 维度

### 目标

补齐 `strategy_id`、`account_id`、`decision_id` 等领域标识，避免未来把 `session_id` 误用成账户或策略。

### 原因

当前 broker 主要以单个 engine 实例表达一个账户：

- `MockBrokerEngine` 内部 `_cash`、`_positions`、`_orders`、`_fills` 都是实例级全局状态。
- 模型中已有 `session_id`，用于连接一次 Agent run。
- 但上游架构要求一个系统内存在多个策略、多个账户、多个会话。

未来语义应该拆开：

- `strategy_id`：策略配置与长期绩效归属。
- `account_id`：交易账户与持仓归属。
- `session_id`：一次分析/执行 run。
- `decision_id`：一次 PM 决策，用于连接审批、订单、成交、记忆。

### 建议产物

- 在 broker 模型中增加可选字段：
  - `strategy_id: str = ""`
  - `account_id: str = ""`
  - `decision_id: str = ""`
- 在 `ExecutionReport`、`BrokerEvent`、ledger records 中传递这些字段。
- 给 `MockBrokerEngine` 预留账户维度，但第一阶段不必实现多账户撮合。
- 写一份字段语义说明，明确 `session_id` 不等于 `account_id`。

### 非目标

- 不立即实现多账户并发撮合。
- 不实现用户/权限系统。
- 不改变当前 backtest 单账户运行方式，除非作为 adapter 映射。

### 需要重点讨论的问题

- 是否先用一个默认账户 `account_id="default"` 过渡？
- 多策略共享一个 broker singleton 时，账户隔离由 engine 管，还是由上层 broker service 管？
- `strategy_id` 是否允许为空以支持 Quick Ask 咨询模式？

## 4. 扩展方向三：状态枚举与字段口径兼容

### 目标

建立内部 broker 语义与上游 API/前端语义之间的稳定映射，避免 merge 后出现大小写、状态名和单位口径混乱。

### 当前不一致

订单方向：

- 当前内部：`BUY` / `SELL`
- 上游契约：`buy` / `sell`

订单类型：

- 当前内部：`MARKET` / `LIMIT`
- 上游契约：`market` / `limit`

订单状态：

- 当前内部：`NEW` / `FILLED` / `CANCELED` / `REJECTED`
- 上游契约：`pending` / `executed` / `cancelled` / `rejected`

仓位方向：

- 当前内部：`LONG` / `SHORT` / `FLAT`
- `DataService` 输出：`long` / `short` / `flat`

百分比口径：

- `Target_position_pct`、`current_position_pct`：看起来使用 `0-100`。
- `BrokerConfig.max_position_pct`、`PortfolioManager.qty_pct`：当前偏向 `0-1`。

### 建议产物

- 新增 canonical mapping 文档和转换函数。
- API DTO 统一输出前端契约枚举，内部撮合继续使用当前枚举。
- 对所有百分比字段在 docstring 和测试中写清楚单位。
- 优先修正高风险契约：
  - `approval_status="pending"` 不能继续自动执行。
  - `execution_timing="next_open"` 未实现前不得在 API 中宣称支持。
  - `max_total_position_pct` 未实现前应标记为预留字段。

### 非目标

- 不进行大规模重命名。
- 不把所有历史测试的内部枚举都改成小写。

### 需要重点讨论的问题

- API 层是否全部使用小写 enum？
- 内部 `OrderStatus.NEW` 映射到 `pending`，还是新增内部 `PENDING`？
- 百分比口径是否应全仓库统一成 `0-100`，还是内部 `0-1`、API `0-100`？

## 5. 扩展方向四：持久化 backend 与审计事件

### 目标

把当前内存级事件与账本扩展到可持久化、可回放、可被审计页面查询的结构。

### 原因

当前已有基础：

- `BrokerEvent` 可以记录 order placed、filled、rejected、risk check failed 等事件。
- `MockBrokerEngine` 有 `_event_log` 和 order/fill callbacks。
- `TradeLedgerBackend` 可以替换内存 backend。

但上游架构要求：

- trades、approvals、events、performance 进入 per-strategy SQLite。
- 前端可以查看 Audit Trail。
- 单次会话可以按 session 回放。
- 后续 memory/reflection 需要读取真实交易 outcome。

### 建议产物

- 扩展 `BrokerEvent` 字段：
  - `event_id`
  - `event_type`
  - `entity_type`
  - `entity_id`
  - `strategy_id`
  - `account_id`
  - `session_id`
  - `payload`
  - `timestamp`
- 给 `TradeLedgerBackend` 增加 SQLite 实现或 ContextStore adapter。
- 明确事件是 append-only，避免覆盖审计历史。
- 提供查询接口：
  - 按 `session_id`
  - 按 `strategy_id`
  - 按 `account_id`
  - 按 `event_type`

### 非目标

- 不实现完整 ContextStore。
- 不实现前端 Audit 页面。
- 不实现权限、加密或生产级审计合规。

### 需要重点讨论的问题

- broker 是否直接依赖 `storage.ContextStore`，还是只依赖 `LedgerBackend`/`EventSink` protocol？
- 审计事件是否需要严格序列号？
- 失败订单和风控拒单是否必须写 ledger，还是只写 event？

## 6. 扩展方向五：Backtest JSON Contract

### 目标

把当前 `BacktestRunner` 的 Python/DataFrame 输出整理为稳定 JSON contract，为未来 `/api/backtest` 做准备。

### 原因

当前 `BacktestRunner` 已经能运行执行型回测，输出：

- trades DataFrame
- portfolio DataFrame
- metrics dict

但上游 API contract 期望：

- `POST /api/backtest` 返回 `backtest_id`。
- `GET /api/backtest/{backtest_id}` 返回 `status`、summary、results。
- 支持 tickers、date range、forward days、frequency、benchmark。

当前不需要一次做到异步任务系统，但应该先把结果结构稳定下来，避免后续 API 层直接绑定 DataFrame 列名。

### 建议产物

- 新增 `BacktestResultView` serializer。
- 明确 summary 字段：
  - `total_predictions`
  - `cumulative_return_pct`
  - `benchmark_return_pct`
  - `excess_return_pct`
  - `sharpe_ratio`
  - `max_drawdown_pct`
  - `total_trades`
- 明确 time series 字段：
  - `date`
  - `strategy_equity`
  - `benchmark_equity`
  - `strategy_drawdown`
  - `benchmark_drawdown`
- 明确 trades 字段：
  - `timestamp`
  - `ticker`
  - `side`
  - `quantity`
  - `price`
  - `commission`
  - `slippage`
  - `realized_pnl`

### 非目标

- 不实现后台 job queue。
- 不实现异步轮询。
- 不实现多策略参数网格。

### 需要重点讨论的问题

- 当前执行型回测和上游“方向预测准确率回测”是否要区分两个 result 类型？
- benchmark 默认是 SPY，还是由用户指定？
- 多 ticker 回测是共享账户还是每个 ticker 独立账户？

## 7. 扩展方向六：HITL 执行语义与审批安全

### 目标

把当前 execution node 的审批插点升级为安全、明确、可被后续 HITL 系统接管的执行契约。

### 当前状态

当前 `execution_node` 已支持：

- `execution_enabled=False` 时不执行。
- `approval_status="rejected"` 时不执行。
- `approval_status="modified"` 时使用 `modified_target_pct`。
- PM 后可插入 `hitl_approval` 节点。

但存在高风险语义：

- `approval_status="pending"` 当前不会阻止执行。
- 没有 `Approval` 对象。
- 没有审批人、审批时间、修改原因、超时状态。
- 没有 `interrupt/resume` 契约。

### 建议产物

- 修正执行语义：
  - `pending`：不执行，返回结构化 pending report。
  - `approved` / `auto_approved`：允许执行。
  - `modified`：允许执行，但必须记录原始目标仓位与修改后目标仓位。
  - `rejected` / `timed_out`：不执行。
- 新增最小审批上下文字段：
  - `approval_id`
  - `approval_status`
  - `approval_reason`
  - `modified_target_pct`
  - `reviewer`
  - `reviewer_notes`
- 执行报告中记录审批状态。
- 为未来 HITL Manager 保留 `on_execution_blocked` 或 event hook。

### 非目标

- 不实现完整 HITL Manager。
- 不实现消息通知审批。
- 不实现前端审批页面。

### 需要重点讨论的问题

- `pending` 时 execution node 应返回字符串、JSON，还是 `ExecutionReport` 的 rejected/pending 变体？
- approval 状态属于 `AgentState`，还是单独 `Approval` 模型？
- HITL 判断规则由 broker 风控触发，还是上层 HITL Manager 触发？

## 8. 建议优先级

建议按以下顺序推进：

1. 状态枚举与百分比口径兼容。
2. strategy/account/decision 标识补齐。
3. API DTO 与 serializer。
4. HITL pending 安全语义。
5. Backtest JSON contract。
6. SQLite backend 与审计事件持久化。

这个顺序的理由是：先固定语义，再固定身份，再固定对外形状，最后接持久化和 API。这样对现有 broker 内核侵入最小，也最利于未来与 `feat/frontend-foundation` 合并。
