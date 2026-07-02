# Broker Plus 执行域契约

## 从 AI 投资建议到可审计模拟执行

本次中期汇报重点:

- 原系统: 多智能体分析 + PM 决策
- 当前推进: PM 决策进入本地模拟券商执行域
- 核心产出: broker-owned execution-domain contract

一句话:

> 我们把系统从"生成建议"推进到"建议可执行、执行可记录、结果可序列化、后续可审计"。

---

## 为什么要做 Broker Plus?

### 当前缺口

原流程:

```text
User input -> Multi-Agent Analysis -> PM Decision -> END
```

问题:

- PM 给出 `BUY / HOLD / SELL`, 但没有统一下单接口
- 没有订单、成交、账户、持仓、拒单和账本语义
- 后续前端、HITL、memory、notification 都会重复解释执行结果

Broker Plus 的目标:

```text
PM decision -> execution node -> broker gateway -> mock execution
            -> events + ledger -> structured views
```

---

## 架构

```text
AgentState / PM Decision
        |
        v
agentgraph.execution_node
        |
        v
BrokerGateway Protocol
        |
        v
MockBrokerEngine
        |
        +--> BrokerEventSink
        +--> TradeLedger
        +--> broker.views serializers
        |
        v
ExecutionReportView / BacktestResultView / ExecutionOutcomeView
```

关键边界:

| Broker 负责 | Broker 不负责 |
| --- | --- |
| 订单、成交、账户、持仓 | FastAPI / React 页面 |
| 风控、事件、账本 | 完整 HITL manager |
| 执行报告、回测结果 view | ContextStore / MemoryStore |
| adapter-ready protocol | 真实券商 SDK / 网络调用 |

---

## 已完成工作

### `feat/broker`: 执行域基线

- `Order / Fill / Position / AccountSnapshot / ExecutionReport`
- `BrokerGateway` + `MockBrokerEngine`
- 市价单、限价单、撤单、做空、风控拒单
- `TradeLedger`: fills、daily snapshots、metrics、CSV
- PM -> execution node -> broker -> execution report
- Streamlit 回测展示和 smoke 验证

### `feat/broker-plus`: 契约增强

- `strategy_id / account_id / session_id / decision_id`
- 账户隔离: cash、positions、orders、fills、events
- `BrokerEventSink` 与 `TradeLedgerBackend` 协议
- `broker/views.py`: public DTO / serializer contract
- `client_order_id` 幂等、event vocabulary、`as_of` 回测合同
- `close_bar / next_open` 确定性执行时机

---

## 验证证据

当前分支: `feat/broker-plus`

| 项目 | 结果 |
| --- | --- |
| HEAD | `8988e4b` |
| origin/upstream broker-plus | 与 HEAD 一致 |
| `feat/broker...feat/broker-plus` | `0/24` |
| `uv run pytest -q` | `97 passed` |
| `uv run ruff check .` | passed |
| `uv run ruff format --check .` | passed |
| `basedpyright --baselinefile` | `0 errors` |

测试覆盖:

- broker models / engine / ledger / views / backtest runner
- execution node: skipped / held / pending / executed / rejected / failed
- HITL approval snapshot mapping
- identity propagation, account isolation, event filtering
- Streamlit backtest dashboard adapter

---

## 限制与下一步

### 当前限制

- 未接真实券商, 当前是本地 `MockBrokerEngine`
- event / ledger 仍是 in-memory backend
- HITL 只有 execution-time mapping, 没有完整审批队列和 UI
- `as_of` 已进入回测合同, 但 data service 强制 no-lookahead 仍待做
- FastAPI / React / memory / notification 属于后续 integration

### 下一步计划

1. 建 integration branch, 保护 broker-plus 执行域不被覆盖
2. 做 no-lookahead data service sandbox
3. 接入 FastAPI / React 平台层
4. 接 HITL manager 到 execution node
5. 用 `ExecutionOutcomeView` 回填 memory / outcome loop
6. 最后再接真实 broker sandbox adapter

### Q&A

谢谢, 欢迎提问。
