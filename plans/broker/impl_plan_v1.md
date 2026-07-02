# Gap C: Broker Mock + Feedback 实施计划

## 项目背景与目标

### 当前状况

- 系统存在 `test/trade.py` 脚本级别的回测逻辑，但**未模块化**、**不在主应用链路中**
- PM Agent 输出 `Action` + `Target_position_pct` 后即结束，无后续执行/反馈环节
- `dataflow/portfolio_manager.py` 有基础的持仓状态管理，但未与交易逻辑联动
- 回测评估 (`test/eva.py`) 是独立的后处理脚本，与 Agent 系统解耦

### Gap C 核心目标（来自 WORKLOAD_GAP_ANALYSIS）

1. **标准化 Broker 接口** — `place/cancel/query/orderbook/position`
2. **统一订单与成交生命周期** — `NEW → PARTIALLY_FILLED → FILLED → CANCELED`
3. **执行结果 → 反馈回代理决策 的持续闭环**

### 完成标志

- 一个可插拔的 `BrokerGateway` Protocol + `MockBroker` 实现
- 支持 `MARKET / LIMIT` 订单，含手续费 & 滑点模型
- 完整的账户/持仓/交易日志系统
- PM 决策 → 自动执行 → 执行结果写回 State → 可选触发重新分析
- Streamlit 中可查看交易日志与绩效指标

---

## 需要你决策的设计问题

> [!IMPORTANT]
>
> ### 决策点 1: 数值精度 — `float` vs `Decimal`
>
> **选项 A: `float`（推荐）**
>
> - ✅ 与现有代码一致（`TradingDecision.target_position_pct: float`、`test/trade.py` 全部用 float）
> - ✅ 与 Pydantic / LangGraph / JSON 序列化天然兼容
> - ✅ 对于模拟/学术项目，float 精度足够（误差 < 1e-10）
> - ❌ 在极端场景下可能出现浮点精度问题（但模拟级别不会遇到）
>
> **选项 B: `Decimal`**
>
> - ✅ 金融行业标准，零浮点误差
> - ❌ 需要全局改造序列化链路（Pydantic、JSON、LangGraph State 都需适配）
> - ❌ 代码复杂度显著提升，与现有代码风格不一致
>
> **建议**: 采用 **float**，与现有项目保持一致。这是学术/模拟项目，float 精度完全够用。如果你同意，我就不再深入 Decimal 方案。

> [!IMPORTANT]
>
> ### 决策点 2: 订单撮合模式 — 简化 vs 完整
>
> **选项 A: 简化撮合（推荐）**
>
> - 市价单：以当前 bar 的 close（或下一 bar 的 open）± 滑点立即全额成交
> - 限价单：检查价格是否触及限价，触及则全额成交
> - 不支持部分成交（`PARTIALLY_FILLED` → 直接跳到 `FILLED`）
> - 适合日线级别的回测 / 仿真
>
> **选项 B: 完整撮合**
>
> - 支持 `PARTIALLY_FILLED` 状态
> - 支持 Order Book 深度模拟
> - 支持更多订单类型（STOP, STOP_LIMIT, OCO 等）
> - 复杂度和工作量大幅增加（估计增加 40-60 小时）
>
> **建议**: 采用 **选项 A（简化撮合）**。原因：
>
> 1. 当前系统用日线数据，部分成交/订单簿深度在日线级别意义不大
> 2. 文档中的预估工作量（100-140 小时）已经很高，简化模式可以控制在合理范围内
> 3. 订单状态机仍然保留 `PARTIALLY_FILLED` 状态定义，未来需要时可扩展

