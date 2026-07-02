# Development Plan

> 配合 `PROGRESS.md` 阅读。本文档描述架构决策、数据策略、开发阶段和潜在问题。

## 核心设计原则

**数据从 0 到 1：** 我们的数据不是从 Wind/Alice 这种现成数据库查询，而是从公开源（YFinance、AkShare、Google News）一点一点爬取积累。数据治理是建设过程，不是查询过程。

**Agent 的角色界定（修正）：**
- Agent **不应** 拉取原始行情数据（那是 DataService + Provider 的工作）
- Agent **应该** 用于需要"理解"和"判断"的任务：
  - 判断行业/主题关系（比 GICS 机械分类更灵活）
  - 审阅历史对话 + watchlist，判断什么领域值得深入爬取
  - 新闻相关性判断（"这条政策对这个策略重要吗？"）
  - 格式化输出 + 报告生成 + 模拟盘决策
  - 任何难以用规则编码的语义判断

**自动化水平：** 放弃一问一答的简单模式。系统主动采集、主动发现、Agent 定期在后台执行判断和总结任务。

## Data Governance: Four Collection Tiers

数据从 0 到 1，分层建设：

```
Tier 1: 综合市场新闻（全局背景）
  └→ 定期爬取全局市场新闻，不限定 ticker
  └→ 来源：东财市场要闻、Google News business 板块
  └→ 频率：30 min
  └→ 用途：市场情绪基调、Daily Brief 生成、宏观事件感知

Tier 2: 热门股票信息（热度驱动）
  └→ 定期爬取成交额/换手率/涨跌幅 top N 的股票
  └→ 来源：AkShare 龙虎榜、YFinance most active
  └→ 频率：日级（收盘后）
  └→ 用途：发现新机会、补充覆盖面

Tier 3: Watchlist + 策略 ticker（用户意图驱动）
  └→ 针对用户明确关注的 ticker，深度采集
  └→ 来源：YFinance + AkShare 全维度
  └→ 频率：行情 15-30min / 新闻 30min / 基本面 daily
  └→ 用途：策略运行、watchlist 展示、用户决策支持

Tier 4: 智能发现（Agent + 算法驱动）   ← 核心创新点
  └→ 针对用户询问过的领域，自动发现相关话题和 ticker
  └→ 两种方案互补：

      Plan A: 推荐算法（快，便宜）
      ├─ 基于 ticker 关系图谱（行业分类 + 新闻共现 + 用户行为）
      ├─ 关键词 TF-IDF + 主题模型做新闻聚类
      ├─ 优点：即时、低成本、可批量
      └─ 缺点：无法理解语义（"新能源补贴" 和 "光伏政策" 是同主题但算法看不出）

      Plan B: Agent 定期审阅（慢，贵，但智能）
      ├─ 定期（每 4h / 每天）调用 Agent 审阅：
      │   ├─ 最近的历史对话 → 提取用户关注的主题
      │   ├─ 当前 watchlist → 判断覆盖缺口
      │   └─ 最新新闻标题 → 识别新兴事件
      ├─ Agent 输出：建议爬取的关键词、ticker、领域
      ├─ 优点：理解语义、能发现 "AI 芯片" "新能源补贴" 等新兴主题
      └─ 缺点：LLM 调用成本、延迟高

      推荐：Plan A 做初筛（批量、高频），Plan B 做精调（定期、定向）
```

## Data Architecture: Search + Recommendation Model

类比搜索引擎的"搜广推"体系：

```
┌── Mode A: Search（搜索 = Quick Ask）────────────────────┐
│                                                          │
│  触发：用户输入 ticker                                    │
│  行为：即时拉取全量数据（行情 + 新闻 + 基本面 + 指标）      │
│  深度：deep（所有可用维度）                                │
│  频率：on-demand（用户等待）                               │
│  优先级：最高（不能被阻塞）                                │
│  产出：Agent 分析结果 → TradingDecision                   │
│  副作用：数据写入 store，下次再问秒出                      │
│                                                          │
├── Mode B: Recommendation（推荐/订阅 = Watchlist + 自动发现）│
│                                                          │
│  Active Pool（主动维护）                                   │
│  ├─ 来源：策略 ticker 列表 + Watchlist                    │
│  ├─ 深度：full（全量数据）                                 │
│  ├─ 频率：行情 15-30min / 新闻 30min / 基本面 daily        │
│  └─ 优先级：medium                                        │
│                                                          │
│  Discovery Pool（自动发现）                                │
│  ├─ 来源：用户分析过某个领域 → 自动发现相关 ticker          │
│  ├─ 深度：light（行情 + 最近新闻，不含深度分析）           │
│  ├─ 频率：idle time（闲时填充）                            │
│  ├─ 触发条件：relation weight > 0.6                        │
│  └─ 优先级：low                                           │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Ticker Relation Graph（关系图谱）

```
AAPL ──[same_sector, w=0.9]──→ MSFT, GOOGL, NVDA, META, AMZN
AAPL ──[supply_chain, w=0.7]─→ QCOM, SWKS, TSMC, CRUS
AAPL ──[competitor, w=0.6]───→ 005930.KS (Samsung), 1810.HK (Xiaomi)
AAPL ──[co_mentioned, w=0.4]─→ INTC, AMD, SPY

