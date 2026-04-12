# Broker 实施分阶段进度追踪

> 基线审计日期: 2026-04-13
> 对应分支: `feat/broker`
> 来源计划: `plans/broker/impl_plan_final.md`

---

## 1 当前基线

当前分支已经具备 Broker 集成前的主链路与若干可复用资产，但正式 Broker 模块尚未开始落地。

### 已存在的可复用基础

- Agent 主流程已打通到 `PM_agent`，但当前仍以 `PM_agent -> END` 结束，尚无 execution node 闭环。
- `DataService` 已支持历史价格、指标、基本面、新闻的 `end_date` 读取语义，可作为回测数据入口。
- `PortfolioManager` 已具备状态化持仓与风险限额管理，但还没有 `sync_from_broker()`。
- `test/trade.py` 已有脚本级回测原型，含手续费、滑点、多空统一 PnL、CSV 输出，可作为撮合/账本参考逻辑。
- Streamlit 已有历史分析与验证页面，但还没有 Broker 级交易日志与绩效面板。

### 当前关键缺口

- 仓库中还没有 `broker/` 顶层包，Phase 1-3 的主体代码均未创建。
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

> 这意味着“项目级质量门禁”已经建立，但“全仓库 0-warning / 0-error”还没有达成；后续实施时需要决定是先清 baseline，还是将 Broker Phase 的新增代码与历史问题做范围隔离。

---

## 4 分阶段状态总览

| Phase | 状态 | 当前判断 | 下一步最小 TDD 切片 | 完成门禁 |
| --- | --- | --- | --- | --- |
| Phase 1 数据模型层 | Not Started | `broker/` 目录不存在 | 先写 `Order` / `OrderStatus` 的失败测试，再实现最小模型 | Phase 1 测试 + `basedpyright` + `ruff` 全绿 |
| Phase 2 撮合引擎 + Broker 接口 | Not Started | 只有 `test/trade.py` 的脚本级执行逻辑可复用 | 先写市价买入成交的行为测试，再抽出最小 `MockBrokerEngine` | Phase 2 测试 + 质量门禁全绿 |
| Phase 3 账本 + 交易日志 | Not Started | 无 `ledger.py`，`PortfolioManager` 也无 broker 同步口 | 先写记录单笔 fill 的失败测试，再实现最小账本 | Phase 3 测试 + 质量门禁全绿 |
| Phase 4 主工作流集成 | Not Started | 目前仍是 `PM_agent -> END` | 先写 execution node 接入状态更新的失败测试 | Phase 4 测试 + 图结构验证 + 质量门禁全绿 |
| Phase 5 UI + 测试 | Not Started | 现有 Streamlit 仅支持历史分析验证 | 先写回测结果展示的数据接口测试，再接 UI | Phase 5 测试 + 手动 UI 验证 + 质量门禁全绿 |

---

## 5 分阶段追踪明细

### Phase 1 数据模型层

**状态**: `Not Started`

**本阶段目标**

- 建立 `broker/models.py`
- 建立 `broker/config.py`
- 建立 `broker/events.py`
- 补齐 `Order` / `Fill` / `Position` / `AccountSnapshot` / `ExecutionReport`

**当前证据**

- 当前仓库没有 `broker/` 目录。
- 计划中 Phase 1 的设计已明确，但尚无正式实现。

**TDD 执行记录**

- [ ] RED: 为最小订单模型写第一个失败测试
- [ ] GREEN: 用最小 Pydantic 模型让测试通过
- [ ] REFACTOR: 提取共享字段与枚举

**阻塞项**

- [ ] 仓库级 `basedpyright` baseline 仍为红色，进入正式实现前需要先明确“先清 baseline”还是“按 Phase 隔离修复”

### Phase 2 撮合引擎 + Broker 接口

**状态**: `Not Started`

**本阶段目标**

- 建立 `broker/gateway.py`
- 建立 `broker/engine.py`
- 建立 `broker/risk_checks.py`
- 让市价单 / 限价单 / 手续费 / 滑点 / 持仓更新进入正式模块

**当前证据**

- `test/trade.py` 已包含可迁移的多空统一 PnL 与执行逻辑，可作为参考实现来源。
- 但当前仍是脚本，不是标准接口，也没有订单状态机和回调 hooks。

**TDD 执行记录**

- [ ] RED: 市价买入立即成交测试
- [ ] GREEN: 最小 `place_order()` + `get_account()` 实现
- [ ] RED: 限价未触发 / 触发测试
- [ ] GREEN: `on_bar()` 与待成交订单处理
- [ ] REFACTOR: 提取共享撮合逻辑与风控校验

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
- [x] `ruff check .` 通过
- [x] `ruff format --check .` 通过
- [ ] `basedpyright` 通过
- [ ] 当前基线：`78 errors / 0 warnings`
