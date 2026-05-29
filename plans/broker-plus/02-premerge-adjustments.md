# feat/broker 可提前调整建议

> 记录日期：2026-05-29
> 目的：列出在不侵入其他职责边界的前提下，`feat/broker` 可以提前完成的调整，降低后续与 `feat/frontend-foundation` 合并和模块对接的摩擦。

## 1. 调整原则

这些调整应该满足三个条件：

1. 只服务 broker 执行域，不接管前端、完整后端、MCP、notification、15-agent pipeline。
2. 保持当前 broker 测试和 Streamlit broker smoke 的稳定。
3. 优先增加 adapter、字段、文档和小型契约测试，避免大规模重命名或跨模块重构。

## 2. 可以提前做的调整

### 2.1 增加领域标识字段

建议在 broker 相关模型中提前加入可选字段：

- `strategy_id`
- `account_id`
- `decision_id`
- 保留现有 `session_id`

目的不是立即实现多账户，而是避免未来把 `session_id` 硬解释为账户或策略。

建议覆盖范围：

- `Order`
- `Fill`
- `Position`
- `AccountSnapshot`
- `ExecutionReport`
- `BrokerEvent`
- ledger record

### 2.2 增加只读 serializer / view 层

建议新增一层不参与撮合的 view adapter：

- 内部 `Position` -> 前端 `PositionView`
- ledger fill record -> 前端 `TradeView`
- account snapshot -> 前端 `AccountView`
- metrics dict -> 前端 `PerformanceMetricsView`
- backtest result -> 前端 `BacktestResultView`

这样未来 FastAPI 路由可以直接调用 serializer，而不需要在路由层理解 broker 内部字段。

### 2.3 明确百分比字段口径

当前有两种口径混用风险：

- `Target_position_pct`、`current_position_pct` 接近 `0-100`。
- `BrokerConfig.max_position_pct`、`PortfolioManager.qty_pct` 接近 `0-1`。

建议提前做：

- 在 docstring 和测试中明确每个字段单位。
- 对 API view 统一输出前端约定的口径。
- 对内部配置保留现状，但通过命名或注释标明 decimal fraction。

### 2.4 修正 HITL pending 执行语义

当前 `approval_status="pending"` 没有被特殊阻止，未来审批系统接入时可能导致“待审批却已执行”。

建议提前改为：

- `pending`：不执行，返回结构化 blocked/pending 结果。
- `approved` / `auto_approved`：允许执行。
- `modified`：允许执行并使用修改后的目标仓位。
- `rejected` / `timed_out`：不执行。

这是低侵入、高收益的安全修正。

### 2.5 扩展 BrokerEvent

当前 `BrokerEvent` 可以记录事件类型、时间、session、ticker、details，但未来审计页面需要更强的索引字段。

建议提前增加：

- `event_id`
- `strategy_id`
- `account_id`
- `entity_type`
- `entity_id`
- `payload`

可以继续保留内存 event log，不必马上做 SQLite。

### 2.6 将 `on_execution_complete` 提升到 orchestrator 构造参数

当前 `create_execution_node` 已支持 `on_execution_complete`，但 orchestrator 默认创建 execution node 时没有将该 hook 作为一等配置传入。

建议调整为：

- `IntelliFin_Assistant(..., on_execution_complete=None)`
- 创建 execution node 时透传该 hook。

这样未来 ContextStore、notification、audit 都可以挂接执行结果，而不需要改 DAG 结构。

### 2.7 写 broker 与 frontend contract mapping 文档

建议新增一份映射文档，说明：

- 内部模型字段。
- API view 字段。
- 单位。
- enum 映射。
- 空值行为。
- 哪些字段暂未实现。

这比提前重构代码更稳，也方便团队合并时对齐语义。

## 3. 不建议提前做的调整

### 3.1 不建议全量同步上游 README

不建议直接把 `feat/frontend-foundation` 的 `README.md` 覆盖到当前 `feat/broker`。

原因：

- 上游 README 把很多架构目标写成当前状态，容易与 `feat/broker` 已完成内容混淆。
- 上游 README 宣称 React/FastAPI/ContextStore/MCP/Memory 等整体能力，但当前分支实现还不完整。
- 当前 README 包含 uv、quality gate、Streamlit broker smoke 等与 `feat/broker` 实际验收相关的信息。

建议做法：

- 不 wholesale replace。
- 可以创建融合版 README 或 docs index。
- 吸收上游的架构地图和文档入口。
- 保留当前 broker 完成状态、测试命令和质量门禁。

### 3.2 不建议接管 React 前端

`frontend/` 页面、shadcn/ui、Next.js 路由属于 `feat/frontend-foundation` 的职责。

`feat/broker` 可以提供 DTO 和契约，但不应在当前分支实现或修复 React 页面。

### 3.3 不建议接管完整 FastAPI 路由

可以为未来 FastAPI 提供 serializer，但不建议当前分支直接新增完整 `/api/strategies/{id}/account`、`/api/backtest`、`/api/approvals`。

原因：

- API 路由涉及 server app 结构、CORS、SSE、错误码、分页、OpenAPI schema。
- 这会跨出 broker 任务边界。

### 3.4 不建议接管完整 ContextStore

可以实现 `TradeLedgerBackend` 的 SQLite 版本或 ContextStore adapter protocol，但不建议把 `storage/` 整个持久化系统放到 broker 分支内完成。

### 3.5 不建议接管 15-agent pipeline

上游规划的 company overview、sentiment、technical、macro、bull/bear debate、risk debate、trader 等属于 agent/orchestrator 大改。

broker 分支只需要保证未来 trader/PM 输出订单或目标仓位时，broker 能稳定执行并记录。

### 3.6 不建议删除 Streamlit 相关验证

即使未来 React 成为主前端，当前 Streamlit broker smoke 仍是 `feat/broker` 已完成能力的回归证据。合并前不应主动移除。

## 4. 当前已知冲突点

非破坏性 merge-tree 预测显示，未来合并主要冲突集中在：

- `README.md`
- `agentgraph/orchestrator.py`
- `agents/utils/agent_tools.py`
- `dataflow/service.py`
- `properties.env`
- `reports/README.md`
- `reports/detail-proposal/proposal.pdf`
- `reports/detail-proposal/proposal.typ`
- `requirements.txt` rename：`feat/broker` 改为 `requirements.old.txt`，上游改为 `archive/requirements.txt`

其中真正与 broker 对接关系最大的文件是：

- `agentgraph/orchestrator.py`
- `agents/utils/agent_tools.py`
- `dataflow/service.py`

因此提前调整时应尽量：

- 不扩大这些文件的改动面。
- 对新增能力采用小函数、adapter、Protocol 方式接入。
- 在文档中说明未来合并策略，避免团队重复改同一段逻辑。

## 5. 推荐的短期行动清单

优先级从高到低：

1. 写 broker/frontend contract mapping 文档。
2. 修正 `approval_status="pending"` 的执行语义。
3. 增加 `strategy_id/account_id/decision_id` 可选字段。
4. 增加 `BrokerEvent` 索引字段。
5. 增加 API view serializer，但不实现 FastAPI。
6. 为 backtest result 增加 JSON adapter。
7. 将 `on_execution_complete` 提升到 orchestrator 构造参数。

这些动作都属于 broker 对接准备，不会侵入前端或后端平台职责。
