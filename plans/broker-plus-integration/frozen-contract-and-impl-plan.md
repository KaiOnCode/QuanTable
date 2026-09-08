# Broker Plus Integration-Owned Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Every code-changing task must use `superpowers:test-driven-development`: write a focused failing test, run it and confirm the expected failure, then implement the smallest passing change.

**Goal:** Extend `feat/broker-plus` from a completed first-stage execution contract into a stronger broker-owned integration foundation for no-lookahead backtests, adapter readiness, deterministic mock execution, stable event/outcome contracts, and downstream platform consumption without implementing platform systems.

**Architecture:** Keep broker-plus responsible for execution-domain contracts only: broker models, gateway protocol, mock broker semantics, in-memory event/ledger boundaries, execution reports, backtest runner seams, serializers, and contract mapping. Keep FastAPI, React, full ContextStore, full HITL manager, MemoryStore, notification channels, async broker lifecycle, and real external broker adapters out of this branch. Use thin protocols, Pydantic views, deterministic in-memory behavior, and test-first contract locks.

**Tech Stack:** Python, Pydantic, pandas, pytest, `uv`, `ruff`, `basedpyright`, existing `broker/`, `agentgraph/`, `test/broker/`, and `test/agentgraph/` layout.

---

## 1. Source Inputs

- Candidate responsibility list: `plans/broker-plus-integration/broker-plus-owned-improvement-items.md`
- Grill-me decision workbench: `plans/broker-plus-integration/broker-plus-owned-improvement-grill-workbench.md`
- Integration WIP reminders: `plans/broker-plus-integration/WIP.md`
- Current broker-plus frozen contract: `plans/broker-plus/frozen-contract-and-impl-plan.md`
- Current implemented contract mapping: `plans/broker-plus/05-contract-mapping.md`
- Current implementation surface:
  - `broker/models.py`
  - `broker/events.py`
  - `broker/engine.py`
  - `broker/gateway.py`
  - `broker/ledger.py`
  - `broker/views.py`
  - `broker/backtest_runner.py`
  - `agentgraph/execution_node.py`
  - `agentgraph/orchestrator.py`
  - `agentgraph/state.py`
  - `test/broker/test_models.py`
  - `test/broker/test_engine.py`
  - `test/broker/test_events.py` if created by this plan
  - `test/broker/test_ledger.py`
  - `test/broker/test_views.py`
  - `test/broker/test_backtest_runner.py`
  - `test/agentgraph/test_execution_node.py`
  - `test/agentgraph/test_orchestrator.py`

## 2. Frozen Decisions From Grill-Me

1. `feat/broker-plus` must own a thin `as_of` no-lookahead contract for execution backtests.
2. `feat/broker-plus` must provide a minimal scoped backtest harness/tool seam, but must not import `DataService`, `MarketDataStore`, SQLite, ContextStore, server, or frontend modules.
3. `BrokerGateway` adapter-readiness is limited to `client_order_id` / idempotency and conformance tests. Full adapter lifecycle, async broker callbacks, external SDKs, credentials, network calls, and real broker adapters remain integration/platform work.
4. `MockBrokerEngine` should implement deterministic `execution_timing` semantics for `close_bar` and `next_open`. Partial fills, liquidity/volume constraints, and exchange-grade matching remain deferred contract-breaking enhancements.
5. Broker-plus should strengthen HITL execution-time mapping only. Full HITL manager, queue, timeout policy, interrupt/resume, API, UI, and notification remain out of scope.
6. Broker-plus should expose a broker-owned execution outcome shape for downstream memory/reflection, with first-stage scope at single execution report level. MemoryStore, OWM scoring, reflection loops, persistence, and recall orchestration remain out of scope.
7. Broker-plus should strengthen identity propagation and filtering, but must not generate `decision_id` or introduce users, permissions, auth, or account ownership management.
8. Broker-plus should solidify event vocabulary and minimal payload contracts. Notification channels, audit dashboards, and production event persistence remain platform work.
9. `plans/broker-plus/05-contract-mapping.md` and the regression gate are updated only after implementation tasks pass, not before code exists.

## 3. Explicit Non-Goals

- No FastAPI routes, server schemas, React pages, API clients, or frontend type generation.
- No SQLite `ContextStore`, production event store, production ledger adapter, or full market-data store.
- No full HITL manager, approval queue, approval policy engine, interrupt/resume, approval API, approval UI, or notification routing.
- No MemoryStore, OWM scoring, reflection loop, long-term memory recall, or conversation memory storage.
- No real Alpaca, Moomoo, IBKR, or other external broker adapter.
- No async broker callback lifecycle, external order update replay, accepted/partial/cancel-pending public lifecycle, or SDK/network calls.
- No partial fills, liquidity constraints, volume constraints, nondeterministic fills, or exchange-grade matching.
- No user/permission/auth/account ownership system.
- No README merge or upstream branch merge.

## 4. File Responsibility Map

- `broker/models.py`: add `client_order_id` to core broker `Order`; keep `decision_id` upstream-generated and unchanged.
- `broker/gateway.py`: document the minimal idempotency expectation through the existing protocol surface; do not add async callback methods.
- `broker/engine.py`: enforce order idempotency by `(strategy_id, account_id, client_order_id)`; add deterministic `execution_timing` behavior; keep partial fills unsupported.
- `broker/events.py`: define broker event vocabulary and minimal event payload contract helpers; add optional `decision_id` filtering to the in-memory sink.
- `broker/ledger.py`: expand in-memory backend and public ledger read methods with optional identity filters while keeping ledger rows limited to fills/trades and snapshots.
- `broker/views.py`: expose `client_order_id`; add `ExecutionOutcomeView` and serializer; type broker events against the event vocabulary; keep `partially_filled` out of public `OrderStatusView`.
- `broker/backtest_runner.py`: add `as_of` propagation, scoped agent factory seam, and explicit `strategy_id`/`account_id` backtest identity propagation.
- `agentgraph/orchestrator.py`: accept `as_of`, `strategy_id`, `account_id`, and `decision_id` in `run()` and place them in initial state; keep `date` compatibility.
- `agentgraph/execution_node.py`: pass `client_order_id` from state into broker orders; strengthen approved/modified/rejected/timed_out mapping tests without adding HITL manager.
- `plans/broker-plus/05-contract-mapping.md`: update only in the final contract mapping task, after implementation tests pass.
- `plans/broker-plus-integration/WIP.md`: keep integration reminders; do not delete deferred warning bullets.

