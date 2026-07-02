# Agent Terminal — 类 Claude Code 的金融 AI Agent

## 设计目标

一个全新的独立 Agent 界面，用户像使用 Claude Code 一样与 AI 对话。Agent 拥有大量工具，能自主决定调用什么、何时调用、如何组合。具备持久记忆、上下文压缩、技能系统、目标追踪、进度展示。

**不与现有 Quick Ask 混在一起**——这是全新的 `GET /agent` 页面和全新后端。

---

## 一、整体架构

```
┌──────────────────────────────────────────────────┐
│  /agent 页面 (全新 React 组件)                     │
│  ┌────────────────────────────────────────────┐  │
│  │ Chat Interface                             │  │
│  │ - 消息列表 (用户/Agent/工具调用/工具结果)      │  │
│  │ - 正在思考的动画 + 实时文字                   │  │
│  │ - 工具调用展开/折叠 (绿色勾/红色叉/蓝色转圈)    │  │
│  │ - 进度条 + 耗时                              │  │
│  │ - 输入框 + 停止按钮                          │  │
│  └────────────────────────────────────────────┘  │
│                      ↕ SSE                       │
│  ┌────────────────────────────────────────────┐  │
│  │ POST /api/agent/chat  (SSE streaming)       │  │
│  │   → AgentLoop.run(user_message, session_id) │  │
│  └────────────────────────────────────────────┘  │
│                      ↕                           │
│  ┌────────────────────────────────────────────┐  │
│  │ AgentLoop (agentgraph/react_loop.py)        │  │
│  │   while not done:                           │  │
│  │     think → act(tool_calls) → observe       │  │
│  │     → compress_if_needed                    │  │
│  │     → emit progress events                  │  │
│  │     → check_goals                           │  │
│  └────────────────────────────────────────────┘  │
│                      ↕                           │
│  ┌────────────────────────────────────────────┐  │
│  │ Tool Registry (agents/tools/)               │  │
│  │   60+ tools, auto-discovered, categorized   │  │
│  └────────────────────────────────────────────┘  │
│                      ↕                           │
│  ┌────────────────────────────────────────────┐  │
│  │ Memory / Skills / Goals / Trace             │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

---

## 二、AgentLoop — 核心循环

### 2.1 主循环伪代码

```python
class AgentLoop:
    def run(self, user_message: str, session_id: str, config: AgentConfig):
        # 1. 初始化
        memory = WorkspaceMemory(session_id)
        context = ContextBuilder(session_id, config)  # 含 Memory + Skills
        trace = TraceWriter(session_id)
        messages = context.build_initial_messages(user_message)
        iteration = 0

        # 2. ReAct 循环
        while iteration < config.max_iterations:
            iteration += 1

            # 2a. 上下文压缩 (如果需要)
            if estimate_tokens(messages) > COMPRESS_THRESHOLD:
                messages = self._compress(messages, memory)
                self._emit("compact", {"after_tokens": estimate_tokens(messages)})

            # 2b. 流式调用 LLM
            self._emit("thinking_start", {})
            thinking_chunks = []
            tool_calls = []

            for chunk in llm.stream_chat(messages, tools):
                if chunk.is_text():
                    thinking_chunks.append(chunk)
                    self._emit("thinking_delta", {"text": chunk})
                elif chunk.is_tool_call():
                    tool_calls.append(chunk)

            self._emit("thinking_end", {"text": join(thinking_chunks)})

            # 2c. 如果没有 tool_calls → 检查是否完成
            if not tool_calls:
                if self._is_final_answer(thinking_chunks):
                    self._emit("done", {"answer": join(thinking_chunks)})
                    break
                # 鼓励继续 → 注入延续提示
                messages.append({"role": "user", "content": CONTINUATION_PROMPT})
                continue

            # 2d. 执行工具 (并行只读, 串行写)
            results = self._execute_tools(tool_calls, memory, self._emit)

            # 2e. 将结果加入消息
            for tc, result in zip(tool_calls, results):
                messages.append(format_tool_result(tc, result))
                trace.write_tool_result(tc, result)
                memory.increment_counter(tc.name)

            # 2f. 检查 Goals (如果有活跃目标)
            self._check_active_goals(messages, results)

        # 3. 收尾
        memory.save()
        trace.close()
        self._store_session(session_id, messages, trace)
        return {"messages": messages, "trace": trace, "iterations": iteration}
