# Reusable Assets Catalog

This document catalogs specific code, patterns, formats, and structures from reference projects that can be directly incorporated into Agentic-Quant. Each entry specifies the source project, license, what to reuse, and where to put it.

---

## 1. Skill System (from Vibe-Trading)

**Source**: [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) — MIT License
**Reuse**: SKILL.md file format + auto-discovery loader pattern
**Target**: `skills/` directory

### SKILL.md Template Format

Every skill follows this structure. We adopt this format for all agent capabilities:

```markdown
---
name: technical-analysis
version: 1.0
category: analysis
description: Technical analysis using price data and indicators
tools: [get_prices, get_indicators]
model: deepseek-chat
temperature: 0.0
---

# Technical Analysis Skill

## Input
- Ticker symbol
- Lookback period (default: 90 days)
- Current position percentage

## Workflow
1. Fetch price data via `get_prices`
2. Calculate technical indicators via `get_indicators` (RSI, MACD, SMA, Bollinger)
3. Analyze trend, momentum, support/resistance levels
4. Output structured report

## Output Format
- 趋势判断: [上涨/下跌/震荡]
- 关键支撑位: $XXX
- 关键阻力位: $XXX
- RSI(14): XX (超买/超卖/中性)
- MACD信号: [金叉/死叉/无信号]
- 风险评估: [低/中/高]
```

### Skill Loader Pattern

```python
# skills/loader.py
import yaml
import glob
from pathlib import Path

class SkillLoader:
    """Auto-discovers SKILL.md files at startup."""

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.skills: dict[str, Skill] = {}

    def discover(self) -> list[Skill]:
        """Scan skills/ directory for *.skill.md files."""
        for skill_file in self.skills_dir.rglob("*.skill.md"):
            skill = self._parse_skill(skill_file)
            self.skills[skill.name] = skill
        return list(self.skills.values())

    def _parse_skill(self, filepath: Path) -> Skill:
        """Parse YAML frontmatter + Markdown body."""
        content = filepath.read_text()
        # Split on --- fences
        parts = content.split("---")
        if len(parts) >= 3:
            frontmatter = yaml.safe_load(parts[1])
            body = "---".join(parts[2:]).strip()
        else:
            frontmatter = {}
            body = content
        return Skill(
            name=frontmatter.get("name", filepath.stem),
            version=frontmatter.get("version", "1.0"),
            category=frontmatter.get("category", "uncategorized"),
            tools=frontmatter.get("tools", []),
            model=frontmatter.get("model", "deepseek-chat"),
            temperature=frontmatter.get("temperature", 0.0),
            prompt_template=body,
            file_path=str(filepath),
        )
```

### Initial Skills to Create

These map directly to our current agent capabilities:

| Skill File | Category | Maps to Agent |
|-----------|----------|---------------|
| `skills/analysis/technical-analysis.skill.md` | analysis | market_analyst |
| `skills/analysis/fundamental-analysis.skill.md` | analysis | fundamentals_analyst |
| `skills/analysis/news-analysis.skill.md` | analysis | news_analyst |
| `skills/analysis/sentiment-analysis.skill.md` | analysis | sentiment_analyst |
| `skills/analysis/macro-analysis.skill.md` | analysis | macro_analyst |
| `skills/analysis/company-overview.skill.md` | analysis | company_overview |
| `skills/strategy/ma-cross.skill.md` | strategy | quant engine |
| `skills/strategy/rsi-reversal.skill.md` | strategy | quant engine |
| `skills/strategy/ts-momentum.skill.md` | strategy | quant engine |
| `skills/risk/var-cvar.skill.md` | risk | risk analyst |
| `skills/risk/stress-test.skill.md` | risk | risk analyst |
| `skills/research/stock-deep-dive.skill.md` | research | report generator |
| `skills/research/sector-analysis.skill.md` | research | report generator |

---

## 2. Alpha Zoo Formulas (from Vibe-Trading)

