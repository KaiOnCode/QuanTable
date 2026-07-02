# Broker Plus Owned Improvement Grill Workbench

> 用途：这是 `grill-me` 决策工作台，不是实现计划。每个问题都先基于当前代码事实给出可行方案、利弊、建议与初始归属判断。每次只讨论一个问题；用户确认后，在“共识记录”处更新结论。

## 当前边界

- `feat/broker-plus` 只拥有 broker 执行域：模拟执行核心、broker 协议、事件、ledger、执行报告、backtest 执行合同、身份传播、broker-owned serializers/views。
- 集成或平台分支拥有 FastAPI、React、完整 ContextStore、完整 HITL manager、MemoryStore、通知、真实 broker adapters、生产持久化、权限、异步任务。
- 本文件允许讨论“为未来平台预留的 broker-owned seam”，但不允许把平台模块实现提前塞进 broker-plus。

## 代码事实速记

- `broker/backtest_runner.py` 当前在每个交易日先 `broker.on_bar(...)`，再调用 `agent.run(..., date=..., current_position_pct=..., execution_enabled=True, session_id=...)`；没有正式 `as_of` 参数，也没有 scoped data-service/tool factory 注入点。
- `agents/utils/agent_tools.py` 已有 `ToolDataService` protocol、`configure_data_service_factory()` 和工具参数 `end_date`；`dataflow/service.py` 已把价格、指标、基本面、新闻查询接收 `end_date`。这些是 agent/dataflow 层能力，不是 broker-owned 实现。
- `broker/gateway.py` 当前协议覆盖 `get_latest_price`、账户/持仓查询、下单、撤单、订单/成交查询和 `publish_event`；没有 `client_order_id`，没有把 engine callbacks 纳入 gateway protocol。
- `broker/models.py` 已有 `OrderStatus.PARTIALLY_FILLED`，但 `broker/views.py` 当前明确拒绝把 partially filled 暴露为 public order status。
- `broker/config.py` 有 `execution_timing: "close_bar" | "next_open"`，但注释仍说当前只是开关，具体填充时机行为待后续落地；`MockBrokerEngine` 目前 market order 用 close reference price 立即成交，limit order 在后续 `on_bar()` 触发时按 limit price 成交。
- `agentgraph/execution_node.py` 已把 `pending`、`rejected`、`timed_out`、`modified`、`skipped`、`held`、`failed`、`executed` 映射为 `ExecutionReportView`，并发布 execution-domain events。
- `broker/events.py` 已有 per `(strategy_id, account_id)` monotonic sequence；event type 和 payload 仍是自由字符串/字典。
- `broker/ledger.py` 只存 fill/trade 与 daily snapshot；rejected/held/skipped 不进 trade ledger。ledger 查询当前主要按 `session_id`，position lineage 修复已按 `(session_id, account_id, ticker)` 做隔离。
- `plans/broker-plus/05-contract-mapping.md` 已覆盖身份、百分比单位、enum 映射、执行报告状态、事件/ledger 边界、backtest JSON shape 和 non-goals；后续若改变合同，需要同步更新。

## 决策状态

| 序号 | 候选项 | 初始建议归属 | 当前状态 |
| --- | --- | --- | --- |
| 1 | Backtest no-lookahead execution contract | `feat/broker-plus` 薄合同增强 | 已确认：选择 A |
| 2 | Minimal scoped data-service seam | 依赖问题 1；优先 broker-owned seam，真实 dataflow 接入留集成分支 | 已确认：选择 A |
| 3 | BrokerGateway adapter-readiness contract | 部分进 `feat/broker-plus`，真实 adapter/异步回调留后续 | 已确认：选择 A 的收窄版；async lifecycle 延后 |
| 4 | Mock broker execution realism | `feat/broker-plus` 可落地 execution_timing；partial fills 延后 | 已确认：选择 A；B 作为 deferred contract-breaking enhancement |
| 5 | ExecutionReportView and HITL result mapping | `feat/broker-plus` 做合同/回归补强，不做 HITL manager | 已确认：选择 A |
| 6 | Ledger and outcome export for downstream memory | broker-plus 定义 outcome shape；平台分支做 MemoryStore/持久化 | 已确认：选择 A 的合同层版本 |
| 7 | Identity and lineage invariants | `feat/broker-plus` 补强不变量和查询边界 | 已确认：选择 A 的收窄版 |
| 8 | Broker event contract for downstream consumers | `feat/broker-plus` 固化事件词汇/载荷；通知与生产存储留平台 | 已确认：选择 A |
| 9 | Contract mapping and regression gate updates | 文档/验证纪律，随决策同步更新 | 已确认：选择 A |

