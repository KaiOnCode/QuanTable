# Product Specification

## Pages Overview

```
/                          → Dashboard (home)
/strategies                → Strategy list + create
/strategies/:id            → Strategy detail
/quick-ask                 → Single/multi ticker analysis
/quick-ask/:conversationId → Saved conversation
/backtest                  → Backtest configuration + results
/memory-lab                → Strategy memory & learning dashboard
/insights                  → Daily investment suggestions
/approvals                 → HITL approval panel
/scanner                   → Market scanner
/watchlist                 → Watchlist management
/risk                      → Risk analytics
/reports                   → Research report generator
/settings                  → System configuration
```

---

## Page 1: Dashboard `/`

**Purpose**: Landing page. Overview of everything at a glance.

**Content**:
- **Header row**: Date, market status (open/closed), quick ticker search bar
- **Strategy leaderboard** (top 6 cards): Ranked by return %. Each card: strategy name, type badge (agent/quant/hitl), total return %, benchmark comparison (+3.2% vs SPY), mini sparkline, status indicator
- **Multi-line performance chart**: Equity curves of top 5 strategies overlaid **with benchmark line (SPY/CSI300)**, selectable time range (1w/1m/3m/all)
- **Today's market brief**: Collapsed card with morning insight summary. Click to expand full text.
- **Alert panel** (right sidebar or bottom): Recent triggered alerts — price alerts, agent flags, HITL pending count with red badge, **memory reflections ready for review**
- **Quick actions bar**: [New Strategy] [Quick Ask] [Run Backtest] [View Approvals] [Memory Lab]

**Empty state**: If no strategies exist, show onboarding cards: "Create your first strategy", "Try Quick Ask", "Explore the scanner".

---

## Page 2: Strategy List `/strategies`

**Content**:
- **Filter bar**: by type (agent/quant/hitl/all), by status (active/paused/stopped/all), by tag, search by name
- **Strategy table/cards**: Name, type, status, tickers, return %, **excess return vs benchmark**, created date, last run time
- **Action buttons per strategy**: Start/Pause/Stop, Edit, Clone, Delete (with confirmation)
- **[+ New Strategy] button** → opens strategy creation flow

**Strategy Creation Flow** (modal or new page):
1. **Basic info**: Name, description, tags
2. **Type selection**: Agent / Quant / HITL (with description of each)
3. **Ticker selection**: Multi-select from predefined groups + manual input
4. **Trading Beliefs** (for Agent/HITL):
   - Natural language belief editor: add one or more trading philosophies
   - Examples provided: "专注于短期事件驱动", "偏好低估值蓝筹"
   - Each belief spawns a Research Agent perspective
   - Belief weight configuration (initially equal, auto-adjusted by performance)
5. **Agent Configuration**:
   - Agent enable/disable toggles (checkboxes grouped by team):
     - Analysts: Market, News, Fundamentals, Sentiment, Technical, Macro
     - Researchers: Bull, Bear (debate rounds: 1-5)
     - Risk: Aggressive, Safe, Neutral (risk debate rounds: 1-5)
   - Custom prompt template (optional override)
   - Model selection (quick-think + deep-think), temperature
   - Cross-review toggle (2nd LLM reviews high-risk decisions)
6. **Quant Configuration** (for Quant type):
   - Select strategy from dropdown (MA Cross, RSI Reversal, TS Momentum, Vol Targeting, Risk Parity)
   - **Alpha Zoo factor selection**: browse 452 pre-built factors, select relevant ones
   - Parameter inputs
7. **Schedule**: Frequency (hourly/daily/weekly), execution time
8. **Memory & Learning**:
   - Memory enabled toggle
   - Weekly reflection toggle
   - Memory recall limit (max past decisions to inject per run)
9. **Review & Deploy**: Summary card → [Deploy Strategy]

---

## Page 3: Strategy Detail `/strategies/:id`

**Content**:
- **Header**: Strategy name, type badge, status badge, [Pause/Resume] [Edit] [Clone]
- **Performance tabs**:
  - **Overview**: Equity curve with **benchmark overlay** (SPY/CSI300), key metrics cards (total return, **excess return**, Sharpe, max drawdown, win rate, total trades), **benchmark comparison panel**
  - **Debate Viewer** (new): Visual timeline of agent debates. Each round shows:
    - Investment debate: Bull claim vs Bear claim side-by-side
    - Risk debate: 3-column layout (Aggressive / Safe / Neutral)
    - Token-level streaming replay available
    - Click agent card → expand full argument
  - **Holdings**: Current positions table (ticker, quantity, entry price, current price, PnL, weight %)
  - **Trade History**: Filterable table of all trades
  - **Decisions**: Timeline of agent decisions — each entry shows direction, confidence, winning belief, report excerpt. Click to expand full analysis including debate history and cross-review result.
  - **Memory Lab** (new): Strategy-specific memory view:
    - Recent memories (OWM-scored)
    - Weekly reflections timeline
    - Knowledge base (rules / findings / failures)
    - Active hypotheses and their status
  - **Approvals** (HITL only): Approval history log with cross-review details
  - **Audit Trail**: Event timeline with expandable nodes
