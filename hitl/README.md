# HITL (Human-in-the-Loop)

The HITL module intercepts high-risk AI trading decisions and submits them for human review before execution.

---

## Architecture

```
PM outputs decision
    |
    ▼
┌─────────────────┐
│   Rule Engine   │  ← evaluates if human review is needed
│   (rules.py)    │
└────────┬────────┘
         |
    ┌────┴────┐
    ▼         ▼
auto-pass   pending
(execute    (enter approval
 directly)   queue)
                |
                ▼
         ┌──────────────┐
         │  State Machine│
         │(state_machine)│
         └──────┬───────┘
                |
    ┌─────┬─────┴─────┬─────┐
    ▼     ▼           ▼     ▼
approved rejected  modified timeout
    |       |          |      |
    ▼       ▼          ▼      ▼
execute   do not    execute  do not
original  execute   modified execute
params              params
```

---

## Files

| File | Purpose | Lines |
|------|---------|-------|
| `models.py` | Pydantic models: rule config, PM decision, approval request, approval decision | ~130 |
| `rules.py` | Rule engine: evaluates whether PM decision needs human review | ~80 |
| `state_machine.py` | State machine: manages pending → approved/rejected/modified transitions | ~100 |
| `executor.py` | Executor: outputs final execution parameters based on approval result | ~130 |
| `__init__.py` | Package entry, exports public API | ~50 |

---

## Trigger Rules (3)

| Rule | Threshold | Description |
|------|-----------|-------------|
| `position_change` | 20% | Target position differs from current by more than 20% |
| `low_confidence` | 0.5 | PM confidence below 50% |
| `high_concentration` | 30% | Single ticker target position exceeds 30% |

All thresholds are configured via `HITLRuleConfig` and can be adjusted in `server/routes/analyze.py`.

> **Note**: `HOLD` + 0% target position is treated as a "no-op" (`is_noop`) and does not trigger approval. To change this behavior, edit lines 48-49 in `rules.py`.

---

## Usage

### Trigger HITL in Backend Code

```python
from hitl import HITLRuleEngine, HITLRuleConfig, PMDecision

config = HITLRuleConfig(position_change_threshold_pct=20)
engine = HITLRuleEngine(config)

decision = PMDecision(action="BUY", target_position_pct=60, confidence=0.8)
needs_approval, rules = engine.evaluate(decision, current_position_pct=0)

if needs_approval:
    # create approval record, wait for human review
    store.create_approval("default", {...})
```

### Human Approval (via API)

```bash
# list pending approvals
GET /api/approvals?status=pending

# approve
POST /api/approvals/{id}/approve
{"reviewer": "user"}

# reject
POST /api/approvals/{id}/reject
{"reviewer": "user", "notes": "risk too high"}

# modify then approve
POST /api/approvals/{id}/modify
{
  "reviewer": "user",
  "modified_action": "BUY",
  "modified_target_position_pct": 30,
  "notes": "reduce position"
}
```

---

## State Transitions

```
PENDING → APPROVED   ✓
PENDING → REJECTED   ✓
PENDING → MODIFIED   ✓
PENDING → TIMED_OUT  ✓ (auto on timeout)

APPROVED → REJECTED  ✗ (invalid)
REJECTED → APPROVED  ✗ (invalid)
any terminal → PENDING   ✗ (invalid)
```

Invalid transitions raise `InvalidTransitionError`.

---

## Integration Points

| Integration | File | Description |
|-------------|------|-------------|
| Storage | `storage/store.py` | `approvals` table added to `{strategy_id}.db` |
| Analysis | `server/routes/analyze.py` | HITL check after PM output, returns `approval_status: "pending"` in SSE result |
| API Routes | `server/routes/approvals.py` | 4 endpoints: list/get/approve/reject/modify |
| Frontend | `frontend/app/approvals/page.tsx` | Approval list with approve/reject/modify actions |

---

## Known Limitations

1. **Executor only logs results, does not call Broker** (Gap C handles trade execution)
2. **HITL config is hardcoded in analyze.py**, not yet wired to strategy config system
3. **Approval timeout is not implemented** (`timeout_at` field is reserved)

---

## Debugging

### View Approval Data

```bash
# command line
sqlite3 data/default.db "SELECT id, ticker, status, reviewer FROM approvals;"

# or open data/default.db in DB Browser for SQLite
```

### Test HITL Trigger

Adjust thresholds in `server/routes/analyze.py` to lower the bar:

```python
hitl_config = HITLRuleConfig(
    position_change_threshold_pct=5.0,   # default 20
    min_confidence_threshold=0.9,         # default 0.5
    max_single_ticker_pct=10.0,           # default 30
)
```

**Restart backend** after changing, then analyze any stock — HITL will almost certainly trigger.

---
