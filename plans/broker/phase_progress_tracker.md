# Broker 实施分阶段进度追踪

> 基线审计日期: 2026-04-13
> 对应分支: `feat/broker`
> 来源计划: `plans/broker/impl_plan_final.md`

---

## 1 当前基线

当前分支已经具备 Broker 集成前的主链路与若干可复用资产；截至 `2026-04-13`，`broker/` 顶层包的 **Phase 1 数据模型层** 已完成落地，Phase 2+ 尚未开始。

### 已存在的可复用基础

- Agent 主流程已打通到 `PM_agent`，但当前仍以 `PM_agent -> END` 结束，尚无 execution node 闭环。
- `DataService` 已支持历史价格、指标、基本面、新闻的 `end_date` 读取语义，可作为回测数据入口。
- `PortfolioManager` 已具备状态化持仓与风险限额管理，但还没有 `sync_from_broker()`。
- `test/trade.py` 已有脚本级回测原型，含手续费、滑点、多空统一 PnL、CSV 输出，可作为撮合/账本参考逻辑。
- Streamlit 已有历史分析与验证页面，但还没有 Broker 级交易日志与绩效面板。

### 当前关键缺口

- `broker/` 顶层包已创建，但目前仅包含 Phase 1 的 `models.py` / `config.py` / `events.py`；`gateway.py` / `engine.py` / `risk_checks.py` / `ledger.py` 仍未开始。
- `agentgraph/state.py` 尚无 `execution_report`、`execution_enabled`、`session_id` 等执行层字段。
- `agentgraph/orchestrator.py` 仍是 `PM_agent -> END`，Phase 4 的执行闭环未接入。
- 项目级 `pyright` / `ruff` / `pytest` 约束现已写入 `pyproject.toml`，但仓库的 `basedpyright` 基线仍为红色，存在历史类型错误待消化。

---

## 2 全局执行规约

- 所有实现必须严格遵循 `tdd` 的 `red -> green -> refactor`，一次只推进一个垂直切片。
- 全部开发、测试、lint、format、type check 统一通过 `uv run ...` 执行。
- 质量门禁固定为：
  - `uv run basedpyright`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - 对应 Phase 的 `uv run pytest ...`
- 验收标准为 `0-warning / 0-error`。

---

## 3 工具状态

| 项目 | 当前状态 | 备注 |
| --- | --- | --- |
| `uv` | Ready | 项目已采用 `uv` 工作流 |
| `ruff` | Ready | 本地可执行，当前版本探测为 `0.14.3` |
| `basedpyright` | Ready, baseline red | 已可执行；使用 `pyproject.toml` 中的 `[tool.pyright]` 配置，首轮检查发现 78 个历史 error |
| `pytest` | Ready | 已作为 dev 依赖纳入项目级工作流 |

### 当前全局质量阻塞

- `uv run ruff check .` 通过。
- `uv run ruff format --check .` 通过。
- `uv run basedpyright` 未通过，当前发现 `78 errors / 0 warnings`。
- `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json` 通过，说明历史类型问题已完成隔离。
- 主要历史问题集中在这些区域：
  - `agentgraph/orchestrator.py`
  - `agentgraph/state.py`
  - `dataflow/providers/YFinance.py`
  - `dataflow/providers/fundamentals_akshare.py`
  - `dataflow/providers/macro_calendar.py`
  - `streamlit_app.py`
  - `test/eva.py`
  - `test/ticker_download.py`
  - `test/trade.py`
  - `utils/pdf_generator.py`

> 这意味着“项目级质量门禁”已经建立，但“全仓库 0-warning / 0-error”还没有达成；当前采用 `bugs/basedpyright/baseline.json` 隔离历史债务，并用带 baseline 的命令作为增量开发 gate。

---

## 4 分阶段状态总览

