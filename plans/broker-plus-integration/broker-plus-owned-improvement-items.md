# Broker Plus Owned Improvement Items

This document lists the follow-up improvement items that can reasonably stay inside
`feat/broker-plus`. It is intended as the input for a later decision session, not as
an implementation plan.

## Overall Goal

The goal of these items is to make `feat/broker-plus` a trustworthy execution-domain
foundation for later platform integration. After this work, upper layers such as
FastAPI, React, HITL, memory, monitoring, and notifications should be able to consume
broker-owned contracts without reinterpreting broker internals or duplicating execution
semantics.

In short, `feat/broker-plus` should own the simulated execution core and its public
execution contracts. It should not become the full data platform, web application,
memory system, notification system, or real broker adapter implementation.

## Scope Boundary

In scope for `feat/broker-plus`:

- Broker execution semantics, broker protocol shape, and mock broker behavior.
- Execution reports, broker event views, ledger outputs, backtest result views, and
  serializer contracts.
- Identity propagation through broker-owned objects: `strategy_id`, `account_id`,
  `session_id`, and `decision_id`.
- Execution-side hooks that allow future data, HITL, memory, and notification layers
  to attach without broker importing those layers.

Out of scope for `feat/broker-plus`:

- Full FastAPI or React integration.
- SQLite `ContextStore`, production event stores, and full market-data stores.
- Full HITL manager, approval queue, notification routing, and approval UI.
- MemoryStore, OWM scoring, reflection loops, or long-term conversation memory.
- Real Alpaca, Moomoo, IBKR, or other paper-trading adapter implementation.

## Candidate Items

### 1. Backtest No-Lookahead Execution Contract

Define the execution-side contract that makes a historical backtest run with a clear
`as_of` boundary for each trading step. `BacktestRunner` should be able to pass the
current trading timestamp into the agent/harness and expose a test seam for a scoped
data service or tool factory. The broker-plus responsibility is to guarantee that
execution backtests have a date boundary and a place to inject date-scoped tools.

Target outcome:

- Each backtest step has a single explicit `as_of` timestamp.
- Agent calls during backtest can be connected to a scoped data service.
- Tests can prove that the runner passes the expected date boundary into the agent.

Non-goals:

- Do not build the full historical market database in broker-plus.
- Do not implement all provider-level historical slicing here.
- Do not rely on prompt-only instructions as the no-lookahead control.

### 2. Minimal Scoped Data-Service Seam For Broker Backtests

Add only the minimal interface needed for broker backtests to receive a scoped data
service or tool factory. This is a boundary item, not a full dataflow rewrite. The
point is to keep broker backtests compatible with future `DataService`,
`MarketDataStore`, or test doubles without making broker depend on platform storage.

Target outcome:

- `BacktestRunner` can accept or construct an agent/harness with `as_of`-scoped data
  access.
- Broker tests can use fake data services to verify date scoping.
- Future integration branches can plug in `MarketDataStore` without changing broker
  semantics.

Non-goals:

- Do not merge `upstream/feat/frontend-backend` dataflow wholesale.
- Do not add SQLite storage to broker-plus.
- Do not make broker import server, frontend, or platform storage modules.

### 3. BrokerGateway Adapter-Readiness Contract

Refine `BrokerGateway` so future real or paper broker adapters can implement it
without changing upper-layer execution code. This should focus on protocol clarity:
orders, fills, account state, positions, cancellations, broker events, and stable
identity fields.

Target outcome:

- The gateway clearly states what a broker adapter must provide.
- Mock broker and future adapters can be tested against the same behavioral contract.
- Upper layers continue to call broker through one execution interface.

Possible design questions:

- Whether to add a `client_order_id` or idempotency field now.
- Whether order lifecycle should explicitly model submitted, accepted, partially
  filled, filled, canceled, rejected, and failed.
- Whether asynchronous broker callbacks should remain event-sink only or become part
  of the gateway protocol.

Non-goals:

- Do not implement a real external broker adapter in this branch.
- Do not add broker-specific credentials, SDK dependencies, or network calls.

### 4. Mock Broker Execution Realism Improvements

Improve `MockBrokerEngine` only where it makes execution tests, backtests, or adapter
contracts more credible. Candidate refinements include making `execution_timing`
behavior explicit, clarifying next-open versus close-bar execution, and defining how
limit orders, rejected orders, and partial fills should appear in reports and events.

Target outcome:

- The mock engine behaves predictably enough for demo and regression tests.
- Execution timing is not just a config field; it has clear tested semantics.
- The mock broker remains simple, deterministic, and easy to reason about.

Non-goals:

- Do not simulate a full exchange matching engine.
- Do not model every market microstructure detail.
- Do not introduce nondeterministic fills unless explicitly required and tested.

### 5. ExecutionReportView And HITL Result Mapping

