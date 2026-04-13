# Broker 实施分阶段进度追踪

> 基线审计日期: 2026-04-13
> 对应分支: `feat/broker`
> 来源计划: `plans/broker/impl_plan_final.md`

---

## 1 当前基线

当前分支已经完成 Broker 集成前的基础设施与主链路收口；截至 `2026-04-13`，`broker/` 顶层包的 **Phase 1-4 核心范围** 已完成落地，Phase 5 仍未开始。

### 已存在的可复用基础

- Agent 主流程现已支持 `PM_agent -> execution_node -> END`，并在 `enable_hitl=True` 时预留 `PM_agent -> hitl_approval -> execution_node -> END` 插入点。
- `DataService` 已支持历史价格、指标、基本面、新闻的 `end_date` 读取语义，可作为回测数据入口。
- `PortfolioManager` 已具备状态化持仓与风险限额管理，现已补上 `sync_from_broker()` 的最小 broker 同步口。
- `test/trade.py` 已有脚本级回测原型，含手续费、滑点、多空统一 PnL、CSV 输出，可作为撮合/账本参考逻辑。
- Streamlit 已有历史分析与验证页面，但还没有 Broker 级交易日志与绩效面板。

### 当前关键缺口

- `broker/` 顶层包现已覆盖 Phase 1-4 的 `models.py` / `config.py` / `events.py` / `gateway.py` / `engine.py` / `risk_checks.py` / `ledger.py` / `backtest_runner.py`。
- `agentgraph/state.py` 已补上 `execution_report`、`execution_enabled`、`session_id`，并正式声明 `approval_status` / `modified_target_pct` 审批字段。
- `agentgraph/orchestrator.py` 已接入 execution 闭环；Phase 5 之前的主缺口转为 UI / Streamlit / 展示层。
- 项目级 `pyright` / `ruff` / `pytest` 约束现已写入 `pyproject.toml`；当前增量开发继续依赖 `bugs/basedpyright/baseline.json` 隔离全仓库历史类型债务。

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
| Phase 2 撮合引擎 + Broker 接口 | Completed | Broker 核心接口、撮合、风控、事件 hooks 已落地并有 pytest 覆盖 | Phase 3 起点：先写记录单笔 fill 后可回读的失败测试，再引入最小账本 | Phase 2 测试 + 质量门禁全绿 |
| Phase 3 账本 + 交易日志 | Completed | `ledger.py`、backend-backed 账本读回、核心指标、CSV 导出与 `PortfolioManager.sync_from_broker()` 已收口并有 pytest 覆盖 | 按当前任务边界暂停；如继续推进，下一步才进入 Phase 4 execution node 的首个失败测试 | Phase 3 测试 + 质量门禁全绿 |
| Phase 4 主工作流集成 | Completed | `AgentState` / `execution_node` / `orchestrator` / `DataService` / `agent_tools` / `backtest_runner` 最小范围已落地，含 HITL 插入点与审批状态契约 | 按当前任务边界暂停；如继续推进，下一步才进入 Phase 5 UI / 回测展示层 | Phase 4 测试 + 图结构验证 + 质量门禁全绿 |
| Phase 5 UI + 测试 | In Progress | `BacktestRunner` happy path、Streamlit 回测数据适配层、交易日志/组合表/KPI 最小展示切片已落地；页面仍需进一步整理 | 下一步补权益/回撤图与更多页面整理，再做更完整 UI 回归 | Phase 5 测试 + 手动 UI 验证 + 质量门禁全绿 |

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

**状态**: `Completed`

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
  - `broker/__init__.py` Phase 2 导出
- `MockBrokerEngine` 现已具备这些可观察行为：
  - `BrokerGateway` 公共查询接口：`get_account()` / `get_position()` / `get_positions()` / `get_order()` / `get_orders()` / `get_fills()`
  - 市价单按 `close ± slippage` 立即成交
  - 限价买单 / 限价卖单先挂起，后续 `on_bar()` 在价格触及时成交
  - 取消挂单后不会被未来 bar 再次成交
  - 多空统一持仓更新已覆盖开多、加多、平多、开空、回补与反手所需的核心符号语义
  - 下单前风控已覆盖资金不足（含滑点+手续费）、`max_position_pct` 与 `allow_short`
  - 订单 / 成交事件 hooks：`register_on_order()` / `register_on_fill()`
  - 结构化事件日志：`get_event_log()`
  - 多 ticker 账户与持仓查询