## 5. Implementation Tasks

### Task 1: Backtest `as_of`, Scoped Harness Seam, And Backtest Identity

**Files:**

- Modify: `broker/backtest_runner.py`
- Modify: `agentgraph/orchestrator.py`
- Test: `test/broker/test_backtest_runner.py`
- Test: `test/agentgraph/test_orchestrator.py`

- [ ] **Step 1: Write failing backtest tests for `as_of` propagation and scoped agent factory**

Append these tests to `test/broker/test_backtest_runner.py`:

```python
class RecordingBacktestAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(self, ticker: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"ticker": ticker, **kwargs})
        return {"execution_report": "HOLD"}


def test_backtest_runner_passes_as_of_to_each_agent_call() -> None:
    agent = RecordingBacktestAgent()
    runner = BacktestRunner(BrokerConfig(), agent=agent)
    price_df = pd.DataFrame(
        [
            {"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0},
            {"Open": 109.0, "High": 111.0, "Low": 108.0, "Close": 110.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    runner.run(
        ticker="AAPL",
        price_df=price_df,
        start_date="2026-01-02",
        end_date="2026-01-03",
    )

    assert [call["as_of"] for call in agent.calls] == [
        "2026-01-02T00:00:00Z",
        "2026-01-03T00:00:00Z",
    ]
    assert [call["date"] for call in agent.calls] == [
        "2026-01-02T00:00:00Z",
        "2026-01-03T00:00:00Z",
    ]


def test_backtest_runner_builds_scoped_agent_for_each_as_of_boundary() -> None:
    created_as_of: list[str] = []
    agent_calls: list[str] = []

    class ScopedAgent:
        def __init__(self, as_of: str) -> None:
            self._as_of = as_of

        def run(self, ticker: str, **kwargs: object) -> dict[str, object]:
            del ticker
            agent_calls.append(self._as_of)
            assert kwargs["as_of"] == self._as_of
            return {"execution_report": "HOLD"}

    def scoped_agent_factory(as_of: str, broker: MockBrokerEngine) -> ScopedAgent:
        assert isinstance(broker, MockBrokerEngine)
        created_as_of.append(as_of)
        return ScopedAgent(as_of)

    runner = BacktestRunner(
        BrokerConfig(),
        scoped_agent_factory=scoped_agent_factory,
    )
    price_df = pd.DataFrame(
        [
            {"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0},
            {"Open": 109.0, "High": 111.0, "Low": 108.0, "Close": 110.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    runner.run(
        ticker="AAPL",
        price_df=price_df,
        start_date="2026-01-02",
        end_date="2026-01-03",
    )

    assert created_as_of == [
        "2026-01-02T00:00:00Z",
        "2026-01-03T00:00:00Z",
    ]
    assert agent_calls == created_as_of
```

Also append this identity test:

```python
def test_backtest_runner_propagates_strategy_and_account_identity() -> None:
    agent = RecordingBacktestAgent()
    runner = BacktestRunner(BrokerConfig(), agent=agent)
    price_df = pd.DataFrame(
        [{"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0}],
        index=pd.to_datetime(["2026-01-02"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        start_date="2026-01-02",
        end_date="2026-01-02",
        strategy_id="strategy-backtest",
        account_id="account-backtest",
    )

    assert agent.calls[0]["strategy_id"] == "strategy-backtest"
    assert agent.calls[0]["account_id"] == "account-backtest"
    assert result.view.config.strategy_id == "strategy-backtest"
    assert result.view.config.account_id == "account-backtest"
    assert list(result.portfolio["strategy_id"]) == ["strategy-backtest"]
    assert list(result.portfolio["account_id"]) == ["account-backtest"]
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
uv run pytest test/broker/test_backtest_runner.py::test_backtest_runner_passes_as_of_to_each_agent_call test/broker/test_backtest_runner.py::test_backtest_runner_builds_scoped_agent_for_each_as_of_boundary test/broker/test_backtest_runner.py::test_backtest_runner_propagates_strategy_and_account_identity -q
```

Expected: fail because `BacktestRunner.__init__()` does not accept `scoped_agent_factory`, `BacktestRunner.run()` does not accept identity overrides, and agent calls do not include `as_of`.

- [ ] **Step 3: Add the scoped factory and identity implementation**

In `broker/backtest_runner.py`, add imports:

```python
from collections.abc import Callable
```

Define the factory alias near `BacktestResult`:

```python
BacktestScopedAgentFactory = Callable[[str, MockBrokerEngine], Any]
```

Update `BacktestRunner.__init__`:

```python
def __init__(
    self,
    config: BrokerConfig,
    *,
    broker: MockBrokerEngine | None = None,
    ledger: TradeLedger | None = None,
    agent: Any | None = None,
    scoped_agent_factory: BacktestScopedAgentFactory | None = None,
) -> None:
    if agent is not None and scoped_agent_factory is not None:
        msg = "agent and scoped_agent_factory cannot both be provided"
        raise ValueError(msg)
    self._config = config
    self.broker = broker or MockBrokerEngine(config)
    self.ledger = ledger or TradeLedger()
    self.agent = (
        agent
        if agent is not None
        else None
        if scoped_agent_factory is not None
        else IntelliFin_Assistant(broker=self.broker)
    )
    self._scoped_agent_factory = scoped_agent_factory
    self.broker.register_on_fill(self.ledger.record_fill)
```

Update `BacktestRunner.run` signature:

