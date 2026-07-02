# Future Works (Broader)

> 优先参考 [future-works](future-works.md), 解决券商模拟接口接入后, 可以对照这篇, 对剩余的决策项做出决策并执行

我用 `superpowers:brainstorming` 的方式做了现状探索和方案拆解；`subagent-driven-development` 本身要求已有实现计划，本轮没有直接改代码，所以我只用了只读 explorer 子代理并行看分支。已刷新远端分支，当前 `feat/broker-plus` 本地验证通过：`uv run pytest` 78 passed，`ruff check` / `ruff format --check` / `basedpyright --baselinefile bugs/basedpyright/baseline.json` 全绿。

**总判断**
当前不是“完全不能用”，而是“几个关键能力分散在不同分支，还没形成一个可运行产品闭环”：

- `feat/broker-plus`：最扎实，已有本地 broker 模拟执行域。见 [broker/gateway.py](/home/eden/MasterGraduation/COMP7705-Agent-Quant/broker/gateway.py:9)、[broker/engine.py](/home/eden/MasterGraduation/COMP7705-Agent-Quant/broker/engine.py:43)、[agentgraph/execution_node.py](/home/eden/MasterGraduation/COMP7705-Agent-Quant/agentgraph/execution_node.py:35)。
- `upstream/feat/frontend-backend`：Web App / FastAPI / SQLite / market API / monitor 的主体。
- `upstream/memory`：有交易记忆 loop 原型，但不能直接 merge，会覆盖 broker-plus 的执行链。
- `upstream/feat/new-hitl`：有 HITL 审批规则、API、页面，但 executor 明说还不调用 broker。
- `upstream/feat/social-media-message-alerts`：有通知渠道和 watchlist alert，可作为“主动提醒”出口。

**Topic 1：历史回测的数据时点隔离**
问题：现在 [broker/backtest_runner.py](/home/eden/MasterGraduation/COMP7705-Agent-Quant/broker/backtest_runner.py:62) 是每天 `on_bar` 后调用 agent，并没有把 agent 的 data tools 强制绑定到“截至当前日期”的数据沙盒。`DataService` 有 `end_date`，但只是接口参数，不是强制时点门控。新闻相对时间解析还用 `datetime.now()`，宏观日历也偏实时。

方案 A：在 `BacktestRunner` 内注入 `BacktestDataService`，只允许读取 `as_of <= current_date` 的切片。
优点：最能证明 no-lookahead；适合毕业项目展示和测试。
缺点：要改 agent tools 的 DataService 工厂和 provider 测试。

方案 B：只靠 prompt 要求 agent 调用工具时传 `end_date`。
优点：改动小。
缺点：不可靠，LLM 不等于权限边界。

建议：选 A。回测必须把“数据可见性”从 prompt 约束升级成代码约束。

**Topic 2：DataService 统一入口**
问题：[dataflow/service.py](/home/eden/MasterGraduation/COMP7705-Agent-Quant/dataflow/service.py:27) 在当前分支是半统一；agent tools 走它，但 Streamlit 和一些分支直接调 provider。上游 `frontend-backend` 的 `MarketDataStore`、market routes 更完整，但没有 broker-aware position。

方案 A：以 `frontend-backend` 的 `MarketDataStore + market routes` 为基础，手工融合当前 broker-aware `df_get_position`。
优点：直接支撑前端、缓存、watchlist、monitor。
缺点：合并冲突高。

方案 B：保留当前轻量 `DataService`，只补 no-lookahead。
优点：短期稳。
缺点：Web app 数据展示继续薄。

建议：先做 A 的最小融合：保留当前 `configure_data_service_factory()` 可测试性和 broker 注入，只摘取上游 storage/market API。

**Topic 3：模拟券商接口**
问题：本地模拟已经可用，但还不是“真实券商接口”。当前有订单、成交、账户、持仓、风控、事件、ledger、account isolation；缺真实认证、异步回报、部分成交、交易日历、真实行情订阅、持久化生产账本。