| Phase | 状态 | 当前判断 | 下一步最小 TDD 切片 | 完成门禁 |
| --- | --- | --- | --- | --- |
| Phase 1 数据模型层 | Completed | `broker/` Phase 1 已落地，含模型/配置/事件和 pytest 覆盖 | Phase 2 起点：先写市价买入立即成交的失败测试，再实现最小 `place_order()` | `uv run pytest test/test_broker_models.py -q` + `basedpyright --baselinefile` + `ruff` 全绿 |
| Phase 2 撮合引擎 + Broker 接口 | Not Started | 只有 `test/trade.py` 的脚本级执行逻辑可复用 | 先写市价买入成交的行为测试，再抽出最小 `MockBrokerEngine` | Phase 2 测试 + 质量门禁全绿 |
| Phase 3 账本 + 交易日志 | Not Started | 无 `ledger.py`，`PortfolioManager` 也无 broker 同步口 | 先写记录单笔 fill 的失败测试，再实现最小账本 | Phase 3 测试 + 质量门禁全绿 |
| Phase 4 主工作流集成 | Not Started | 目前仍是 `PM_agent -> END` | 先写 execution node 接入状态更新的失败测试 | Phase 4 测试 + 图结构验证 + 质量门禁全绿 |
| Phase 5 UI + 测试 | Not Started | 现有 Streamlit 仅支持历史分析验证 | 先写回测结果展示的数据接口测试，再接 UI | Phase 5 测试 + 手动 UI 验证 + 质量门禁全绿 |

---

## 5 分阶段追踪明细

### Phase 1 数据模型层

**状态**: `Completed`

**本阶段目标**

- [x] 建立 `broker/models.py`
- [x] 建立 `broker/config.py`
- [x] 建立 `broker/events.py`
- [x] 补齐 `Order` / `Fill` / `Position` / `AccountSnapshot` / `ExecutionReport`
- [x] 建立 `broker/__init__.py` 统一导出 Phase 1 公共类型
- [x] 建立 `test/test_broker_models.py` 与 `test/conftest.py`

**当前证据**

- 已创建 `broker/` 顶层包，并落地这些文件：
  - `broker/__init__.py`
  - `broker/models.py`
  - `broker/config.py`
  - `broker/events.py`
- `broker/models.py` 已包含：
  - 枚举：`OrderSide` / `OrderType` / `OrderStatus`
  - 模型：`Order` / `Fill` / `Position` / `AccountSnapshot` / `ExecutionReport`
- `ExecutionReport` 已按计划保留 `pm_action` / `pm_report_summary`，全部模型均保留 `session_id` 预留字段。
- `BrokerConfig` 已使用 `BaseSettings` 落地；为此已补充项目依赖 `pydantic-settings`。
- 已建立 Phase 1 pytest 用例，覆盖订单默认行为、模型约束、嵌套执行报告、事件默认值与配置默认值。

**TDD 执行记录**

- [x] RED -> GREEN: `Order` 默认 `NEW` 状态、自动生成 `id` / UTC 时间戳
- [x] RED -> GREEN: `LIMIT` 订单缺少 `limit_price` 时校验失败
- [x] RED -> GREEN: `Order.qty` 必须为正数
- [x] RED -> GREEN: `Fill` 自动补 UTC 时间戳与 `session_id`
- [x] RED -> GREEN: `Position` 从 `shares` 符号推导 `side`
- [x] RED -> GREEN: `AccountSnapshot` + `ExecutionReport` 嵌套模型与 `pm_action` / `pm_report_summary`
- [x] RED -> GREEN: `BrokerEvent` 默认 `details` 独立且不共享可变状态
- [x] RED -> GREEN: `BrokerConfig` 默认值与显式覆盖行为
- [x] REFACTOR: 增加 `test/conftest.py`，让标准 `uv run pytest ...` 可导入本地 `broker` 包
- [x] REFACTOR: 补充 `pydantic-settings` 依赖，使 `BrokerConfig(BaseSettings)` 与类型检查一致

**验证结果**