Keep broker-plus responsible for how approval outcomes are represented at execution
time. The formal approval lifecycle belongs to future `hitl/`, but broker-plus should
define how `pending`, `approved`, `modified`, `rejected`, and `timed_out` approval
results become `ExecutionReportView` statuses and approval snapshots.

Target outcome:

- HITL pending decisions do not place orders.
- Approved and modified decisions execute through the broker gateway.
- Rejected and timed-out decisions return structured reports and do not create trades.
- Status naming is compatible with upstream HITL concepts without importing HITL code.

Non-goals:

- Do not implement HITL trigger policy rules.
- Do not implement approval storage, approval API routes, or approval UI.
- Do not let HITL bypass broker execution reports.

### 6. Ledger And Outcome Export For Downstream Memory

Expose enough broker-owned outcome data for future memory/reflection layers to update
decision quality after execution. Broker-plus should not own MemoryStore, but it should
make the data that memory needs easy to query: decision/session identity, fills, account
snapshots, realized PnL, rejected orders, held/skipped decisions, and drawdown metrics.

Target outcome:

- A future memory layer can map a PM decision to later execution outcome.
- Outcome data comes from ledger and execution reports, not free-text PM summaries.
- Failed, held, skipped, rejected, and executed decisions remain distinguishable.

Non-goals:

- Do not implement OWM scoring or memory recall in broker-plus.
- Do not store conversation summaries in broker.
- Do not make broker depend on `memory/`.

### 7. Identity And Lineage Invariants

Strengthen the existing identity discipline across broker models, events, ledger
records, reports, and backtests. `session_id` should mean one agent graph run or one
execution turn; `decision_id` should mean one PM decision; `account_id` should isolate
account state; `strategy_id` should own long-lived strategy performance.

Target outcome:

- Identity fields propagate through order, fill, position, account, event, ledger, and
  public views.
- Tests catch cross-account and cross-session contamination.
- Downstream platform code can join records without guessing identity semantics.

Non-goals:

- Do not add users, permissions, auth, or account ownership management.
- Do not generate `decision_id` inside broker unless explicitly agreed later.

### 8. Broker Event Contract For Downstream Consumers

Make broker event types and payloads stable enough for future platform consumers such
as audit views, notifications, HITL status pages, and memory outcome updates. This is
the broker-owned event vocabulary, not the notification system itself.

Target outcome:

- Execution-domain events have clear type names and payload fields.
- Event sequence is monotonic per `(strategy_id, account_id)`.
- Events distinguish order placement, fill, cancellation, risk rejection, execution
  pending, execution rejected, and execution failed.

Non-goals:

- Do not implement notification channels.
- Do not implement platform audit dashboards.
- Do not implement production event persistence beyond protocol boundaries.

### 9. Contract Mapping And Regression Gate Updates

Keep `plans/broker-plus/05-contract-mapping.md` and the broker-plus test gate aligned
with the agreed integration-facing contract. This item is documentation and validation
discipline: the mapping should tell future integration workers what broker-plus owns,
what it exposes, and what it intentionally excludes.

Target outcome:

- Contract mapping covers identity, percentages, enum mapping, execution report
  statuses, event vocabulary, ledger boundaries, backtest JSON shape, and non-goals.
- Future integration sessions can consume the contract without reopening settled
  broker ownership decisions.
- The accepted regression gate remains explicit and runnable.

Non-goals:

- Do not rewrite platform docs broadly.
- Do not resolve frontend/backend merge conflicts in this item.

## Recommended Next-Session Skill

Use `grill-me` first.

Reason: the next session is not starting from a blank feature idea. It already has a
candidate responsibility list and needs to pressure-test scope boundaries, dependencies,
and decision order. `grill-me` is better for asking one hard question at a time,
exploring the codebase when the answer is discoverable, and resolving the decision tree
without prematurely writing a formal spec.

Use `superpowers:brainstorming` after the grilling session only if the user wants to
turn one agreed item into a formal design/spec workflow. `superpowers:brainstorming`
is stronger for producing an approved design document, but its full process is heavier
than needed for initial scope triage.

## One-Paragraph Prompt For The Next Session

Use `grill-me` on `plans/broker-plus-integration/broker-plus-owned-improvement-items.md`, with `plans/broker-plus/frozen-contract-and-impl-plan.md` and `plans/broker-plus/05-contract-mapping.md` as the current broker-plus contract context. Ask one question at a time; for each candidate item, first inspect the codebase if the answer is discoverable, then describe the concrete problem, give feasible solution options with pros and cons, state your recommendation, and help me decide whether the item belongs in `feat/broker-plus`, belongs only in an integration/platform branch, or should be deferred. Do not implement code, do not merge upstream branches, and keep FastAPI, React, full ContextStore, full HITL manager, MemoryStore, notifications, and real broker adapters outside broker-plus unless we explicitly agree to change the boundary.