```python
def run(
    self,
    ticker: str,
    price_df: pd.DataFrame,
    start_date: str,
    end_date: str,
    *,
    strategy_id: str = "",
    account_id: str = "default",
) -> BacktestResult:
```

Inside the loop, calculate `as_of` once and select the scoped agent:

```python
as_of = self._to_iso_date(trading_date)
if self._scoped_agent_factory is not None:
    agent = self._scoped_agent_factory(as_of, self.broker)
else:
    agent = self.agent
    if agent is None:
        msg = "backtest agent is not configured"
        raise RuntimeError(msg)
current_position_pct = self._calculate_current_position_pct(
    ticker,
    account_id=account_id,
)
agent.run(
    ticker,
    date=as_of,
    as_of=as_of,
    current_position_pct=current_position_pct,
    execution_enabled=True,
    session_id=session_id,
    strategy_id=strategy_id,
    account_id=account_id,
)
```

Update `_calculate_current_position_pct`:

```python
def _calculate_current_position_pct(self, ticker: str, account_id: str = "default") -> float:
    account = self.broker.get_account(account_id=account_id)
    position = self.broker.get_position(ticker, account_id=account_id)
    ...
```

Update daily snapshot call:

```python
account=self._account_snapshot_for_date(
    trading_timestamp,
    session_id,
    strategy_id=strategy_id,
    account_id=account_id,
),
```

Update `_account_snapshot_for_date`:

```python
def _account_snapshot_for_date(
    self,
    trading_date: Any,
    session_id: str,
    *,
    strategy_id: str = "",
    account_id: str = "default",
) -> AccountSnapshot:
    snapshot = self.broker.get_account(account_id=account_id)
    snapshot.timestamp = cast(
        datetime,
        self._require_timestamp(self._to_iso_date(trading_date)).to_pydatetime(),
    )
    snapshot.strategy_id = strategy_id
    snapshot.account_id = account_id
    snapshot.session_id = session_id
    return snapshot
```

Update `BacktestConfigView(...)` construction:

```python
config=BacktestConfigView(
    tickers=[ticker],
    start_date=start_date,
    end_date=end_date,
    benchmark_symbol="SPY",
    strategy_id=strategy_id,
    account_id=account_id,
),
```

Update the existing `ScriptedExecutionAgent` and `BuyThenHoldAgent` test doubles in `test/broker/test_backtest_runner.py` so their `run()` signatures accept `as_of`, `strategy_id`, and `account_id`. Pass `strategy_id` and `account_id` into the execution-node state where the test double actually executes; ignore `as_of` only if the test does not inspect it.

- [ ] **Step 4: Update orchestrator `run()` compatibility**

Add a failing test to `test/agentgraph/test_orchestrator.py`:

```python
def test_orchestrator_run_accepts_as_of_and_identity_fields() -> None:
    captured_state: dict[str, object] = {}

    def execution_node(state):
        captured_state.update(state)
        return {"execution_report": "{}"}

    assistant = IntelliFin_Assistant(
        llm=object(),
        tool_nodes=_stub_tool_nodes(),
        agent_nodes=_stub_agent_nodes(),
        execution_node=execution_node,
        broker=MockBrokerEngine(BrokerConfig()),
    )

    assistant.run(
        "AAPL",
        date="2026-01-02T00:00:00Z",
        as_of="2026-01-02T00:00:00Z",
        current_position_pct=10.0,
        execution_enabled=True,
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )

    assert captured_state["date"] == "2026-01-02T00:00:00Z"
    assert captured_state["as_of"] == "2026-01-02T00:00:00Z"
    assert captured_state["strategy_id"] == "strategy-1"
    assert captured_state["account_id"] == "account-1"
    assert captured_state["session_id"] == "session-1"
    assert captured_state["decision_id"] == "decision-1"
```

Run:

```bash
uv run pytest test/agentgraph/test_orchestrator.py::test_orchestrator_run_accepts_as_of_and_identity_fields -q
```

Expected: fail because `IntelliFin_Assistant.run()` does not accept `as_of`, `strategy_id`, `account_id`, or `decision_id`.

Then update `agentgraph/orchestrator.py`:

```python
def run(
    self,
    ticker: str,
    date: str | None = None,
    current_position_pct: float = 0.0,
    *,
    as_of: str | None = None,
    execution_enabled: bool = False,
    strategy_id: str = "",
    account_id: str = "default",
    session_id: str = "",
    decision_id: str = "",
):
    effective_date = date or as_of
    initial_state = {
        "ticker": ticker,
        "date": effective_date,
        "as_of": as_of or effective_date,
        "current_position_pct": current_position_pct,
        "execution_enabled": execution_enabled,
        "strategy_id": strategy_id,
        "account_id": account_id,
        "session_id": session_id,
        "decision_id": decision_id,
    }
    thread_id = session_id or "42"
    return self.wf.invoke(
        initial_state,
        config={"configurable": {"thread_id": thread_id}},
    )
```

- [ ] **Step 5: Run focused and existing backtest/orchestrator tests**

Run:

```bash
uv run pytest test/broker/test_backtest_runner.py test/agentgraph/test_orchestrator.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add broker/backtest_runner.py agentgraph/orchestrator.py test/broker/test_backtest_runner.py test/agentgraph/test_orchestrator.py
git commit -m "feat: add backtest as_of scoped harness contract"
```

### Task 2: Identity Filters For Events And Ledger

**Files:**

- Modify: `broker/events.py`
- Modify: `broker/engine.py`
- Modify: `broker/ledger.py`
- Test: `test/broker/test_models.py`
- Test: `test/broker/test_engine.py`
- Test: `test/broker/test_ledger.py`

- [ ] **Step 1: Write failing event filter test**

Append to `test/broker/test_models.py`:

```python
def test_event_sink_filters_by_decision_id() -> None:
    sink = InMemoryBrokerEventSink()
    sink.publish(
        BrokerEvent(
            event_type="order_placed",
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
            decision_id="decision-a",
        )
    )
    sink.publish(
        BrokerEvent(
            event_type="order_filled",
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
            decision_id="decision-b",
        )
    )

    events = sink.load_events(decision_id="decision-b")

    assert [event.event_type for event in events] == ["order_filled"]
    assert events[0].decision_id == "decision-b"
```

Run:

```bash
uv run pytest test/broker/test_models.py::test_event_sink_filters_by_decision_id -q
```

Expected: fail because `load_events()` does not accept `decision_id`.

- [ ] **Step 2: Implement event decision filtering**

Update `BrokerEventSink.load_events` and `InMemoryBrokerEventSink.load_events` in `broker/events.py`:

```python
def load_events(
    self,
    *,
    strategy_id: str | None = None,
    account_id: str | None = None,
    session_id: str | None = None,
    decision_id: str | None = None,
    event_type: str | None = None,
) -> list[BrokerEvent]: ...
```

Add filtering:

```python
if decision_id is not None:
    events = [event for event in events if event.decision_id == decision_id]
```

Update `MockBrokerEngine.get_event_log` in `broker/engine.py` to accept and pass through `decision_id`.

- [ ] **Step 3: Write failing ledger filter tests**

Append to `test/broker/test_ledger.py`:

```python
def test_in_memory_ledger_backend_filters_by_identity_fields() -> None:
    backend = InMemoryLedgerBackend()
    ledger = TradeLedger(backend=backend)
    first_position = Position(
        ticker="AAPL",
        shares=10,
        avg_cost=100.0,
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )
    first_account = AccountSnapshot(
        cash=99_000.0,
        equity=100_000.0,
        positions=[first_position],
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )
    second_position = Position(
        ticker="MSFT",
        shares=5,
        avg_cost=200.0,
        strategy_id="strategy-2",
        account_id="account-2",
        session_id="session-2",
        decision_id="decision-2",
    )
    second_account = AccountSnapshot(
        cash=99_000.0,
        equity=100_000.0,
        positions=[second_position],
        strategy_id="strategy-2",
        account_id="account-2",
        session_id="session-2",
        decision_id="decision-2",
    )
    ledger.record_fill(
        Fill(
            order_id="order-1",
            fill_price=100.0,
            fill_qty=10,
            fee=1.0,
            slippage=0.5,
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
            decision_id="decision-1",
        ),
        first_position,
        first_account,
    )
    ledger.record_fill(
        Fill(
            order_id="order-2",
            fill_price=200.0,
            fill_qty=5,
            fee=1.0,
            slippage=0.5,
            strategy_id="strategy-2",
            account_id="account-2",
            session_id="session-2",
            decision_id="decision-2",
        ),
        second_position,
        second_account,
    )

    records = ledger.load_fill_records(
        strategy_id="strategy-2",
        account_id="account-2",
        decision_id="decision-2",
    )

    assert [record.fill.order_id for record in records] == ["order-2"]
```

Run:

```bash
uv run pytest test/broker/test_ledger.py::test_in_memory_ledger_backend_filters_by_identity_fields -q
```

Expected: fail because ledger methods do not accept these filters.

- [ ] **Step 4: Implement ledger filters without changing ledger semantics**

Update `TradeLedgerBackend` protocol, `InMemoryLedgerBackend`, and `TradeLedger` read methods to accept optional filters:

```python
def load_fill_records(
    self,
    session_id: str | None = None,
    *,
    strategy_id: str | None = None,
    account_id: str | None = None,
    decision_id: str | None = None,
) -> list[LedgerFillRecord]: ...
```

For snapshots:

```python
def load_snapshot_records(
    self,
    session_id: str | None = None,
    *,
    strategy_id: str | None = None,
    account_id: str | None = None,
    decision_id: str | None = None,
) -> list[LedgerSnapshotRecord]: ...
```

Use a private helper:

```python
def _matches_identity(
    *,
    record_strategy_id: str,
    record_account_id: str,
    record_decision_id: str,
    strategy_id: str | None,
    account_id: str | None,
    decision_id: str | None,
) -> bool:
    if strategy_id is not None and record_strategy_id != strategy_id:
        return False
    if account_id is not None and record_account_id != account_id:
        return False
    if decision_id is not None and record_decision_id != decision_id:
        return False
    return True
```

Also update `compute_metrics`, `to_trades_dataframe`, `to_portfolio_dataframe`, and `load_fill_records` to pass through filters. Preserve existing `session_id` positional compatibility.

- [ ] **Step 5: Run focused ledger/event/engine tests**

Run:

```bash
uv run pytest test/broker/test_models.py test/broker/test_engine.py test/broker/test_ledger.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add broker/events.py broker/engine.py broker/ledger.py test/broker/test_models.py test/broker/test_engine.py test/broker/test_ledger.py
git commit -m "feat: add broker identity filters"
```

### Task 3: `client_order_id` And Minimal Idempotency Contract

**Files:**

- Modify: `broker/models.py`
- Modify: `broker/engine.py`
- Modify: `broker/views.py`
- Modify: `agentgraph/execution_node.py`
- Test: `test/broker/test_models.py`
- Test: `test/broker/test_engine.py`
- Test: `test/broker/test_views.py`
- Test: `test/agentgraph/test_execution_node.py`

- [ ] **Step 1: Write failing model and view tests**

Append to `test/broker/test_models.py`:

```python
def test_order_exposes_client_order_id_for_adapter_idempotency() -> None:
    order = Order(
        ticker="AAPL",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        qty=10,
        client_order_id="client-1",
    )

    assert order.client_order_id == "client-1"
```

Append to `test/broker/test_views.py`:

```python
def test_order_view_exposes_client_order_id() -> None:
    order = Order(
        ticker="AAPL",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        qty=10,
        client_order_id="client-1",
    )

    view = to_order_view(order, fills=[])

    assert view.client_order_id == "client-1"
```

Run:

```bash
uv run pytest test/broker/test_models.py::test_order_exposes_client_order_id_for_adapter_idempotency test/broker/test_views.py::test_order_view_exposes_client_order_id -q
```