- `PARTIALLY_FILLED` 与总仓位上限 `max_total_position_pct` 仍维持为后续扩展点；按当前计划与日线简化撮合假设，不作为 Phase 2 完成阻塞。

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
- [x] RED -> GREEN: `test_canceling_a_pending_limit_order_prevents_future_fills`
- [x] RED -> GREEN: `cancel_order()` + `get_orders(status=...)` 生命周期查询
- [x] RED -> GREEN: `test_limit_sell_order_stays_pending_until_a_future_bar_touches_the_limit`
- [x] RED -> GREEN: 限价卖单触发成交
- [x] RED -> GREEN: `test_market_sell_can_open_a_short_and_market_buy_can_cover_it`
- [x] RED -> GREEN: 做空开仓 / 回补平仓的现金与持仓语义
- [x] RED -> GREEN: `test_market_short_sell_is_rejected_when_shorting_is_disabled`
- [x] RED -> GREEN: `allow_short=False` 的拒单校验
- [x] RED -> GREEN: `test_market_fill_emits_order_and_fill_callbacks_and_records_events`
- [x] RED -> GREEN: `register_on_order()` / `register_on_fill()` / `get_event_log()`
- [x] RED -> GREEN: `test_rejected_and_canceled_orders_are_recorded_in_event_log`
- [x] RED -> GREEN: 拒单 / 撤单事件落盘
- [x] RED -> GREEN: `test_account_snapshot_tracks_multiple_tickers_through_public_queries`
- [x] RED -> GREEN: 多 ticker 账户与持仓查询
- [x] REFACTOR: 在 `broker/__init__.py` 统一导出 Phase 2 公共类型

**验证结果**

- [x] `uv run pytest test/test_broker_models.py test/test_broker_engine.py -q`
- [x] `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json`
- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`

**阻塞项**

- [x] 无外部阻塞；Phase 2 当前范围已收口，后续进入 Phase 3

### Phase 3 账本 + 交易日志

**状态**: `Completed`

**本阶段目标**

- 建立 `broker/ledger.py`
- 记录 fills / snapshots
- 计算核心绩效指标
- 在 `PortfolioManager` 增加 `sync_from_broker()`

**当前证据**

- 已新增：
  - `broker/ledger.py`
  - `test/test_broker_ledger.py`
  - `test/test_portfolio_manager.py`
- `broker/ledger.py` 现已包含：
  - `TradeLedgerBackend` Protocol
  - `InMemoryLedgerBackend`
  - `LedgerFillRecord` / `LedgerSnapshotRecord`
  - `TradeLedger.record_fill()` / `record_daily_snapshot()`
  - `TradeLedger.to_trades_dataframe()` / `to_portfolio_dataframe()` / `to_csv()`
  - `TradeLedger.compute_metrics()`，当前覆盖 `total_return` / `annualized_return` / `max_drawdown` / `max_drawdown_duration` / `sharpe_ratio` / `win_rate` / `profit_factor` / `avg_win` / `avg_loss` / `payoff_ratio` / `number_of_trades` / `avg_holding_period_days`
- `TradeLedger` 现已真正以 backend 作为账本数据源：同一个 backend 下重新实例化 `TradeLedger` 后，仍可通过公共接口读回 trades / snapshots / metrics。
- `TradeLedger` 的 `realized_pnl` 口径现已与 `test/trade.py` 对齐：平仓净额按 `gross - fee - slippage` 结算，而不是只扣手续费。
- `broker/__init__.py` 已增补 Phase 3 公共导出：`TradeLedger` / `TradeLedgerBackend` / `InMemoryLedgerBackend`
- `dataflow/portfolio_manager.py` 已新增 `sync_from_broker(broker)`，可把 broker 公共持仓同步到现有 `side` / `qty_pct` / `avg_cost` 结构。

**TDD 执行记录**

- [x] RED -> GREEN: `test_trade_ledger_records_a_fill_and_exposes_it_via_trade_export`
- [x] RED -> GREEN: 最小 `TradeLedger` + `InMemoryLedgerBackend`，支持单笔 fill 记录与公共导出读回
- [x] RED -> GREEN: `test_trade_ledger_records_daily_snapshot_and_exposes_portfolio_export`
- [x] RED -> GREEN: 日度账户快照记录与账户级 DataFrame 导出
- [x] RED -> GREEN: `test_trade_ledger_rehydrates_trades_and_snapshots_from_shared_backend`
- [x] RED -> GREEN: backend-backed 账本重建，解决“只写不读”的伪抽象问题
- [x] RED -> GREEN: `test_trade_ledger_exports_csv_from_persisted_backend_records`
- [x] RED -> GREEN: CSV 导出从 backend persisted records 回读后仍可正常落盘
- [x] RED -> GREEN: `test_trade_ledger_computes_core_metrics_from_snapshots_and_round_trip_fills`
- [x] RED -> GREEN: 核心绩效指标 + `avg_holding_period_days` / `max_drawdown_duration`
- [x] RED -> GREEN: 将 `realized_pnl` 修正为 `gross - fee - slippage`，与 `test/trade.py` 参考语义收口
- [x] RED -> GREEN: `test_portfolio_manager_syncs_broker_positions_and_clears_flat_tickers`
- [x] RED -> GREEN: `test_portfolio_manager_syncs_short_positions_with_negative_position_pct`
- [x] REFACTOR: 在 `broker/__init__.py` 统一导出 Phase 3 公共类型，并将 pandas 相关实现收敛到可通过 `basedpyright --baselinefile` 的稳定写法

**验证结果**

- [x] `uv run pytest test/test_broker_models.py test/test_broker_engine.py test/test_broker_ledger.py test/test_portfolio_manager.py -q`
- [x] `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json`
- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`