**Source**: [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) — formulas are mathematical content (not copyrightable), Qlib158 is Apache-2.0
**Reuse**: Factor expressions + categorization
**Target**: `quant/alpha_zoo/`

### Factor Categories to Implement

These 452 factors can be directly used. The mathematical expressions are public domain.

**GTJA 191 (most relevant for A-shares):**

```
# Momentum factors
gtja191_001: rank(ts_av_diff(close, 10))
gtja191_002: rank(ts_delta(close, 5))
gtja191_017: rank(ts_max(close, 20) / close)

# Reversal factors
gtja191_020: rank(close / ts_mean(close, 20))
gtja191_035: rank(ts_decay_linear(close / ts_mean(close, 20), 10))

# Volume factors
gtja191_010: rank(ts_corr(close, volume, 10))
gtja191_050: rank(volume / ts_mean(volume, 20))

# Volatility factors
gtja191_043: rank(ts_std(returns, 20))
gtja191_078: rank(ts_mean(high / low, 20))
```

**Alpha101 (Kakushadze 2015, arXiv:1601.00991):**

```
alpha001: rank(ts_argmax(signed_power(returns, 2), 5)) - 0.5
alpha002: rank(ts_corr(rank(volume), rank(close), 6))
alpha006: rank(open - ts_mean(open, 10)) * -1
alpha012: sign(delta(volume, 1)) * (-1 * delta(close, 1))
alpha049: rank(ts_max(high, 20) / close)
```

### Integration Code

```python
# quant/alpha_zoo/registry.py
from dataclasses import dataclass

@dataclass
class AlphaFactor:
    id: str              # e.g. "gtja191_001"
    zoo: str             # "qlib158" | "alpha101" | "gtja191" | "academic"
    name: str
    expression: str      # The formula
    theme: str           # "momentum" | "reversal" | "volume" | "volatility" | "value"
    source: str          # Attribution

class AlphaZoo:
    """Registry of 452 pre-built alpha factors."""

    def __init__(self):
        self.factors: dict[str, AlphaFactor] = {}
        self._load_all()

    def _load_all(self):
        """Load factors from JSON definitions."""
        # Load from quant/alpha_zoo/definitions/*.json
        pass

    def search(self, zoo: str = None, theme: str = None) -> list[AlphaFactor]:
        """Filter factors by zoo and/or theme."""
        pass

    def compute_signal(self, factor_id: str, prices: pd.DataFrame) -> pd.Series:
        """Compute the signal for a given factor on price data."""
        # Parse expression → compute → return series
        pass
```

---

## 3. Memory Layer (from TradeMemory Protocol)

