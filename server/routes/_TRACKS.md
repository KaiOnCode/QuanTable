# Route Track Assignment

| Route | Track | File | Notes |
|-------|-------|------|-------|
| `/api/agent/*` | **ACTIVE** | `agent.py` | ReAct agent terminal (main dev) |
| `/api/agent/backtest*` | **ACTIVE** | `agent.py` | Persisted single-ticker typed-policy backtest jobs and CSV exports |
| `/api/agent/scanner` | **ACTIVE** | `agent.py` | Restricted AgentLoop compiles query/belief requests through the typed Scanner tool |
| `/api/analyze` | LEGACY | `analyze.py` | Old LangGraph pipeline (frozen) |
| `/api/health` | SHARED | `health.py` | Health check |
| `/api/market/*` | SHARED | `market.py` | Market data REST |
| `/api/insights/*` | SHARED | `insights.py` | Insights/brief |
| `/api/monitor/*` | SHARED | `monitor.py` | Monitor runner |
| `/api/memory/*` | SHARED | `memory.py` | Memory management |
| `/api/strategies/*` | SHARED | `strategies.py` | Strategy config |
| `/api/watchlist/*` | SHARED | `watchlist.py` | Watchlist CRUD |
| `/api/settings/*` | SHARED | `settings.py` | User settings |
| `/api/scanner/*` | SHARED | `scanner.py` | Deterministic tracked-universe rule scans and persisted run reads |

## Rules
- ACTIVE interactive routes must use `agentgraph.react_loop.AgentLoop` — NEVER import from `agents/` or `agentgraph.orchestrator`
- `/api/agent/backtest*` uses the typed policy executor; its canonical deterministic path must not instantiate `AgentLoop`, and experimental mode uses one-shot structured decisions without ReAct read tools
- LEGACY routes are frozen — do not modify, do not add features
- SHARED routes can be modified but must NOT import from ACTIVE or LEGACY agent code
