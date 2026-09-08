<p align="center">
  <a href="https://github.com/KaiOnCode/QuanTable">
    <img src="https://img.shields.io/badge/version-0.1.0-blue?style=flat-square" alt="Version" />
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License" />
  </a>
  <img src="https://img.shields.io/badge/python-3.12-blueviolet?style=flat-square" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/LangGraph-StateGraph-orange?style=flat-square" alt="LangGraph" />
  <img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Next.js-Frontend-black?style=flat-square" alt="Next.js" />
</p>

<p align="center">
  <a href="README.md">English</a> | <b>简体中文</b>
</p>

<h1 align="center">QuanTable</h1>

<p align="center">
  AI 驱动的量化研究工作台<br/>
  多智能体辩论、金融分析与投资推理 -- 一站式完成
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> &middot;
  <a href="#系统架构">架构</a> &middot;
  <a href="#功能特性">功能</a> &middot;
  <a href="#文档">文档</a> &middot;
  <a href="#参与贡献">贡献</a>
</p>

---

## 项目简介

QuanTable 是一个研究工作台，多个 LLM 智能体协作分析股票并产出投资决策。与单模型直接给出买卖建议不同，本系统编排了一场结构化的辩论：分析师提供数据证据，多头与空头研究员进行正反对弈，风险委员会评估下行场景，最终由投资组合经理做出决定。

系统内置两条智能体流水线，共享同一套数据层和工具基础设施。自建的 ReAct 引擎处理单股深度分析，支持流式执行和自动错误恢复。基于 LangGraph 的 12 智能体流水线在四个分析阶段中进行多智能体辩论，提供三种深度模式。

你可以把它想象成一个工作台：输入一个股票代码，工作台就会自动组建分析师团队、发起辩论、完成风险审查，最终给出投资结论。

本项目为香港大学 COMP7705 毕业设计作品。

---

## 系统架构

```
                           React 前端 (16 个页面)
                          / Agent | Quick Ask | Backtest \
                                       |
                                  REST + SSE
                                       |
                            +----------+----------+
                            |    FastAPI 服务器    |
                            +----------+----------+
                                       |
            +--------------------------+--------------------------+
            |                                                     |
   自建 ReAct 引擎 (agent/)              LangGraph 流水线 (quick_ask/)
   +---------------------------+             +---------------------------+
   | 25 轮迭代循环              |             | 阶段 1: 4 位分析师        |
   | 流式工具执行               |             | 阶段 2: 多空辩论          |
   | 5 层上下文压缩             |             | 阶段 3: 交易员            |
   | 自动错误恢复               |             | 阶段 4: 三方风险讨论      |
   | 21+ 金融工具               |             | 阶段 5: 投资经理决策      |
   +---------------------------+             +---------------------------+
            |                                                     |
            +-------------------- 共享基础设施 --------------------+
                 dataflow / memory / storage / scheduler / skills
```

### 智能体流水线（12 个智能体，3 种深度模式）

```
阶段 1: 市场 -> 情绪 -> 新闻 -> 基本面
        (顺序执行，独立工具循环)

阶段 2: 多头研究员 <-> 空头研究员 (多轮辩论)
        -> 研究主管 (投资计划)

阶段 3: 交易员 (交易方案)

阶段 4: 激进 <-> 保守 <-> 中性风险 (多轮讨论)
        -> 风险分析师 (风险报告)

阶段 5: 投资组合经理 (最终 买入/持有/卖出)
```

三种深度模式控制辩论强度：

| 模式 | 辩论轮数 | 风险讨论 | 典型耗时 |
|------|:---:|:---:|:---:|
| 快速 | 1 | 单次通过 | ~30 秒 |
| 标准 | 2 | 2 轮 | ~60 秒 |
| 深度 | 3 | 3 轮 | ~120 秒 |

---

## 功能特性

**智能体终端** -- 交互式 ReAct 分析，配备 21+ 金融工具：价格数据、技术指标、基本面、资产负债表、现金流、新闻、情绪、行业背景、网络搜索等。支持流式输出，工具调用失败时自动恢复。

**Quick Ask** -- 一键结构化分析，通过 12 智能体 LangGraph 流水线执行。选择快速、标准或深度模式来控制分析深度和辩论强度。

**数据工作台** -- 多源数据采集，覆盖 Yahoo Finance、Google News RSS、AkShare、Finnhub，支持数据源自动回退。SQLite 缓存带 SHA256 完整性校验。APScheduler 定时采集价格、新闻、情绪和宏观数据。

**记忆系统** -- 跨会话持久化记忆，OWM 五因子评分。交易前安全检查，在决策前注入历史经验教训。上下文压缩机制在长会话中保留关键发现。

**技能库** -- 76 份 SKILL.md 文档，涵盖 10 个类别（技术分析、基本面、宏观、风险管理等），智能体动态加载以指导分析方法论。

