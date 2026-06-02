# Future Works

我用 `superpowers:brainstorming` 的思路做了只读分析；没有使用 `subagent-driven-development`，因为它适用于“已有实现计划后执行代码任务”，本轮还在方案判断阶段。已刷新远端 ref，当前分支是 `feat/broker-plus`；我没有改文件，`plans/further-works/` 仍是未跟踪目录。

**总判断**
现在不能说“已经可以正式对接券商模拟接口”。更准确是：

当前分支已经有可验证的本地 broker 模拟执行域，可以支撑 demo 和后续 adapter contract。`BrokerGateway` 已定义稳定接口，[MockBrokerEngine](/home/eden/MasterGraduation/COMP7705-Agent-Quant/broker/engine.py:43) 已支持订单、成交、账户、持仓、风控、事件、账本和账户隔离，[execution_node](/home/eden/MasterGraduation/COMP7705-Agent-Quant/agentgraph/execution_node.py:35) 能把 PM 决策转成结构化执行结果。验证也绿了：`uv run pytest -q` 是 78 passed，`ruff` 和 `basedpyright` 都通过。

但它还没形成“历史数据沙盒 -> agent 决策 -> HITL -> broker 执行 -> ledger/outcome -> memory -> monitor/notification -> Web 展示”的产品闭环。你队友说 dataflow/backend 还没做好，核心上是对的；只是“没什么功能可以用”有点低估了 `broker-plus` 已经做好的执行域。

**问题 1：历史回测没有强制 no-lookahead**
当前 [BacktestRunner](/home/eden/MasterGraduation/COMP7705-Agent-Quant/broker/backtest_runner.py:53) 每个交易日 `on_bar` 后调用 agent，并传入当日 date；但 agent tool 只是可选接收 `end_date`，[DataService](/home/eden/MasterGraduation/COMP7705-Agent-Quant/dataflow/service.py:39) 也只是把 `end_date` 传给 provider。也就是说，代码没有强制 agent 只能看到 `as_of <= current_date` 的数据。

方案 A：做 `BacktestDataService` 或 `ScopedDataService(as_of=current_date)`，由 harness 注入给 tools。优点是最可信、可测试、可展示；缺点是要改 tool factory、provider 和回测测试。建议选 A。

方案 B：只靠 prompt 要求 agent 传 `end_date`。优点是快；缺点是 LLM prompt 不是权限边界，回测结果无法严肃解释。不建议。

方案 C：先离线预构建历史数据包，每个交易日只读本地切片。优点是最稳定；缺点是数据准备成本高。适合毕业 demo 的固定样例，不适合长期产品。

**问题 2：DataService 是半统一，不是数据中台**
当前分支的 `DataService` 有价格、指标、基本面、新闻、仓位入口，但宏观、policy、新闻规范化仍有 TODO。`upstream/feat/frontend-backend` 的 `MarketDataStore` 更像数据层雏形，有 SQLite、OHLCV、fundamentals、news、FTS、freshness 和 monitor；但它不 broker-aware，而且整支合并会删除当前 `broker/`。

方案 A：以 `broker-plus` 为底座，手工摘取 `frontend-backend` 的 `MarketDataStore`、market routes、storage 思路，同时保留当前 `configure_data_service_factory()` 和 broker 注入。优点是能保住执行域；缺点是融合要仔细。建议选 A。

方案 B：保留当前轻量 DataService，只补 no-lookahead。优点稳；缺点 Web app 和持续追踪继续薄。可作为短期第一步。

方案 C：以 `frontend-backend` 为主线再补 broker。风险最大，因为它会覆盖/删除当前最扎实的 broker 能力。不建议。

**问题 3：agent harness 没有统一数据访问策略**
现在 agent tools 只暴露 price、indicators、fundamentals、news；仓位和风控限额没有作为工具暴露，risk agent 主要靠 `current_position_pct`。这会导致 agent “知道当前仓位”但不知道完整账户、限额、订单历史、审批状态。

建议把 harness 变成数据权限入口：每次 run 构造 `RunContext(strategy_id, account_id, session_id, as_of, mode)`，所有 tools 只能通过这个 context 下的 DataService 访问数据。这样不仅解决回测时点隔离，也让 live/paper/backtest 三种模式用同一套接口。

