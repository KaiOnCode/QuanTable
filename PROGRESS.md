# Progress & Roadmap

Last updated: 2026-05-30 | Branch: `feat/frontend-foundation`

## Verified Modules

| Module | Verified | Notes |
|--------|----------|-------|
| Agent pipeline (CLI) | ✅ | 5-agent, DeepSeek LLM, real output |
| Agent pipeline (API) | ✅ | POST /api/analyze SSE stream |
| AkShare news | ✅ | East Money, mainland accessible |
| Google News → AkShare fallback | ✅ | automatic |
| Frontend build | ✅ | 17 routes, 0 errors |
| Frontend Quick Ask | ✅ | input AAPL → Analyze → result |
| Landing page | ✅ | Hero + Features + Reference |
| MemoryStore | ✅ | SQLite CRUD + OWM scoring |
| ContextStore | ✅ | sessions, reports, decisions |
| MarketDataStore | ✅ | OHLCV, fundamentals, news (FTS5) |
| Python imports | ✅ | 13 modules, 8 tools, 22 routes |

## Built but Not Connected

| Module | Missing |
|--------|---------|
| MemoryStore | Orchestrator doesn't call recall/remember |
| ContextStore | only `/api/analyze` partially uses it |
| Frontend pages (12/14) | mock data, not wired to backend APIs |
| `/api/strategies` CRUD | returns mock data |
| MCP Client | not connected to external servers |
| DataCollector | not run long-term |

## Remaining Modules (priority order)

1. **Memory/Context/Store → orchestrator** (30h)
2. **Frontend ↔ backend API** (40h) — replace mock data
3. **Agent expansion** (60h) — 5→15 agents, debate
4. **Debate Manager** (40h)
5. **MCP Server** (20h) — expose tools via fastmcp
6. **Backtest pipeline** (30h)
7. **HITL Approval** (75h) — human-in-the-loop
8. **Broker Mock Engine** (120h)
9. **Notification system** (60h)
10. **Alpha Zoo integration** (30h)
11. **Belief Contest engine** (25h)
12. **Weekly Reflection generator** (15h)
13. **End-to-end tests** (40h)

**Remaining total: ~585h**

## Branch Strategy

```
main ←── feat/frontend-foundation (current, merge when verified)
  ↑
  ├── feat/strategy-crud
  ├── feat/agent-expansion
  ├── feat/hitl-approval
  └── feat/broker-engine
```