- **Settings tab**: View/edit strategy configuration (same form as creation but pre-filled)

**Empty state (new strategy)**: "Waiting for first execution..." with next scheduled run time.

---

## Page 4: Quick Ask `/quick-ask`

**Content**:
- **Left sidebar**: Conversation history list (saved + recent). Each item: auto-generated title, date, tags. Search/filter.
- **Main area**:
  - **Input bar**: Ticker input + optional natural language question + date picker (default: today)
  - **Analysis mode selector**: Fast (market + news only) / Standard (all agents) / Deep (debate mode with cross-review)
  - **Agent toggle panel** (collapsible): Quick enable/disable individual agents for this analysis
  - **Belief selector** (optional): Pick which trading belief to apply for this analysis
  - **Progress display**: During analysis, show agent status cards with streaming progress:
    ```
    [company_overview] ✅ Complete (1.2s)
    [market_analyst]   ✅ Complete (3.2s)
    [news_analyst]     🔄 Fetching news...
    [fundamentals]     ⏳ Queued
    [sentiment]        ✅ Complete (2.1s)
    [technical]        ✅ Complete (1.8s)
    [macro]            ⏳ Queued
    ──────────────────────────────
    [bull_researcher]  🔄 Debate round 1/2...
    [bear_researcher]  🔄 Debate round 1/2...
    ──────────────────────────────
    [risk_analysts]    ⏳ Waiting for upstream
    ```
  - **Result display**: Decision card (direction, confidence, timeframe, one-line summary) → **debate visualization** (collapsible: bull vs bear arguments) → expandable full reports per agent → news sources with links
  - **Bottom actions**: [Save to History] [Add Tags] [New Follow-up Question] [Export PDF]
  - **Multi-ticker comparison**: "Compare AAPL vs MSFT" → side-by-side result cards
  - **Topic analysis**: Describe a sector/theme → system auto-discovers relevant tickers → batch analysis

---

## Page 5: Conversation `/quick-ask/:conversationId`

Same layout as Quick Ask but pre-loaded with saved conversation history. Supports follow-up questions that maintain context from previous analyses in the same conversation. Past debate records are preserved and viewable.

---

## Page 6: Backtest `/backtest`

**Content**:
- **Configuration panel** (left or top):
  - Strategy selector (existing + "ad-hoc parameters")
  - Ticker(s) selector
  - Date range (start/end with calendar picker)
  - Forward validation period (7/14/30/60/90 days)
  - **Benchmark selector**: SPY / CSI300 / custom ticker
  - [Run Backtest] button
- **Results panel**:
  - **Summary metrics**: Total predictions, accuracy %, cumulative return vs **benchmark**, excess return, information ratio, Sharpe ratio
  - **Timeline chart**: Each prediction plotted on price chart — green dot = correct, red dot = wrong, dot size = confidence. **Benchmark line overlaid.**
  - **Confusion matrix**: Predicted vs Actual direction (Bullish/Bearish/Neutral)
  - **Per-period breakdown table**: Date, ticker, predicted direction + confidence, actual direction + return, was correct?
  - **Export**: CSV of all results, PDF report
- **Parameter grid backtest**: Run same strategy on multiple tickers or multiple date ranges in parallel

---

## Page 7: Memory Lab `/memory-lab` (New)

**Purpose**: Central hub for strategy learning and knowledge accumulation. Inspired by TradeMemory Protocol + QuantGPT knowledge base.

**Content**:
- **Strategy selector**: Pick which strategy to view memory for
- **Memory Overview tab**:
  - OWM score distribution chart (histogram of memory quality)
  - Recent memories table: ticker, action, outcome, OWM score, date
  - Click memory → expand full record (all 5 layers)
  - Search memories by ticker, date range, outcome
- **Reflections tab**:
  - Weekly reflection timeline
  - Each reflection card: win rate, drawdown, behavioral diagnostics
  - Trend chart: win rate over time (strategy health monitor)
  - Strategy decay alerts
- **Knowledge Base tab** (from QuantGPT):
  - Rules (verified, must follow)
  - Findings (empirical discoveries)
  - Failures (falsified paths, avoid)
  - Add/edit/delete entries
  - Link entries to specific sessions/memories
- **Hypotheses tab**:
  - Active hypotheses with status badges
  - Evidence table per hypothesis
  - Create new hypothesis → define claim + acceptance criteria + budget
  - Resolve hypothesis (confirm/reject/stale)

---

## Page 8: Daily Insights `/insights`