## 问题 1：Backtest 是否必须在 broker-plus 内正式拥有 `as_of` 无前视合同？

### 具体问题

当前 backtest runner 虽然把当前交易日以 `date=` 传给 agent，但这只是普通状态字段，不是强制合同。agent/tool 层是否真的只访问 `as_of` 之前的数据，依赖 prompt 和工具调用习惯；broker-plus 没有测试证明每一步都传入了明确日期边界。

### 可行方案

**方案 A：在 `feat/broker-plus` 增加薄 `as_of` 合同。**

- 内容：让 `BacktestRunner` 明确计算每步唯一 `as_of`，并传给 agent/harness；保留 `date` 兼容，或者把 `date` 视为 `as_of` 的 legacy alias；增加 focused tests 证明每个 trading step 的 `as_of` 正确传递。
- 优点：直接解决无前视偏差的 broker-owned 执行合同；不需要实现数据库或 provider slicing；未来平台只需接入这个边界。
- 缺点：会触碰 backtest runner 与 agent harness 调用签名；如果命名不谨慎，可能和现有 `date` 状态产生重复。

**方案 B：只在集成/platform 分支通过 DataService `end_date` 控制。**

- 内容：broker-plus 不改；未来平台负责把 `as_of` 映射到 DataService/MarketDataStore 的 `end_date`。
- 优点：broker-plus 代码最少变动；不提前约束 agent harness。
- 缺点：broker backtest 自身仍没有可测试的 no-lookahead 合同；未来平台容易重复解释 broker backtest 语义。

**方案 C：暂缓，只在文档写“不要前视”。**

- 优点：最快，不引入任何签名变化。
- 缺点：风险最大；prompt-only 约束不是可靠控制，也无法作为回归门。

### 我的建议

选择 **方案 A**。这是 execution backtest 的核心可信度问题，属于 broker-plus 的执行域合同；但实现边界必须很薄，只定义并测试 `as_of` 传播，不实现完整历史数据库、不接 FastAPI/React/ContextStore。

### 建议归属

`feat/broker-plus`。

### 共识记录

- 状态：已确认
- 结论：选择方案 A。`feat/broker-plus` 应正式拥有薄 `as_of` 无前视合同：`BacktestRunner` 每个 trading step 必须计算并传递唯一 `as_of` 边界，并由 focused tests 证明该边界进入 agent/harness。实现不得扩大到完整历史数据库、provider slicing、FastAPI、React、ContextStore 或平台存储。

## 问题 2：Scoped data-service seam 应该做到哪一层？

### 具体问题

现有工具层已有 `configure_data_service_factory()` 和 `end_date` 参数，DataService 也接收 `end_date`。但是 `BacktestRunner` 没有 broker-owned seam 来创建“按 `as_of` 限定的数据访问/工具”。如果不定义 seam，问题 1 的 `as_of` 只能停留在 agent state，不能自然约束工具。

### 可行方案

**方案 A：定义 broker-owned backtest agent/tool seam，但不导入 DataService。**

- 内容：在 backtest runner 周边定义最小 protocol/factory，例如 `agent_factory(as_of, broker)` 或 `scoped_harness_factory(as_of=...)`；测试用 fake service/agent 证明 as_of 被传入。真实 DataService/MarketDataStore 接入留给集成分支。
- 优点：broker-plus 拥有可测试边界；不依赖 dataflow/storage/server；未来集成分支有明确插口。
- 缺点：需要设计一个小 protocol；如果过早抽象过宽，会制造空泛接口。

**方案 B：BacktestRunner 直接调用 `agent_tools.configure_data_service_factory()`。**

- 优点：复用现有工具层，短期容易把 end_date 传进去。
- 缺点：broker/backtest 会反向依赖 agents/utils/dataflow 的全局 factory；全局状态对并发和测试不友好；边界更像平台接线，不像 broker-owned 合同。

**方案 C：broker-plus 只传 `as_of`，scoped data service 完全留给集成分支。**