**阻塞项**

- [x] 无 Phase 3 特有阻塞；按当前任务边界停在 Phase 3，Phase 4+ 未启动

### Phase 4 主工作流集成

**状态**: `Completed`

**本阶段目标**

- 扩展 `AgentState`
- 新增 `agentgraph/execution_node.py`
- 将 `PM_agent` 之后接入执行节点
- 让 `DataService` / `agent_tools` 可以注入 broker
- 建立 `broker/backtest_runner.py`

**当前证据**

- 已新增 `agentgraph/execution_node.py`，并完成这些可观察行为：
  - `execution_enabled=False` 时跳过执行
  - `Action=HOLD` 时只返回执行结果，不下单
  - `BUY/SELL` 决策会构造市价单、调用 broker、生成 `ExecutionReport`
  - 执行后联动 `PortfolioManager.sync_from_broker()`
  - `approval_status=rejected/modified` 已接入执行前审批状态检查
- `agentgraph/orchestrator.py` 现已支持：
  - 无 broker 时保持 `PM_agent -> END`
  - 有 broker 时走 `PM_agent -> execution_node -> END`
  - `enable_hitl=True` 时预留 `PM_agent -> hitl_approval -> execution_node -> END`
- `dataflow/service.py` 已支持 broker 注入，`agents/utils/agent_tools.py` 已切换为可配置 `DataService` 工厂。
- `broker/backtest_runner.py` 已建立最小骨架，并用 pytest 覆盖空窗口结构化返回。

**TDD 执行记录**

- [x] RED -> GREEN: `execution_enabled=False` 时 execution node 跳过执行
- [x] RED -> GREEN: `Action=HOLD` 时不下单，仅返回可观察执行结果
- [x] RED -> GREEN: `BUY/SELL` 决策生成订单、调用 broker、序列化 `ExecutionReport`
- [x] RED -> GREEN: execution 后联动 `PortfolioManager.sync_from_broker()`
- [x] RED -> GREEN: `approval_status=rejected/modified` 的审批状态检查与目标仓位改写
- [x] RED -> GREEN: `orchestrator` 接入 `PM_agent -> execution_node -> END`
- [x] RED -> GREEN: `enable_hitl=True` 时接入 `hitl_approval -> execution_node` 插入路径
- [x] REFACTOR: `DataService` broker 注入、`agent_tools` 工厂化、`BacktestRunner` 最小骨架收敛

### Phase 5 UI + 测试

**状态**: `In Progress`

**本阶段目标**

- Streamlit 增加交易日志与绩效面板
- 建立 `test/test_broker.py`
- 完成端到端回测测试

**当前证据**

- `test/test_backtest_runner.py` 已新增最小 happy path，验证 `BacktestRunner.run()` 会返回结构化 `trades / portfolio / metrics`，并且真实驱动 broker + agent + ledger 产生交易与日终快照。
- `streamlit_app.py` 已新增：
  - `Backtester.run_execution_backtest()`：将价格 rows 转成 OHLC DataFrame，并调用正式 `BacktestRunner`
  - `build_backtest_dashboard_data()`：将 `BacktestResult` 适配成 Streamlit 直接消费的交易表、组合表、KPI 卡片
  - `render_backtest_dashboard()`：最小渲染交易日志表、组合时间线表、绩效指标面板
  - Backtest Mode 侧边栏的 broker preview 配置（窗口、初始资金、手续费、滑点）
  - Backtest 结果区中的 broker backtest 展示入口
- 已新增 `test/test_streamlit_app.py`，覆盖回测结果数据适配、UI 渲染调用与 `Backtester` → `BacktestRunner` 接通。

**TDD 执行记录**

- [x] RED -> GREEN: `BacktestRunner.run()` 最小 happy path，返回结构化 `trades / portfolio / metrics`
- [x] RED -> GREEN: Streamlit 回测结果数据适配层 `build_backtest_dashboard_data()`
- [x] RED -> GREEN: Streamlit 最小展示切片 `render_backtest_dashboard()`
- [x] RED -> GREEN: `Backtester.run_execution_backtest()` 接通 `BacktestRunner`
- [x] REFACTOR: 将回测展示拆成“数据适配层 + 渲染层”，避免页面直接耦合底层 ledger 列结构
- [ ] 下一步：补权益曲线 / 回撤曲线与更完整的页面整理