```

### 2.2 工具执行策略

```python
def _execute_tools(self, tool_calls, memory, emit):
    """批量执行工具调用。只读并行,写串行。"""

    # 分组
    readonly = [tc for tc in tool_calls if TOOL_META[tc.name]["is_readonly"]]
    write = [tc for tc in tool_calls if not TOOL_META[tc.name]["is_readonly"]]

    results = []

    # 只读: 线程池并行
    if readonly:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(self._invoke, tc, emit): tc for tc in readonly}
            for f in as_completed(futures):
                results.append(f.result())

    # 写: 严格串行, 不超时杀死
    for tc in write:
        with HeartbeatTimer(tc.name, emit=emit):
            result = self._invoke(tc, emit)
            results.append(result)

    return results

def _invoke(self, tool_call, emit):
    """执行单个工具, 带超时控制"""
    tool_name = tool_call.name
    timeout = TOOL_META[tool_name].get("timeout", 60)

    try:
        if timeout:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(tool_registry.execute, tool_call)
                result = future.result(timeout=timeout)
        else:
            result = tool_registry.execute(tool_call)
        emit("tool_done", {"tool": tool_name, "status": "ok"})
        return result
    except TimeoutError:
        emit("tool_timeout", {"tool": tool_name})
        return '{"status":"error","error":"tool_timeout"}'
    except Exception as e:
        emit("tool_error", {"tool": tool_name, "error": str(e)})
        return f'{{"status":"error","error":"{str(e)}"}}'
```

### 2.3 上下文压缩

```python
def _compress(self, messages, memory):
    """五层压缩系统"""
    token_count = estimate_tokens(messages)

    # L1: 微压缩 (零成本, 每次迭代)
    messages = self._microcompact(messages)
    # 保留最近 3 条 tool_result, 更早的标记为 [cleared]

    token_count = estimate_tokens(messages)
    if token_count < COMPRESS_THRESHOLD:
        return messages

    # L2: 折叠大文本 (零成本)
    messages = self._collapse_large_texts(messages)
    # 文本 > 2000 字符 → 保留头 900 + 尾 500, 中间折叠

    token_count = estimate_tokens(messages)
    if token_count < COMPRESS_THRESHOLD:
        return messages

    # L3: LLM 压缩 (1 次 LLM 调用)
    # 备份完整 transcript
    self.trace.write_full_transcript(messages)

    # 尾部保护: 最近 20K tokens 不压缩
    tail = self._extract_tail(messages, token_budget=20000)
    head = messages[:-len(tail)]

    summary = llm.invoke(COMPRESS_PROMPT, head)
    # 修复 tool_call ↔ tool_result 配对
    compressed = self._fix_tool_pairs([summary] + tail)

    return compressed
