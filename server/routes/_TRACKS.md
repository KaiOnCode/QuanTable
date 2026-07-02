# Route Track Assignment

| Route | Track | File | Notes |
|-------|-------|------|-------|
| `/api/agent/*` | **ACTIVE** | `agent.py` | ReAct agent terminal (main dev) |
| `/api/analyze` | LEGACY | `analyze.py` | Old LangGraph pipeline (frozen) |
| `/api/health` | SHARED | `health.py` | Health check |
| `/api/market/*` | SHARED | `market.py` | Market data REST |
| `/api/insights/*` | SHARED | `insights.py` | Insights/brief |
| `/api/monitor/*` | SHARED | `monitor.py` | Monitor runner |
| `/api/memory/*` | SHARED | `memory.py` | Memory management |
| `/api/strategies/*` | SHARED | `strategies.py` | Strategy config |
| `/api/watchlist/*` | SHARED | `watchlist.py` | Watchlist CRUD |
| `/api/settings/*` | SHARED | `settings.py` | User settings |

## Rules
- ACTIVE routes must use `agentgraph.react_loop.AgentLoop` — NEVER import from `agents/` or `agentgraph.orchestrator`
- LEGACY routes are frozen — do not modify, do not add features
- SHARED routes can be modified but must NOT import from ACTIVE or LEGACY agent code
