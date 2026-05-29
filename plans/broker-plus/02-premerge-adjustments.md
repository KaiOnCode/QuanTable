# broker-plus 可提前调整清单

> 记录日期：2026-05-29
> 定位：本文只是一份排期前置清单，不是冻结契约，也不是实现脚本。冻结契约唯一来源是 `plans/broker-plus/frozen-contract-and-impl-plan.md`。

## 1. 使用原则

所有提前调整必须服从冻结契约中的边界：

1. broker 只负责执行域：订单、成交、持仓、账户隔离、风控、账本、broker 事件、执行报告和 broker-owned view/serializer。
2. broker 不接管 React/Next.js 前端、完整 FastAPI、ContextStore、MCP、通知系统、完整 HITL manager 或 15-agent pipeline。
3. 第一阶段只定义协议边界和内存实现，不实现 SQLite、ContextStore adapter 或生产级审计存储。
4. `broker/views.py` 是 API/前端消费的执行域契约层，但它不是 HTTP 层。
5. 失败订单和风控拒单不写入 trade ledger；它们进入 event sink 和 order/report view。
6. `execution_enabled=False`、PM `HOLD`、目标仓位已满足只返回 report，不写 broker event sink。

## 2. 立即执行

这些事项可以在实现代码前完成，且本身不改变 broker 运行行为。

### 2.1 将本文降级为排期清单

- **动作**：明确本文只解释哪些调整提前做、何时做、在哪里做；不再作为实现顺序的事实来源。
- **对应文件范围**：`plans/broker-plus/02-premerge-adjustments.md`。
- **依赖**：必须先阅读 `plans/broker-plus/frozen-contract-and-impl-plan.md`。
- **验收 gate**：本文所有字段、状态、事件和非目标都能追溯到冻结契约。
- **非目标**：不在本文新增冻结决策，不覆盖冻结契约。

### 2.2 固定 broker-plus 与 integration 的职责分界

- **动作**：把可提前事项分为 broker-plus 内执行、随实现排期执行、integration branch 执行、明确不做四类。
- **对应文件范围**：`plans/broker-plus/02-premerge-adjustments.md`、`plans/broker-plus/frozen-contract-and-impl-plan.md`。
- **依赖**：`plans/broker-plus/03-merge-order-recommendation.md` 只作为集成顺序背景。
- **验收 gate**：FastAPI routes、React 页面、ContextStore、MCP、通知、完整 HITL workflow 不出现在 broker-plus 实现任务内。
- **非目标**：不解决分支 merge 冲突，不修改 README。

### 2.3 保留当前 Streamlit broker smoke 证据

- **动作**：在计划里继续把 Streamlit broker smoke 视为 broker 已有能力的回归证据。
- **对应文件范围**：`plans/broker-plus/frozen-contract-and-impl-plan.md` 的最终回归 gate。
- **依赖**：无代码依赖；只依赖冻结契约的非目标。
- **验收 gate**：最终 gate 仍包含 `test/streamlit/test_streamlit_app.py` 或等价 smoke 证据。
- **非目标**：不迁移 Streamlit 到 React，不删除 Streamlit 验证。

## 3. 随实现排期执行

这些事项属于 broker-plus 第一阶段实现。它们可以早于 frontend integration 完成，但必须按照冻结契约的 phase 和测试 gate 推进。

### 3.1 身份字段和账本传播

- **phase**：Phase 1 / Task 1。
- **动作**：为 `Order`、`Fill`、`Position`、`AccountSnapshot`、`ExecutionReport`、`BrokerEvent`、ledger records 补齐 `strategy_id`、`account_id`、`session_id`、`decision_id` 的默认语义。
- **依赖**：冻结契约的 identity semantics。
- **对应文件范围**：`broker/models.py`、`broker/events.py`、`broker/ledger.py`、`broker/__init__.py`、`test/broker/test_models.py`、`test/broker/test_ledger.py`。
- **验收 gate**：默认值和 ledger round-trip 测试通过；`session_id` 不被解释为 strategy/account/decision。
- **非目标**：不实现用户/权限系统，不把 `decision_id` 生成职责放入 broker。

### 3.2 broker event sink 协议和内存实现

- **phase**：Phase 1 / Task 3。
- **动作**：扩展 broker execution-domain event 字段，新增 `BrokerEventSink` protocol 和 `InMemoryBrokerEventSink`，由 sink 按 `(strategy_id, account_id)` 分配单调 `sequence`。
- **依赖**：身份字段默认语义。
- **对应文件范围**：`broker/events.py`、`broker/engine.py`、`broker/__init__.py`、`test/broker/test_models.py`、`test/broker/test_engine.py`。
- **验收 gate**：事件字段完整；不同 account 的 sequence 独立从 1 开始。
- **非目标**：不实现 SQLite event store，不接入 ContextStore，不做权限、加密或生产级审计合规。

