# 分支合并顺序建议

> 记录日期：2026-05-29
> 目的：记录 `feat/broker`、`main`、`feat/frontend-foundation` 之间的依赖关系、冲突风险和推荐合并顺序。

## 1. 当前分支关系

本地观察到的分支关系如下：

- 当前工作分支：`feat/broker`
- 上游前端分支：`upstream/feat/frontend-foundation`
- 当前主干：`main`

关键事实：

- `feat/broker` 与 `upstream/feat/frontend-foundation` 的共同祖先很早，是 `01f223d Initial Demo`。
- `feat/frontend-foundation` 只有 3 个新增提交，但它是从早期基线开出的，因此相对当前 `main` 落后较多。
- `feat/broker` 基于较新的 uv/main 线路，已经包含 broker 计划、类型检查 baseline、ruff、pytest、uv 等工程化内容。
- `broker/` 在 `feat/broker` 中是单边新增能力，未来合并时不应被上游前端分支误删。

## 2. 不建议的合并方式

### 2.1 不建议直接把 `feat/frontend-foundation` 合进 `feat/broker`

原因：

- 两条分支共同祖先太早，直接合并会引入大量旧基线差异。
- 上游分支删除或归档了许多当前分支仍用于验收的文件。
- 上游分支没有 `pyproject.toml` 和 `uv.lock`，但当前项目已经采用 uv 工作流。
- 上游 React 前端当前存在缺失的 `frontend/lib/*` 依赖，不宜直接作为稳定主线。

### 2.2 不建议把 `feat/broker` 重写成上游前端分支形状

原因：

- `feat/broker` 已经有完整 broker 内核、测试和文档证据。
- 上游前端分支的 broker engine 仍是规划项，不是已实现替代品。
- 当前 broker 的价值在于可执行闭环，不应在合并中被当成旧代码清理掉。

### 2.3 不建议全量采用任一方 README

当前 README 更贴近 `feat/broker` 的实际工程状态；上游 README 更像目标产品架构说明。

未来应做融合版 README，而不是单边覆盖。

## 3. 推荐合并顺序

### Step 1：先让 `feat/frontend-foundation` 对齐当前 `main`

推荐由前端分支先执行：

```text
upstream/feat/frontend-foundation
  <- merge/rebase current main
```

需要解决：

- 恢复或重新引入 `pyproject.toml`。
- 恢复或重新生成 `uv.lock`。
- 明确 `requirements.txt` 归档策略。
- 修复缺失的 `frontend/lib/utils`、`frontend/lib/api/client`、`frontend/lib/types/models`、`frontend/lib/providers/query-provider`。
- 校准 README 中“已完成”和“规划中”的边界。

完成标志：

- Python 后端依赖仍可 `uv sync`。
- 前端可以 `npm install`、`npm run lint` 或至少 TypeScript 编译不因缺失文件失败。
- README 不再宣称未实现能力已经完成。

### Step 2：从 `main` 开 integration branch

建议不要直接在任一功能分支上做最终大合并，而是新建集成分支：

```text
main
  -> integration/frontend-broker
```

这个分支的职责是合并和对接，不承载单独模块研发。

### Step 3：先合入 `feat/broker`

推荐先把 broker 内核合进 integration branch。

原因：

- `feat/broker` 基于更新主线。
- broker 代码有测试、质量门禁和 phase tracker。
- `broker/` 是后续前端/后端 API 的执行基础。

合入后应验证：

- broker 单测。
- execution node 单测。
- backtest runner 单测。
- ruff。
- basedpyright baseline gate。
- Streamlit broker smoke 如环境允许。

### Step 4：再合入已对齐 main 的 `feat/frontend-foundation`

合入时重点保护：

- `broker/` 不应被删除。
- `bugs/basedpyright/` 不应被无意删除。
- `pyproject.toml` 和 `uv.lock` 应保留。
- `streamlit_app.py` 是否归档需要团队明确，不应在集成阶段直接丢失 broker smoke 证据。

主要冲突处理策略：

- `README.md`：人工融合，不采用单边版本。
- `agentgraph/orchestrator.py`：保留 broker execution node 与 HITL 插点，同时评估上游 FastAPI/SSE 需要的 run wrapper。
- `agents/utils/agent_tools.py`：保留当前 data service factory/testability，吸收上游新增工具时避免恢复全局硬编码单例。
- `dataflow/service.py`：保留 broker 注入与 position conversion，吸收 cache、AkShare news fallback、sentiment、MarketDataStore 时拆小步合入。
- `properties.env`：不得把真实 key 或个人配置作为 merge 结果。
- `requirements.txt` rename：统一到 uv 工作流，旧 pip 文件只保留归档说明。

### Step 5：建立 API adapter 对接层

集成分支中再补：

- broker serializer/view。
- FastAPI broker routes。
- backtest route adapter。
- strategy/account 绑定。
- event/audit 查询 adapter。

这一步应该依赖前两条分支都已进入 integration branch，避免在功能分支中互相猜接口。

## 4. 推荐合并后的职责边界

### `feat/broker` 负责

- 模拟券商执行内核。
- 订单、成交、持仓、账户、风控。
- 执行报告。
- 账本和绩效计算。
- 回测执行 runner。
- broker 对外 DTO/serializer。
- 与 AgentState 的最小执行闭环。

### `feat/frontend-foundation` 负责

- React/Next.js 页面。
- UI 组件与交互。
- 前端类型与 API client。
- 产品规格与前端路由。
- FastAPI skeleton，如该分支继续承担后端基础。

### integration branch 负责

- FastAPI route 与 broker serializer 对接。
- Strategy/account 资源绑定。
- README 融合。
- pyproject/uv/frontend package 的统一启动文档。
- 端到端 smoke。

## 5. README 处理建议

不建议提前在 `feat/broker` 直接同步上游 README。

推荐在 integration branch 中做融合版 README：

- 第一部分说明当前实际可运行能力。
- 第二部分说明目标架构。
- 第三部分给出后端和前端启动方式。
- 第四部分列出当前完成、进行中、规划中。
- 第五部分保留质量门禁和 broker smoke。

这样既不会抹掉 `feat/broker` 的真实完成状态，也不会浪费上游前端分支对未来产品结构的整理。

## 6. 最小集成检查清单

合并完成后至少检查：

- `uv sync`
- `uv run pytest test/broker/test_models.py test/broker/test_engine.py test/broker/test_ledger.py test/broker/test_backtest_runner.py`
- `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `cd frontend && npm install`
- `cd frontend && npm run lint`
- FastAPI `/api/health`
- Quick Ask SSE happy path
- broker backtest happy path

如以上任一项暂时无法通过，应在 integration branch 的 tracker 中记录阻塞原因和归属模块，不应静默合入主干。