```

---

## 三、工具系统

### 3.1 工具架构

```
agents/tools/
├── __init__.py           # ToolRegistry + build_registry()
├── registry.py           # 注册、发现、元数据
├── base.py               # BaseTool ABC
├── financial/            # 金融专用工具 (复用现有)
│   ├── prices.py         # get_price, get_indicators
│   ├── news.py           # get_news, search_news
│   ├── fundamentals.py   # get_fundamentals
│   ├── screening.py      # screen_market, rank_by_sector
│   ├── dragon_tiger.py   # get_dragon_tiger (龙虎榜)
│   ├── fund_flow.py      # get_fund_flow (资金流向)
│   ├── northbound.py     # get_northbound (北向资金)
│   └── options.py        # options_pricing, get_options_chain
├── research/             # 研究工具
│   ├── backtest.py       # run_backtest
│   ├── factor.py         # factor_analysis, alpha_bench
│   ├── hypothesis.py     # create_hypothesis, link_backtest
│   └── goal.py           # start_goal, add_evidence
├── data/                 # 数据工具
│   ├── search.py         # web_search, search_symbol
│   ├── read.py           # read_url, read_document
│   ├── sec.py            # get_sec_filings
│   └── macro.py          # get_macro_series (FRED)
├── workspace/            # 工作区工具
│   ├── files.py          # read_file, write_file, edit_file
│   ├── bash.py           # bash, background_run
│   └── skill.py          # load_skill, save_skill
├── trading/              # 交易工具 (未来)
│   ├── connector.py      # trading_connect, trading_account
│   └── order.py          # trading_place_order (需授权)
├── memory/               # 记忆工具
│   ├── remember.py       # remember, recall, forget
│   └── session.py        # session_search
└── swarm/                # Swarm 工具 (未来)
    └── run.py            # run_swarm, list_presets
```

### 3.2 工具元数据

每个工具必须提供：

```python
@dataclass
class ToolMeta:
    name: str
    description: str              # LLM 看到的描述
    is_readonly: bool = True      # 是否只读 (决定并行策略)
    timeout: int = 30             # 超时秒数 (只读工具有效)
    repeatable: bool = True       # 是否可重复调用
    category: str = ""            # 分类
    requires_auth: bool = False   # 是否需要认证
    cooldown_seconds: int = 0     # 冷却时间 (防止滥用)
    cost_estimate: str = "free"   # 成本估算
```

### 3.3 60+ 工具清单

**金融数据 (10)**
| 工具 | 来源 | 超时 |
|------|------|------|
| get_price | YFinance | 15s |
| get_indicators | YFinance | 15s |
| get_fundamentals | YFinance | 20s |
| get_news | DataService | 20s |
| search_news | FTS5 | 5s |
| get_macro_series | FRED | 15s |
| get_sec_filings | SEC EDGAR | 20s |
| get_dragon_tiger | AKShare | 15s |
| get_fund_flow | AKShare | 15s |
| get_northbound | AKShare | 15s |
| get_margin_trading | AKShare | 15s |
| get_block_trades | AKShare | 15s |

**研究分析 (8)**
| 工具 | 来源 | 超时 |
|------|------|------|
| run_analysis | LangGraph Pipeline | 120s |
| run_backtest | Backtest Engine | 300s |
| factor_analysis | Factor Zoo | 60s |
| generate_brief | Morning Brief | 120s |
| run_monitor | Monitor Engine | 60s |
| screen_market | EastMoney | 15s |
| search_symbol | EastMoney/Yahoo | 10s |
| options_pricing | Black-Scholes | 5s |

**网络搜索 (4)**
| 工具 | 来源 | 超时 |
|------|------|------|
| web_search | Bing/Google | 15s |
| web_fetch | Jina Reader | 20s |
| get_stock_news | Yahoo/Bing | 15s |
| search_sec | SEC EDGAR | 15s |

**工作区 (6)**
| 工具 | 来源 | 超时 |
|------|------|------|
| read_file | 本地 | 5s |
| write_file | 本地 | 5s |
| edit_file | 本地 | 5s |
| bash | Shell | 60s |
| background_run | Shell | 不限 |
| check_background | 本地 | 5s |

**技能与记忆 (8)**
| 工具 | 来源 | 超时 |
|------|------|------|
| load_skill | SkillsLoader | 3s |
| save_skill | SkillsLoader | 3s |
| remember | MemoryStore | 3s |
| recall | MemoryStore | 3s |
| forget | MemoryStore | 3s |
| list_sessions | SessionStore | 3s |
| session_search | FTS5 | 5s |
| compact | AgentLoop | 1s |

**目标与研究 (6)**
| 工具 | 来源 | 超时 |
|------|------|------|
| start_goal | GoalManager | 3s |
| add_evidence | GoalManager | 3s |
| update_goal | GoalManager | 3s |
| create_hypothesis | HypothesisStore | 3s |
| link_backtest | HypothesisStore | 3s |
| search_hypotheses | HypothesisStore | 3s |

**可视化与报告 (4)**
| 工具 | 来源 | 超时 |
|------|------|------|
| render_chart | Matplotlib | 10s |
| generate_report | LLM | 30s |
| export_pdf | ReportLab | 15s |
| show_widget | HTML/Plotly | 5s |

**Watchlist/Portfolio (4)**
| 工具 | 来源 | 超时 |
|------|------|------|
| get_watchlist | ContextStore | 3s |
| add_to_watchlist | ContextStore | 3s |
| get_portfolio | ContextStore | 3s |
| get_positions | ContextStore | 3s |

**总计: 58+ 工具**

---

## 四、Memory 系统

### 4.1 三层记忆架构

```
Working Memory (运行时)
  ↓ 对话结束 → 持久化