**Source**: [mnemox-ai/tradememory-protocol](https://github.com/mnemox-ai/tradememory-protocol) — MIT License
**Reuse**: OWM 5-factor scoring algorithm, 5-layer memory structure design
**Target**: `memory/`

### OWM Scoring Function

The core algorithm from TradeMemory Protocol:

```python
# memory/owm.py
def compute_owm_score(
    outcome_quality: float,      # -1.0 to 1.0
    context_similarity: float,   # 0.0 to 1.0
    recency: float,              # 0.0 to 1.0 (exponential decay)
    confidence: float,           # 0.0 to 1.0
    affective_weight: float = 1.0,  # 1.0 = neutral
    weights: dict = None
) -> float:
    """
    Outcome-Weighted Memory score.

    Default weights (from TradeMemory):
    - outcome: 0.35
    - similarity: 0.25
    - recency: 0.20
    - confidence: 0.15
    - affective: 0.05
    """
    if weights is None:
        weights = {
            "outcome": 0.35,
            "similarity": 0.25,
            "recency": 0.20,
            "confidence": 0.15,
            "affective": 0.05,
        }

    score = (
        weights["outcome"] * outcome_quality +
        weights["similarity"] * context_similarity +
        weights["recency"] * recency +
        weights["confidence"] * confidence +
        weights["affective"] * affective_weight
    )
    return max(-1.0, min(1.0, score))


def compute_recency(timestamp: str, current_time: str, half_life_days: float = 30.0) -> float:
    """Exponential decay recency score."""
    from datetime import datetime
    t = datetime.fromisoformat(timestamp)
    now = datetime.fromisoformat(current_time)
    days_elapsed = (now - t).days
    return 2.0 ** (-days_elapsed / half_life_days)


def compute_context_similarity(
    current_context: dict,
    past_context: dict,
    feature_weights: dict = None
) -> float:
    """
    Cosine similarity between current and past market contexts.
    Features: sector, market_cap, vix_level, market_trend, ticker_match
    """
    # Ticker exact match gets a base score
    if current_context.get("ticker") == past_context.get("ticker"):
        base = 0.5
    else:
        base = 0.0

    # Compare other features
    feature_scores = []
    for feature in ["sector", "market_cap_bucket", "market_trend"]:
        if current_context.get(feature) == past_context.get(feature):
            feature_scores.append(1.0)
        else:
            feature_scores.append(0.0)

    if feature_scores:
        base += 0.5 * (sum(feature_scores) / len(feature_scores))

    return base
```

### Pre-Trade Safety Check

```python
# memory/safety.py
@dataclass
class SafetyCheck:
    passed: bool
    blocking_reasons: list[str]
    warnings: list[str]

def pre_trade_check(
    strategy_id: str,
    ticker: str,
    proposed_action: str,
    proposed_size_pct: float,
    memory_store: "MemoryStore",
    account: Account,
    config: StrategyConfig,
) -> SafetyCheck:
    """5-factor pre-trade gate before executing any trade."""
    blocking = []
    warnings = []

    # 1. Drawdown check
    if account.max_drawdown_pct > config.max_drawdown_pct:
        blocking.append(f"Max drawdown exceeded: {account.max_drawdown_pct}%")

    # 2. Losing streak check
    recent_trades = memory_store.get_recent_trades(strategy_id, limit=10)
    if recent_trades:
        recent_pnls = [t["pnl_pct"] for t in recent_trades[:5]]
        if all(p < 0 for p in recent_pnls):
            blocking.append(f"5 consecutive losses detected")

    # 3. Concentration check
    positions = account.get_positions()
    ticker_weight = positions.get(ticker, {}).get("weight_pct", 0)
    new_weight = ticker_weight + proposed_size_pct
    if new_weight > config.max_position_pct:
        blocking.append(f"Position size {new_weight}% exceeds max {config.max_position_pct}%")

    # 4. Confidence check
    # (done in HITL layer, but basic gate here)

    # 5. Memory check
    similar_memories = memory_store.recall(ticker, limit=3)
    recent_losses = [m for m in similar_memories if m.outcome_quality < 0]
    if len(recent_losses) >= 2:
        warnings.append(f"2+ recent losses for {ticker} in similar conditions")

    return SafetyCheck(
        passed=len(blocking) == 0,
        blocking_reasons=blocking,
        warnings=warnings,
    )
```

---

## 4. Belief System (from ContestTrade)

**Source**: [FinStep-AI/ContestTrade](https://github.com/FinStep-AI/ContestTrade) — Apache 2.0 License
**Reuse**: Belief configuration format, contest mechanism design
**Target**: `belief/`

### Belief JSON Format

```json
// belief/presets.json
{
  "presets": [
    {
      "id": "aggressive_event_driven",
      "text": "专注于短期事件驱动机会：优先关注公司公告、并购重组、订单暴增、技术突破等催化事件；偏好中小市值、高波动的题材股，适合激进套利策略。",
      "style": "aggressive",
      "tags": ["event-driven", "short-term", "small-cap"]
    },
    {
      "id": "conservative_value",
      "text": "专注于稳健的价值投资：关注低PE、高股息、稳定现金流、强护城河的蓝筹股；偏好长期持有，追求稳定复利。",
      "style": "conservative",
      "tags": ["value", "long-term", "large-cap"]
    },
    {
      "id": "momentum_growth",
      "text": "专注于成长动量：关注营收和利润高增长、行业景气度上升、机构持续加仓的标的；偏好中大盘成长股，持有周期1-4周。",
      "style": "aggressive",
      "tags": ["momentum", "growth", "mid-cap"]
    },
    {
      "id": "technical_reversal",
      "text": "专注于技术反转信号：寻找RSI超卖/超买、MACD金叉/死叉、布林带突破等技术信号；以技术面为主，基本面为辅，持有周期1-5天。",
      "style": "moderate",
      "tags": ["technical", "reversal", "swing-trading"]
    },
    {
      "id": "macro_sensitive",
      "text": "专注于宏观政策敏感型机会：关注货币政策转向、财政刺激、产业政策变化对相关板块的影响；结合利率、汇率、大宗商品走势进行配置。",
      "style": "moderate",
      "tags": ["macro", "policy", "sector-rotation"]
    }
  ]
}
```

### Belief Contest Engine

```python
# belief/contest.py
class BeliefContest:
    """
    Internal contest mechanism (from ContestTrade).

    Multiple Research Agents, each biased by a trading belief,
    independently analyze the same data and submit proposals.
    The contest scores each proposal and synthesizes the final decision.
    """

    def __init__(self, beliefs: list[TradingBelief], orchestrator):
        self.beliefs = beliefs
        self.orchestrator = orchestrator

    async def run_contest(
        self, state: AgentState
    ) -> tuple[list[dict], str]:
        """
        Run all belief-biased agents in parallel.
        Returns (scored_proposals, winning_belief_id).
        """
        proposals = []

        # Phase 1: Each belief spawns a Research Agent
        for belief in self.beliefs:
            proposal = await self._run_belief_agent(belief, state)
            proposals.append(proposal)

        # Phase 2: Score proposals
        scored = self._score_proposals(proposals, state)

        # Phase 3: Select winner or synthesize
        winner = max(scored, key=lambda p: p["score"])
        return scored, winner["belief_id"]

    async def _run_belief_agent(
        self, belief: TradingBelief, state: AgentState
    ) -> dict:
        """Run a single belief-biased analysis."""
        # Inject belief into agent's system prompt
        # Run analysis
        # Return proposal
        pass

    def _score_proposals(
        self, proposals: list[dict], state: AgentState
    ) -> list[dict]:
        """
        Score each proposal on:
        1. Internal consistency (does reasoning match conclusion?)
        2. Risk-reward ratio
        3. Alignment with market conditions
        4. Historical belief performance weight
        """
        for p in proposals:
            consistency = self._check_consistency(p)
            risk_reward = self._evaluate_risk_reward(p)
            market_alignment = self._check_market_alignment(p, state)
            historical_weight = p["belief"].weight

            p["score"] = (
                0.30 * consistency +
                0.25 * risk_reward +
                0.25 * market_alignment +
                0.20 * historical_weight
            )
        return proposals
```

---

## 5. Debate Architecture (from TradingAgents-MCPmode)

**Source**: [guangxiangdebizi/TradingAgents-MCPmode](https://github.com/guangxiangdebizi/TradingAgents-MCPmode) — Apache 2.0 License
**Reuse**: Dual debate structure (investment + risk), debate state machine
**Target**: `agentgraph/debate.py`

### Debate State Machine

```python
# agentgraph/debate.py
from enum import Enum
from dataclasses import dataclass, field

class DebatePhase(str, Enum):
    CLAIM = "claim"           # Initial argument
    EVIDENCE = "evidence"     # Supporting data
    REBUTTAL = "rebuttal"     # Counter-argument
    SYNTHESIS = "synthesis"   # Resolution

@dataclass
class DebateRound:
    round_num: int
    speaker: str
    role: str                 # "bull" | "bear" | "aggressive_risk" | etc.
    phase: DebatePhase
    claim: str
    evidence: list[str] = field(default_factory=list)
    rebuttal_to: str | None = None  # ID of claim being rebutted
    timestamp: str = ""

@dataclass
class DebateResult:
    debate_type: str          # "investment" | "risk"
    rounds: list[DebateRound]
    winner: str | None        # Which side prevailed
    resolution: str           # Final synthesis

class DebateManager:
    """Manages structured debates between agents."""

    def __init__(self, max_rounds: int = 2):
        self.max_rounds = max_rounds

    async def run_investment_debate(
        self, bull_agent, bear_agent, state: AgentState
    ) -> DebateResult:
        """
        Bull vs Bear structured debate.

        Round 1: Both make initial claims with evidence
        Round 2+: Rebut opponent's previous claim
        Final: Research Manager synthesizes
        """
        rounds = []

        for r in range(self.max_rounds):
            if r == 0:
                # Initial claims
                bull_round = await self._get_claim(bull_agent, state, "bull")
                bear_round = await self._get_claim(bear_agent, state, "bear")
            else:
                # Rebuttals
                prev_bull = rounds[-2] if len(rounds) >= 2 else rounds[0]
                prev_bear = rounds[-1] if len(rounds) >= 2 else rounds[0]
                bull_round = await self._get_rebuttal(bull_agent, state, prev_bear)
                bear_round = await self._get_rebuttal(bear_agent, state, prev_bull)

            rounds.extend([bull_round, bear_round])

        return DebateResult(
            debate_type="investment",
            rounds=rounds,
            winner=None,  # Determined by Research Manager
            resolution="",  # Filled by Research Manager
        )

    async def run_risk_debate(
        self, aggressive_agent, safe_agent, neutral_agent, state: AgentState
    ) -> DebateResult:
        """
        3-way risk debate: Aggressive vs Safe vs Neutral.
        Same structure but with 3 participants.
        """
        # Similar to investment debate but 3-way
        pass
```

---

## 6. Knowledge Base Structure (from QuantGPT)

**Source**: [Miasyster/QuantGPT](https://github.com/Miasyster/QuantGPT) — MIT License
**Reuse**: Directory structure, knowledge entry format
**Target**: `knowledge/`

### Directory Layout

```
data/{strategy_id}/knowledge/
├── rules.md       # Verified stable rules (must follow)
├── findings.md    # Empirical discoveries (reference)
└── failures.md    # Falsified paths (avoid repeating)
```

### Knowledge Entry Format

```markdown
## Rule: AAPL post-earnings rally
- **Type**: rule
- **Confidence**: 0.9
- **Source**: session_abc123, session_def456
- **Created**: 2024-03-15
- **Updated**: 2024-06-20

When AAPL reports earnings that beat consensus by >5%, the stock
rallies 3-5% within the next 5 trading days. Confirmed across 4
earnings cycles (Q1-Q4 2024).

### Evidence
- 2024-Q1: Beat by 7%, rallied 4.2% in 3 days (session_abc123)
- 2024-Q2: Beat by 6%, rallied 3.8% in 5 days (session_def456)
- 2024-Q3: Beat by 3%, rallied 1.1% in 5 days (session_ghi789) — weaker
- 2024-Q4: Beat by 8%, rallied 5.1% in 4 days (session_jkl012)
```

### Knowledge Manager

```python
# knowledge/manager.py
class KnowledgeManager:
    """Manages the structured knowledge base for a strategy."""

    def __init__(self, strategy_id: str, data_dir: str = "data"):
        self.kb_dir = Path(data_dir) / strategy_id / "knowledge"
        self.kb_dir.mkdir(parents=True, exist_ok=True)

    def add_rule(self, title: str, content: str, confidence: float, source: str):
        """Add a verified rule to rules.md."""
        entry = self._format_entry("Rule", title, content, confidence, source)
        self._append_to_file("rules.md", entry)

    def add_finding(self, title: str, content: str, confidence: float, source: str):
        """Add an empirical finding to findings.md."""
        entry = self._format_entry("Finding", title, content, confidence, source)
        self._append_to_file("findings.md", entry)

    def add_failure(self, title: str, content: str, source: str):
        """Record a falsified approach in failures.md."""
        entry = self._format_entry("Failure", title, content, 0.0, source)
        self._append_to_file("failures.md", entry)

    def get_context_for_agent(self, ticker: str = None) -> str:
        """Get relevant knowledge to inject into agent prompt."""
        context_parts = []

        # Always include rules
        rules = self._read_file("rules.md")
        if rules:
            context_parts.append("## 已验证规则 (必须遵守)\n" + rules)

        # Include relevant findings
        findings = self._read_file("findings.md")
        if findings and ticker:
            # Filter findings mentioning this ticker
            relevant = [f for f in findings.split("\n## ") if ticker in f]
            if relevant:
                context_parts.append("## 相关发现\n" + "\n## ".join(relevant))

        # Include recent failures to avoid
        failures = self._read_file("failures.md")
        if failures:
            context_parts.append("## 已证伪路径 (避免重复)\n" + failures[:500])

        return "\n\n".join(context_parts)
```

---

## 7. MCP Tool Definitions (from Vibe-Trading + TradeMemory)

**Source**: Multiple projects — design patterns, not code
**Reuse**: Tool naming convention, tool structure pattern
**Target**: `mcp/`

### MCP Server Setup

```python
# mcp/server.py
from mcp.server import Server, stdio_server
from mcp.types import Tool, TextContent

server = Server("agentic-quant")

# Tool definitions following Vibe-Trading's pattern
TOOLS = [
    Tool(
        name="analyze_ticker",
        description="Run full multi-agent analysis on a ticker",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "date": {"type": "string", "description": "Analysis date (ISO 8601)"},
                "mode": {
                    "type": "string",
                    "enum": ["fast", "standard", "deep"],
                    "description": "Analysis depth"
                },
                "beliefs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Trading beliefs to apply"
                }
            },
            "required": ["ticker"]
        }
    ),
    Tool(
        name="get_market_data",
        description="Get OHLCV prices and technical indicators for a ticker",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "lookback_days": {"type": "integer", "default": 90},
                "indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "RSI, MACD, SMA, BB, etc."
                }
            },
            "required": ["ticker"]
        }
    ),
    Tool(
        name="run_backtest",
        description="Backtest a strategy on historical data",
        inputSchema={
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}},
                "date_from": {"type": "string"},
                "date_to": {"type": "string"},
                "strategy_type": {"type": "string"},
                "strategy_params": {"type": "object"}
            },
            "required": ["tickers", "date_from", "date_to"]
        }
    ),
    Tool(
        name="scan_market",
        description="Scan market for tickers matching conditions",
        inputSchema={
            "type": "object",
            "properties": {
                "conditions": {"type": "array"},
                "universe": {"type": "string", "default": "sp500"},
                "mode": {"type": "string", "enum": ["rule", "agent", "belief"]}
            },
            "required": ["conditions"]
        }
    ),
    Tool(
        name="recall_memory",
        description="Search past trading decisions by context similarity",
        inputSchema={
            "type": "object",
            "properties": {
                "strategy_id": {"type": "string"},
                "ticker": {"type": "string"},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["strategy_id"]
        }
    ),
    Tool(
        name="generate_report",
        description="Generate a research report (PDF)",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "sections": {"type": "array", "items": {"type": "string"}},
                "format": {"type": "string", "enum": ["pdf", "md"]}
            },
            "required": ["ticker"]
        }
    ),
]
```

### MCP Client Config

```json
// ~/.agentic-quant/agent.json
{
  "mcpServers": {
    "financial-datasets": {
      "command": "uvx",
      "args": ["financial-datasets-mcp"],
      "enabledTools": ["get_income_statements", "get_balance_sheets", "get_historical_stock_prices"]
    },
    "tradememory": {
      "command": "uvx",
      "args": ["tradememory-protocol"],
      "enabledTools": ["*"]
    }
  }
}
```

---

## 8. Notification Multi-Channel Pattern (from Daily Stock Analysis)

**Source**: [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) — MIT License
**Reuse**: Multi-channel adapter pattern, message format
**Target**: `notification/`

### Channel Adapter Pattern

```python
# notification/channels.py
from abc import ABC, abstractmethod

class NotificationChannel(ABC):
    @abstractmethod
    async def send(self, message: str, title: str = "", priority: str = "normal") -> bool:
        pass

    @abstractmethod
    async def test(self) -> bool:
        pass

class EmailChannel(NotificationChannel):
    def __init__(self, host: str, port: int, user: str, password: str, recipients: list[str]):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.recipients = recipients

    async def send(self, message: str, title: str = "", priority: str = "normal") -> bool:
        import aiosmtplib
        # HTML email with formatted report
        html = self._format_html(title, message, priority)
        # ... SMTP send logic
        return True

class TelegramChannel(NotificationChannel):
    def __init__(self, bot_token: str, chat_ids: list[str]):
        self.bot_token = bot_token
        self.chat_ids = chat_ids

    async def send(self, message: str, title: str = "", priority: str = "normal") -> bool:
        import httpx
        for chat_id in self.chat_ids:
            # Telegram send message API
            pass
        return True

class WeChatWorkChannel(NotificationChannel):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, message: str, title: str = "", priority: str = "normal") -> bool:
        import httpx
        # WeChat Work bot webhook
        markdown_msg = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {title}\n{message}"
            }
        }
        # ... POST to webhook
        return True

class FeishuChannel(NotificationChannel):
    # Similar to WeChat Work, different JSON format
    pass

class DiscordChannel(NotificationChannel):
    # Discord webhook
    pass

class SlackChannel(NotificationChannel):
    # Slack bot API
    pass


class NotificationManager:
    """Multi-channel notification with fallback."""

    def __init__(self):
        self.channels: dict[str, NotificationChannel] = {}

    def register(self, name: str, channel: NotificationChannel):
        self.channels[name] = channel

    async def broadcast(self, message: str, title: str = "", priority: str = "normal",
                        channels: list[str] = None):
        """Send to all or specified channels."""
        targets = channels or list(self.channels.keys())
        results = {}
        for name in targets:
            if name in self.channels:
                results[name] = await self.channels[name].send(message, title, priority)
        return results

    async def send_alert(self, message: str, priority: str = "high"):
        """Time-sensitive alert — all channels."""
        return await self.broadcast(message, "⚠️ Alert", priority)

    async def send_daily_brief(self, message: str):
        """Daily brief — email + messaging channels."""
        return await self.broadcast(
            message, "Daily Market Brief",
            channels=["email", "telegram"]
        )

    async def send_approval_request(self, decision: dict):
        """HITL approval — urgent channels only."""
        return await self.broadcast(
            f"Approval needed: {decision['ticker']} {decision['action']}",
            "HITL Approval Required",
            priority="high",
            channels=["telegram", "wechat", "feishu"]
        )
```

---

## 9. Agent Enable/Disable Pattern (from TradingAgents-MCPmode)

**Source**: [guangxiangdebizi/TradingAgents-MCPmode](https://github.com/guangxiangdebizi/TradingAgents-MCPmode) — Apache 2.0
**Reuse**: Frontend toggle pattern, backend conditional execution
**Target**: `agentgraph/orchestrator.py` + frontend

### Backend Conditional Execution

```python
# agentgraph/orchestrator.py (pattern to adopt)
class IntelliFin_Assistant:
    def __init__(self, config: StrategyConfig):
        self.active_agents = config.active_agents
        self.graph = self._build_graph()

    def _should_run(self, agent_name: str) -> bool:
        """Check if agent is enabled in strategy config."""
        return agent_name in self.active_agents

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(AgentState)

        # Company overview (always runs if enabled)
        if self._should_run("company_overview"):
            builder.add_node("company_overview", self.company_overview_agent)

        # Parallel analysts — only add enabled ones
        parallel_agents = []
        for name in ["market", "news", "fundamentals", "sentiment", "technical", "macro"]:
            if self._should_run(name):
                builder.add_node(f"{name}_analyst", getattr(self, f"{name}_analyst"))
                parallel_agents.append(f"{name}_analyst")

        # Debate — only if both researchers are enabled
        if self._should_run("bull_researcher") and self._should_run("bear_researcher"):
            builder.add_node("bull_researcher", self.bull_researcher)
            builder.add_node("bear_researcher", self.bear_researcher)
            # ... debate edges
        elif self._should_run("bull_researcher"):
            # Single researcher (no debate)
            builder.add_node("bull_researcher", self.bull_researcher)
            # ... direct edge to research_manager
        # ... similar for other agents

        return builder.compile()
```

---

## 10. Direct Code Dependencies (pip installable)

These reference projects can be installed as Python packages and used directly:

| Package | Install | What it provides |
|---------|---------|-----------------|
| `vibe-trading-ai` | `pip install vibe-trading-ai` | MCP tools, backtest engine, Alpha Zoo |
| `tradememory-protocol` | `pip install tradememory-protocol` | OWM memory layer, 17 MCP tools |
| `financial-datasets-mcp` | `pip install financial-datasets-mcp` | Financial data via MCP |

**Integration pattern** (MCP client mode):
```json
// ~/.agentic-quant/agent.json
{
  "mcpServers": {
    "vibe-trading": {
      "command": "vibe-trading-mcp",
      "enabledTools": ["backtest", "factor_analysis", "get_market_data"]
    },
    "tradememory": {
      "command": "uvx",
      "args": ["tradememory-protocol"]
    }
  }
}
```

This allows Agentic-Quant's agents to call Vibe-Trading's backtest engine and TradeMemory's memory layer without implementing them from scratch.

---

## Summary: What to Add to the Project Now

### Immediate (create these files/directories)

```
skills/                              # Skill system
├── analysis/
│   ├── technical-analysis.skill.md
│   ├── fundamental-analysis.skill.md
│   ├── news-analysis.skill.md
│   ├── sentiment-analysis.skill.md
│   └── macro-analysis.skill.md
├── strategy/
│   ├── ma-cross.skill.md
│   └── rsi-reversal.skill.md
└── risk/
    ├── var-cvar.skill.md
    └── stress-test.skill.md

quant/alpha_zoo/                     # Alpha factor library
├── __init__.py
├── registry.py                      # Factor registry + search
├── definitions/
│   ├── qlib158.json                 # 154 factors
│   ├── alpha101.json                # 101 factors
│   ├── gtja191.json                 # 191 factors
│   └── academic.json                # 6 factors
└── bench_runner.py                  # IC + alive/reversed/dead

memory/                              # Memory layer
├── __init__.py
├── owm.py                           # OWM scoring algorithm
├── store.py                         # SQLite-backed memory store
├── safety.py                        # Pre-trade safety checks
└── reflection.py                    # Weekly reflection generator

belief/                              # Belief engine
├── __init__.py
├── contest.py                       # Belief contest mechanism
├── presets.json                     # Default belief presets
└── scoring.py                       # Proposal scoring logic

knowledge/                           # Knowledge base
├── __init__.py
└── manager.py                       # Knowledge entry CRUD + context injection

mcp/                                 # MCP integration
├── __init__.py
├── server.py                        # MCP server (expose tools)
└── client.py                        # MCP client (load external tools)
```

### Integration priority

1. **Skills first** — refactor existing agents to use SKILL.md format. This is low-risk and makes the system immediately more modular.
2. **Memory layer** — implement OWM scoring + SQLite store. Every decision gets recorded and recalled.
3. **Belief system** — replace fixed strategy types with natural language beliefs.
4. **Debate architecture** — add bull/bear debate rounds to the existing agent pipeline.
5. **Alpha Zoo** — load factor definitions for quant strategy use.
6. **MCP server** — expose tools to external agents.
7. **Knowledge base** — add when strategies have enough history to learn from.