Expected: fail because `client_order_id` fields do not exist.

- [ ] **Step 2: Add `client_order_id` to model and view**

Add to `Order` in `broker/models.py`:

```python
client_order_id: str = ""
```

Add to `OrderView` in `broker/views.py`:

```python
client_order_id: str = ""
```

Set it in `to_order_view`:

```python
client_order_id=order.client_order_id,
```

- [ ] **Step 3: Write failing idempotency test**

Append to `test/broker/test_engine.py`:

```python
def test_client_order_id_is_idempotent_within_strategy_account_scope() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
        )
    )
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        }
    )
    first_order = Order(
        ticker="AAPL",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        qty=10,
        strategy_id="strategy-1",
        account_id="account-1",
        client_order_id="client-order-1",
    )
    duplicate_order = first_order.model_copy(update={"id": "different-order-id"})

    first_result = broker.place_order(first_order)
    duplicate_result = broker.place_order(duplicate_order)

    assert duplicate_result.id == first_result.id
    assert duplicate_result.status is OrderStatus.FILLED
    assert len(broker.get_orders(account_id="account-1")) == 1
    assert len(broker.get_fills(account_id="account-1")) == 1
    assert [event.event_type for event in broker.get_event_log(account_id="account-1")] == [
        "order_placed",
        "order_filled",
    ]
```

Run:

```bash
uv run pytest test/broker/test_engine.py::test_client_order_id_is_idempotent_within_strategy_account_scope -q
```

Expected: fail because duplicate client order IDs create duplicate orders/fills/events.

- [ ] **Step 4: Implement idempotency in `MockBrokerEngine.place_order`**

At the top of `place_order`, after `account_state = ...`, add:

```python
if order.client_order_id:
    existing_order = self._find_order_by_client_order_id(
        strategy_id=order.strategy_id,
        account_id=order.account_id,
        client_order_id=order.client_order_id,
    )
    if existing_order is not None:
        return existing_order
```

Add helper:

```python
def _find_order_by_client_order_id(
    self,
    *,
    strategy_id: str,
    account_id: str,
    client_order_id: str,
) -> Order | None:
    account_state = self._accounts.get(account_id)
    if account_state is None:
        return None
    for stored_order in account_state.orders.values():
        if (
            stored_order.client_order_id == client_order_id
            and stored_order.strategy_id == strategy_id
        ):
            return stored_order.model_copy(deep=True)
    return None
```

Do not apply idempotency when `client_order_id == ""`.

- [ ] **Step 5: Include `client_order_id` in order event payloads**

Add to `_record_order_event` payload in `broker/engine.py`:

```python
"client_order_id": order.client_order_id,
```

Add this assertion to the idempotency test:

```python
assert broker.get_event_log(account_id="account-1")[0].payload["client_order_id"] == "client-order-1"
```

- [ ] **Step 6: Pass client order ID from execution state**

Append to `test/agentgraph/test_execution_node.py`:

```python
def test_execution_node_passes_client_order_id_to_broker_order() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "execution_enabled": True,
            "client_order_id": "client-order-1",
        }
    )

    report = _report_view(result)
    assert report.order is not None
    assert report.order.client_order_id == "client-order-1"
    assert broker.get_orders()[0].client_order_id == "client-order-1"
```

Run:

```bash
uv run pytest test/agentgraph/test_execution_node.py::test_execution_node_passes_client_order_id_to_broker_order -q
```

Expected: fail because execution node does not pass the field.

Then update `Order(...)` construction in `agentgraph/execution_node.py`:

```python
client_order_id=str(state.get("client_order_id", "") or ""),
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
uv run pytest test/broker/test_models.py test/broker/test_engine.py test/broker/test_views.py test/agentgraph/test_execution_node.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add broker/models.py broker/engine.py broker/views.py agentgraph/execution_node.py test/broker/test_models.py test/broker/test_engine.py test/broker/test_views.py test/agentgraph/test_execution_node.py
git commit -m "feat: add broker client order id idempotency"
```

### Task 4: Stable Broker Event Vocabulary And Payload Contract

**Files:**

- Modify: `broker/events.py`
- Modify: `broker/engine.py`
- Modify: `broker/views.py`
- Modify: `agentgraph/execution_node.py`
- Test: `test/broker/test_models.py`
- Test: `test/broker/test_engine.py`
- Test: `test/broker/test_views.py`
- Test: `test/agentgraph/test_execution_node.py`

- [ ] **Step 1: Write failing event vocabulary tests**

Append to `test/broker/test_models.py`:

```python
def test_broker_event_rejects_unknown_event_type() -> None:
    with pytest.raises(ValidationError):
        BrokerEvent(event_type="made_up_event")
```

Run:

```bash
uv run pytest test/broker/test_models.py::test_broker_event_rejects_unknown_event_type -q
```

Expected: fail because arbitrary strings are currently accepted.

- [ ] **Step 2: Define event vocabulary in `broker/events.py`**

Add near imports:

```python
from typing import Any, Literal, Protocol
```

Define:

```python
BrokerEventType = Literal[
    "order_placed",
    "order_filled",
    "order_canceled",
    "risk_check_failed",
    "order_rejected",
    "execution_pending",
    "execution_rejected",
    "execution_failed",
]

BROKER_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "order_placed",
        "order_filled",
        "order_canceled",
        "risk_check_failed",
        "order_rejected",
        "execution_pending",
        "execution_rejected",
        "execution_failed",
    }
)
ORDER_EVENT_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {"order_id", "client_order_id", "order_status", "side", "order_type", "qty"}
)
EXECUTION_EVENT_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {"status", "reason", "pm_action"}
)
```

Update `BrokerEvent.event_type` type:

```python
event_type: BrokerEventType
```

Pydantic will reject unknown event types.

- [ ] **Step 3: Write failing payload contract test**

Append to `test/broker/test_engine.py`:

