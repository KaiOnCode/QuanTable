# Agentic-Quant 功能差距与工作量评估

更新时间：2026-05-29

## 1. 与 proposal 目标的核心差距

### 已完成的模块

| 模块 | 状态 | 说明 |
|------|------|------|
| 5-agent 管道 (market/news/fundamentals → risk → PM) | ✅ | 已验证端到端可用（DeepSeek LLM） |
| 数据源 (YFinance, Google News, AkShare, Finnhub) | ✅ | Google News → AkShare 自动 fallback |
| 数据缓存 (pickle + SHA256) | ✅ | `dataflow/cache.py` |
| 数据采集调度 (APScheduler) | ✅ | `scheduler/` — 价格/新闻/情绪/宏观定期采集 |
| MarketDataStore (SQLite) | ✅ | OHLCV, 基本面, 新闻(FTS5), 新鲜度追踪 |
| ContextStore (SQLite) | ✅ | `storage/store.py` — 会话/报告/决策/事件持久化 |
| MemoryStore (SQLite) + OWM 评分 | ✅ | `memory/` — 5 层记忆, 5 因子评分 |
| Knowledge Base (文件) | ✅ | `knowledge/manager.py` — 规则/发现/失败 CRUD |
| Belief 数据模型 | ✅ | `belief/models.py` |
| FastAPI 后端 | ✅ | `server/` — /api/analyze SSE, /api/strategies, /api/settings 等 |
| React 前端 (14 页, 15 路由) | ✅ | `frontend/` — Next.js 16, shadcn/ui, TailwindCSS v4 |
| MCP BaseTool + ToolRegistry | ✅ | `mcp/base_tool.py` — 95 行, 零依赖 |
| MCP Client Manager | ✅ | `mcp/client.py` — stdio/SSE/streamableHttp |
| 76 个 SKILL.md | ✅ | `skills/` — 10 个类别, 来自 Vibe-Trading (MIT) |
| 文档体系 | ✅ | README, docs/README, architecture, data-models, spec, api-contracts, data-layer |

### 已实现但未接入核心管道的模块

| 模块 | 代码状态 | 缺失 |
|------|---------|------|
| MemoryStore | ✅ 已实现 | ❌ Orchestrator 未调用 recall/remember |
| ContextStore | ✅ 已实现 | ❌ 仅在 `/api/analyze` 中部分使用 |
| MarketDataStore | ✅ 已实现 | ❌ DataCollector 未使用新鲜度追踪 |
| 前端页面 (12/14) | ✅ 渲染正常 | ❌ 使用 mock 数据, 未接后端 API |

### 未开始的模块

| 模块 | 预估工时 | 说明 |
|------|---------|------|
| Orchestrator 扩展 (5→15 agents) | 60h | 6 并行分析师, Bull/Bear debate, 3-way risk debate |
| Debate Manager | 40h | 结构化辩论状态机 + Research Manager |
| HITL 审批 | 75h | 风险触发策略 + 审批状态机 + Cross-review |
| Broker Mock | 120h | 订单撮合, 账户账本, 绩效计算 |
| 通知系统 | 60h | Email, Telegram, WeChat, Feishu, Discord, Slack |
| MCP Server (fastmcp) | 20h | 暴露工具给外部 AI agent |
| Alpha Zoo 因子库集成 | 30h | 452 个预构建因子公式, IC/IR 计算 |
| Belief Contest 引擎 | 25h | 多信念竞争, 评分, 权重调整 |
| Weekly Reflection 生成器 | 15h | 行为漂移检测, 策略衰减诊断 |
| 前端接入后端 (12 页) | 40h | 替换 mock 数据, 接入真实 API |
| 回测管道 | 30h | 点对点历史数据 + 前向验证 |
| 端到端测试 | 40h | 模块单测 + 集成测试 + 回归基线 |

## 2. 工作量统计

| 类别 | 状态 | 预估工时 |
|------|------|---------|
| 已完成 | ✅ | ~ |
| 已实现但未接入 | ⚠️ | 30h |
| 未开始 | ❌ | 555h |
| **剩余合计** | | **~585h** |

## 3. 建议优先级

按价值/工时比排序：

1. **Memory/Context/Store 接入 orchestator** (30h) — 让已有代码真正工作
2. **前端接入后端 API** (40h) — 替换 mock 数据
3. **Orchestrator 扩展** (60h) — 15 agent 完整管道
4. **MCP Server** (20h) — 对外暴露工具
5. **回测管道** (30h) — 历史验证
6. **HITL 审批** (75h) — 人工把关
7. **Broker Mock** (120h) — 执行闭环
8. **通知系统** (60h) — 多通道触达
