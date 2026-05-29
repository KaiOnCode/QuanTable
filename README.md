# IntelliFin Assistant - 智能股票分析系统

基于 LangGraph 的多智能体股票分析系统，5个专业AI智能体协同工作，提供全面投资建议。

## ✨ 核心特性

- **多智能体协作**：市场/新闻/基本面/风险分析师 + PM决策
- **实时数据**：Yahoo Finance + Google News
- **回测验证**：历史预测准确性评估
- **技术图表**：K线、SMA、布林带、RSI、MACD

## 📋 系统要求

- Python 3.12
- OpenAI API Key
- 网络连接

## 🚀 快速开始

### 1. 安装后端依赖

```bash
cd /path/to/your/project

# 如未安装 uv，可先执行：
# curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync
```

### 2. 配置 API Key

编辑 `properties.env` 文件：

```bash
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_MODEL=gpt-4o-mini
```

### 3. 启动应用

#### Streamlit Web界面（传统）

```bash
./run_web.sh
# 或: uv run streamlit run streamlit_app.py
```

浏览器打开 <http://localhost:8501>

#### 命令行模式

```bash
uv run python app.py AAPL              # 基础分析
uv run python app.py TSLA --visualize  # 带图表
uv run python app.py NVDA --output report.txt  # 保存报告
```

## 📊 使用说明

### Streamlit前端界面

- 输入股票代码 → 选择分析模式 → 配置图表选项
- 开始分析
- 支持历史记录查看和报告导出

**CLI输出**：方向(Bullish/Bearish/Neutral) + 时间范围 + 置信度 + 详细分析

## ✅ 验证与 QA

### 项目质量门禁

```bash
cp bugs/basedpyright/baseline.json /tmp/basedpyright-baseline.json
uv run basedpyright --baselinefile /tmp/basedpyright-baseline.json
uv run ruff check .
uv run ruff format --check .
```

### Phase 5 Streamlit Broker Smoke

先确保已安装浏览器自动化依赖：

```bash
uv add --dev playwright
uv run playwright install chromium
```

然后执行浏览器层 smoke：

```bash
uv run python /home/eden/.agents/skills/webapp-testing/scripts/with_server.py \
  --server "uv run streamlit run streamlit_app.py --server.headless true --server.port 8501" \
  --port 8501 \
  -- uv run python test/streamlit/streamlit_broker_phase5_smoke.py
```

## 🏗️ 项目结构

```text
├── agentgraph/          # LangGraph工作流编排
├── agents/              # 5个AI智能体
├── dataflow/            # 数据服务层
├── utils/               # PDF生成、图表工具
├── app.py               # CLI入口
├── streamlit_app.py     # Streamlit Web界面
└── properties.env       # 配置文件
```

## 🔧 工作流程

```text
START → [市场/新闻/基本面分析师 并行] → [风险分析师] → [PM决策] → END
```

## ⚠️ 注意事项

- **API成本**：每次分析调用多次LLM
- **数据延迟**：Yahoo Finance有15-20分钟延迟
- **免责声明**：仅供参考，不构成投资建议

## 🐛 常见问题

| 问题 | 解决方案 |
| ---- | -------- |
| 未找到配置文件 | 确保 `properties.env` 包含有效的 `OPENAI_API_KEY` |
| 分析失败/超时 | 检查网络、API Key、API配额 |
| 股票代码无效 | 使用美股代码（AAPL、TSLA等） |

## 📄 许可证

本项目仅供学习研究使用。

---

**免责声明**：本系统提供的分析仅供参考，不构成投资建议。投资有风险，决策需谨慎。