**Content**:
- **Calendar view**: Monthly calendar with dots on days that have insights. Click a day → expand that day's morning/midday briefs.
- **Today's briefs**: Morning brief card + Midday update card (if available). Full text with key events listed.
- **Accuracy tracking**: For each past insight, show whether the directional call was correct. Overall accuracy % chart.
- **Channel status**: Show which notification channels are active (Email, Telegram, WeChat, Feishu, Discord, Slack)
- **Email preview**: Show what the email looks like (HTML preview)
- **Event alerts**: Chronological list of event-driven alerts

---

## Page 9: Approvals (HITL) `/approvals`

**Content**:
- **Pending queue**: Cards sorted by urgency. Each card:
  - Strategy name, ticker(s), decision summary, triggered rules, time remaining
  - **Cross-review badge**: shows whether 2nd LLM agreed or disagreed
  - [Approve] [Reject] [Modify]
- **Review detail** (click a card to expand):
  - Full context: all agent reports + **debate history** for this decision
  - Decision details: direction, position change, confidence
  - **Cross-review panel**: 2nd LLM's independent analysis + consensus/divergence indicator
  - Triggered rules (highlighted)
  - **Modify form**: Adjust target position %, override direction, add notes
- **History tab**: All past approvals, filterable

**Empty state**: "No pending approvals" with green checkmark.

---

## Page 10: Market Scanner `/scanner`

**Content**:
- **Mode toggle**: Rule-based / Agent-driven / **Belief-driven** (new)
- **Rule-based mode**:
  - Condition builder: [+ Add Condition] → field dropdown, operator, value
  - Saved queries list
  - Results table: ticker, current price, matched conditions, action links
- **Agent-driven mode**:
  - Natural language input
  - Agent reasoning display
  - Results with explanations
- **Belief-driven mode** (new):
  - Select a trading belief from existing strategies
  - System auto-generates scanner query matching that belief's philosophy
- **Export**: CSV download of results

---

## Page 11: Watchlist `/watchlist`

**Content**:
- **Multiple watchlists** (tabs): "My Positions", "AI Stocks", custom...
- **Per-watchlist**: Table (ticker, price, change %, RSI, MACD signal, news sentiment badge, alerts). Click ticker → Quick Ask popover.
- **Add ticker**: Search + add to list
- **Alert management**: Per-ticker alert configuration. Alert type + threshold.
- **Drag reorder**: Tickers

---

## Page 12: Risk Analytics `/risk`

**Content**:
- **Portfolio selector**: Pick a strategy to analyze
- **VaR/CVaR**: Value at Risk chart (histogram of historical returns with VaR line)
- **Stress test**:
  - Preset scenarios: "2008 Financial Crisis", "2020 COVID Crash", "2022 Rate Hikes"
  - Custom scenario: "Market drops X%, VIX spikes to Y"
  - Results: estimated portfolio impact
- **Correlation heatmap**: All holdings pairwise correlations
- **Sector concentration**: Pie chart of sector allocation
- **Drawdown chart**: Historical drawdown curve with peak-to-trough annotations

---

## Page 13: Reports `/reports`

**Content**:
- **Report type selector**: Stock Deep Dive / Sector Analysis
- **Stock Deep Dive**: Ticker input → Generate. Agent runs full analysis + extended research. 10-15 page PDF with charts, tables, analysis text.
- **Sector Analysis**: Sector/theme description → system discovers tickers → batch analysis → aggregated report
- **Report history**: Previously generated reports, click to re-download PDF
- **Report template**: Select sections to include (Technical, News, Fundamentals, Sentiment, Risk, Recommendation, **Debate Summary**)

---

## Page 14: Settings `/settings`

**Content**:
- **LLM Configuration**:
  - API key (masked), base URL, model selection
  - Quick-think model + Deep-think model (separate)
  - Test connection button
- **Agent Defaults**:
  - Default active agents (checkboxes)
  - Default debate rounds
  - Cross-review default (on/off)
- **Skill Management** (new):
  - List all skills (builtin + user-created)
  - Enable/disable skills
  - Create new skill: name, category, prompt template
  - Edit existing skill (user-created only, builtin are read-only)
  - Skill version history
- **MCP Integration** (new):
  - MCP Server status (running/stopped)
  - Transport mode (stdio/SSE/streamable-http)
  - External MCP servers list: add/remove/configure
  - Tool listing per server
- **Data Sources**:
  - Yahoo Finance status indicator
  - Google News status
  - AkShare status
  - Cache TTL setting
- **Notifications** (expanded):
  - Email: SMTP host, port, credentials, test button
  - Telegram: Bot token, chat IDs, test button
  - Enterprise WeChat: Webhook URL, test button
  - Feishu: Webhook URL, test button
  - Discord: Webhook URL, test button
  - Slack: Bot token, channel ID, test button
- **Memory & Learning**:
  - Memory retention period (days)
  - Weekly reflection schedule (day + time)
  - Clear memory (per strategy)
- **Scheduler**:
  - Global execution frequency limits
  - News fetch interval
- **Data Management**:
  - Export all data (JSON dump)
  - Clear cache
  - Delete strategy data
- **About**:
  - Version, team, licenses
  - Link to proposal PDF
