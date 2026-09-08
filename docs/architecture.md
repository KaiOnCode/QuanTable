# Agentic-Quant 架构文档

2026-07-17 · dev 分支 · COMP7705 毕业设计

---

## 1. 项目概述

多 Agent 推理驱动的量化分析框架。LangGraph + DeepSeek LLM + FastAPI + Next.js 16 + SQLite。

核心能力：金融对话分析（ReAct Agent）、策略回测（MockBrokerEngine）、实时数据采集（Yahoo/Google/AkShare）、PDF 报告、OWM 记忆、技能系统、HITL 审批、风险分析、扫描器。

---

## 2. Track 系统（架构红线）

```
agent/     = ACTIVE   (主开发 — ReAct Agent 终端)
quick_ask/ = LEGACY   (冻结 — 旧 LangGraph 管线)
agents/    = LEGACY   (冻结 — 旧 Agent 实现)
agentgraph/= LEGACY   (冻结 — 旧编排层)
其余       = SHARED   (可修改)
```

铁律：
- ACTIVE 代码禁止 import LEGACY 代码
- `RunAnalysisTool` 是唯一允许的桥接（调用时 import）
- LEGACY 目录禁止修改
- 新功能放在 `agent/loop.py`、`agent/tools/` 或 `skills/`

---

## 3. 架构总览

```
前端 (Next.js 16) ── 14 个页面
       │ REST + SSE
       ▼
FastAPI (server/main.py) ── 13 个路由模块
       │
       ▼
┌──────────────────────────────────────────┐
│           数据层 (SHARED)                 │
│  DataService ──→ MarketDataStore (SQLite) │
│  ContextStore ──→ system.db + 策略级 DB   │
│  MemoryStore  ──→ memory.db (OWM 评分)    │
│  8 个 Provider (Yahoo/Google/AkShare)     │
└──────────────────────────────────────────┘
```

---

## 4. Agent 模块 (`agent/` — ACTIVE)

### 4.1 ReAct 循环 (`loop.py`)

`AgentLoop` — 核心执行引擎。5 阶段迭代（参照 Claude Code query.ts）：

| 阶段 | 名称 | 说明 |
|------|------|------|
| 1 | Preprocess | 上下文压缩 L0→L1→L2→L3 |
| 1.5 | Prefetch | Memory 异步预取 |
| 2 | Call Model | 流式 LLM + StreamingToolExecutor |
| 3 | Execute Tools | 收集工具结果，写入 messages |
| 4 | Inject Attachments | Memory 注入为 `<system-reminder>` |
| 5 | Check Terminate | 错误分类 + 恢复决策 |

关键机制：`needsFollowUp` 自停、跨迭代去重、断路器、权限框架。

### 4.2 提示 (`prompts.py`)

7 节系统提示：Identity → Doing Tasks → Actions → Tool Rules → Tool Descriptions → Output Rules → Environment。Skills 关键词动态注入。

### 4.3 压缩 (`compression.py`)

L0 (工具结果截断 50K) → L1 (micro-compact，保留 15 个) → L2 (折叠大文本) → L3 (LLM 摘要，40K 令牌触发)。

### 4.4 恢复 (`recovery.py`)

错误分类 → 终止决策树（prompt_too_long → collapse_drain → reactive_compact → 终止；max_output_tokens → 升级 64K → 恢复消息 ×3 → 终止；等）。`RecoveryState` 追踪尝试次数。

### 4.5 工具 (`tools/`)

21 个工具，5 个类别：

| 类别 | 工具 | 文件 |
|------|------|------|
| 金融数据 | get_price, get_indicators, get_news, get_fundamentals, get_meta, get_sentiment, get_macro_calendar, search_symbol, web_search, search_news, run_analysis, generate_brief, web_fetch | `financial.py` |
| 工作空间 | read_file, write_file, glob, bash | `workspace.py` |
| 技能 | load_skill, search_skills, list_skills, save_skill, delete_skill | `financial.py` |
| 回测 | submit_backtest_decision | `backtest.py` |
| 扫描器 | scan | `scanner.py` |