关系权重 = static_classification * 0.5 + news_co_occurrence * 0.2 + user_grouping * 0.3

扩展阈值：
  weight >= 0.7 → 加入 Discovery Pool，拉取轻量数据
  weight >= 0.5 → 仅记录关系，不自动采集
  weight < 0.5  → 不记录
```

**关系来源：**
- GICS 行业分类（YFinance `sector`/`industry`）— 准确但静态，权重 0.5
- 新闻共现（同一篇文章提到多个 ticker）— 动态但有噪音，权重 0.2
- 用户行为（同一策略/watchlist 的 ticker 分组）— 反映用户意图，权重 0.3

**跨市场映射问题：**
- 美股用 GICS，A 股用申万行业分类
- 需要维护行业映射表或做自然语言匹配
- 例如："消费电子" ≈ "电子制造" ≈ "Consumer Electronics"

### Data Priority Queue

```
Priority 1（最高）：Demand Pool
  └→ 用户正在等待的 on-demand 请求
  └→ 不能被阻塞，优先使用缓存 + 并行拉取

Priority 2（中等）：Active Pool
  └→ 策略 + Watchlist ticker 的定时刷新
  └→ 按 staleness 排序（最过时的先刷新）

Priority 3（最低）：Discovery Pool
  └→ 关系图谱扩展发现的相关 ticker
  └→ 仅在其他任务空闲时执行
