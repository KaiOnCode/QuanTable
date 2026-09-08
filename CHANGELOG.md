# Changelog

All notable changes to QuanTable are documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-08-01

Initial public release.

### Added

- **Custom ReAct Harness** (`agent/`): 25-iteration loop with streaming tool execution, 5-layer context compression, automatic error recovery state machine, and 7-section prompt engineering.
- **LangGraph Pipeline** (`quick_ask/`): 12-agent TradingAgents-style pipeline with 4 sequential analysts, bull/bear debate, trader proposal, 3-way risk discussion, and PM final decision. Three depth modes (fast/standard/deep).
- **Data Ingestion**: Yahoo Finance, Google News RSS, AkShare, and Finnhub with multi-provider fallback and cache-first strategy.
- **Data Cache**: SQLite MarketDataStore with SHA256 integrity verification.
- **News Aggregation**: Multi-source merging from Yahoo Finance and Google News RSS with category-based deduplication.
- **Sentiment Analysis**: Keyword-based news sentiment aggregation with 16 bullish and 16 bearish terms.
- **14 Agent Tools**: Price data, technical indicators, fundamentals, balance sheet, cash flow, income statement, market snapshot, news, global news, macro indicators, sentiment, sector context, web search, symbol search.
- **React Frontend**: 16-page Next.js 16 application with shadcn/ui and TailwindCSS v4.
- **Memory Layer**: OWM 5-factor scoring, SQLite persistence, pre-trade safety checks.
- **ContextStore**: SQLite persistence with per-strategy database isolation.
- **Data Collector**: APScheduler-based periodic fetching for prices, news, sentiment, and macro data.
- **76 Skills**: 10 categories of SKILL.md documents for agent analysis methodology.
- **Bash/Shell Tools**: read_file, write_file, glob, bash (gated).
- **Knowledge Base**: Rules, findings, and failures CRUD operations.
- **Belief System**: Trading belief models and presets.
- **MCP Integration**: BaseTool, ToolRegistry, and MCPClientManager.
- **HITL Approval**: Rule-triggered approval state machine for high-risk decisions.
- **Backtest Engine**: MockBrokerEngine with next-open execution and hash-verified reproducibility.
- **Risk Analytics**: VaR, CVaR, correlation matrix, stress testing.
- **Stock Scanner**: Deterministic stock scanning with rule, agent, and belief modes.
- **PDF Reporting**: fpdf2 + Jinja2 templates with Chinese font support.
- **Multi-channel Notifications**: Email, Telegram, WeChat, WhatsApp.
- **Morning Brief**: Daily market intelligence report from 50+ news categories and 25 market tickers.