> [!IMPORTANT]
>
> ### 决策点 3: 反馈闭环深度 — 只记录 vs 重新触发分析
>
> **选项 A: 记录 + 单向反馈（推荐作为第一阶段）**
>
> - 执行结果写入 `AgentState`（新字段 `execution_report`）
> - 持仓更新 → `PortfolioManager` 同步
> - 下一轮分析自动使用更新后的持仓
> - 不额外触发 Agent 重新分析
>
> **选项 B: 完整闭环 — 执行后触发重新评估**
>
> - 在 LangGraph 中增加一个 `execution_node`
> - 执行后通过条件边判断是否需要重新走 PM → Risk 分析
> - 触发条件：实际成交价偏离预期过大、部分成交导致仓位不匹配等
> - 增加 LangGraph DAG 复杂度
>
> **选项 C: 两阶段推进**
>
> - Phase 1: 先实现 A（记录+单向反馈）
> - Phase 2: 在 A 稳定后，添加重新评估的条件边
>
> **建议**: 采用 **选项 C（两阶段推进）**。先确保基础闭环稳定，再增加重新评估逻辑。第一阶段已经满足 proposal 中关于"执行结果反馈"的核心要求。

> [!WARNING]
>
> ### 决策点 4: 执行时机 — 收盘价执行 vs 下一开盘价执行
>
> **选项 A: 当日收盘价 ± 滑点执行（与现有 `test/trade.py` 一致）**
>
> - ✅ 与现有回测脚本逻辑保持一致
> - ❌ 存在"未来函数"争议（真实中你不可能在收盘价出来后的同一时刻下单）
>
> **选项 B: 下一 bar 的 Open ± 滑点执行**
>
> - ✅ 更真实，避免未来函数
> - ❌ 需要多一根 bar 的数据，回测逻辑更复杂
> - ❌ 与现有 `test/trade.py` 不兼容
>
> **建议**: 采用 **选项 A**，与现有 `test/trade.py` 保持一致。在配置中预留 `execution_timing` 参数（`close_bar` / `next_open`），未来可切换。

---

## 无需讨论的技术决策

以下决策我认为方案明确、无需考虑其他选项：

| 决策项 | 选择 | 理由 |
| -------- | ------ | ------ |
| 接口抽象模式 | Python `Protocol` (typing) | 文档示例已用 Protocol，零依赖，与现有代码风格一致 |
| 模块目录 | `broker/` 顶层包 | 文档规划的目录结构已明确 |
| 配置管理 | Pydantic `BaseSettings` | 项目已引入 Pydantic，天然适合 |
| 标识符生成 | `uuid4` | 订单/成交 ID 无外部依赖，唯一性保证 |
| 数据时间处理 | `datetime` (UTC) | 项目已用 ISO 格式 UTC 字符串 |
| 测试框架 | `pytest` | Python 社区标准，项目已有 test/ 目录 |

---

## 分阶段实施方案

### Phase 1: 数据模型层 （预估 4-6 小时）

建立所有数据模型和枚举，这是后续所有 Phase 的基础。

#### [NEW] [models.py](../../broker/models.py)

核心数据模型定义：

```python
# 枚举类型
class OrderSide(str, Enum): BUY / SELL
class OrderType(str, Enum): MARKET / LIMIT
class OrderStatus(str, Enum): NEW / PARTIALLY_FILLED / FILLED / CANCELED / REJECTED

# 数据模型 (Pydantic BaseModel)
class Order:          # 订单（含 id, ticker, side, type, qty, limit_price, status, timestamps）
class Fill:           # 成交记录（含 order_id, fill_price, fill_qty, fee, slippage, timestamp）
class Position:       # 单只股票持仓（含 ticker, shares, avg_cost, side, unrealized_pnl）
class AccountSnapshot: # 账户快照（含 cash, equity, positions, timestamp）
class ExecutionReport: # 执行报告（含 order, fills, position_after, account_after）
```

#### [NEW] [config.py](../../broker/config.py)

```python
class BrokerConfig(BaseSettings):
    initial_cash: float = 100_000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    execution_timing: str = "close_bar"  # "close_bar" | "next_open"
    max_position_pct: float = 1.0
    allow_short: bool = True
```

---

### Phase 2: 撮合引擎 + Broker 接口 （预估 8-12 小时）

实现核心交易引擎和标准化接口。

#### [NEW] [gateway.py](../../broker/gateway.py)

```python
class BrokerGateway(Protocol):
    """标准化 Broker 接口（Protocol），未来可替换为真实券商"""
    def get_account(self) -> AccountSnapshot: ...
    def get_positions(self) -> list[Position]: ...
    def get_position(self, ticker: str) -> Position | None: ...
    def place_order(self, order: Order) -> Order: ...
    def cancel_order(self, order_id: str) -> Order: ...
    def get_order(self, order_id: str) -> Order | None: ...
    def get_orders(self, status: OrderStatus | None = None) -> list[Order]: ...
    def get_fills(self, order_id: str | None = None) -> list[Fill]: ...
```

