# 验证与证据

## 当前验证结果

验证日期: 2026-06-03, 当前分支 `feat/broker-plus`。

| 命令 | 结果 |
| --- | --- |
| `uv run pytest -q` | `97 passed in 2.81s` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `53 files already formatted` |
| `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json` | `0 errors, 0 warnings, 0 notes` |

表述时注意: `basedpyright` 使用 baseline 隔离历史类型债务, 不等于全仓库历史类型问题已经全部消失。

## 测试分布

当前 pytest 收集到 97 个 `def test_`:

| 目录 | 数量 | 覆盖重点 |
| --- | ---: | --- |
| `test/broker/` | 64 | models、engine、ledger、views、backtest runner |
| `test/agentgraph/` | 24 | execution node、orchestrator、HITL routing、execution hook |
| `test/dataflow/` | 3 | broker 注入后的 data service / portfolio manager 同步 |
| `test/agents/` | 1 | agent tools data service factory |
| `test/streamlit/` | 5 | backtest dashboard 数据和渲染适配 |

`pyproject.toml` 中 pytest 配置为:

```toml
python_files = ["test_*.py"]
testpaths = ["test"]
```

因此 `test/trade.py`、`test/eva.py`、CSV fixture、`streamlit_broker_phase5_smoke.py` 更适合表述为历史/手工 smoke 资料, 不属于本轮 `pytest -q` 自动收集的 97 个测试。

## 测试证明了什么

Broker 层:

- 订单默认值、limit order 校验、身份字段默认值与传播。
- 市价/限价买卖、做空/回补、撤单、风险拒单。
- `close_bar` 与 `next_open` 确定性执行时机。
- 多账户隔离, 默认账户查询不会跨非默认账户。
- `client_order_id` 在 `(strategy_id, account_id)` 内幂等。
- 事件 sink 按 `(strategy_id, account_id)` 独立 sequence。
- Ledger records 支持 identity filters、CSV、核心指标、持仓周期和 drawdown。

AgentGraph 层:

- execution disabled -> `skipped`。
- PM HOLD / target already satisfied -> `held`。
- approval pending -> `pending`。
- approval rejected / timed out -> `rejected`。
- approval modified -> 按修改后目标仓位执行。
- 缺价格 -> `failed`。
- broker 风控拒单 -> rejected report + execution event。
- PM 后可进入 execution node, HITL enabled 时可经过 approval placeholder。
- `on_execution_complete` hook 可接后续通知、memory 或审计。

Views 层:

- 内部 enum 到 public enum 的映射。
- 百分比输出为 percentage points。
- order fills 聚合为 filled quantity、avg price、commission。
- `price_source` 明确 mark price 来源。
- `ExecutionReportView` 支持无订单分支。
- `ExecutionOutcomeView` 支持后续 memory/reflection 消费。
- `BacktestResultView` 固定 completed result JSON shape。

## 工程卫生证据

| 项目 | 当前状态 |
| --- | --- |
| 当前分支 | `feat/broker-plus` |
| 当前 HEAD | `8988e4b` |
| `origin/feat/broker-plus` | `8988e4b` |
| `upstream/feat/broker-plus` | `8988e4b` |
| `origin/feat/broker-plus...upstream/feat/broker-plus` | `0/0` |
| `feat/broker...feat/broker-plus` | `0/24` |
| `upstream/feat/broker...feat/broker` | `0/4` |
| `properties.env` | 已不在 Git 跟踪中, 由 `.gitignore` 忽略 |

`properties.env` 证据:

- `git ls-files properties.env` 输出为空。
- `git check-ignore --no-index -v properties.env` 指向 `.gitignore:223:properties.env`。
- `git status --ignored --short properties.env` 输出 `!! properties.env`。

## 会议可用验证口径

> 当前 `feat/broker-plus` 的验证对象是 broker-owned execution-domain contract。测试已经按域组织, 回归覆盖身份字段、事件、账户隔离、view serializers、执行报告、HITL 安全映射、回测 JSON、orchestrator hook 和 Streamlit dashboard 适配。当前质量门是 pytest、ruff、format check 和 basedpyright baseline 增量检查, 本地最新验证全部通过。