**问题 4：本地 mock broker 还不等于真实券商 paper API**
当前 mock 足够做 execution demo，但缺真实认证、异步订单回报、部分成交、交易日历、公司行动、真实行情订阅、断线恢复、幂等 request id、持久化账本。官方文档也说明真实 paper/sandbox 会带来环境约束：Alpaca paper 是实时模拟环境且走 paper API endpoint；Moomoo/Futu 需要本地或云端 OpenD 网关；IBKR TWS API 走 TWS/IB Gateway socket，paper 行为也可能和 live 不一致。  

建议先不要接真实券商 sandbox。先把 `BrokerGateway` 当稳定 adapter contract，完成可信本地模拟盘；后续再做一个 `AlpacaPaperBrokerGateway` 或 `MoomooPaperBrokerGateway`，并用同一套 broker contract tests 约束。

**问题 5：历史询问/记忆不应只存关键词**
关键词检索适合“找资料”，不适合“复盘交易判断”。`upstream/memory` 已经有 MemoryRecord、OWM scoring 和 recall，但它在 PM 后立即写 `outcome_quality=0.0`，没有等 ledger/PnL 回填，所以还不是完整交易记忆闭环。

建议分三类存：

1. conversation summary：用户问过什么、关注什么、约束是什么。
2. decision memory：某次 PM 决策、输入报告、置信度、目标仓位、理由。
3. trade outcome memory：成交后和持有一段时间后的 PnL、drawdown、是否触发止损、结论是否失效。

保留原文 artifact，同时存结构化字段和短 summary。不要只存关键词，也不要只存 LLM summary；前者太碎，后者不可审计。

**问题 6：持续追踪应由 scheduler/harness 调度，不应让 agent 随机爬**
队友问“定时启动后是让 agent 调 tools 还是爬虫”。建议是：scheduler 触发 monitor task，monitor task 调 DataService 收集数据，再调用 agent/summary 工具，最后写 ContextStore、发 notification。agent 可以决定“需要什么分析”，但不能拥有无限制爬取权限。

`frontend-backend` 的 monitor 和 `social-media-message-alerts` 的通知都可摘取：保留 SQLite watchlist/monitor，移植 notification channel，让通知消费统一事件，比如 `analysis_completed`、`approval_pending`、`execution_executed`、`risk_rejected`。

**问题 7：HITL 要接到 broker，但不能接管 broker**
`upstream/feat/new-hitl` 有 ApprovalRequest、规则、状态机和 API；当前 `broker-plus` 有 approval snapshot 和 execution report。正确边界是：HITL 管审批生命周期，broker 管最终执行。审批通过/修改后，把结果映射回 `AgentState.approval_status / modified_target_pct`，再走 `execution_node`。不要让 HITL executor 直接下单。

## 推荐路线

1. 新建 integration branch，以 `feat/broker-plus` 为底座，明确 broker 不可被覆盖。
2. 先做 no-lookahead `ScopedDataService`，这是回测可信度的根。
3. 手工融合 `frontend-backend` 的 `MarketDataStore`、FastAPI routes、前端数据展示。
4. 接 `new-hitl` 的审批状态机到当前 execution node。
5. 接 memory outcome loop：PM 后写 decision memory，成交/持有后回填 outcome memory。
6. 接 notification/monitor，形成主动追踪 demo。
7. 最后再做真实 broker paper adapter，放在 `BrokerGateway` 后面，feature flag 开关。

一句话建议：现在最值得做的不是“马上连券商”，而是把本地模拟盘做成可信、可审计、可回测、可展示的闭环。这样无论之后接 Alpaca、Moomoo 还是 IBKR，都是换 adapter，而不是重写系统。

**Sources**
Alpaca Trading API paper trading: <https://docs.alpaca.markets/us/docs/trading-api>  
Moomoo OpenAPI introduction: <https://openapi.moomoo.com/moomoo-api-doc/en/intro/intro.html>  
IBKR TWS API documentation: <https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/>