Session Memory (SQLite, 当前会话)
  ↓ 会话结束 → 提取关键信息
Persistent Memory (SQLite + FTS5, 跨会话)
  ↓ 定期反思 → 提炼
Learned Patterns (规则/模式)
```

### 4.2 Working Memory (WorkspaceMemory)

```python
@dataclass
class WorkspaceMemory:
    session_id: str
    run_dir: Path               # 当前会话的工作目录
    counters: dict              # 工具调用计数
    artifacts: list             # 生成的制品列表
    active_goals: list[str]     # 活跃目标 ID
    focus_topics: list[str]     # 当前关注的主题
```

### 4.3 Persistent Memory

```sql
CREATE TABLE persistent_memory (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    tag TEXT NOT NULL,           -- 记忆标签
    content TEXT NOT NULL,       -- 记忆内容 (JSON)
    category TEXT,               -- market/strategy/lesson/fact
    importance REAL DEFAULT 0.5, -- 重要性 (0-1)
    times_recalled INTEGER DEFAULT 0,
    created_at TEXT,
    last_recalled_at TEXT
);

CREATE VIRTUAL TABLE memory_fts USING fts5(
    tag, content, category
);
```

### 4.4 记忆工具

```python
# remember: 存储记忆
remember(tag="TSLA_RSI_pattern", content={"pattern": "RSI<30_bounce",
    "conditions": "RSI(14)<30 + volume_spike>2x", "win_rate": 0.73})

# recall: 精确召回
recall(tag="TSLA_RSI_pattern")
# → {"pattern": "RSI<30_bounce", ...}

# find_relevant: FTS5 语义搜索
find_relevant("TSLA RSI oversold bounce pattern")
# → [matched_memories...]

# reflect: 基于历史决策结果优化
reflect(ticker="TSLA", decision_id="...")
# → 自动获取实际回报 → 更新 memory → 记录教训
```

### 4.5 自动召回机制

ContextBuilder 在每次对话开始时：

```python
def build_context(self, user_message):
    # 1. 召回相关记忆
    relevant = self.memory.find_relevant(user_message, limit=5)

    # 2. 召回同 ticker 的历史分析
    ticker_history = self.memory.find_by_tag(ticker, limit=3)

    # 3. 召回通用教训
    lessons = self.memory.find_by_category("lesson", limit=3)

    # 4. 注入系统提示
    memory_context = f"""
## Relevant Memories
{format_memories(relevant)}

## Past Analysis for {ticker}
{format_history(ticker_history)}

## Lessons Learned
{format_lessons(lessons)}
"""
    return memory_context
```

---

## 五、Skill 系统

### 5.1 SKILL.md 格式

```markdown
---
name: technical-analysis-breakout
description: 技术分析突破策略。识别关键支撑/阻力位的有效突破，给出入场/止损/目标位。
category: strategy
tools:
  - get_price
  - get_indicators
requires:
  - OHLCV 价格数据
  - RSI, MACD, 布林带指标
---

# 技术分析突破策略

