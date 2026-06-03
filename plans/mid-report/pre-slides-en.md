# Broker Plus Execution-Domain Contract

## From AI recommendation to auditable mock execution

Mid-report focus:

- Original system: multi-agent analysis + PM decision
- Current progress: PM decision enters a local mock broker execution domain
- Core output: broker-owned execution-domain contract

One-sentence summary:

> We moved the system from "generate a recommendation" toward "execute, record, serialize, and audit the recommendation."

---

## Why Broker Plus?

### Current gap

Original pipeline:

```text
User input -> Multi-Agent Analysis -> PM Decision -> END
```

Problems:

- PM can output `BUY / HOLD / SELL`, but there is no unified order interface
- No stable semantics for orders, fills, accounts, positions, rejections, or ledger records
- Frontend, HITL, memory, and notification layers would otherwise reinterpret execution results separately

Broker Plus goal:

```text
PM decision -> execution node -> broker gateway -> mock execution
            -> events + ledger -> structured views
```

---

## Architecture

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

Boundary:

| Broker owns | Broker does not own |
| --- | --- |
| Orders, fills, accounts, positions | FastAPI / React pages |
| Risk checks, events, ledger | Full HITL manager |
| Execution reports, backtest views | ContextStore / MemoryStore |
| Adapter-ready protocol | Real broker SDK / network calls |

---

## Completed Work

### `feat/broker`: execution-domain baseline

- `Order / Fill / Position / AccountSnapshot / ExecutionReport`
- `BrokerGateway` + `MockBrokerEngine`
- Market orders, limit orders, cancellation, shorting, risk rejection
- `TradeLedger`: fills, daily snapshots, metrics, CSV export
- PM -> execution node -> broker -> execution report
- Streamlit backtest dashboard and smoke validation

### `feat/broker-plus`: contract hardening

- `strategy_id / account_id / session_id / decision_id`
- Account isolation: cash, positions, orders, fills, events
- `BrokerEventSink` and `TradeLedgerBackend` protocols
- `broker/views.py`: public DTO / serializer contract
- `client_order_id` idempotency, event vocabulary, `as_of` backtest contract
- Deterministic `close_bar / next_open` execution timing

---

## Evidence

Current branch: `feat/broker-plus`

| Item | Result |
| --- | --- |
| HEAD | `8988e4b` |
| origin/upstream broker-plus | aligned with HEAD |
| `feat/broker...feat/broker-plus` | `0/24` |
| `uv run pytest -q` | `97 passed` |
| `uv run ruff check .` | passed |
| `uv run ruff format --check .` | passed |
| `basedpyright --baselinefile` | `0 errors` |

Test coverage:

- broker models / engine / ledger / views / backtest runner
- execution node: skipped / held / pending / executed / rejected / failed
- HITL approval snapshot mapping
- identity propagation, account isolation, event filtering
- Streamlit backtest dashboard adapter

---

## Limitations & Future Work

### Limitations

- No real broker integration yet; current engine is `MockBrokerEngine`
- Event and ledger backends are still in-memory
- HITL is execution-time mapping only; no full approval queue or UI in this branch
- `as_of` is in the backtest contract, but data service no-lookahead enforcement is still future work
- FastAPI / React / memory / notification belong to the integration layer

### Future work

1. Create an integration branch and protect broker-plus execution semantics
2. Build a no-lookahead data service sandbox
3. Connect FastAPI / React platform layers
4. Connect HITL manager to the execution node
5. Feed `ExecutionOutcomeView` into memory / outcome loop
6. Add a real broker sandbox adapter after the mock contract is stable

### Q&A

Thank you. Questions are welcome.