基础设施：`BaseTool` ABC + `ToolMeta` + `build_tool()` 工厂 + `ToolRegistry` 单例 + `StreamingToolExecutor` + `PermissionManager`。

### 4.6 回测与发现 (agent/ 内)

| 文件 | 说明 |
|------|------|
| `backtest_jobs.py` | BacktestJobService (1921 行) |
| `backtest_policy.py` | 策略资格 + 快照 |
| `backtest_policy_executor.py` | Agent 实验执行器 |
| `backtest_adapter.py` | Agent-Broker 适配器 |
| `backtest_errors.py` | 回测错误类型 |
| `run_context.py` | 作用域执行 |
| `scanner_adapter.py` | 扫描器编译 |
| `discovery.py` | Ticker 发现 |

---

## 5. 服务端 (`server/`)

### 5.1 路由

| 前缀 | 状态 |
|------|------|
| `/api/agent` — Agent 对话 + 回测 + 技能 | ACTIVE |
| `/api/analyze` — 旧版分析 | LEGACY |
| `/api/strategies` `/market` `/watchlist` `/monitor` `/insights` `/risk` `/reports` `/scanner` `/approvals` `/memory` `/settings` | SHARED |

### 5.2 `/api/agent` 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | SSE 流式 Agent 对话 |
| GET/POST/DELETE | `/sessions` | 会话 CRUD |
| POST | `/backtest` | 创建回测 (202 Accepted) |
| GET | `/backtest/{id}` | 回测状态 |
| POST | `/backtest/{id}/replay` | 重放 |
| GET | `/backtest/{id}/*.csv` | CSV 导出 |
| POST | `/scanner` | 编译扫描器 |
| GET/POST/DELETE | `/skills` | 技能 CRUD |

### 5.3 其他文件

`main.py` (CORS + 启动恢复 + 后台调度器), `llm_defaults.py`, `monitor_engine.py`, `morning_brief.py`, `analysis_runs.py`。

---

## 6. 前端 (`frontend/`)

Next.js 16 App Router + TypeScript + shadcn/ui + TailwindCSS v4。

14 个页面：agent, dashboard, quick-ask (LEGACY), strategies, backtest, approvals, insights, monitor, memory-lab, risk, reports, scanner, settings, watchlist。

关键依赖：`@tanstack/react-query` (服务端状态), `zustand` (客户端状态), `recharts` (图表), `remark-gfm` (Markdown)。

---

## 7. 数据层 (`dataflow/` — SHARED)

### 7.1 DataService (`service.py`)

统一数据访问入口。方法：`get_prices()`, `get_news()`, `get_fundamentals()`, `get_indicators()`, `get_meta()`, `search_news()`。

### 7.2 Provider (`providers/`)

| Provider | 数据 |
|----------|------|
| YFinance | OHLCV、指标、基本面 |
| Google News / RSS | 股票新闻、网页搜索 |
| AkShare | A 股基本面、新闻 |
| Bing News | 替代新闻源 |
| Finnhub | 经济日历 |
| Sentiment | 关键词情绪聚合 |

### 7.3 MarketDataStore (`store.py`)

`data/market_data.db` — 6 张表：ohlcv, fundamentals, news, news_fts (FTS5), data_freshness, ticker_meta。

### 7.4 History (`history.py`)

`DataServiceHistoryLoader` — 回测数据预加载（最多 4 次重试，递增回看窗口）。

---

## 8. 回测引擎 (`broker/`)

`MockBrokerEngine` — 日线模拟交易。组件：models (Order/Fill/Position), ledger (账本/PnL), views (报告), risk_checks (交易前检查), config (佣金/滑点), events, backtest_runner (编排), gateway (协议接口)。

数据流：`DataServiceHistoryLoader.preload()` → MarketDataStore → `BacktestDataService` → `MockBrokerEngine`。

---