- 优点：边界最干净；避免提前设计工具接口。
- 缺点：no-lookahead 的控制链只有前半段，未来接线者仍需重新判断如何约束工具。

### 我的建议

选择 **方案 A**，但前提是问题 1 选择 broker-plus `as_of` 合同。seam 的形状要很小：只表达“每个 backtest step 可以拿到 `as_of` scoped harness/tool factory”，不要引入 SQLite、ContextStore、MarketDataStore 或 server。

### 建议归属

合同 seam 在 `feat/broker-plus`；真实 DataService/MarketDataStore 适配在 integration/platform branch。

### 共识记录

- 状态：已确认
- 结论：选择方案 A。`feat/broker-plus` 应定义 broker-owned 的最小 backtest scoped harness/tool seam，用于表达每个 backtest step 可以拿到 `as_of` scoped 的 agent/harness/tool factory。该 seam 不得导入 `DataService`、`MarketDataStore`、SQLite、ContextStore、server 或 frontend；真实 DataService/MarketDataStore 适配留给 integration/platform branch。

## 问题 3：BrokerGateway 为真实/paper adapter 预留到什么程度？

### 具体问题

当前 `BrokerGateway` 足以支撑 mock broker 与执行节点，但真实 adapter 常见需求包括 idempotency/client order id、更细的订单生命周期、异步状态回调、外部订单 ID、账户状态刷新等。一次性全加会跨入真实 adapter 实现；完全不加又可能让未来 adapter 反复改上层执行代码。

### 可行方案

**方案 A：只加入最小 adapter-readiness 字段与契约测试。**

- 内容：考虑在 `Order` 或 view 中加入 `client_order_id`/idempotency 字段；补充 gateway conformance-style tests，验证 mock broker 与未来 adapter 应维持相同基础行为。异步回调、SDK、credentials 不做。
- 优点：对未来 adapter 最有帮助，仍保持 broker-owned execution contract；不会引入外部依赖。
- 缺点：会扩展模型表面；需要决定 `client_order_id` 是否由上游生成、是否唯一、是否进入 event payload。

**方案 B：扩展完整订单生命周期，包括 accepted、partially_filled、failed 等 public view 状态。**

- 优点：更贴近真实 broker；未来 adapter 改动少。
- 缺点：当前 mock engine 不产生 partial fills，`views.py` 还明确拒绝 partially filled；会迫使报告/status 映射大改，超过当前需求。

**方案 C：保持现有 gateway，adapter-readiness 只写入集成分支计划。**

- 优点：broker-plus 稳定，不新增模型字段。
- 缺点：未来真实 adapter 很可能要回头改 broker contract；上层可能继续依赖不足够稳定的订单身份。

### 我的建议

选择 **方案 A 的收窄版**：优先讨论是否现在加入 `client_order_id`/idempotency；订单生命周期只维持当前 public mapping，partial fill 与 async broker callbacks 延后。真实 adapter 实现、SDK、网络调用全部不属于 broker-plus。

### 建议归属

最小 idempotency/contract tests 可进 `feat/broker-plus`；真实 adapter 与异步 callback integration 留后续 integration/platform branch。

### 共识记录

- 状态：已确认
- 结论：选择方案 A 的收窄版。`feat/broker-plus` 应加入最小 adapter-readiness 合同，重点是 `client_order_id` / idempotency 字段与 conformance-style tests；`client_order_id` 应由上游或调用方生成，broker 只接收、传播、序列化并用于幂等/重复提交边界。完整 adapter lifecycle、async broker callbacks、外部 SDK、credentials、network calls、partial lifecycle 和真实 broker adapter 实现留给 integration/platform branch。

## 问题 4：MockBrokerEngine realism 应该优先补哪一种现实语义？

### 具体问题

当前 engine 已有 market fill、limit fill、cancel、risk rejection、short、account isolation 和 events；但 `execution_timing` 配置尚未落地。market order 实际用当前 close 价即时成交，limit order 在后续 bar 按 limit price 成交。这个行为足以做 demo，但如果 backtest 声称支持 `close_bar`/`next_open`，需要测试化。

### 可行方案

**方案 A：只把 `execution_timing` 的 `close_bar`/`next_open` 语义落地并测试。**

- 内容：明确 market order 在 close_bar 下如何成交，在 next_open 下是否挂到下一根 bar 的 open；保持 deterministic，不引入 partial fills。
- 优点：直接对应已有配置字段；提升 backtest 可信度；复杂度可控。
- 缺点：可能改变现有测试预期；需要小心定义 first bar/last bar 未成交订单怎么处理。