- [x] `uv run pytest test/test_broker_models.py -q`
- [x] `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json`
- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`

**阻塞项**

- [x] 无 Phase 1 特有阻塞；历史类型债务已通过 `bugs/basedpyright/baseline.json` 隔离

### Phase 2 撮合引擎 + Broker 接口

**状态**: `In Progress`

**本阶段目标**

- 建立 `broker/gateway.py`
- 建立 `broker/engine.py`
- 建立 `broker/risk_checks.py`
- 让市价单 / 限价单 / 手续费 / 滑点 / 持仓更新进入正式模块

**当前证据**

- `test/trade.py` 已包含可迁移的多空统一 PnL 与执行逻辑，可作为参考实现来源。
- 已新增：
  - `broker/gateway.py`
  - `broker/engine.py`
  - `broker/risk_checks.py`
  - `test/test_broker_engine.py`
- `MockBrokerEngine` 现已具备这些可观察行为：
  - `BrokerGateway` 公共查询接口：`get_account()` / `get_position()` / `get_positions()` / `get_order()` / `get_orders()` / `get_fills()`
  - 市价单按 `close ± slippage` 立即成交
  - 限价买单先挂起，后续 `on_bar()` 在价格触及时成交
  - 多空统一持仓更新已覆盖“开多、加多、平多、反手”所需的核心符号语义
  - 下单前风控已覆盖资金不足（含滑点+手续费）与 `max_position_pct`
- 事件 hooks / 事件日志、总仓位上限、更多订单生命周期场景仍待后续切片完成。

**TDD 执行记录**

- [x] RED -> GREEN: `test_market_buy_order_fills_immediately_and_updates_account_state`
- [x] RED -> GREEN: 最小 `BrokerGateway` / `MockBrokerEngine.place_order()` / `get_account()` / `get_position()` / `get_fills()`
- [x] RED -> GREEN: `test_limit_buy_order_stays_pending_until_a_future_bar_touches_the_limit`
- [x] RED -> GREEN: `on_bar()` + pending limit order trigger
- [x] RED -> GREEN: `test_market_sell_can_close_an_existing_long_position`
- [x] RED -> GREEN: 从 `test/trade.py` 提炼多空统一持仓更新逻辑，覆盖平仓与反手语义
- [x] RED -> GREEN: `test_market_buy_is_rejected_when_cash_cannot_cover_slippage_and_fees`
- [x] RED -> GREEN: 风控资金检查改为按市场单预计成交价（含滑点）+ 手续费估算
- [x] RED -> GREEN: `test_market_buy_is_rejected_when_it_would_breach_max_position_pct`
- [x] RED -> GREEN: 单票仓位上限 `max_position_pct` 前置校验
- [x] REFACTOR: 提取 `_calculate_next_position()`，把持仓符号语义收敛到引擎内部
- [ ] RED: 限价卖单 / 取消订单行为测试
- [ ] RED: 做空开仓 / 回补行为测试
- [ ] RED: `allow_short=False` 的拒单测试

**验证结果**

- [x] `uv run pytest test/test_broker_models.py test/test_broker_engine.py -q`
- [x] `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json`
- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`

**阻塞项**

- [ ] 无外部阻塞；剩余工作主要是继续按 TDD 补齐 Phase 2 其余行为切片

### Phase 3 账本 + 交易日志

**状态**: `Not Started`

**本阶段目标**

- 建立 `broker/ledger.py`
- 记录 fills / snapshots
- 计算核心绩效指标
- 在 `PortfolioManager` 增加 `sync_from_broker()`

**当前证据**

- `PortfolioManager` 目前只有 `update_position()`，没有从 broker 同步的正式接口。
- 现有回测 CSV 输出逻辑散落在 `test/trade.py`，还没有抽象成账本模块。

**TDD 执行记录**

- [ ] RED: 记录单笔 fill 后可回读测试
- [ ] GREEN: 最小 `InMemoryLedgerBackend`
- [ ] RED: 绩效指标最小样例测试
- [ ] GREEN: `compute_metrics()`
- [ ] REFACTOR: `PortfolioManager.sync_from_broker()`

### Phase 4 主工作流集成

**状态**: `Not Started`

**本阶段目标**