#### [NEW] [engine.py](../../broker/engine.py)

`MockBrokerEngine` — 实现 `BrokerGateway`：

- **核心能力**：
  - 账户资金管理（cash, equity 计算）
  - 持仓追踪（多空统一，avg_cost 加权更新）
  - 订单簿管理（pending orders 列表）
  - 市价单即时撮合
  - 限价单条件触发
  - 手续费 + 滑点扣减
  - Realized / Unrealized PnL 计算

- **关键方法**：
  - `place_order()` → 创建订单 → 尝试撮合
  - `_try_fill_market()` → 市价撮合
  - `_try_fill_limit()` → 限价撮合
  - `_execute_fill()` → 实际成交处理（更新持仓、现金、PnL）
  - `on_bar()` → 接收新 bar 数据后，检查 pending limit orders

- **复用 `test/trade.py` 的核心逻辑**：
  现有 trade.py L222-268 的多空统一 Position & PnL 逻辑将被提取并封装到 engine 中。

#### [NEW] [risk_checks.py](../../broker/risk_checks.py)

下单前风控检查（前置校验层）：

```python
class PreTradeRiskChecker:
    def check(self, order: Order, account: AccountSnapshot) -> tuple[bool, str]:
        """返回 (通过, 原因)"""
        # 1. 资金充足性检查
        # 2. 单只股票仓位上限检查
        # 3. 做空权限检查
        # 4. 订单合理性检查（qty > 0, price > 0 for limit）
```

---

### Phase 3: 账户/持仓账本 + 交易日志 （预估 6-8 小时）

#### [NEW] [ledger.py](../../broker/ledger.py)

交易日志和绩效统计系统：

```python
class TradeLedger:
    """交易记录 & 绩效指标计算"""

    def record_fill(self, fill: Fill, position: Position, account: AccountSnapshot): ...
    def record_daily_snapshot(self, date: str, account: AccountSnapshot): ...

    # 绩效指标
    def compute_metrics(self) -> dict:
        """计算: 总收益率, 年化收益率, 最大回撤, 夏普比率, 胜率, 盈亏比"""

    # 导出
    def to_trades_dataframe(self) -> pd.DataFrame: ...
    def to_portfolio_dataframe(self) -> pd.DataFrame: ...
    def to_csv(self, trades_path: str, portfolio_path: str): ...
```

**绩效指标清单**：

- Total Return / Annualized Return
- Max Drawdown / Max Drawdown Duration
- Sharpe Ratio（无风险利率可配置）
- Win Rate / Profit Factor
- Avg Win / Avg Loss / Payoff Ratio
- Number of Trades / Avg Holding Period

#### [MODIFY] [portfolio_manager.py](../../dataflow/portfolio_manager.py)

改造现有 `PortfolioManager`，使其与 `MockBrokerEngine` 联动：

- 新增 `sync_from_broker(broker: BrokerGateway)` 方法
- 执行后自动调用 `sync_from_broker()` 更新持仓状态
- 保持向后兼容（原有 `update_position()` 接口不变）

---

### Phase 4: 与主工作流集成 — 反馈闭环 （预估 10-14 小时）

这是最关键的阶段，将 Broker 系统接入 LangGraph Agent DAG。

#### [MODIFY] [state.py](../../agentgraph/state.py)

新增字段到 `AgentState`：

```python
# ========== 新增：执行层字段 ==========
execution_report: Annotated[Optional[str], "本轮执行报告（JSON序列化）"] = ""
execution_enabled: Annotated[bool, "是否启用自动执行"] = False
```

#### [NEW] [execution_node.py](../../agentgraph/execution_node.py)

新增 LangGraph 执行节点：