## 入场条件
1. 价格突破 20 日布林带上轨（上破）或下轨（下破）
2. 突破当日成交量 > 20 日均量 × 1.5
3. RSI(14) 确认方向 (上破时 RSI>50, 下破时 RSI<50)

## 止损设置
- 上破入场：止损设在突破前 3 根 K 线最低价下方 1 ATR
- 下破入场：止损设在突破前 3 根 K 线最高价上方 1 ATR

## 目标位
- 第一目标：入场价 + 2 ATR
- 第二目标：入场价 + 4 ATR

## 失效条件
- 价格回到布林带内且成交量萎缩
- RSI 背离（价格新高但 RSI 未新高）
```

### 5.2 SkillsLoader

```python
class SkillsLoader:
    def __init__(self):
        self.bundled = {}      # 内置技能
        self.user = {}         # 用户技能 (覆盖同名内置)
        self._scan()

    def _scan(self):
        # 扫描 skills/bundled/*/SKILL.md
        # 扫描 skills/user/*/SKILL.md (用户技能优先)

    def get_descriptions(self) -> str:
        """返回所有技能的一行摘要，注入系统提示"""
        return "\n".join(f"- {s.name}: {s.description}" for s in self.all_skills())

    def get_content(self, name: str) -> str:
        """返回技能的完整文档（按需加载）"""
        skill = self.user.get(name) or self.bundled.get(name)
        return f"<skill name='{name}'>\n{skill.body}\n</skill>"

    def save_skill(self, name: str, content: str):
        """用户保存新技能到 skills/user/{name}/SKILL.md"""

    def delete_skill(self, name: str):
        """删除用户技能（不能删内置）"""
```

### 5.3 内置技能 (第一版 10 个)

| 技能 | 分类 | 说明 |
|------|------|------|
| technical-breakout | strategy | 技术突破策略 |
| mean-reversion | strategy | 均值回归策略 |
| value-investing | strategy | 价值投资框架 |
| fundamental-screening | analysis | 基本面筛选 |
| earnings-analysis | analysis | 财报分析模板 |
| risk-assessment | risk | 风险评估清单 |
| sector-rotation | macro | 板块轮动分析 |
| macro-event-analysis | macro | 宏观事件影响评估 |
| trade-journal | workflow | 交易日志分析流程 |
| deep-research | workflow | 深度研究框架 |

---

## 六、Goal 系统

### 6.1 ResearchGoal

```python
@dataclass
class ResearchGoal:
    id: str
    title: str                          # "评估 TSLA 在 Cybertruck 放量后的投资价值"
    hypothesis: str                     # "Cybertruck 月产量超 5000 将显著提升 TSLA 营收"
    status: str                         # active/paused/completed/failed
    priority: int = 5                   # 1-10
    evidence_for: list[Evidence]        # 支持证据
    evidence_against: list[Evidence]    # 反对证据
    sub_goals: list[str]                # 子目标 ID
    created_at: str
    deadline: str                       # 截止日期
    completed_at: str
    conclusion: str                     # 最终结论
    confidence: float                   # 0-1
```

### 6.2 GoalManager

```python
class GoalManager:
    def create_goal(title, hypothesis) → ResearchGoal
    def add_evidence(goal_id, evidence, direction) → None
    def update_status(goal_id, status) → None
    def get_active_goals() → list[ResearchGoal]
    def get_goal_tree(goal_id) → dict    # 目标 + 子目标树
    def evaluate_completion(goal_id) → bool  # 检查是否可标记完成