- 扩展 `AgentState`
- 新增 `agentgraph/execution_node.py`
- 将 `PM_agent` 之后接入执行节点
- 让 `DataService` / `agent_tools` 可以注入 broker
- 建立 `broker/backtest_runner.py`

**当前证据**

- `agentgraph/orchestrator.py` 当前明确是 `PM_agent -> END`。
- `dataflow/service.py` 当前没有 broker 注入参数。
- `agents/utils/agent_tools.py` 仍是模块级数据服务入口。

**TDD 执行记录**

- [ ] RED: `execution_enabled=False` 时跳过执行测试
- [ ] GREEN: 最小 execution node 框架
- [ ] RED: `BUY/SELL` 决策生成执行报告测试
- [ ] GREEN: broker 调用与 state 写回
- [ ] REFACTOR: `DataService` 注入与 `BacktestRunner` 接口收敛

### Phase 5 UI + 测试

**状态**: `Not Started`

**本阶段目标**

- Streamlit 增加交易日志与绩效面板
- 建立 `test/test_broker.py`
- 完成端到端回测测试

**当前证据**

- 当前 Streamlit 页面主要是分析结果展示与历史验证，不是 Broker 执行视角。
- 当前 `test/` 目录以脚本为主，不是 pytest 测试套件。

**TDD 执行记录**

- [ ] RED: 回测结果数据结构测试
- [ ] GREEN: 最小展示数据管线
- [ ] RED: 端到端回测最小 happy path 测试
- [ ] GREEN: `BacktestRunner` 与 UI 读取接通
- [ ] REFACTOR: 整理测试夹具与页面数据适配层

---

## 6 审计参考点

- `agentgraph/orchestrator.py`: 当前工作流止于 `PM_agent`
- `agentgraph/state.py`: 当前仅有分析/决策字段
- `dataflow/service.py`: 当前尚无 broker 注入
- `dataflow/portfolio_manager.py`: 当前尚无 `sync_from_broker()`
- `test/trade.py`: 脚本级回测与执行参考逻辑
- `streamlit_app.py`: 现有历史分析验证 UI

---

## 7 近期更新记录

### 2026-04-13

- [x] 完成 `feat/broker` 当前实现状态审计
- [x] 新建本阶段追踪文档
- [x] 将工程规约与质量门禁回写到 `impl_plan_final.md`
- [x] 将 `pyright` / `basedpyright` / `pytest` / `ruff` 项目级配置补入 `pyproject.toml`
- [x] 完成首轮 `ruff` / `basedpyright` 基线检查
- [x] 生成 `bugs/basedpyright/baseline.json` 并完成历史类型问题隔离
- [x] 将历史类型问题按工具基线 + AI 可检索索引归档到 `bugs/basedpyright/`
- [x] `ruff check .` 通过
- [x] 启动 Phase 2：完成 `BrokerGateway` / `MockBrokerEngine` / `PreTradeRiskChecker` 的首批 TDD 切片
- [x] 完成 Phase 2 首批公共行为测试：市价买入、限价挂单触发、平多、资金不足拒单、单票仓位上限拒单
- [x] `uv run pytest test/test_broker_models.py test/test_broker_engine.py -q` 通过
- [x] `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json` 通过
- [x] `uv run ruff check .` 通过（含 Phase 2 增量）
- [x] `uv run ruff format --check .` 通过（含 Phase 2 增量）
- [x] `ruff format --check .` 通过
- [x] 新建 `broker/__init__.py` / `broker/models.py` / `broker/config.py` / `broker/events.py`
- [x] 新建 `test/test_broker_models.py` 与 `test/conftest.py`
- [x] 为 `BrokerConfig(BaseSettings)` 补充 `pydantic-settings` 依赖
- [x] 完成 Phase 1 数据模型层的 TDD 切片并全部转绿
- [x] `basedpyright --baselinefile bugs/basedpyright/baseline.json` 通过
- [x] Phase 1 当前增量质量门禁：`0 errors / 0 warnings / 0 notes`