## 9. 存储 (`storage/` — SHARED)

`ContextStore` — 每策略独立 SQLite：

| 数据库 | 表 |
|--------|-----|
| `data/system.db` | strategies, backtest_jobs, monitor_tasks, watchlists 等 |
| `data/insights.db` | monitoring_reports, monitor_news, daily_briefs |
| `data/{strategy_id}.db` | sessions, agent_reports, decisions, events, approvals |
| `data/memory.db` | memories (OWM 评分) |

---

## 10. 其他模块

| 模块 | 说明 | 状态 |
|------|------|------|
| `memory/` | OWM 记忆 (5 因子评分 + Pre-Trade 安全检查) | SHARED |
| `skills/` | 76 个 SKILL.md，10 个类别 + 关键词匹配注入 | ACTIVE |
| `scheduler/` | APScheduler 数据采集 (价格 15min, 新闻 30min) | SHARED |
| `notification/` | 多渠道告警 (邮件/Telegram/微信/WhatsApp) | ACTIVE |
| `risk/` | 风险分析 (集中度/相关性/VaR/压力测试) | ACTIVE |
| `hitl/` | 人机协作审批 (规则引擎 + 状态机) | ACTIVE |
| `scanner/` | 确定性股票扫描 (范围 + 条件评估) | ACTIVE |
| `reporting/` | PDF 报告 (fpdf2 + Jinja2 + NotoSansCJK 中文字体) | ACTIVE |
| `knowledge/` | 文件知识库 (rules/findings/failures) | SHARED |
| `belief/` | 交易理念 (TradingBelief + 5 预设) | SHARED |
| `mcp/` | MCP 外部工具集成 | SHARED |
| `quick_ask/` | 旧 LangGraph 管线 (5 Agent) | LEGACY |

---

## 11. 目录结构

```
COMP7705-Agent-Quant/
├── agent/          # ACTIVE — ReAct Agent + 回测策略 + 扫描器适配
├── server/         # FastAPI — 13 个路由 + 监控引擎 + 早间简报
├── frontend/       # Next.js 16 — 14 个页面 + UI 组件
├── broker/         # 回测引擎 — 模拟交易 + 账本 + 风控
├── dataflow/       # DataService + 8 个 Provider + MarketDataStore + HistoryLoader
├── storage/        # ContextStore — 策略级 SQLite 隔离
├── memory/         # OWM MemoryStore + 安全检查
├── skills/         # 76 个 SKILL.md + SkillLoader
├── scheduler/      # APScheduler 数据采集
├── notification/   # 多渠道告警
├── risk/           # 风险分析
├── hitl/           # 人机协作审批
├── scanner/        # 股票扫描器
├── reporting/      # PDF 报告 + 中文字体
├── knowledge/      # 文件知识库
├── belief/         # 交易理念
├── mcp/            # MCP 外部工具
├── quick_ask/      # LEGACY — LangGraph 5-Agent 管线
├── agents/         # LEGACY — 旧 Agent 实现
├── agentgraph/     # LEGACY — 旧编排层
├── test/           # 60+ 测试文件
├── docs/           # 文档
├── data/           # 运行时 SQLite 数据
├── plans/          # 设计文档
└── archive/        # 归档文件
```

---

## 12. 技术栈

| 类别 | 技术 |
|------|------|
| LLM | OpenAI 兼容 API (deepseek-chat / deepseek-v4-flash) |
| Agent 编排 | 自研 ReAct 循环 + LangChain ChatOpenAI (仅 LLM 调用) |
| 后端 | FastAPI + uvicorn |
| 前端 | Next.js 16 + React + TypeScript + shadcn/ui + TailwindCSS v4 |
| 数据 | Yahoo Finance, Google News, AkShare, Finnhub |
| 存储 | SQLite (WAL 模式, 每策略隔离, FTS5 全文搜索) |
| 调度 | APScheduler |
| 类型 | Pydantic |
| 测试 | pytest |
| 打包 | uv (Python), npm (前端) |