**方案 B：加入 partial fills、复杂拒单、流动性/成交量约束。**

- 优点：更接近真实市场；有利于未来 adapter lifecycle。
- 缺点：容易演变成简易交易所撮合引擎；对当前 contract 价值不成比例；会冲击 view/status 映射。

**方案 C：只文档化当前行为，不改 engine。**

- 优点：低风险；不扰动现有回归。
- 缺点：`execution_timing` 继续是未实现配置；backtest 语义含混。

### 我的建议

选择 **方案 A**。这是 broker-plus 内合理的 mock realism；方案 B 延后，除非后续真实 adapter 合同需要 partial fill public mapping。

### 建议归属

`feat/broker-plus` 可做 `execution_timing`；partial fills 和交易所级模拟 deferred。

### 共识记录

- 状态：已确认
- 结论：选择方案 A。`feat/broker-plus` 应优先落地并测试 `execution_timing` 的 `close_bar` / `next_open` 语义，保持 deterministic mock execution，不引入 partial fills、流动性、成交量约束或交易所级撮合模拟。方案 B 记为 deferred contract-breaking enhancement：若未来要做 partial fills 或更真实成交模型，必须先单独冻结 public status/view/report/ledger/outcome/event 合同，再实现 engine 行为。

## 问题 5：HITL 结果映射还需要 broker-plus 做什么？

### 具体问题

`ExecutionReportView` 和 execution node 已经覆盖 `pending`、`modified`、`rejected`、`timed_out` 等状态，并确保 pending 不下单。剩下的问题是：broker-plus 是否需要进一步定义 formal HITL result model，还是只保留 approval snapshot 与 regression coverage？

### 可行方案

**方案 A：只补强 mapping 文档和边缘回归测试。**

- 内容：确认 `pending/approved/modified/rejected/timed_out` 到 report status、approval snapshot、event/no-order 的映射；不新增 `hitl/` manager。
- 优点：保持边界正确；让未来 HITL manager 可以薄接 broker report；改动低风险。
- 缺点：不能解决审批队列、超时策略、通知、UI、resume 等平台问题。

**方案 B：在 broker-plus 定义 formal HITL result protocol/model。**

- 优点：未来 HITL manager 输入输出可能更稳定。
- 缺点：很容易把 HITL domain 拉进 broker；当前冻结合同已说 formal approval domain 属于 future `hitl/`。

**方案 C：完全不动。**

- 优点：现有实现已经基本够用。
- 缺点：如果未来 HITL 接入方只看合同文档，可能遗漏 timed_out/modified 等边缘语义。

### 我的建议

选择 **方案 A**。broker-plus 只负责 execution-time 表达：approval snapshot 如何进入 `ExecutionReportView`、哪些状态不下单、哪些事件被写入。完整 HITL manager、API、UI、通知全部保持出界。

### 建议归属

`feat/broker-plus` 的合同/测试补强；完整 HITL 只属于 integration/platform branch。

### 共识记录

- 状态：已确认
- 结论：选择方案 A。`feat/broker-plus` 只补强 HITL execution-time mapping 文档和边缘回归测试，确认 `pending/approved/modified/rejected/timed_out` 如何进入 `ExecutionReportView`、approval snapshot、order/no-order 分支和 execution-domain events。完整 HITL manager、审批队列、超时策略、interrupt/resume、API、UI 与通知仍属于 integration/platform branch；未来 HITL manager 应薄接 broker-owned report，而不是绕过或重写 broker execution report。

## 问题 6：给 Memory/Reflection 的 outcome export 应该是 ledger 扩展还是 report/view 扩展？

### 具体问题

未来 MemoryStore 需要从 PM decision 追到执行 outcome。当前 fill/trade/daily snapshot 在 ledger，rejected/held/skipped/pending/failed 主要在 execution report/events；如果 Memory 层直接解析 PM 文本或散落事件，会重复 broker 语义。但把所有非交易结果写入 trade ledger 又会破坏 ledger 边界。

### 可行方案

**方案 A：定义 broker-owned `ExecutionOutcomeView` 或等价 serializer shape。**