### 3.3 MockBrokerEngine 账户隔离

- **phase**：Phase 2 / Task 2。
- **动作**：让 `MockBrokerEngine` 按 `account_id` 隔离 cash、positions、orders、fills 和 event log，同时保留 `"default"` 兼容行为。
- **依赖**：身份字段和 event sink 边界。
- **对应文件范围**：`broker/engine.py`、`broker/gateway.py`、`test/broker/test_engine.py`。
- **验收 gate**：两个 account 的账户快照、持仓、订单、成交和事件互不污染；旧默认账户测试继续通过。
- **非目标**：不实现多策略调度，不实现多用户权限，不改写 backtest 为 per-ticker 独立账户。

### 3.4 broker-owned 视图/序列化层

- **phase**：Phase 3 / Task 4。
- **动作**：新增 `broker/views.py`，固定 `AccountView`、`PositionView`、`OrderView`、`FillView`、`TradeView`、`ApprovalSnapshotView`、`ExecutionReportView`、`BrokerEventView`、`PerformanceMetricsView`、`BacktestConfigView`、`BacktestSeriesPointView`、`BacktestResultView`。
- **依赖**：身份字段、账户隔离和 ledger/event 边界。
- **对应文件范围**：`broker/views.py`、`broker/__init__.py`、`test/broker/test_views.py`。
- **验收 gate**：枚举映射、百分比单位、订单成交聚合、持仓价格来源和从账本生成交易视图的语义都有测试固定。
- **非目标**：不实现 FastAPI route，不让 React 直接依赖 broker 内部模型，不把内部 enum 大规模改名。

### 3.5 执行报告和 HITL 安全语义

- **phase**：Phase 4 / Task 5。
- **动作**：让 execution node 所有分支返回结构化 `ExecutionReportView` JSON；`pending`、`rejected`、`timed_out`、缺价格、禁用执行、HOLD、目标已满足都有明确状态。
- **依赖**：`ExecutionReportView`、event sink、身份传播。
- **对应文件范围**：`agentgraph/execution_node.py`、`agentgraph/state.py`、`test/agentgraph/test_execution_node.py`、`test/agentgraph/test_orchestrator.py`。
- **验收 gate**：`pending/skipped/held/rejected/failed/executed` 分支都有测试；`skipped/held` 不写 broker event；`modified` 记录原始和修改后目标仓位。
- **非目标**：不实现 HITL manager、审批策略规则、通知、interrupt/resume 或前端审批页。

### 3.6 回测 JSON 契约

- **phase**：Phase 5 / Task 6。
- **动作**：把执行型回测结果序列化成同步完成的 `BacktestResultView`，包含 `benchmark_symbol`、summary、series、trades。
- **依赖**：view/serializer 层和 TradeView 语义。
- **对应文件范围**：`broker/backtest_runner.py`、`broker/views.py`、`test/broker/test_backtest_runner.py`、`test/broker/test_views.py`。
- **验收 gate**：`status="completed"`、`benchmark_symbol="SPY"` 默认、百分比点输出、benchmark/excess return、portfolio-level series 和 ledger-derived trades 都有测试。
- **非目标**：不实现异步 job queue，不实现 `/api/backtest`，不实现方向预测准确率回测 contract。

### 3.7 orchestrator 执行 hook 透传

- **phase**：Phase 6 / Task 7。
- **动作**：把 `on_execution_complete` 提升为 `IntelliFin_Assistant` 构造参数，并透传到 execution node。
- **依赖**：结构化 `ExecutionReportView`。
- **对应文件范围**：`agentgraph/orchestrator.py`、`test/agentgraph/test_orchestrator.py`。
- **验收 gate**：callback 精确收到一次 broker-owned report 和 state。
- **非目标**：不改变 graph topology，不在 broker-plus 接入 ContextStore、notification 或 audit service。

### 3.8 契约映射和最终回归

- **phase**：Phase 7 / Task 8。
- **动作**：新增最终 mapping 文档，收敛 `WIP.md` 指向冻结契约和 mapping 文档。
- **依赖**：前面所有 phase 已实现并通过测试。
- **对应文件范围**：`plans/broker-plus/05-contract-mapping.md`、`plans/broker-plus/WIP.md`、现有 broker/agentgraph/streamlit 测试。
- **验收 gate**：mapping 文档覆盖身份字段、百分比单位、enum 映射、执行报告状态、event/ledger 边界、backtest JSON shape 和非目标；完整 broker-plus 回归命令通过。
- **非目标**：不把 mapping 文档变成 API server 说明书，不融合 README。