```python
def test_order_event_payload_contains_minimal_contract_fields() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        }
    )
    broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
            client_order_id="client-order-1",
        )
    )

    placed_event = broker.get_event_log()[0]

    assert set(ORDER_EVENT_PAYLOAD_KEYS).issubset(placed_event.payload)
    assert placed_event.payload["order_id"]
    assert placed_event.payload["client_order_id"] == "client-order-1"
    assert placed_event.payload["order_status"] == "NEW"
```

Add imports to the test:

```python
from broker.events import ORDER_EVENT_PAYLOAD_KEYS
```

Run:

```bash
uv run pytest test/broker/test_engine.py::test_order_event_payload_contains_minimal_contract_fields -q
```

Expected: fail if `client_order_id` has not been added to payload or constants are missing.

- [ ] **Step 4: Ensure execution event payload contract**

Append to `test/agentgraph/test_execution_node.py`:

```python
def test_execution_event_payload_contains_minimal_contract_fields() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    execution_node = create_execution_node(broker)

    execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "execution_enabled": True,
            "strategy_id": "strategy-1",
            "account_id": "account-1",
            "session_id": "session-1",
            "decision_id": "decision-1",
        }
    )

    event = broker.get_event_log(account_id="account-1", event_type="execution_failed")[0]
    assert event.entity_type == "execution"
    assert event.entity_id == "decision-1"
    assert event.payload == {
        "status": "failed",
        "reason": "missing market price",
        "pm_action": "BUY",
    }
```

Run:

```bash
uv run pytest test/agentgraph/test_execution_node.py::test_execution_event_payload_contains_minimal_contract_fields -q
```

Expected: pass if current payload already matches; if it fails, adjust `_publish_execution_event` to match exactly.

- [ ] **Step 5: Update view event typing**

In `broker/views.py`, import `BrokerEventType`:

```python
from broker.events import BrokerEvent, BrokerEventType
```

Update `BrokerEventView`:

```python
event_type: BrokerEventType
```

Add or update `test_broker_event_view_uses_payload_contract` in `test/broker/test_views.py` to assert the type still serializes:

```python
assert view.event_type == "order_filled"
```

- [ ] **Step 6: Run focused event tests**

Run:

```bash
uv run pytest test/broker/test_models.py test/broker/test_engine.py test/broker/test_views.py test/agentgraph/test_execution_node.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add broker/events.py broker/engine.py broker/views.py agentgraph/execution_node.py test/broker/test_models.py test/broker/test_engine.py test/broker/test_views.py test/agentgraph/test_execution_node.py
git commit -m "feat: freeze broker event vocabulary"
```

### Task 5: Execution Outcome View And HITL Mapping Regression

**Files:**

- Modify: `broker/views.py`
- Modify: `broker/__init__.py`
- Test: `test/broker/test_views.py`
- Test: `test/agentgraph/test_execution_node.py`

- [ ] **Step 1: Write failing outcome serializer test for executed reports**

First update imports in `test/broker/test_views.py`:

```python
from broker.models import (
    AccountSnapshot,
    ExecutionReport,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from broker.views import (
    ...
    to_execution_outcome_view,
    to_execution_report_view,
)
```

Append to `test/broker/test_views.py`:

```python
def test_execution_outcome_view_serializes_executed_report_for_memory_consumers() -> None:
    position = Position(
        ticker="AAPL",
        shares=10,
        avg_cost=100.0,
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )
    account = AccountSnapshot(
        cash=99_000.0,
        equity=100_000.0,
        positions=[position],
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )
    order = Order(
        ticker="AAPL",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        qty=10,
        status=OrderStatus.FILLED,
        client_order_id="client-order-1",
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )
    fill = Fill(
        order_id=order.id,
        fill_price=100.0,
        fill_qty=10,
        fee=1.0,
        slippage=0.5,
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )
    report = to_execution_report_view(
        ExecutionReport(
            order=order,
            fills=[fill],
            position_after=position,
            account_after=account,
            pm_action="BUY",
            pm_report_summary="Open position.",
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
            decision_id="decision-1",
        )
    )
    trade_record = LedgerFillRecord(
        fill=fill,
        ticker="AAPL",
        side="BUY",
        realized_pnl=-1.5,
        position_after=position,
        account_after=account,
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )

    outcome = to_execution_outcome_view(report, trades=[trade_record])

    assert outcome.status == "executed"
    assert outcome.strategy_id == "strategy-1"
    assert outcome.account_id == "account-1"
    assert outcome.session_id == "session-1"
    assert outcome.decision_id == "decision-1"
    assert outcome.order is not None
    assert outcome.order.client_order_id == "client-order-1"
    assert len(outcome.trades) == 1
    assert outcome.realized_pnl == pytest.approx(-1.5)
    assert outcome.account_after is not None
    assert outcome.account_after.equity == pytest.approx(100_000.0)
```

Run:

```bash
uv run pytest test/broker/test_views.py::test_execution_outcome_view_serializes_executed_report_for_memory_consumers -q
```

Expected: fail because `ExecutionOutcomeView` and serializer do not exist.

- [ ] **Step 2: Implement `ExecutionOutcomeView`**

In `broker/views.py`, define:

```python
class ExecutionOutcomeView(BaseModel):
    status: ExecutionStatusView
    order: OrderView | None = None
    trades: list[TradeView] = Field(default_factory=list)
    account_after: AccountView | None = None
    realized_pnl: float = 0.0
    reason: str = ""
    pm_action: str = ""
    approval_status: str = ""
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""
```

Add serializer:

```python
def to_execution_outcome_view(
    report: ExecutionReportView,
    *,
    trades: Sequence[LedgerFillRecord] | None = None,
) -> ExecutionOutcomeView:
    trade_views = [to_trade_view(record) for record in trades or []]
    return ExecutionOutcomeView(
        status=report.status,
        order=report.order,
        trades=trade_views,
        account_after=report.account_after,
        realized_pnl=sum(trade.realized_pnl for trade in trade_views),
        reason=report.reason,
        pm_action=report.pm_action,
        approval_status=(
            report.approval.approval_status if report.approval is not None else ""
        ),
        strategy_id=report.strategy_id,
        account_id=report.account_id,
        session_id=report.session_id,
        decision_id=report.decision_id,
    )
```