**Phase 5 Active Task List**

- [x] Task 1: 补绩效图表数据接口与最小图表渲染（Strategy vs Benchmark + Drawdown）
- [x] Task 2: 将 broker backtest 配置从 preview window 推进到明确的 `start_date / end_date`
- [x] Task 3: 整理 broker backtest 页面结构，使 KPI / Performance / Trades / Portfolio 更清晰
- [x] Task 4: 补强 Phase 5 回归测试，覆盖多 bar、日期区间和页面展示主路径

---

## 6 审计参考点

- `agentgraph/orchestrator.py`: 已支持 execution 闭环与 HITL 插入点
- `agentgraph/state.py`: 已包含执行 / 会话 / 审批相关状态契约
- `dataflow/service.py`: 已支持 broker 注入
- `dataflow/portfolio_manager.py`: 已补 `sync_from_broker()`，并由 execution node 联动调用
- `test/trade.py`: 继续作为执行语义参考，不直接复用脚本结构
- `streamlit_app.py`: 仍是 Phase 5 的主要待改造目标

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
- [x] 完成 Phase 2 后续公共行为测试：撤单、限价卖出、做空开仓/回补、`allow_short=False` 拒单、多 ticker 查询
- [x] 完成 Phase 2 事件面：`register_on_order()` / `register_on_fill()` / `get_event_log()`
- [x] 在 `broker/__init__.py` 增补 Phase 2 公共导出
- [x] `uv run pytest test/test_broker_models.py test/test_broker_engine.py -q` 通过
- [x] `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json` 通过
- [x] `uv run ruff check .` 通过（含 Phase 2 增量）
- [x] `uv run ruff format --check .` 通过（含 Phase 2 增量）
- [x] Phase 2 当前范围完成并收口
- [x] 启动并完成 Phase 3：落地 `broker/ledger.py`、`TradeLedgerBackend`、`InMemoryLedgerBackend` 与 `TradeLedger`
- [x] 完成 Phase 3 账本行为测试：fill 读回、daily snapshot 导出、核心 metrics、持有期统计
- [x] 完成 Phase 3 收尾：backend-backed ledger reload、`to_csv()` 导出验证、short 仓位同步覆盖
- [x] 将 Phase 3 `realized_pnl` 口径修正为 `gross - fee - slippage`，与 `test/trade.py` 语义对齐
- [x] 完成 `PortfolioManager.sync_from_broker()` 的最小联动与 pytest 覆盖
- [x] 在 `broker/__init__.py` 增补 Phase 3 公共导出
- [x] `uv run pytest test/test_broker_models.py test/test_broker_engine.py test/test_broker_ledger.py test/test_portfolio_manager.py -q` 通过
- [x] `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json` 通过（含 Phase 3 增量）
- [x] `uv run ruff check .` 通过（含 Phase 3 增量）
- [x] `uv run ruff format --check .` 通过（含 Phase 3 增量）
- [x] `ruff format --check .` 通过
- [x] 新建 `broker/__init__.py` / `broker/models.py` / `broker/config.py` / `broker/events.py`
- [x] 新建 `test/test_broker_models.py` 与 `test/conftest.py`
- [x] 为 `BrokerConfig(BaseSettings)` 补充 `pydantic-settings` 依赖
- [x] 完成 Phase 1 数据模型层的 TDD 切片并全部转绿
- [x] `basedpyright --baselinefile bugs/basedpyright/baseline.json` 通过
- [x] Phase 1 当前增量质量门禁：`0 errors / 0 warnings / 0 notes`
- [x] 启动并完成 Phase 4：落地 `agentgraph/execution_node.py`、`AgentState` 执行层字段与 `orchestrator` 执行闭环
- [x] 完成 Phase 4 execution node 行为测试：skip / HOLD / BUY / SELL / portfolio sync / approval rejected / approval modified
- [x] 完成 Phase 4 graph 集成测试：无 broker 向后兼容、有 broker 执行闭环、`enable_hitl=True` 的 `hitl_approval -> execution_node` 插入路径
- [x] 完成 `DataService` broker 注入、`agent_tools` 工厂化与 `BacktestRunner` 最小骨架
- [x] `uv run pytest test/test_broker_models.py test/test_broker_engine.py test/test_broker_ledger.py test/test_portfolio_manager.py test/test_execution_node.py test/test_orchestrator.py test/test_data_service.py test/test_agent_tools.py test/test_backtest_runner.py -q` 通过
- [x] `uv run ruff check .` 通过（含 Phase 4 增量）
- [x] `uv run ruff format --check .` 通过（含 Phase 4 增量）
- [x] 使用临时 baseline 副本完成 `basedpyright --baselinefile` 增量校验，正式 `bugs/basedpyright/baseline.json` 保持未修改