- 内容：从 execution report、order/fill views、ledger metrics/events 组合出 memory 可消费 outcome：decision/session identity、status、fills、realized PnL、account snapshot、rejection/hold/failure reason 等。只定义 shape/serializer，不做 MemoryStore。
- 优点：Memory 层不用重新解释 broker internals；不污染 trade ledger；符合 broker-owned contract。
- 缺点：需要决定 outcome 是单次执行 report 级，还是 session summary 级；如果没有平台持久化，查询能力仍有限。

**方案 B：扩展 ledger，让 rejected/held/skipped 也成为 ledger records。**

- 优点：一个地方查询所有 outcome，MemoryStore 接入简单。
- 缺点：违背当前“ledger stores fills/trades and daily snapshots only”的合同；trade ledger 语义会变混。

**方案 C：integration/platform branch 自行从 reports/events 派生 memory outcome。**

- 优点：broker-plus 不新增 view。
- 缺点：平台层可能复制 status/ledger/identity 映射；Memory 语义容易和 broker 执行报告脱节。

### 我的建议

选择 **方案 A 的合同层版本**：broker-plus 定义 outcome view/serializer 或在现有 `ExecutionReportView`/`TradeView` 上明确 memory-consumable 字段；平台分支负责 MemoryStore、OWM scoring、reflection、持久化和查询编排。

### 建议归属

broker-owned outcome shape 属于 `feat/broker-plus`；MemoryStore 与评分/召回属于 integration/platform branch。

### 共识记录

- 状态：已确认
- 结论：选择方案 A 的合同层版本。`feat/broker-plus` 应定义 broker-owned execution outcome shape，或在现有 `ExecutionReportView`/`TradeView` 上明确 memory-consumable 字段。first-stage outcome 以单次执行报告级为主，包含 decision/session identity、execution status、order/fill/trade linkage、account snapshot、realized PnL 或 rejection/hold/failure reason。session summary、MemoryStore、OWM scoring、reflection、持久化和召回编排留给 integration/platform branch。

## 问题 7：Identity/lineage 还需要补强哪些不变量？

### 具体问题

当前身份字段已广泛存在，也有账户隔离测试；但仍有可疑边界：backtest runner 目前固定 `account_id="default"`、不显式接收 `strategy_id/account_id/decision_id`；ledger backend 查询主要按 `session_id`；event sink 查询没有 `decision_id` 过滤；broker 不应生成 `decision_id` 的边界要继续守住。

### 可行方案

**方案 A：补强查询和 backtest identity propagation，不生成 identity。**

- 内容：增加必要的可选参数或 filtering，如 backtest config/runner 接收 `strategy_id/account_id`，event/ledger view 支持更细身份过滤；测试跨 account/session/decision 不污染。`decision_id` 仍由上游传入。
- 优点：直接强化 broker-owned lineage；有利于 future platform join。
- 缺点：会扩大 runner/config/backend 查询表面；需要避免把用户/权限/ownership 引入 broker。

**方案 B：只更新文档，维持当前实现。**

- 优点：当前大部分字段已经存在，改动少。
- 缺点：后续平台做 join 时可能发现查询粒度不足，尤其是 decision-level outcome。

**方案 C：broker 内生成或管理 `decision_id`/账户归属。**

- 优点：broker 数据更自足。
- 缺点：明确违反冻结合同；PM/orchestrator 才是 decision identity 来源，用户/权限也不属于 broker。

### 我的建议

选择 **方案 A 的收窄版**：补 propagation 和 filter，不生成身份、不做 auth/ownership。这个问题和问题 1/6/8 有依赖：如果引入 outcome/event contracts，应同步确认它们按哪些 identity 可 join。

### 建议归属

`feat/broker-plus`。

### 共识记录

- 状态：已确认
- 结论：选择方案 A 的收窄版。`feat/broker-plus` 应补强 identity propagation 与 filtering，例如 backtest identity propagation、event/ledger/outcome 可按必要身份维度 join 或过滤；但 broker 不生成 `decision_id`，不引入用户、权限、账户 ownership 或 auth。

## 问题 8：Broker event contract 要不要从自由字符串升级成稳定词汇/载荷合同？

### 具体问题

当前事件序列已经按 `(strategy_id, account_id)` 单调递增，事件类型也在实现中使用固定字符串；但模型层没有 literal/constant vocabulary，payload 仍是自由字典。未来 audit view、notifications、HITL status、Memory outcome 都会消费这些事件，如果不固化，会把事件解释逻辑留给平台层猜。