```python
def create_execution_node(broker: BrokerGateway):
    """创建执行节点 — PM 决策后自动下单"""
    def execution_node(state: AgentState):
        if not state.get("execution_enabled", False):
            return {}  # 未启用执行，跳过

        action = state.get("Action", "HOLD")
        target_pct = state.get("Target_position_pct", 0.0)
        ticker = state.get("ticker", "")

        if action == "HOLD":
            return {"execution_report": "HOLD — 无需执行"}

        # 1. 计算目标股数
        # 2. 构建 Order
        # 3. 调用 broker.place_order()
        # 4. 生成 ExecutionReport
        # 5. 同步 PortfolioManager

        return {"execution_report": report_json}

    return execution_node
```

#### [MODIFY] [orchestrator.py](../../agentgraph/orchestrator.py)

扩展 DAG 图——在 PM 节点后增加执行节点：

```text
现有: START → [并行分析] → risk_analyst → PM_agent → END
新增: START → [并行分析] → risk_analyst → PM_agent → execution_node → END
```

关键改动：

1. `IntelliFin_Assistant.__init__()` 新增可选 `broker` 参数
2. 当 `broker` 不为 None 时，添加 `execution_node` 到 DAG
3. `run()` 方法新增 `execute: bool = False` 参数
4. 保持向后兼容：不传 broker 时，行为与现在完全一致

#### [NEW] [backtest_runner.py](../../broker/backtest_runner.py)

将 `test/trade.py` 重构为正式的回测入口：

```python
class BacktestRunner:
    """回测运行器 — 替代 test/trade.py"""

    def __init__(self, config: BrokerConfig):
        self.broker = MockBrokerEngine(config)
        self.ledger = TradeLedger()
        self.agent = IntelliFin_Assistant(broker=self.broker)

    def run(self, ticker: str, price_df: pd.DataFrame,
            start_date: str, end_date: str) -> BacktestResult:
        """逐日遍历 → Agent分析 → 执行 → 记录"""
        for date, bar in price_df.iterrows():
            # 1. broker.on_bar(bar) — 更新市场数据
            # 2. agent.run(ticker, date, current_pct) — 获取决策
            # 3. 执行（通过 execution_node 或直接调用）
            # 4. ledger.record_daily_snapshot()

        return BacktestResult(
            trades=self.ledger.to_trades_dataframe(),
            portfolio=self.ledger.to_portfolio_dataframe(),
            metrics=self.ledger.compute_metrics()
        )
```

---

### Phase 5: Streamlit UI + 测试 （预估 6-10 小时）

#### [MODIFY] [streamlit_app.py](../../streamlit_app.py)

在 Streamlit 中新增 Broker / 回测相关页面：

1. **回测配置面板**（侧边栏扩展）
   - 初始资金、手续费率、滑点率配置
   - 日期范围选择
   - 执行/非执行模式切换

2. **交易日志页面**
   - 交易明细表格（trades DataFrame）
   - 每日组合状态表格（portfolio DataFrame）

3. **绩效指标面板**
   - 关键 KPI 卡片（收益率、最大回撤、夏普比、胜率）
   - 权益曲线图（Strategy vs Benchmark）
   - 回撤曲线图

#### [NEW] [test_broker.py](../../test/test_broker.py)

Pytest 单元测试 + 集成测试：

```python
# 单元测试
class TestOrderModels: ...        # 模型创建与验证
class TestMockBrokerEngine: ...   #
    # test_place_market_buy
    # test_place_market_sell
    # test_place_limit_buy_triggered
    # test_place_limit_buy_not_triggered
    # test_cancel_order
    # test_short_selling
    # test_position_pnl_calculation
    # test_insufficient_funds_rejection
    # test_commission_and_slippage

class TestPreTradeRiskChecker: ... # 风控检查
class TestTradeLedger: ...         # 日志与指标

# 集成测试
class TestExecutionNode: ...       # 执行节点与 AgentState 集成
class TestBacktestRunner: ...      # 端到端回测流程
```

---

## 文件清单总览

