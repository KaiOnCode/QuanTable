# 开发进度记录

最后更新：2026-05-29 | 分支：`feat/frontend-foundation`

## 当前分支概览

```
feat/frontend-foundation (基于 main, 合并了 detailed-proposal)
├── 前端: React 15 页 + FastAPI + 数据层 + 76 skills
├── 3 个 SQLite store + MCP + scheduler
└── detailed-proposal 的 agent 重构 + uv 迁移 + proposal 文档
```

## 已验收通过的模块

| 模块 | 验证方式 | 状态 |
|------|---------|------|
| Agent 管道 CLI | `uv run python app.py AAPL` | ✅ LLM 正常调用, agent 产出分析 |
| Agent 管道 API | `POST /api/analyze` SSE 流 | ✅ 4 agent 进度 + result 返回 |
| LLM 连接 | DeepSeek chat/completions | ✅ 所有调用 HTTP 200 |
| 新闻数据源 | AkShare `stock_news_em()` (东方财富) | ✅ 可用, 无需 VPN |
| 数据 fallback | Google News → AkShare 自动切换 | ✅ |
| 前端 Quick Ask | `localhost:3000/quick-ask` | ✅ 输入 AAPL → Analyze → 等 30s → 出结果 |
| 前端构建 | `npm run build` | ✅ 17 routes, 0 errors |
| 后端导入 | 全部模块可导入 | ✅ 8 tools, 22 routes |
| MemoryStore | SQLite CRUD + OWM 评分 | ✅ 独立测试通过 |
| ContextStore | SQLite 会话/报告/决策 | ✅ 独立测试通过 |
| MarketDataStore | OHLCV/基本面/新闻/FTS5 | ✅ 独立测试通过 |
| Landing Page | `/` 首页 | ✅ Hero + Features + Reference |

## 已实现但未验证/未接入的模块

| 模块 | 状态 | 待办 |
|------|------|------|
| 前端页面 (12/14) | UI 渲染正常, mock 数据 | 需要接入后端 API |
| `/api/strategies` CRUD | 返回 mock 数据 | 接入 ContextStore 真实读写 |
| `/api/strategies/:id/memory` | 返回空 | 接入 MemoryStore 真实查询 |
| MemoryStore → Orchestrator | store 写好了 | orchestrator 没调 recall/remember |
| ContextStore → Orchestrator | store 写好了 | 只 `/api/analyze` 部分使用 |
| MarketDataStore | 通过 DataService 自动写入 | DataCollector 未用新鲜度追踪 |
| MCP Client | 框架搭好 | 未实际连接外部 MCP server |
| 76 SKILL.md | 文件到位 | 未通过 load_skill 工具在运行时加载 |
| DataCollector | 调度逻辑写好 | 未长时间运行验证 |

## 未开始的核心模块

见 `WORKLOAD_GAP_ANALYSIS.md`，关键项目：
- 15-agent 管道扩展 + Debate Manager
- HITL 审批 + Cross-review
- Broker Mock 引擎
- Multi-channel 通知系统
- Belief Contest 引擎
- Alpha Zoo 因子集成
- 前端接入后端 API（12 页）

## 队友测试指南

```bash
# 1. 克隆并切换分支
git clone https://github.com/KaiOnCode/COMP7705-Agent-Quant.git
cd COMP7705-Agent-Quant
git checkout feat/frontend-foundation

# 2. 配置 API key
cp properties.env.example properties.env  # 如果没有 example, 手动创建
# 编辑 properties.env:
#   OPENAI_API_KEY=sk-your-deepseek-key
#   OPENAI_MODEL=deepseek-chat
#   OPENAI_API_BASE=https://api.deepseek.com/v1

# 3. 后端
uv sync
uv run uvicorn server.main:app --host 0.0.0.0 --port 8000

# 4. 前端（另一个终端）
cd frontend
npm install
npm run dev

# 5. 测试
# 浏览器打开 http://localhost:3000
# 进入 /quick-ask → 输入 AAPL → Analyze
# F12 Console 观察是否有报错
```

## Git 分支策略

```
main ←── feat/frontend-foundation (当前, 待队友验证后合入)
  ↑
  ├── feat/strategy-crud        ← 下一优先级
  ├── feat/memory-integration
  ├── feat/agent-expansion
  ├── feat/hitl-approval
  └── feat/broker-engine
```