## 4. 集成分支执行

这些事项需要等 broker-plus contract 通过验收后，在 `integration/frontend-broker` 或等价集成分支处理。

### 4.1 README 和项目入口融合

- **动作**：融合当前 broker 工程状态和 frontend-foundation 的目标架构说明。
- **依赖**：broker-plus 最终 gate；frontend 分支先对齐当前 `main`。
- **对应文件范围**：`README.md`、docs index、启动说明。
- **验收 gate**：README 区分已完成、进行中、规划中；保留 uv、quality gate、broker smoke；不宣称未实现能力已经完成。
- **非目标**：不在 broker-plus 分支单边覆盖 README。

### 4.2 FastAPI adapter 和路由对接

- **动作**：把 FastAPI routes 做成 broker view/serializer 的薄 adapter。
- **依赖**：`broker/views.py` 和 `ExecutionReportView` 稳定。
- **对应文件范围**：未来 server/FastAPI app、route schemas、OpenAPI、错误码、分页和 SSE glue。
- **验收 gate**：API 返回 broker-owned view contract，不复制 broker 内部语义。
- **非目标**：不让 broker package import FastAPI。

### 4.3 React/Next.js 前端对接

- **动作**：前端 API client、类型、页面和交互消费 broker API contract。
- **依赖**：FastAPI adapter 和 broker view contract。
- **对应文件范围**：`frontend/`、前端 types、API client、query provider、页面组件。
- **验收 gate**：前端类型与后端 response contract 对齐。
- **非目标**：不在 broker-plus 中修 React 页面或 shadcn/ui 组件。

### 4.4 持久化、ContextStore、MCP、通知和完整 HITL

- **动作**：在平台层决定 SQLite/ContextStore adapter、MCP memory/reflection、通知渠道、HITL manager、approval workflow 和 audit 查询。
- **依赖**：broker event sink protocol、ledger backend protocol、ExecutionReportView approval snapshot。
- **对应文件范围**：未来 storage/server/hitl/notification/MCP 模块。
- **验收 gate**：平台 adapter 只依赖 broker protocol 或 view contract，不把平台依赖反向塞进 broker。
- **非目标**：不在 broker-plus 第一阶段实现这些系统。

## 5. 明确不做

以下事项不进入 broker-plus 第一阶段。若未来要做，必须另开平台、前端、后端或 HITL 计划。

1. 不实现 React/Next.js 页面、前端路由、前端组件库或 API client。
2. 不实现完整 FastAPI app、REST routes、SSE、OpenAPI schema、分页或 HTTP 错误模型。
3. 不实现 ContextStore、MCP、Memory/reflection、notification channels。
4. 不实现完整 HITL manager、审批策略规则、通知审批、interrupt/resume 或前端审批页。
5. 不实现 SQLite adapter、生产级审计存储、权限、加密或合规审计。
6. 不实现 15-agent pipeline、company overview、sentiment、technical、macro、bull/bear debate、risk debate 等上游 agent 大改。
7. 不实现异步 backtest job queue，不实现方向预测准确率回测 contract。
8. 不把失败订单、风险拒单写入 trade ledger。
9. 不对内部 broker enum 做大规模重命名；小写 enum 只属于 view contract。
10. 不删除 Streamlit broker smoke 证据。
11. 不在 broker-plus 分支融合或单边覆盖 README。

## 6. 当前冲突风险的处理口径

`plans/broker-plus/03-merge-order-recommendation.md` 中提到的冲突点仍然有效，但它们不是 broker-plus 实现任务。

- `agentgraph/orchestrator.py`：broker-plus 只做 execution hook 透传；FastAPI/SSE run wrapper 留给 integration branch。
- `agents/utils/agent_tools.py`：不在 broker-plus 中吸收前端分支的工具扩展。
- `dataflow/service.py`：不在 broker-plus 中合入 frontend-foundation 的 cache、AkShare news fallback、sentiment 或 MarketDataStore 改造。
- `README.md`：只在 integration branch 人工融合。
- `requirements.txt`、`pyproject.toml`、`uv.lock`：由 integration branch 统一依赖管理策略。

短期结论：broker-plus 的提前价值是把执行域契约做稳，而不是提前接管平台集成。