方案 A：先把 `BrokerGateway` 作为稳定接口，继续用 `MockBrokerEngine` 做 demo。
优点：当前测试扎实，最快形成闭环。
缺点：不是实盘/券商沙盒。

方案 B：现在接真实券商 sandbox adapter。
优点：听起来更完整。
缺点：认证、订单状态、行情、交易时间都会拖慢主线。

建议：先不接真实券商。毕业/开源展示优先做“可信模拟盘 + 清晰 adapter boundary”。

**Topic 4：Memory / 历史询问 / 持续跟踪**
问题：`upstream/memory` 有 `MemoryStore`、OWM、`MemoryService.recall_context()`，但新记忆 `outcome_quality=0.0`，没有 PnL 回填；它记的是 PM 决策摘要，不是完整 conversation memory，也没有真正持续跟踪。

方案 A：把 memory 分为三类：conversation summary、decision memory、trade outcome memory。
优点：语义清楚，能回答“问过什么、决定过什么、后来结果怎样”。
缺点：需要 ContextStore schema 和写入时机设计。

方案 B：直接移植 `upstream/memory`。
优点：快。
缺点：会覆盖当前 orchestrator/state，并且闭环不完整。

建议：摘取模型和 service 思路，重新接到当前 broker-plus。交易执行后由 ledger/outcome 更新 memory，而不是 PM 后立刻当作“经验”。

**Topic 5：HITL 审批与执行衔接**
问题：`new-hitl` 有审批状态机和 UI，但 `hitl/executor.py` 不调用 broker；broker-plus 有 `approval_status` 快照和 execution report，但没有完整审批队列。

方案 A：HITL 管审批生命周期，broker-plus 管最终执行。审批通过后把 result 转成当前 `AgentState` 的 `approval_status/modified_target_pct`，再走 `execution_node`。
优点：边界干净，符合已有 broker-plus contract。
缺点：要处理状态名差异，如 `auto_passed` vs `auto_approved`。

方案 B：让 HITL executor 直接下单。
优点：少一层。
缺点：容易绕过 broker-plus 的统一 execution report。

建议：选 A。HITL 不应拥有交易执行，执行只能从 broker gateway 走。

**Topic 6：Web App 最终呈现**
问题：当前分支偏后端执行域；`frontend-backend` 才有 FastAPI/Next.js/market/watchlist/monitor。两边直接 merge 会互相删东西，尤其 `agentgraph/orchestrator.py`、`dataflow/service.py`、`pyproject.toml`。

方案 A：以 `broker-plus` 为执行底座，手工融合 `frontend-backend` 的 server/frontend/storage。
优点：最终 demo 最完整。
缺点：集成成本最高。

方案 B：以 `frontend-backend` 为主，后续再加 broker。
优点：页面先跑起来。
缺点：容易把真正可执行的 broker 价值丢掉。

建议：选 A。故事线应是：Quick Ask -> PM 决策 -> HITL pending -> approve/modify -> broker 模拟成交 -> dashboard/ledger/event 展示。

**Topic 7：定时追踪与通知**
问题：`frontend-backend` 有 monitor task，`social-media-message-alerts` 有 Telegram/email/webhook/WhatsApp 和 watchlist alert，但两者 watchlist 存储方案不同，且通知还没接 broker events。

方案 A：保留 `frontend-backend` 的 SQLite watchlist/monitor，移植 notification channels，把通知接到 analysis complete、approval pending、execution complete、risk rejected。
优点：功能展示很强。
缺点：需要异步化，避免拖慢 SSE。

方案 B：整体移植通知分支 watchlists JSON 路由。
优点：快。
缺点：和 SQLite watchlist 重叠。

建议：只移植 notification，不整体替换 watchlist。

## 推荐优先级

1. 建 integration branch，明确“broker-plus 不可被覆盖”。
2. 先做 no-lookahead backtest data service，这是队友对话里最核心的问题。
3. 融合 `frontend-backend` 的 FastAPI/Next.js/DataStore。
4. 接 HITL 到 broker execution。
5. 接 memory outcome loop。
6. 接 notification/monitor，形成主动追踪 demo。