### 可行方案

**方案 A：在 broker-plus 固化事件类型常量/typing 与 payload 最小字段。**

- 内容：定义 broker-owned event vocabulary，例如 `order_placed`、`order_filled`、`order_canceled`、`risk_check_failed`、`order_rejected`、`execution_pending`、`execution_rejected`、`execution_failed`；为每类事件测试关键 payload 字段。仍使用 in-memory sink，不做通知。
- 优点：平台消费者可稳定订阅/过滤；不需要生产存储；符合 broker execution-domain contract。
- 缺点：payload typing 需要谨慎，过度严格会降低未来扩展弹性。

**方案 B：定义完整 typed event subclasses。**

- 优点：类型安全更强。
- 缺点：复杂度高；当前 Pydantic view 与 event sink 不需要这么重。

**方案 C：只在 `05-contract-mapping.md` 写事件名，不改代码。**

- 优点：低风险。
- 缺点：代码仍没有约束，回归测试可能漏掉字段漂移。

### 我的建议

选择 **方案 A**：固定 vocabulary 和最小 payload contract，但不实现 notification channels、platform audit dashboard 或生产持久化。

### 建议归属

`feat/broker-plus`。

### 共识记录

- 状态：已确认
- 结论：选择方案 A。`feat/broker-plus` 应固化 broker-owned event vocabulary 和最小 payload contract，并用回归测试约束关键事件字段。事件消费者可依赖这些词汇订阅/过滤；但 notification channels、platform audit dashboard、生产 event persistence 仍属于 integration/platform branch。

## 问题 9：合同映射和 regression gate 应该如何跟随这些决策？

### 具体问题

`05-contract-mapping.md` 已经存在并覆盖当前冻结合同。如果本轮同意新增 `as_of`、scoped seam、event vocabulary、outcome view 等，映射文档和回归门必须同步，否则未来 integration worker 会读到过期合同。

### 可行方案

**方案 A：每达成一项共识，就在本工作台记录；形成实现计划时同步更新 `05-contract-mapping.md` 与 gate。**

- 优点：决策轨迹清楚；不会把未确认项误写成冻结合同；未来可按共识批量转 implementation plan。
- 缺点：需要维护两层文档：本工作台记录过程，`05` 记录最终合同。

**方案 B：直接把所有建议写入 `05-contract-mapping.md`。**

- 优点：单一合同文档更集中。
- 缺点：会把尚未确认的 grill-me 候选项伪装成已冻结合同，不利于边界纪律。

**方案 C：等实现完成后再更新文档。**

- 优点：少做中间文档。
- 缺点：最容易造成代码和合同漂移；也违背当前文档先行的决策方式。

### 我的建议

选择 **方案 A**。本文件先承载问题和共识；只有用户确认并转入实现/冻结时，才同步更新 `05-contract-mapping.md` 和测试 gate。

### 建议归属

当前文件属于 integration planning；最终合同更新可发生在 `feat/broker-plus` 的文档阶段。

### 共识记录

- 状态：已确认
- 结论：选择方案 A。本工作台和 `plans/broker-plus-integration/WIP.md` 先记录 grill-me 共识；只有当这些共识转成冻结实现计划或下一轮 broker-plus 任务时，才同步更新 `plans/broker-plus/05-contract-mapping.md` 与 regression gate。不要把尚未实现的 `as_of`、scoped seam、`client_order_id`、`execution_timing` 等能力提前写成已实现合同；也不要等代码实现后才补文档。

## 建议提问顺序

1. 先决策问题 1：是否在 broker-plus 内正式拥有 `as_of` no-lookahead 合同。
2. 再决策问题 2：如果有 `as_of`，scoped data-service seam 做到哪一层。
3. 决策问题 7：identity/lineage 是否需要配合 backtest/outcome/event 补强。
4. 决策问题 8：event vocabulary/payload 是否固定。
5. 决策问题 6：Memory outcome 是 report/view shape 还是 ledger 扩展。
6. 决策问题 5：HITL 映射只补合同/测试，还是引入 formal HITL result。
7. 决策问题 4：mock realism 是否落地 execution_timing。
8. 决策问题 3：gateway adapter-readiness 是否加入 idempotency。
9. 最后决策问题 9：如何同步 `05-contract-mapping.md` 与 regression gate。