Export `ExecutionOutcomeView` from `broker/__init__.py`; keep `to_execution_outcome_view` in `broker.views` with the existing serializer functions.

- [ ] **Step 3: Write failing outcome serializer test for no-trade branches**

Append to `test/broker/test_views.py`:

```python
def test_execution_outcome_view_preserves_no_trade_reason() -> None:
    report = to_execution_status_report_view(
        status="rejected",
        reason="approval rejected",
        pm_action="BUY",
        pm_report_summary="Increase exposure.",
        approval=ApprovalSnapshotView(
            approval_id="approval-1",
            approval_status="timed_out",
            original_target_pct=50.0,
        ),
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )

    outcome = to_execution_outcome_view(report)

    assert outcome.status == "rejected"
    assert outcome.order is None
    assert outcome.trades == []
    assert outcome.realized_pnl == pytest.approx(0.0)
    assert outcome.reason == "approval rejected"
    assert outcome.approval_status == "timed_out"
    assert outcome.decision_id == "decision-1"
```

Run:

```bash
uv run pytest test/broker/test_views.py::test_execution_outcome_view_preserves_no_trade_reason -q
```

Expected: pass after Step 2.

- [ ] **Step 4: Add HITL approved mapping regression**

Append to `test/agentgraph/test_execution_node.py`:

```python
def test_execution_node_treats_approved_approval_as_execution_without_snapshot() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "approval_status": "approved",
            "execution_enabled": True,
        }
    )

    report = _report_view(result)

    assert report.status == "executed"
    assert report.approval is None
    assert report.order is not None
    assert report.order.status == "executed"
```

Run:

```bash
uv run pytest test/agentgraph/test_execution_node.py::test_execution_node_treats_approved_approval_as_execution_without_snapshot -q
```

Expected: pass with current behavior; if it fails, fix without adding HITL manager.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest test/broker/test_views.py test/agentgraph/test_execution_node.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add broker/views.py broker/__init__.py test/broker/test_views.py test/agentgraph/test_execution_node.py
git commit -m "feat: add broker execution outcome view"
```

### Task 6: Deterministic `execution_timing` Semantics

**Files:**

- Modify: `broker/engine.py`
- Modify: `broker/config.py` only if comments need alignment
- Test: `test/broker/test_engine.py`
- Test: `test/agentgraph/test_execution_node.py`

- [ ] **Step 1: Write failing next-open market execution test**

Append to `test/broker/test_engine.py`:

```python
def test_market_order_with_next_open_timing_fills_on_next_bar_open() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
        )
    )
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        }
    )

    placed_order = broker.place_order(
        Order(ticker="AAPL", side=OrderSide.BUY, type=OrderType.MARKET, qty=10)
    )

    assert placed_order.status is OrderStatus.NEW
    assert broker.get_fills(placed_order.id) == []
    assert [event.event_type for event in broker.get_event_log()] == ["order_placed"]

    broker.on_bar(
        {
            "AAPL": {"open": 105.0, "high": 106.0, "low": 104.0, "close": 105.5},
        }
    )

    stored_order = broker.get_order(placed_order.id)
    assert stored_order is not None
    assert stored_order.status is OrderStatus.FILLED
    fills = broker.get_fills(placed_order.id)
    assert len(fills) == 1
    assert fills[0].fill_price == pytest.approx(105.0)
    assert broker.get_position("AAPL").avg_cost == pytest.approx(105.0)
    assert [event.event_type for event in broker.get_event_log()] == [
        "order_placed",
        "order_filled",
    ]
```

Run:

```bash
uv run pytest test/broker/test_engine.py::test_market_order_with_next_open_timing_fills_on_next_bar_open -q
```

Expected: fail because market orders fill immediately at current close.

- [ ] **Step 2: Implement next-open timing**

Update `MockBrokerEngine.on_bar`:

```python
def on_bar(self, bars: dict[str, BarData]) -> None:
    self._latest_bars.update(bars)
    for account_state in self._accounts.values():
        for order in list(account_state.orders.values()):
            if order.status is not OrderStatus.NEW or order.ticker not in bars:
                continue
            if order.type is OrderType.MARKET and self._config.execution_timing == "next_open":
                self._try_fill_market(order, float(bars[order.ticker]["open"]))
            elif order.type is OrderType.LIMIT:
                self._try_fill_limit(order, bars[order.ticker])
```

Update `place_order`:

```python
if stored_order.type is OrderType.MARKET and self._config.execution_timing == "close_bar":
    self._try_fill_market(stored_order, reference_price)
```

Leave `"next_open"` orders as `OrderStatus.NEW` after risk check. Do not create `execution_pending` here; execution-node handles broker-returned pending status.

Update the stale comment in `broker/config.py`:

```python
# close_bar fills market orders from the current close reference; next_open
# queues market orders until the next bar's open. Both modes are deterministic.
execution_timing: Literal["close_bar", "next_open"] = "close_bar"
```

- [ ] **Step 3: Write execution-node pending test for next-open**

Append to `test/agentgraph/test_execution_node.py`:

```python
def test_execution_node_reports_pending_for_next_open_market_order() -> None:
    broker = MockBrokerEngine(BrokerConfig(execution_timing="next_open"))
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "execution_enabled": True,
        }
    )

    report = _report_view(result)

    assert report.status == "pending"
    assert report.order is not None
    assert report.order.status == "pending"
    assert report.fills == []
    assert [event.event_type for event in broker.get_event_log()] == [
        "order_placed",
        "execution_pending",
    ]