**前端界面** -- 16 页 Next.js 16 应用，使用 shadcn/ui 和 TailwindCSS v4。包含智能体终端、Quick Ask、回测、晨间简报、股票扫描、记忆查看器和审批管理。

**回测引擎** -- MockBrokerEngine，次日开盘执行，哈希校验可复现，VaR/CVaR 风险分析，PDF 报告生成。

**风险管理** -- 人在回路审批系统，规则触发门控（仓位变动、置信度阈值、集中度限制）。审批工作流状态机。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 智能体编排 | 自建 ReAct 循环 + LangGraph StateGraph |
| LLM 后端 | OpenAI 兼容 API (DeepSeek) |
| 后端服务 | FastAPI + uvicorn |
| 前端界面 | Next.js 16 + React + TypeScript + shadcn/ui |
| 数据源 | Yahoo Finance, Google News RSS, AkShare, Finnhub |
| 持久化存储 | SQLite (ContextStore, MarketDataStore, MemoryStore) |
| 定时调度 | APScheduler |
| 结构化输出 | Pydantic |
| 包管理 | uv (Python), npm (前端) |

---

## 快速开始

### 环境要求

- Python 3.12
- Node.js 22+
- DeepSeek API 密钥（或任意 OpenAI 兼容密钥）

### 1. 克隆并配置

```bash
git clone https://github.com/KaiOnCode/QuanTable.git
cd QuanTable
cp properties.env.example properties.env
```

编辑 `properties.env`，填入你的 API 凭据：

```ini
OPENAI_API_KEY=sk-your-deepseek-key
OPENAI_API_BASE=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

> `properties.env` 已被 gitignore，切勿提交真实密钥。

### 2. 启动后端

```bash
uv sync
PYTHONPATH=. uv run uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

### 4. 打开工作台

访问 `http://localhost:3000`：

- `/agent` -- 交互式 ReAct 智能体终端
- `/quick-ask` -- 结构化多智能体分析（3 种模式）

---

## 项目结构

```
QuanTable/
+-- agent/                  # 自建 ReAct 引擎（活跃开发）
|   +-- loop.py             #   25 轮迭代 ReAct 循环引擎
|   +-- state.py            #   AgentLoopState + TransitionType
|   +-- compression.py      #   5 层上下文压缩
|   +-- progress.py         #   心跳计时器 + 进度事件
|   +-- trace.py            #   JSONL 轨迹记录
|   +-- tools/              #   21+ 金融和工作区工具
+-- quick_ask/              # LangGraph 12 智能体流水线（遗留）
|   +-- orchestrator.py     #   IntelliFin_Assistant (StateGraph)
|   +-- state.py            #   AgentState (MessagesState)
|   +-- agents/             #   5 个智能体模块
+-- skills/                 # 76 份 SKILL.md 文档（共享）
+-- dataflow/               # 数据提供者和采集
+-- memory/                 # 跨会话持久化记忆
+-- storage/                # SQLite 持久化层
+-- scheduler/              # APScheduler 定时数据采集
+-- server/                 # FastAPI 后端
|   +-- main.py             #   应用入口
|   +-- routes/             #   REST 和 SSE 端点
+-- frontend/               # Next.js 16 前端
+-- data/                   # 运行时数据（已 gitignore）
+-- test/                   # 测试套件
+-- docs/                   # 架构和设计文档
```

---

## 文档

| 主题 | 文件 |
|------|------|
| 架构概览 | [`docs/architecture.md`](docs/architecture.md) |
| 数据模型 | [`docs/data-models.md`](docs/data-models.md) |
| API 契约 | [`docs/api-contracts.md`](docs/api-contracts.md) |
| 前端规范 | [`docs/spec.md`](docs/spec.md) |
| 开发计划 | [`docs/development-plan.md`](docs/development-plan.md) |
| 添加数据源 | [`dataflow/providers/`](dataflow/providers/) |

---

## 参与贡献

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解开发环境搭建、编码规范和 PR 指南。

---

## 路线图

| 阶段 | 功能 | 状态 |
|------|------|------|
| 阶段 1 | 数据基础（市场数据 REST 接口、APScheduler） | 进行中 |
| 阶段 2 | 前后端集成（SSE 流式传输、全页面接入） | 计划中 |
| 阶段 3 | 记忆注入智能体流水线 | 计划中 |
| 阶段 4 | 回测引擎对接真实券商 | 计划中 |
| 阶段 5 | 生产部署与监控 | 计划中 |

---

## 许可证

MIT 许可证 -- 详见 [LICENSE](LICENSE)。

---

**免责声明**: QuanTable 是用于教育和研究目的的研究型软件，不构成投资建议，不持有资金，不执行真实交易。过往业绩不代表未来表现。使用风险自负。