```
broker/                          # [NEW] 顶层模块
├── __init__.py                  # [NEW] 包初始化 & 便捷导出
├── models.py                    # [NEW] 数据模型与枚举
├── config.py                    # [NEW] 配置 (Pydantic BaseSettings)
├── gateway.py                   # [NEW] BrokerGateway Protocol
├── engine.py                    # [NEW] MockBrokerEngine 实现
├── risk_checks.py               # [NEW] 下单前风控检查
├── ledger.py                    # [NEW] 交易日志与绩效指标
└── backtest_runner.py           # [NEW] 回测运行器

agentgraph/
├── state.py                     # [MODIFY] 新增 execution_report 等字段
├── orchestrator.py              # [MODIFY] 新增 execution_node 到 DAG
└── execution_node.py            # [NEW] 执行节点

dataflow/
└── portfolio_manager.py         # [MODIFY] 新增 sync_from_broker()

streamlit_app.py                 # [MODIFY] 新增交易日志/绩效面板

test/
└── test_broker.py               # [NEW] 完整测试套件
```

---

## 依赖变更

无需引入新的外部依赖。所需库都已在 `pyproject.toml` 中：

- `pydantic` — 数据模型
- `pandas` — DataFrame 操作
- `numpy` — 数值计算
- `plotly` / `streamlit` — 可视化

测试可能需要新增 `pytest` 到 dev dependencies（如果尚未安装）。

---

## Open Questions

> [!NOTE]
>
> ### Q1: 是否需要考虑与 Gap A（ContextStore 持久化）的联动？
>
> Gap A 涉及 SQLite 持久化。如果 Gap A 先于/同步实施，Broker 的交易日志也应写入 SQLite。
> 但如果 Gap A 尚未开始，我们可以先用内存 + CSV 导出，后续适配。
> **你知道 Gap A 的进展吗？需不需要我在设计中预留 SQLite 接入点？**

> [!NOTE]
>
> ### Q2: 是否需要考虑与 Gap B（HITL 审批）的联动？
>
> Gap B 的 HITL 流程会在 PM 之后、执行之前插入审批节点。这会影响 DAG 的边连接顺序。
> 当前计划是 `PM → execution_node → END`。如果 Gap B 也在做，可能变成 `PM → [HITL审批] → execution_node → END`。
> **你知道 Gap B 的进展吗？需不需要我在 DAG 设计中预留 HITL 插入点？**

> [!NOTE]
>
> ### Q3: 回测运行器是否需要支持多 Ticker 并行？
>
> 当前 `test/trade.py` 只支持单 Ticker 回测。如果需要支持 portfolio-level 多 Ticker 回测，
> engine 的 Position 管理和仓位计算逻辑会更复杂。
> **第一版是否只需支持单 Ticker 回测？**

---

## 验证计划

### 自动化测试

```bash
# 运行所有单元测试
uv run pytest test/test_broker.py -v

# 运行特定测试类
uv run pytest test/test_broker.py::TestMockBrokerEngine -v

# 端到端集成测试（不调 LLM，用 mock 数据）
uv run pytest test/test_broker.py::TestBacktestRunner -v
```

### 手动验证

1. **模型验证**: 手动构建 Order/Fill 对象并验证字段约束
2. **撮合验证**: 与 `test/trade.py` 对比同一数据集的交易结果，确保一致
3. **DAG 验证**: 运行 `agent.visualize()` 确认新增 execution_node 正确连接
4. **UI 验证**: 在 Streamlit 中运行一次回测，检查交易日志和绩效面板

### 回归测试

- 确保不传 broker 时，系统行为与修改前完全一致
- 现有的 CLI (`app.py`) 和 Streamlit 入口不受影响

---

## 工作量预估总结

| Phase | 内容 | 预估时间 |
|-------|------|---------|
| Phase 1 | 数据模型层 | 4-6 小时 |
| Phase 2 | 撮合引擎 + 接口 | 8-12 小时 |
| Phase 3 | 账本 + 绩效指标 | 6-8 小时 |
| Phase 4 | 主流程集成 + 反馈闭环 | 10-14 小时 |
| Phase 5 | Streamlit UI + 测试 | 6-10 小时 |
| **Total** | | **34-50 小时** |

> [!TIP]
> 以上预估已考虑"AI Agent 辅助开发"的效率提升。如果大部分编码交给 Agent，实际人力投入主要在 review + 决策 + 调试。预估时间约为 WORKLOAD_GAP_ANALYSIS 文档中 M3 (100-140 小时) 的 30-40%。