```

Run:

```bash
uv run pytest test/agentgraph/test_execution_node.py::test_execution_node_reports_pending_for_next_open_market_order -q
```

Expected: pass after Step 2 or fail only on event ordering; fix event mapping without adding partial lifecycle.

- [ ] **Step 4: Confirm close-bar behavior remains unchanged**

Run:

```bash
uv run pytest test/broker/test_engine.py::test_market_buy_order_fills_immediately_and_updates_account_state test/agentgraph/test_execution_node.py::test_execution_node_places_market_order_and_serializes_execution_report -q
```

Expected: pass.

- [ ] **Step 5: Run focused engine/execution tests**

Run:

```bash
uv run pytest test/broker/test_engine.py test/agentgraph/test_execution_node.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add broker/engine.py broker/config.py test/broker/test_engine.py test/agentgraph/test_execution_node.py
git commit -m "feat: implement deterministic execution timing"
```

### Task 7: Final Contract Mapping And Regression Gate

**Files:**

- Modify: `plans/broker-plus/05-contract-mapping.md`
- Modify: `plans/broker-plus-integration/WIP.md`
- Test/Verify: full project checks

- [ ] **Step 1: Update contract mapping after code tasks pass**

Edit `plans/broker-plus/05-contract-mapping.md` to add sections or bullets for:

```markdown
## Backtest No-Lookahead Boundary

- `BacktestRunner` passes a single explicit `as_of` timestamp to each agent/harness call.
- `date` remains a compatibility alias for `as_of` during backtest calls.
- Broker-plus exposes a scoped agent factory seam for tests and future integration adapters.
- Broker-plus does not import DataService, MarketDataStore, SQLite, ContextStore, server, or frontend modules.

## Adapter Readiness

- `Order.client_order_id` is caller-generated and broker-propagated.
- `client_order_id` is used for idempotency within `(strategy_id, account_id)`.
- Full async adapter lifecycle, SDK/network calls, real broker adapters, and partial lifecycle states remain out of scope.

## Execution Timing

- `close_bar` fills market orders from the current close reference.
- `next_open` keeps market orders pending until the next bar and fills from that next bar's open.
- Partial fills, volume/liquidity constraints, and exchange-grade matching remain out of scope.

## Execution Outcome View

- `ExecutionOutcomeView` is the broker-owned single-execution outcome shape for future memory/reflection consumers.
- It is derived from `ExecutionReportView` plus optional ledger fill records.
- MemoryStore, OWM scoring, reflection loops, persistence, and recall remain outside broker-plus.

## Event Vocabulary

- Broker events are restricted to the broker-owned execution vocabulary.
- Order event payloads include at least `order_id`, `client_order_id`, `order_status`, `side`, `order_type`, and `qty`.
- Execution event payloads include at least `status`, `reason`, and `pm_action`.
```

Keep existing non-goals and keep `partially_filled` excluded from public `OrderStatusView`.

- [ ] **Step 2: Update integration WIP with implementation completion note**

Append to `plans/broker-plus-integration/WIP.md`:

```markdown
## Implementation Follow-Through

- After the broker-plus integration-owned improvements are implemented, `plans/broker-plus/05-contract-mapping.md` is the source for the implemented broker-owned contract. This WIP remains an integration reminder for deferred platform work: full HITL manager, notifications, MemoryStore, real broker adapters, async lifecycle, and partial-fill contract expansion.
```

- [ ] **Step 3: Run broker and agentgraph regression**

Run:

```bash
uv run pytest test/broker test/agentgraph -q
```

Expected: all tests pass.

- [ ] **Step 4: Run full regression and static checks**

Run:

```bash
uv run pytest -q
uv run basedpyright --baselinefile bugs/basedpyright/baseline.json
uv run ruff check .
uv run ruff format --check .
```

Expected: all commands pass. If a command fails due to unrelated pre-existing issues, record exact failures in the final handoff and do not hide them.

- [ ] **Step 5: Commit**

```bash
git add plans/broker-plus/05-contract-mapping.md plans/broker-plus-integration/WIP.md
git commit -m "docs: map broker plus integration-owned contracts"
```

## 6. Required Execution Discipline For Next Session

1. Start from `feat/broker-plus`; do not implement on `main` or merge upstream branches.
2. Use `superpowers:subagent-driven-development` if available; otherwise use `superpowers:executing-plans`.
3. Every code-changing task must use `superpowers:test-driven-development`.
4. For every task, write the failing tests first and confirm expected RED before implementation.
5. Keep commits task-scoped.
6. Stop if a task requires FastAPI, React, ContextStore, MemoryStore, notification channels, full HITL manager, async broker lifecycle, real adapter SDKs, or partial-fill public status changes.
7. Do not update `plans/broker-plus/05-contract-mapping.md` until implementation tasks 1-6 pass focused tests.

## 7. Suggested Goal-Mode Prompt For Next Session

```text
Use `plans/broker-plus-integration/frozen-contract-and-impl-plan.md` as the implementation plan. Work on `feat/broker-plus` only. Use `superpowers:subagent-driven-development` if available; otherwise use `superpowers:executing-plans`. Every code-changing task must use `superpowers:test-driven-development`: write failing tests first, verify RED, implement minimal GREEN, then refactor. Implement all tasks in order, with task-scoped commits, and stop only if blocked by a genuine ambiguity or if the work would require FastAPI, React, ContextStore, MemoryStore, notifications, full HITL manager, async broker lifecycle, real broker adapters, or partial-fill public status changes. After tasks pass, run the broker-plus regression gate and update `plans/broker-plus/05-contract-mapping.md` only as specified in the final task.
```

## 8. Self-Review Checklist

- [x] Every grill-me confirmed item has an implementation or explicit deferred/non-goal handling path.
- [x] No task imports FastAPI, React, ContextStore, MemoryStore, notifications, full HITL manager, or real broker adapters.
- [x] Partial fills and async adapter lifecycle are explicitly deferred.
- [x] Tests are specified before implementation steps.
- [x] `05-contract-mapping.md` is updated only after code tasks pass.
- [x] Regression gate includes pytest, basedpyright, ruff check, and ruff format check.