```

## Data Layer Design: Five Data Categories

### Layer A: 市场基础数据（所有策略共用）

| 字段 | 来源 | 频率 | 存储 |
|------|------|------|------|
| OHLCV 日线/周线/月线 | YFinance + AkShare(A股) | 15-30 min | market_data.db |
| 复权因子（前复权） | YFinance | daily | market_data.db |
| 成交量 / 成交额 | YFinance + AkShare | 15-30 min | market_data.db |
| 技术指标（MA, RSI, MACD, BB, ATR） | 计算（从 OHLCV） | on-demand | 计算缓存 |

### Layer B: 基本面数据（价值/质量策略）

| 字段 | 来源 | 频率 | 存储 |
|------|------|------|------|
| 估值：PE/PB/PS/EV_EBITDA（当前 + 历史分位） | YFinance snapshot | daily + on-demand | market_data.db |
| 盈利：EPS, ROE, 毛利率, 净利率 | YFinance | quarterly | market_data.db |
| 成长：营收增速, 利润增速（YoY, QoQ） | YFinance | quarterly | market_data.db |
| 质量：负债率, 现金流, 股息率 | YFinance + AkShare | quarterly | market_data.db |

### Layer C: 事件/新闻数据（事件驱动/情绪策略）

| 字段 | 来源 | 频率 | 存储 |
|------|------|------|------|
| 公司新闻：公告、财报、并购、人事 | AkShare 东财（国内）+ Google News（海外） | 30 min | market_data.db |
| 行业新闻：政策、竞争、技术 | 同上 | 30 min | market_data.db |
| 宏观新闻：央行、经济、地缘 | 同上 | 30 min | market_data.db |
| 情感评分：positive/negative/neutral + 强度 | keyword aggregation（sentiment provider） | per-fetch | market_data.db |
| 实体识别：新闻 -> 关联 ticker（多对多） | 正则 + 公司名称关键词表 | per-fetch | market_data.db |

### Layer D: 宏观/市场环境（所有策略的风险输入）

| 字段 | 来源 | 频率 | 存储 |
|------|------|------|------|
| 指数：SPY, QQQ, CSI300, 恒生 | YFinance | 15 min | market_data.db |
| 波动率：VIX, ATR | YFinance + 计算 | 15 min | market_data.db |
| 利率：Fed Funds, 国债 2Y/10Y | YFinance + FRED | daily | market_data.db |
| 外汇：USD/CNY, DXY | YFinance | daily | market_data.db |
| 经济日历：CPI, PMI, GDP, 就业 | Finnhub | daily @ 08:00 | market_data.db |

### Layer E: 行业/板块数据（相对强度、轮动）

| 字段 | 来源 | 频率 | 存储 |
|------|------|------|------|
| GICS 行业分类 | YFinance | weekly | market_data.db |
| 申万行业分类（A股） | AkShare | weekly | market_data.db |
| 行业 PE 中位数 | 计算 | weekly | market_data.db |
| 板块龙头对比 | YFinance | weekly | market_data.db |
| 跨市场行业映射表 | 维护 | as-needed | system.db |

## Development Phases

### Phase 1: Data Foundation

**目标：数据能自动流入系统，前端能直接查询**

| # | Task | Why | Dependencies |
|---|------|-----|-------------|
| 1.1 | 安装 APScheduler，激活 DataCollector 后台运行 | 数据不能只靠手动跑 CLI | 无 |
| 1.2 | 为 dataflow/store.py 写简洁的 Python 访问接口（MarketDataStore 已有完整实现，只需确认 API 干净） | 市场数据有 SQLite 但路由层需要 import | 无 |
| 1.3 | `GET /api/market/prices/:ticker` — 从 market_data.db 读行情 | 前端 watchlist、dashboard 需要价格数据 | 1.2 |
| 1.4 | `GET /api/market/news/:ticker` — 从 market_data.db 读新闻 | 前端展示最新新闻 | 1.2 |
| 1.5 | `GET /api/market/fundamentals/:ticker` — 从 market_data.db 读基本面 | 前端展示估值指标 | 1.2 |
| 1.6 | `GET /api/market/search?q=keyword` — FTS5 全文搜索新闻 | 用户搜索相关新闻 | 1.2 |

**验证：** `curl localhost:8000/api/market/prices/AAPL` 返回 80+ 条行情记录

### Phase 2: Strategy Storage & Management

**目标：策略能创建、持久化、查询，按钮可点击且有效果**

| # | Task | Why | Dependencies |
|---|------|-----|-------------|
| 2.1 | 重构 `system.db` strategies 表为结构化字段（tickers JSON array, beliefs JSON, agent_config JSON, schedule JSON） | 当前是单列 JSON blob，不支持按字段查询 | 无 |
| 2.2 | `GET /api/strategies` — 从 system.db 读真实策略列表 | 替换 mock | 2.1 |
| 2.3 | `POST /api/strategies` — 创建策略（含 validation） | 替换 mock | 2.1 |
| 2.4 | `GET /api/strategies/:id` — 返回完整策略配置 | 替换 mock | 2.1 |
| 2.5 | `PUT /api/strategies/:id` — 更新策略（partial update） | 替换 mock | 2.1 |
| 2.6 | `DELETE /api/strategies/:id` — 删除策略 + 关联数据 | 已部分实现，需修复 | 2.1 |
| 2.7 | `POST /api/strategies/:id/start` / `pause` / `stop` | 状态管理 | 2.1 |
| 2.8 | `GET /api/strategies/:id/performance` — 从 ContextStore 计算真实指标 | 替换 mock（当前返回硬编码 5.23%） | 2.1 |
| 2.9 | `GET /api/strategies/:id/decisions` — 修复 date filter bug | 已实现但 from/to 参数未传递到 store | 2.1 |

**验证：** 在 strategies 页面创建一个策略 → 刷新列表页 → 策略出现在列表中 → 点进去能看到详情

### Phase 3: Frontend Integration

**目标：前端 3 个核心页面（Dashboard, Strategies, Strategy Detail）接入真实 API**

| # | Task | Why | Dependencies |
|---|------|-----|-------------|
| 3.1 | Strategies List 页面：TanStack Query 替换 `MOCK_STRATEGIES` | 列表页目前完全用本地 mock | Phase 2 |
| 3.2 | Strategy Detail 页面：Tab-by-tab 接入 API | Details 页面用了 5 个本地 mock 对象 | Phase 2 |
| 3.3 | Dashboard 页面：聚合真实策略数据 + 行情摘要 | Dashboard 是空壳 | Phase 2 |
| 3.4 | Market Data 组件：行情表格 + 新闻列表（复用 market data API） | Watchlist 和 Detail 页面都需要 | Phase 1 |
| 3.5 | 按钮必须产生实际效果（Start/Stop/Delete/Clone/Edit） | 之前所有按钮都是装饰性的 | Phase 2 |

**验证：** 每个页面的按钮可点击，数据从后端加载，操作有实际效果，无 console error

### Phase 4: Agent + Memory Integration

| # | Task | Why | Dependencies |
|---|------|-----|-------------|
| 4.1 | orchestrator 调用 `MemoryStore.recall_by_context()` 注入 PM prompt | 记忆层目前完全不参与分析 | 无 |
| 4.2 | 分析结束后 `MemoryStore.remember()` 写入记忆 | 累积经验 | 4.1 |
| 4.3 | 策略执行：`POST /api/strategies/:id/run` 对该策略的 ticker 列表运行 pipeline | 策略需要有实际产出 | Phase 2 |

### Phase 5+: Advanced Features（每个独立完整实现，不完半成品）

| Module | Effort | Dependencies |
|--------|--------|-------------|
| Backtest engine + API | Large | Phase 4 |
| Scanner（rule + agent + belief 三种模式） | Large | Phase 4 |
| Risk Analytics（VaR/CVaR, stress test, correlation, concentration） | Medium | Phase 2 |
| HITL Approval（approval FSM + cross-review） | Large | Phase 4 |
| Knowledge Base + Hypotheses CRUD | Medium | Phase 2 |
| Watchlist CRUD | Medium | Phase 1 |
| Daily Insights（morning brief + midday update） | Medium | Phase 1 + 4 |
| Reports（stock deep dive + sector analysis） | Medium | Phase 4 |
| Conversations（save Quick Ask sessions） | Small | Phase 2 |
| Skills management | Medium | Phase 2 |
| MCP server + client | Medium | Phase 4 |
| Settings（persist to system.db） | Small | Phase 2 |
| Alpha Zoo factor library | Large | Phase 4 |

## Potential Problems & Mitigations

### Cold Start
- **问题：** 用户第一次查 ticker，market_data.db 无数据，需等待 3-5s 拉取
- **缓解：** Seeding 默认 ticker 列表（AAPL/MSFT/NVDA/GOOGL/AMZN/META/TSLA/SPY/QQQ + 热门 A 股），DataCollector 启动时预热

### API Rate Limiting
- **问题：** YFinance 限速 ~1 req/s，AkShare 更慢。多个用户/concurrent query 会撞墙
- **缓解：** Priority queue + client-side rate limiter + 交叉 provider 并行

### Cross-Market Sector Mapping
- **问题：** 美股 GICS vs A 股申万分类，无法直接对应
- **缓解：** 维护映射表，key 为归一化的行业名（中文），同时存储原始分类。逐步完善。

### News Dedup & Entity Resolution
- **问题：** 同一事件被多家媒体报道；同一篇新闻提到多个 ticker
- **缓解：** URL 去重（已实现）；标题相似度去重（待实现）；实体识别关联 ticker（正则 + 关键词表 + 待实现）

### Data Staleness
- **问题：** 用户看到的数据可能是 30 分钟前的；非活跃 ticker 数据更旧
- **缓解：** UI 显示 `last_updated` 时间戳；on-demand pull 触发即时刷新

### Frontend State Consistency
- **问题：** 创建策略后，列表页缓存可能不更新
- **缓解：** TanStack Query `invalidateQueries` 在 mutation 成功后触发

### Agent vs Direct Data
- **问题：** Agent 天然慢（30-60s）、黑盒、可能输出不可解析
- **缓解：** Agent 用于需要语义理解的环节（分析决策、关系判断、内容审阅）；数据展示全部走直接 API。Agent 从 DataService 读数据（不是自己通过网络获取）。关键：限制 Agent 必须调用什么工具、必须输出什么格式，提高确定性。

## Agent Orchestration Design

Agent 编排的核心原则：

### 确定性输出
- 每个 Agent 必须绑定特定工具（不能随意选择）
- 输出必须是 Pydantic schema，不能是自由文本
- 约束："你必须用 `get_price` 获取行情，用 `get_news` 获取新闻，输出必须符合 TradingDecision schema"

### 上下文管理
- 不同 Agent 有不同的上下文窗口：
  - 分析师 Agent：只看自己领域的数据（market agent 不看 news）
  - Debate Agent：只看上游所有 analyst reports
  - PM Agent：看 debate summary + risk report + memory
- 不把所有数据塞给所有 Agent
- Memory recall 的结果只在 PM 阶段注入

### Agent 可以替代硬编码逻辑的场景
- 行业关系判断：Agent 比 GICS 分类更灵活（"AI 芯片" 这个概念 GICS 里不存在）
- 新闻相关性：Agent 判断 "这条政策对策略 X 有没有影响"
- 爬取方向决策：Agent 审阅历史对话 → 建议新的爬取关键词和 ticker
- 策略信号解释：Agent 把技术指标信号翻译成自然语言解释

### Agent 不能替代的场景
- 数据获取：必须走 DataService（速度、可靠性、缓存）
- 数值计算：指标、VaR、回测收益（Python 直接算，不需要 LLM）
- 定时触发：APScheduler（不需要 Agent 决定什么时候跑）
- 简单的 CRUD：策略配置、watchlist 增删改查

### Database Migration
- **问题：** Schema 演进，SQLite ALTER TABLE 能力有限
- **缓解：** 每个 store 类负责自己的 schema init（CREATE TABLE IF NOT EXISTS）；migration 用备份 + 重建模式