```

### 6.3 Autopilot 循环

```python
def autopilot_loop(goal: ResearchGoal):
    """Agent 自主驱动研究目标直到完成"""

    while goal.status == "active":
        # 1. 评估当前状态
        gap = assess_evidence_gap(goal)  # 还需要什么证据?

        # 2. 决定下一步
        if gap == "data":
            # 需要更多数据 → 搜索
            results = agent.search_and_collect(goal.hypothesis)
            goal.add_evidence(results)

        elif gap == "analysis":
            # 需要分析 → 运行 pipeline
            analysis = agent.run_analysis(goal.hypothesis)
            goal.add_evidence(analysis)

        elif gap == "validation":
            # 需要验证 → 回测
            backtest = agent.run_backtest(goal.hypothesis)
            goal.add_evidence(backtest)

        else:
            # 证据足够 → 生成结论
            goal.conclusion = agent.generate_conclusion(goal)
            goal.status = "completed"
            break

        # 3. 检查是否应该停止
        if goal.deadline_passed() or goal.confidence > 0.8:
            break

    return goal
```

---

## 七、前端设计

### 7.1 /agent 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Terminal                                    [⚙] [×] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 用户: 帮我深度研究 TSLA，评估 Q3 投资价值              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Agent: 🔵 正在思考...                                │   │
│  │                                                        │   │
│  │ 我会从多个角度分析 TSLA。首先获取技术面数据。          │   │
│  │                                                        │   │
│  │ ▸ get_indicators("TSLA")                               │   │
│  │   ✅ 完成 (2.3s)                                       │   │
│  │   RSI(14)=42.3, MACD=bearish, SMA20=$246.50...        │   │
│  │                                                        │   │
│  │ 技术面偏弱。接下来查看基本面和新闻。                    │   │
│  │                                                        │   │
│  │ ▸ get_fundamentals("TSLA")                             │   │
│  │   🔵 运行中...                                         │   │
│  │ ▸ get_news("TSLA", days=30)                            │   │
│  │   ⏳ 等待中...                                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Agent: ✅ 分析完成                                    │   │
│  │                                                        │   │
│  │ ## TSLA Q3 投资评估                                   │   │
│  │                                                        │   │
│  │ ### 技术面 (偏空)                                      │   │
│  │ RSI 处于弱势区间，MACD 死叉未修复...                    │   │
│  │                                                        │   │
│  │ ### 基本面 (中性偏多)                                  │   │
│  │ PE 估值回落至合理区间，Cybertruck 产量爬坡...          │   │
│  │                                                        │   │
│  │ ### 综合建议                                           │   │
│  │ 短期观望，等待技术面确认反转信号后介入...              │   │
│  │                                                        │   │
│  │ 📊 使用了 8 个工具  ⏱ 47.3s  🔗 24 条新闻             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  [输入框: 追问...                                  ] [发送] │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 SSE 事件类型

| 事件 | 载荷 | 前端效果 |
|------|------|---------|
| `thinking_start` | `{}` | 显示 "正在思考..." |
| `thinking_delta` | `{text}` | 实时显示 LLM 输出文字 |
| `thinking_end` | `{full_text}` | 完成思考阶段 |
| `tool_call` | `{tool, args}` | 显示工具调用卡片 (蓝色转圈) |
| `tool_progress` | `{tool, stage, current, total}` | 更新进度条 |
| `tool_heartbeat` | `{tool, elapsed_s}` | 更新耗时 |
| `tool_result` | `{tool, status, preview}` | 绿色勾/红色叉, 展开详情 |
| `tool_error` | `{tool, error}` | 红色, 显示错误 |
| `compact` | `{before, after}` | 静默 (不显示给用户) |
| `goal_update` | `{goal_id, status}` | 更新目标状态 |
| `answer` | `{text}` | 最终答案 |
| `error` | `{message}` | 全局错误 |
| `done` | `{session_id, stats}` | 完成, 显示统计 |

---

## 八、实现路线图

### Phase 1: 基础架构 (核心循环 + 工具 + 前端)

目标：能用。一个可以对话的 Agent, 拥有基本工具, 能自主决定调用什么。

- [ ] `agentgraph/react_loop.py` — ReAct 循环引擎
- [ ] `agentgraph/tools/registry.py` — 工具注册表 (自动发现 + 元数据)
- [ ] `agentgraph/tools/base.py` — BaseTool ABC
- [ ] `agentgraph/progress.py` — HeartbeatTimer + ProgressEvent
- [ ] `agentgraph/trace.py` — JSONL 轨迹记录
- [ ] `agentgraph/context_compression.py` — L1+L2 压缩
- [ ] `server/routes/agent.py` — SSE 端点
- [ ] `frontend/app/agent/page.tsx` — Agent Terminal 界面
- [ ] 20 个核心工具 (prices, news, search, files, memory)

### Phase 2: Memory (记忆系统)

目标：Agent 能记住过去的对话, 自动召回相关信息。

- [ ] `memory/persistent.py` — FTS5 持久化记忆
- [ ] `memory/models.py` — 扩展 MemoryRecord
- [ ] ContextBuilder 自动召回
- [ ] 延迟反思 (outcome tracking)
- [ ] remember/recall/forget 工具

### Phase 3: Skills (技能系统)

目标：Agent 有一套可复用的分析框架。

- [ ] `skills/loader.py` — SkillsLoader
- [ ] 10 个内置技能
- [ ] load_skill/save_skill/delete_skill 工具
- [ ] 用户自定义技能目录

### Phase 4: Goals (目标系统)

目标：Agent 能管理复杂的研究项目。

- [ ] `agentgraph/goals.py` — ResearchGoal + GoalManager
- [ ] Autopilot 循环
- [ ] Goal 可视化 (前端)

### Phase 5: 自优化

目标：Agent 从历史决策中学习, 持续提升。

- [ ] 决策追踪
- [ ] 结果回验
- [ ] 策略提炼

---

## 九、文件清单

| 文件 | 动作 | 说明 |
|------|------|------|
| `agentgraph/react_loop.py` | NEW | ReAct 循环核心 (300+ 行) |
| `agentgraph/context_compression.py` | NEW | L1+L2+L3 压缩 (200+ 行) |
| `agentgraph/progress.py` | NEW | HeartbeatTimer (100+ 行) |
| `agentgraph/trace.py` | NEW | JSONL 轨迹 (200+ 行) |
| `agentgraph/goals.py` | NEW | GoalManager (200+ 行) |
| `agentgraph/tools/__init__.py` | NEW | 工具注册表导出 |
| `agentgraph/tools/registry.py` | NEW | ToolRegistry (100+ 行) |
| `agentgraph/tools/base.py` | NEW | BaseTool ABC (80+ 行) |
| `agentgraph/tools/financial/*.py` | NEW | 金融工具 (~12 个) |
| `agentgraph/tools/research/*.py` | NEW | 研究工具 (~8 个) |
| `agentgraph/tools/data/*.py` | NEW | 数据工具 (~6 个) |
| `agentgraph/tools/workspace/*.py` | NEW | 工作区工具 (~5 个) |
| `agentgraph/tools/memory/*.py` | NEW | 记忆工具 (~4 个) |
| `memory/persistent.py` | NEW | FTS5 持久化记忆 (150+ 行) |
| `memory/models.py` | MODIFY | 扩展字段 |
| `skills/loader.py` | NEW | SkillsLoader (150+ 行) |
| `skills/bundled/*/SKILL.md` | NEW | 10 个内置技能 |
| `server/routes/agent.py` | NEW | SSE 端点 (200+ 行) |
| `server/main.py` | MODIFY | 注册 agent router |
| `frontend/app/agent/page.tsx` | NEW | Agent Terminal (500+ 行) |
| `frontend/components/agent/*.tsx` | NEW | ChatMessage, ToolCall, 等 |

## 十、验证

```bash
# 1. 基本对话
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"message":"分析 AAPL 最近一周的走势","session_id":"test-1"}'

# 2. 多步推理
curl ... -d '{"message":"帮我研究一下 NVDA 的供应链,看看有没有投资机会"}'

# 3. Memory
curl http://localhost:8000/api/agent/memories?session_id=test-1

# 4. Skills
curl http://localhost:8000/api/agent/skills

# 5. UI
open http://localhost:3000/agent
npm run build  # must pass
```
