<!-- markdownlint-disable MD013 -->

# Backtest Reliability, Fidelity, and Validation Plan

> Status: planning complete, implementation not started  
> Date: 2026-07-12  
> Planning baseline: `dev` at `289d728869e1745d0e8e936855032e9a3341abf2`  
> Remote baseline at diagnosis start: `HEAD == origin/dev == upstream/dev`  
> Primary goal: 修复 daily/weekly backtest 的结构化 decision 失败，使 daily/weekly/monthly 都能可靠完成；同时把当前“能出页面但策略未生效、结果带有前视与会计偏差”的实现升级为可复现、可审计、数值可信的单标的回测。  
> Scope lock: 本文件是下一 session 的 Goal-mode 执行依据。本轮不实现产品代码；执行时不得修改 `quick_ask/`、不得编辑 `properties.env`、不得 push/PR，除非用户另行明确授权。

## TL;DR（给人读）

当前问题并不是 `monthly` 分支正确而其他 frequency 分支写错。相同 AAPL/SPY、61 个交易日窗口会触发 61 次 daily、13 次 weekly、3 次 monthly LLM 决策；当前实现要求每一次 ReAct 都恰好产生一个合法的 `submit_backtest_decision` tool result，任何一次缺失、重复、超时或 schema 失败都会让整个 job 失败。`07c08ef` 之后的真实持久化记录显示：monthly 6/6 完成，weekly 排除一次服务重启后只有 2/8 完成、6/8 为 `agent_failed`；所有 8 个完成 job 又全部是 0 trades。以 weekly 观测反推单次 decision 成功率约为 89.9%，则完整 daily 的理论成功率仅约 0.15%，与“只有 monthly 看起来能用”完全一致。这是串联可靠性缺陷，不是 frequency 枚举缺陷。

截图二也不能视为可信回测：所选 `strategy_id` 没有把 Strategy 的 description、beliefs、type、model、capital、risk 参数带给决策 Agent；`agent`、`quant`、`hitl` 三种 Strategy 走同一个通用提示；指标实际只有 SMA20/SMA50，RSI/MACD/ATR 是空值；没有 warm-up 数据；Agent 读取当日 close 后默认按同一 close 成交；Fill 时间戳来自 2026 运行时而不是 2024 历史日期；收益率以第一次交易后的 equity 而非 initial capital 为分母；win rate / profit factor 把 fills 当 closed trades，并把开仓成本当成亏损交易。因此页面完成只证明 API/UI 能显示结果，不证明策略执行或数值正确。

本计划采用两层修复：先建立可观察、typed、strategy-aware 的 decision boundary，消除 frequency 放大的随机 tool-call 失败；再把“标准绩效回测”改为冻结的 deterministic quant policy + point-in-time features + next-open execution。v1 deterministic 只支持具有受支持 `quant_strategy_name` 与 typed params 的 `quant` Strategy；`agent` 只允许明确标注的 experimental agent-decision mode；`hitl` 历史回测直接拒绝。LLM 不能继续作为 canonical performance 每个历史 bar 的不可审计必经条件。完成后，daily/weekly/monthly 都用同一引擎、同一数据和会计契约，仅 rebalance cadence 不同；任何零交易、订单拒绝、数据不足或 experimental nondeterminism 都必须在结果中明确说明，不能显示成无警告的绿色绩效。

**Effort:** XL，建议 6 个顺序 phase、12 个 implementation+test todos。  
**Risk:** High，风险来自策略语义、historical timing、会计与 persisted API contract 同时变化；必须 TDD-first、numerical golden fixtures、真实 API 与 Chromium QA。  
**下一步：** 在新的 Goal-mode session 中读取本计划，从 Todo 1 开始；只执行最早未完成 todo，所有 gate 通过后再进入下一项。

## 1. 已确认事实与证据

### 1.1 当前调用链

```text
frontend/app/backtest/page.tsx
  -> POST /api/agent/backtest
  -> server/routes/agent.py:create_backtest
  -> agent/backtest_jobs.py:BacktestJobService
  -> ActiveBacktestJobRunner
  -> BacktestDatasetPreparer(target + benchmark exact window)
  -> BacktestRunner(day-by-day bars)
  -> _ScopedBacktestAgent per decision date
  -> BacktestDecisionAdapter
  -> restricted AgentLoop(get_price, get_indicators, submit_backtest_decision)
  -> SubmitBacktestDecisionTool
  -> MockBrokerEngine
  -> TradeLedger
  -> BacktestResultView
  -> persisted result_json / error_json
  -> frontend polling, metrics/chart/trades
```

### 1.2 Frequency 失败的直接证据

在 `07c08ef`（`2026-07-12T19:54:33+08:00`）之后：

| Frequency | Decision calls / 61 bars | Completed | `agent_failed` | Interrupted | Completed with trades > 0 |
| --- | ---: | ---: | ---: | ---: | ---: |
| daily | 61 | 0 | 尚无完整观测 | 1 | 0 |
| weekly | 13 | 2 | 6 | 1 | 0 |
| monthly | 3 | 6 | 0 | 0 | 0 |

`BacktestDecisionAdapter` 对每个 date 要求 exactly one decision tool message；`BacktestJobService` 对其中任意一个 `BacktestDecisionError` 都终止整个 job。weekly 2/8 的端到端成功率若近似为 `p^13 = 0.25`，单次成功率推断为 `p ≈ 0.8989`；同样条件下 daily 为 `p^61 ≈ 0.0015`，monthly 为 `p^3 ≈ 0.7262`。这是基于少量真实运行的解释性推断，不是模型 SLA；它足以证明“增加 decision 数量会乘法放大失败”。

当前 job 只存 `agent_failed` 和通用 message；没有 `decision_date`、失败 stage、attempt、raw typed category 或 partial decisions。因此无法从已失败 job 还原究竟是 provider transient、no tool call、duplicate call、tool error、timeout、max iteration 还是 invalid schema。这个不可观测性本身是 P0 bug。

### 1.3 截图二的准确性缺陷

| Severity | 已确认缺陷 | 当前证据 | 结果影响 |
| --- | --- | --- | --- |
| P0 | Strategy 只传 identity，不传 executable semantics | `agent/backtest_jobs.py:128-153`; `agent/backtest_adapter.py:122-143` | “Tech Momentum” 名称不代表 momentum 逻辑；不同 Strategy 可能得到同一决策 |
| P0 | `agent` / `quant` / `hitl` type 被忽略 | route 只验证 strategy exists；runner 不读取 type | UI 选择看似不同，实际同一通用 Agent |
| P0 | 每个 decision 依赖多轮 ReAct tool choice | exact-one tool validation + 真实频率统计 | daily/weekly 随 decision 数量快速失效、慢且贵 |
| P0 | 同-bar look-ahead fill | `BacktestRunner` 先 `on_bar`、再 decision；`BrokerConfig.execution_timing="close_bar"` | Agent 看到 close 后以同一 close 成交，收益偏乐观 |
| P0 | Fill / Order 使用 runtime timestamp | `broker/models.py` default `_utc_now`; tool 未覆盖 | 2024 回测 trade 日期显示 2026；holding period 错误 |
| P0 | return denominator 错误 | `TradeLedger.compute_metrics()` 使用首个 post-decision snapshot | 首日费用/滑点被排除；实测报告 5.003754%，真实 initial-cash return 4.924975% |
| P0 | fill-based trade stats | entry fill 的费用被记作负 realized P/L | buy-only 未平仓仍算 1 trade、win rate=0、profit factor=0 |
| P0 | 无 warm-up contract | loader 只加载 `date_from..date_to` | 2024-01-02 的 SMA20/SMA50 都由 1 bar 得出；结果依赖 ambient cache |
| P0 | indicator payload 不完整 | `BacktestDataService.get_indicators()` 返回 RSI/ATR `None`、MACD `{}` | Tech Momentum Agent 没有被 UI/skill 描述承诺的指标 |
| P1 | Strategy capital/risk/model fields 被忽略 | runner 使用 default `BrokerConfig()` | initial capital、max position、short policy、model choice 与 Strategy 不一致 |
| P1 | no-trade/rejected/HOLD 不可区分 | result 只展示 fills；不展示 decisions/orders/rejections | 0 trades 可能是全 HOLD、订单拒绝、工具失败或无有效规则 |
| P1 | implicit adjustment/data provenance | yfinance history 未显式固定 adjustment；result 无 fingerprint | library/default/cache 变化可使同 request 结果漂移 |
| P1 | max drawdown duration 与 trade metrics 语义不清 | duration 是 bars；UI/contract 无 unit；risk-free=0 未声明 | 指标难以解释、无法与其他系统一致比较 |

### 1.4 现有测试能证明与不能证明的内容

- 已通过：Agent/Runner/Data/View focused tests `39 passed`；FastAPI job/API/lifecycle `12 passed, 1 warning`（沙箱外）。
- 现有 `test_backtest_runner_rebalances_weekly_but_records_daily_equity` 只证明 weekly 调用两次和返回四个 points，没有覆盖 daily/monthly 端到端、单次 decision failure 放大、strategy semantics、next-open、历史 timestamps 或数值 oracle。
- prior browser evidence 证明页面能显示 persisted completed/failed result、chart、CSV 与 reload；它没有断言 trade count > 0、策略规则实际生效或 metric 数值正确。
- `skills/bundled/tool/backtest-diagnose/SKILL.md` 把 `trade_count=0` 视为 hard-gate failure；因此截图二按项目自己的 backtest diagnosis 标准也未通过。

## 2. 修复后的冻结契约

### 2.1 Backtest mode 与 Strategy eligibility

1. `mode="deterministic"` 是 canonical performance backtest：
   - request 必须解析出一个 versioned、typed、可执行的 `BacktestPolicySnapshot`；
   - 同一 strategy snapshot、data snapshot、engine version 与 config 必须产生相同 canonical economic payload/hash；完整 job JSON 的 operational IDs/timestamps 允许且必须独立；
   - 不允许在 bar loop 中调用 LLM。
2. `mode="agent_experiment"` 是可选实验模式：
   - 结果明确显示 stochastic / provider-dependent 警告；
   - 使用预先计算的 point-in-time feature snapshot 和单次 typed structured decision call，不再让模型自行选择 read tools；
   - bounded retry 只处理 transient/provider/schema category；不得 silent HOLD；
   - 失败保留 partial decisions、date、attempt 和 safe category。
3. Strategy 必须在 enqueue 之前同步解析并冻结：`BacktestJobService.create()` 先 resolve/validate Strategy，构造 immutable `BacktestRunSpec`，在同一 transaction 持久化 job + frozen spec，commit 成功后才 `executor.submit(job_id, frozen_spec)`；worker/`ActiveBacktestJobRunner` 禁止再次读取 mutable Strategy。
   - `quant`：v1 deterministic 的唯一受支持 type；必须有受支持的 `quant_strategy_name` 与 validated `quant_params`。首批只实现 `momentum` 与 `sma_crossover`，参数范围由 typed model 固定；
   - `agent`：v1 只允许 `mode="agent_experiment"`；本目标不增加自然语言 strategy compiler，避免把模糊描述编译成未经批准的隐藏规则；
   - `hitl`：v1 返回 `strategy_type_unsupported`；不得在历史循环中等待真人审批；
   - 完整 eligibility matrix：仅 `status="active"` 可运行，其他 status 返回 `strategy_inactive`；`tickers` 必须是非空 uppercase symbol list，request ticker 必须在其中，否则 `ticker_not_allowed`，空列表不是 wildcard；`initial_capital` 必须 finite 且 `>0`，`max_position_pct` 必须 finite 且 `0<value<=100`，`max_drawdown_pct` 必须 finite 且 `0<value<=100`，否则 `strategy_config_invalid`；deterministic 不读取/校验 `agent_model`，agent experiment 要求 non-empty `agent_model` 且 provider 支持 forced structured output，否则分别返回 `agent_model_missing` / `provider_capability_unsupported`。
4. 当前 `Tech Momentum` 的 `description="Try the best"`、空 beliefs、空 quant config 不得被系统暗中解释为某个 momentum 策略。它可以作为带强 warning 的 `agent_experiment` 运行，但不能产生 canonical performance；deterministic UI 应提示缺少 executable quant definition，并提供到 Strategy 配置页的明确路径。
5. Strategy New/Edit 必须让 `quant` 用户选择上述受支持 rule 并填写 typed params；否则系统中永远没有可从 UI 创建的 eligible deterministic Strategy。
6. LLM availability gate 必须 request-aware：deterministic 即使没有 `OPENAI_API_KEY` 也可创建/运行；只有 `agent_experiment` 做 provider/key capability preflight。当前全局 `BacktestJobService.can_start` bool 必须被替换为 mode-aware preflight。
7. deterministic rule v1 语义不得留给 executor 决定：
   - `momentum/v1` params：`lookback_bars` 为 2..252；`entry_threshold` 与 `exit_threshold` 为 decimal return，且 exit <= entry；`target_position_pct` 为 0..Strategy max。`close_t / close_t-lookback - 1 >= entry` 时 target=配置值，`<= exit` 时 target=0，中间区域保持当前 target。
   - `sma_crossover/v1` params：`fast_window` 为 2..100，`slow_window` 为 fast+1..252，`target_position_pct` 为 0..Strategy max。fast SMA > slow SMA 时 target=配置值，否则 target=0；不加未声明 hysteresis。
   - rule name/version/params 进入 policy hash；参数非法时 preflight reject。

### 2.2 Frequency、signal 与 fill timing

- `frequency` 只控制 rebalance/signal cadence；market data、valuation 和 equity series 保持 daily。
- request `frequency` 是本次 scenario 的显式 override；selected Strategy 的 `execution_frequency` 只作为 UI 初始默认值。result 同时保存 `strategy_execution_frequency` 与 `run_frequency`，避免覆盖关系不可见。
- Strategy 的 `max_position_pct` 当前是 0..100 百分数，进入 `BrokerConfig.max_position_pct` 前必须除以 100；`initial_capital` 直接使用正数 USD。v1 canonical 强制 `allow_short=false`。
- Strategy 的 `max_drawdown_pct` 在 v1 只作为 result risk limit/reference，不自动强平，因为当前字段没有冻结 liquidation/circuit-breaker timing contract；result 必须写 `max_drawdown_limit_enforced=false` warning，不能暗示已执行该风险控制。
- signal 在选定 trading bar 收盘后生成，只能看到该 bar 及之前的数据。
- market order 在下一可用 target trading bar 的 open 成交，并应用 fees/slippage；不得使用 signal bar close。
- weekly/monthly cadence 选择 period-end signal bar；下一交易日 open 执行。若 period-end signal 后没有 evaluation window 内下一 bar，则不生成不可执行信号，或记录为 `unfilled_end_of_window`，两者必须由一个固定实现与测试锁定；本计划采用“不生成最后一个不可执行 signal”。
- cadence 以 target exchange 的 session date 分组：week=`ISO Monday..Sunday`、month=`calendar month`；holiday 只改变该 period 的最后实际 target trading bar。首个 partial week/month 正常参与，末尾 partial period 仅在窗口内还有 next target bar 时参与。截图窗口 61 根 target bars 的 GREEN 精确计数是 `daily=60, weekly=12, monthly=2`；现状 `61/13/3` 只作为 RED evidence，不得继续当期望值。
- decision timestamp 与 order-created timestamp = signal bar close；Fill timestamp = execution bar open；三者独立持久化，全部来自 historical event clock。
- timezone 统一为 exchange/session calendar 对应日期；v1 只支持 daily bars，不引入 intraday ambiguity。
- policy output 的唯一仓位真值是 long-only `target_position_pct ∈ [0, max_position_pct]`；BUY/SELL/HOLD 由 target 相对 current position 派生。不得再让 LLM 同时输出 `action` 与 target，避免“80% 降至 50%”被解释成 target `-50%` 开空。必须锁定 `0→80`、`80→50`、`50→0`、`50→50` 四个仓位迁移 fixture。
- signal close 只持久化 target-position intent，不提前冻结 shares。next open 以 fill 前 cash/position、当日 open 经 slippage 后的 execution price、commission 和整数股规则计算可负担 target shares，再用 `delta=target_shares-current_shares` 派生 side/quantity；BUY 向下取整并为 fees 预留现金，SELL reduction 不得越过目标或产生负仓位。

该契约与 [Backtrader order execution 官方说明](https://www.backtrader.com/docu/order-creation-execution/order-creation-execution/)一致：已经观察到的当前 bar 不能再作为新 market order 的成交机会，market order 的自然下一价格是 upcoming open。VectorBT 官方示例也明确对 signal 做 forward shift 并在 open 成交，同时把 fees/slippage 作为显式模拟输入：[VectorBT Portfolio API](https://vectorbt.dev/api/portfolio/base/)。

### 2.3 Data、warm-up 与 reproducibility

- evaluation window 仍是 `date_from..date_to`；warm-up window 单独向前扩展，并由 policy 所需最大 indicator lookback 计算，不能写死为 100 calendar days。
- warm-up bars 由实际 policy 最大 lookback 派生，不把未使用的通用指标强塞给每条规则。evaluation 内早期 cadence 未 ready 时记录 `decision_status="not_ready"` 并跳过；若直到最后一个可执行 signal date 都不可能 ready，preflight/run 终止为 typed `insufficient_history`。progress 分别统计 `decisions_eligible/not_ready/completed`。
- v1 冻结 `provider_adjustment_mode="auto_adjusted_prices_v1"`：yfinance 使用 `interval="1d", auto_adjust=True, actions=False`，target/benchmark 一致；不再单独派发 split/dividend cash events，result 必须显示 `corporate_actions_mode="provider_adjusted_prices"` 及其 synthetic-adjusted-price limitation。provider name/version、完整 history args 与 timezone normalization 进入 snapshot/hash。官方 API 入口：[yfinance Ticker.history](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html)。
- raw data 与 derived features 分层：store 保存 source、adjustment mode、fetched_at；run 保存 symbol、date range、row count、first/last date、content hash、provider/version。`fetched_at` 只属 operational metadata，不进入 content hash/canonical replay comparison。
- 真正可重放不能只保存 hash。一个 snapshot BLOB 同时包含 target、benchmark normalized OHLCV 与 metadata，使用 UTF-8 canonical JSON（sorted keys、UTC/session-date ISO、finite decimal strings、无空白）后 gzip，SHA-256 针对未压缩 canonical bytes；job 引用一个 snapshot hash。hash 用于验证，snapshot 用于重放。不得把内部路径或原始 provider body 暴露给 API。
- v1 snapshot retention：只要任何 backtest job 引用就永久保留；当前没有 job-delete/GC API，因此本目标不实现 orphan GC。结果/API 回显 compressed/uncompressed byte counts，便于后续容量治理。
- feature 只从 `<= as_of` rows 计算；warm-up rows 不进入 performance series。
- cache hit 与 empty-cache preload 必须生成同一 data fingerprint 和结果；ambient older rows 不能改变一个 frozen request 的 feature values。
- 指标在交易前必须 ready。QuantConnect 官方同样要求在交易前 warm up indicator：[Warm Up Indicators](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/manual-indicators)。
- OHLCV boundary 必须验证 finite、unique、strictly increasing、volume>=0，以及 `low <= min(open, close) <= max(open, close) <= high`。

### 2.4 Execution、cost 与 end-of-window

- initial cash、commission、slippage、max position、allow short 从 frozen run config 进入 `BrokerConfig`，并回显在 result。
- v1 Strategy schema 没有 cost override，因此固定使用 engine defaults `commission_rate=0.001`、`slippage_rate=0.0005`；request 也不得覆盖。二者在 frozen run spec/result 同时显示 decimal 与 bps，保存实际 total fees/slippage。自定义 cost 是后续 typed schema 工作，不能从 arbitrary `quant_params` 读取。
- v1 不实现 volume participation/market impact；result 必须写 `capacity_model="not_modeled"` warning。后续扩展时再加基于 ADV 的 capacity。
- ending open position 默认 mark-to-market，不隐式强平；result 显示 end position、unrealized P/L 与 `liquidated_at_end=false`。
- rejected/cancelled/unfilled order 必须进入 order/decision evidence，不能因为 fills 为空而消失。

### 2.5 Metrics 与 benchmark

- `total_return = final_equity / configured_initial_capital - 1`，不是首个 post-trade snapshot。
- CAGR 使用 evaluation 的实际 calendar duration；annualized volatility / Sharpe 使用 daily equity returns 与明确 `periods_per_year=252`，risk-free 默认 0 并写入 result。
- max drawdown 是 peak-to-trough magnitude；duration unit 明确为 `trading_days`。
- `number_of_fills`、`number_of_orders`、`number_of_closed_trades` 分开；UI `Trades` 指 closed round trips，不再指 fills。
- win rate、avg win/loss、profit factor、payoff ratio 只基于 closed trades；开仓成本进入 position cost basis / net P&L，不单独伪装为 losing trade。
- v1 是 long-only average-cost episode ledger：flat→positive 开始一笔 episode，scale-in 用含费用/滑点的加权平均成本，partial reduction 产生 realized P/L 但不关闭 episode，positive→flat 才产生一笔 closed trade；closed-trade net P/L 累计该 episode 全部 entry/exit costs，holding period 从首次开仓 fill session 到最终平仓 fill session。期末仍 positive 只计 open position/unrealized P/L，不计 closed trade；short、direction flip/reversal fixtures 全部从本 Goal 删除。
- 曝光、turnover、total fees、total slippage、rejections、open position、realized/unrealized P&L 必须返回。
- target trading calendar 对 strategy loop 具有唯一权威；benchmark 缺 bar 不得删除 target bar或改变 signal schedule。benchmark 在比较层对 target dates left join，只允许把最近过去 bar forward-fill 最多 5 个 target sessions，禁止 bfill。若 evaluation 首日没有 benchmark bar，则 benchmark/excess metrics 全部为 `null` 并给 `benchmark_start_unavailable` warning，strategy full-window metrics 保持不变，禁止跨不同 horizon 相减。若首日可用，则 benchmark 与 strategy 使用同一完整 comparison horizon、同一 initial cash；benchmark 在首日 open 以 slipped price、commission、整数股向下取整且预留 fee，残余 cash 保留，期末 mark-to-market；超过 stale limit 的 benchmark/excess 为 `null` + warning。
- 对 `<63` evaluation bars、`<252` bars、`<30` closed trades 分别返回 sample-size warnings；允许描述性运行，但不得显示“统计上可靠”的暗示。
- 零交易是合法 terminal outcome `completed_no_trades`，但不是成功绩效验证；必须给出 reason distribution，例如 `no_signals`、`not_ready`、`all_hold`、`all_rejected`。只有“golden fixture 明确应入场但为零成交”才是 test failure；一般全程持币策略不应被强制改出交易。

### 2.6 Persistence 与 observability

每个 job 必须有：

- immutable request + strategy snapshot hash + policy hash + data fingerprint + engine version；
- progress：`bars_total`, `bars_processed`, `decisions_total`, `decisions_eligible`, `decisions_not_ready`, `decisions_completed`, `current_decision_date`；
- decision evidence：sequence、signal date、feature readiness/hash、policy output、target position、confidence、attempts、status；
- order/fill evidence：historical timestamps、status、rejection reason category、fees/slippage；
- safe failure：`code`, `stage`, `decision_date`, `attempt`, `message`；
- secret/provider hygiene：不保存 prompt、API key、raw provider body、base URL token、stack trace；内部日志也不得输出 secret。

当前历史失败的精确 provider/tool 子原因无法从既有 DB 还原；本计划确认并消除 compound failure architecture，但不得在实施报告中伪称已经还原每个旧 job 的具体 provider 根因。

`ContextStore` 是唯一 persistence owner。live repo 当前没有 migration registry，因此本 Goal 新建并唯一使用 `schema_migrations(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)`，本次固定 migration key=`20260712_backtest_contract_v1`；在一个 `BEGIN IMMEDIATE` transaction 内先创建 snapshot、再给 job 加 frozen references、再创建 decision FK/index，成功后插入 key，失败 rollback；启动时 key 存在即跳过，否则先用 `PRAGMA table_info` 做一致性检查，禁止再建 `PRAGMA user_version` 或第二套 registry。`ContextStore._get_conn()` 每个 connection 都执行 `PRAGMA foreign_keys=ON` 并断言返回 1；migration/restart tests 必须证明 invalid FK insert 失败、job delete 会 cascade decisions，但 snapshot 因 retention contract不会被 cascade 删除：

```sql
CREATE TABLE backtest_input_snapshots (
  content_hash TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL CHECK (schema_version = 1),
  codec TEXT NOT NULL CHECK (codec = 'gzip-json-v1'),
  payload BLOB NOT NULL,
  compressed_bytes INTEGER NOT NULL,
  uncompressed_bytes INTEGER NOT NULL,
  row_count_target INTEGER NOT NULL,
  row_count_benchmark INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
ALTER TABLE backtest_jobs ADD COLUMN contract_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE backtest_jobs ADD COLUMN run_spec_json TEXT;
ALTER TABLE backtest_jobs ADD COLUMN input_snapshot_hash TEXT REFERENCES backtest_input_snapshots(content_hash);
ALTER TABLE backtest_jobs ADD COLUMN progress_json TEXT;
CREATE TABLE backtest_decisions (
  job_id TEXT NOT NULL REFERENCES backtest_jobs(id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL,
  signal_date TEXT NOT NULL,
  execution_date TEXT,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL,
  target_position_pct REAL,
  confidence REAL,
  feature_hash TEXT,
  policy_hash TEXT NOT NULL,
  error_code TEXT,
  error_stage TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (job_id, sequence)
);
```

新 job 在 enqueue 前必须 `contract_version=1` 且有 `run_spec_json`，此时 `input_snapshot_hash=NULL` 是唯一允许的 pending state；worker 获取/验证数据后在一个 transaction 中 upsert snapshot + 绑定 job reference，commit 后才允许第一条 decision。数据失败时 job 可 terminal failed 且 hash 为空；只有非空 hash 的 job 可 replay。旧 row 保持 `contract_version=0`，由 view adapter 原样读旧 `result_json` 并追加 `legacy_result_unverified`，不回填伪 provenance。内部 replay owner 固定为 `BacktestJobService.replay(job_id)`：只读取 frozen run spec + snapshot，不访问 provider/Strategy；Todo 9 的 public `POST /api/agent/backtest/{id}/replay` 仅委托该方法。另一个普通 Run 才重新 resolve Strategy/取数。ACTIVE route 不直接写 SQLite。

## 3. Scope 与 Must NOT Have

### Scope IN

- 单 ticker、daily OHLCV、daily/weekly/monthly cadence、独立 benchmark。
- `agent/backtest_*`、`broker/backtest_*`、`broker/engine.py`、`broker/ledger.py`、`broker/views.py`、`dataflow` historical loader/store、`storage.ContextStore`、ACTIVE backtest route、frontend Backtest page，以及为创建 eligible quant policy 所必需的 Strategy New/Edit 最小字段与对应 docs/tests。
- deterministic quant rule policy 与明确标注的 agent experimental policy；HITL historical backtest 明确拒绝。
- numerical correctness、PIT/no-lookahead、reproducibility、typed errors、restart persistence、browser/manual QA。
- deterministic replay、sample sufficiency 与 overfitting warning；完整 walk-forward、parameter sensitivity、bootstrap/Monte Carlo、DSR/PBO 作为本 Goal 之后的独立 follow-up plan。研究背景可参考 [The Probability of Backtest Overfitting](https://escholarship.org/content/qt4hn4t174/qt4hn4t174.pdf)。

### Scope OUT / 禁止事项

- 不修改 `quick_ask/`；不扩展 frozen `server/routes/analyze.py`；不违反 `server/routes/_TRACKS.md`。
- 不新增 live broker、real-money execution、Redis/Celery/WebSocket、intraday/tick、multi-asset portfolio、options/futures margin。
- 不把 Strategy name 自动映射为隐藏规则；不把 missing decision 变成 silent HOLD；不把 experimental Agent 结果包装成 deterministic performance。
- 不依赖同-bar close fill；不使用 runtime clock 作为 historical order/fill timestamp。
- 不用全样本优化后再把同一全样本当 validation；不在 61 bars / 0 trades 上计算并宣称稳健性。
- 本 Goal 不实现参数优化、walk-forward、bootstrap/Monte Carlo、DSR/PBO；不得临时选择未冻结的 grid/seed/objective。
- 不引入 vectorbt 作为 production engine；若本地已有，可仅作 independent numerical oracle。不得为此无必要地下载大依赖。
- 不编辑/读取输出 `properties.env`；不提交 data DB、API key、provider response、runtime trace、浏览器 profile 或 `.omo/evidence/`。
- 不使用 `as any`、`@ts-ignore`、`@ts-expect-error`；不删除/弱化失败测试。
- 不运行 `git add .`、force push、reset hard；本计划没有 push/PR 授权。

## 4. Verification strategy

### 4.1 Test decision

- **TDD-first**。每个 behavioral boundary 先保存 RED，再做最小 GREEN；Implementation + Test 为同一 todo。
- Python 使用现有 pytest；Frontend 不引入新 test runner，pure helper 使用 `node --test frontend/test/*.test.mjs`，其余由 TypeScript/ESLint/build + real browser 覆盖。
- 每 phase evidence 写 `.omo/evidence/backtest-reliability-and-fidelity/phase-<N>/`，不纳入产品 commit。
- 所有 numeric tests 使用手算 fixture；断言具体 cash、position、fees、fill price、timestamp、equity、return、drawdown、closed-trade metrics，不接受 snapshot-only 或“非空”。

### 4.2 Baseline commands

```bash
git branch --show-current
git status --short --branch
git rev-parse HEAD
git rev-parse origin/dev
git rev-parse upstream/dev
.venv/bin/pytest -q \
  test/agent/test_backtest_adapter.py \
  test/agent/test_backtest_tools.py \
  test/agent/test_streaming_tool_executor.py \
  test/agent/test_tool_allowlist.py \
  test/broker/test_backtest_data.py \
  test/broker/test_backtest_runner.py \
  test/broker/test_engine.py \
  test/broker/test_ledger.py \
  test/broker/test_views.py
```

FastAPI `TestClient` 在当前 managed sandbox 内可能卡在 AnyIO portal；已证明沙箱外为 `12 passed, 1 warning`。执行时先在 sandbox 跑；若同一 faulthandler stack 指向 `starlette.testclient.__enter__`，按权限规则申请 sandbox-external 重跑，不能把它写成产品 failure，也不能跳过：

```bash
.venv/bin/pytest -q test/server/test_backtest_api.py test/server/test_job_service_lifecycle.py
```

### 4.3 每 phase gate

```bash
.venv/bin/pytest -q <focused-test-files>
.venv/bin/basedpyright --baselinefile bugs/basedpyright/baseline.json <changed-python-paths>
.venv/bin/ruff check <changed-python-paths>
.venv/bin/ruff format --check <changed-python-paths>
cd frontend && node --test test/*.test.mjs
cd frontend && npm run lint -- <changed-frontend-paths-if-supported>
cd frontend && npm run build
git diff --check
```

不得只保留点输出；每条 evidence 包含 command、exit code、assertion count 与关键数值。

### 4.4 Final gate

```bash
.venv/bin/pytest -q
.venv/bin/basedpyright --baselinefile bugs/basedpyright/baseline.json
.venv/bin/ruff check .
.venv/bin/ruff format --check .
cd frontend && node --test test/*.test.mjs
cd frontend && npm run lint
cd frontend && npm run build
git diff --check
git diff --name-only "$BASELINE_HEAD"..HEAD
git diff --name-only --cached
git diff --name-only
git ls-files --others --exclude-standard
# 对上面四类路径合并检查；任何 quick_ask/, server/routes/analyze.py,
# properties.env, data/*.db, secret/runtime/browser artifacts 均失败。
```

## 5. Execution strategy

### 5.1 Goal-mode 启动协议

每次 session / continuation：

1. 读取 `CLAUDE.md`、`PROGRESS.md`、`docs/development-plan.md`、`server/routes/_TRACKS.md`、本计划和 `bugs/bug-and-issues-list.md`。
2. 确认 branch=`dev`。首次 Goal session 固定 `BASELINE_HEAD=$(git rev-parse HEAD)`（规划时为 `289d728869e1745d0e8e936855032e9a3341abf2`）并写入 `PROGRESS.md` 的本 Goal section；所有 continuation 必须读取该值，若已存在禁止覆盖/重算。记录 `origin/dev/upstream/dev` 与 dirty worktree，保留所有非本任务变更，不覆盖其他 agent/user 文件。
3. 使用 `omo:debugging`、`tdd`、`omo:programming`；改 UI 后使用 `omo:frontend` + `omo:visual-qa`；最终使用 `omo:review-work`。本地量化参考仅使用 `/home/eden/.agents/skills/backtesting-frameworks/SKILL.md`；`skills/bundled/tool/backtest-diagnose/SKILL.md` 仅作为检查清单参考，其“0 trades 一律失败”规则被本计划 Section 2.5 的 typed outcome 契约覆盖。不得调用要求另建 VectorBT/OpenAlgo 脚本的 `/home/eden/.agents/skills/backtest/SKILL.md`，也不得把 vectorbt 引入 production。
4. 只执行最早未完成 todo；先 RED，后最小 GREEN；当前 phase gate 通过前不得进入下一 phase。
5. 每 phase 更新 `PROGRESS.md`；只有 final gate 后才更新 bug list。不得 push，除非用户另行授权。

### 5.2 Waves 与依赖

| Wave / Phase | Todos | Outcome | Hard dependency |
| --- | --- | --- | --- |
| Phase 1 | 1-2 | Characterization + frozen domain contract | baseline |
| Phase 2 | 3-4 | Strategy-aware deterministic/experimental decision policy | Phase 1 |
| Phase 3 | 5-6 | PIT warm-up + next-open historical execution | Phase 2 contract |
| Phase 4 | 7-8 | Correct accounting, closed trades, benchmark, metrics | Phase 3 |
| Phase 5 | 9-10 | Persistence/API + truthful frontend | Phase 4 result contract |
| Phase 6 | 11-12 | Deterministic replay + full QA/review/closeout | Phase 5 |

Phase 内仅并行互不写同一 owner 的 research/test lanes；`agent/backtest_jobs.py`、`broker/backtest_runner.py`、`broker/ledger.py`、`storage/store.py` 与 frontend contract 变更按依赖顺序串行集成。

## 6. Todos

- [x] 1. 固化 current-behavior characterization 与诊断 evidence

  **问题分析：** 当前测试没有固定现状 `61/13/3` decision count、Nth-decision failure、strategy config 未消费、same-bar fill、runtime timestamp、initial-cost denominator、fill-based win rate 与 cache-dependent warm-up。Phase 1 只保存可独立通过的现状 characterization/诊断证据；目标行为的 RED 由后续 owning todo 现场新增并立即最小 GREEN，避免跨 phase 长期红灯或 xfail。

  **解决方案：**

  - 为已有 current behavior 写能独立 GREEN 的 characterization tests/evidence：61 bars 当前调用 `61/13/3`、第 N 个 invalid decision 使 job generic fail、same-close fill、runtime timestamp、current denominator/trade classification、early shortened SMA。测试名称明确 `characterizes_current_*`，不得把缺陷写成目标契约。
  - 把 corrected `60/12/2`、next-open、historical clock、initial-capital accounting、warm-up、typed policy 等目标 tests 分别列入 Todo 2/5/6/7 的 RED checklist；对应 todo 开始时先证明 assertion RED，再改 production 并在同 todo GREEN。
  - 保存当前真实 SQLite aggregation 作为 diagnosis evidence，不把 `data/system.db` 纳入测试或 commit。

  **Must NOT do：** 此 todo 不改 production behavior，不调用真实 LLM，不创建依赖当前个人 DB 的 test。

  **References：** `agent/backtest_adapter.py:93-174`; `agent/backtest_jobs.py:117-272`; `broker/backtest_runner.py:77-199`; `broker/engine.py:43-88,151-234`; `broker/ledger.py:235-340,486-572`; `broker/backtest_data.py:40-146`；现有 matching tests。

  **验收标准：** Phase 1 gate 全绿；evidence 明确标记 `61/13/3` 仅为 current RED baseline，并记录 same-bar fill、runtime timestamp、5.003754% vs 4.924975%、entry fill win-rate misclassification；没有 xfail/skip/长期 RED。

  **QA：** `.venv/bin/pytest -vv` 精确运行新增 node IDs；failure scenario 使用 invalid structured decision；Evidence：`.omo/evidence/backtest-reliability-and-fidelity/phase-1/task-1-characterization.txt`。

  **Commit：** N；与 Todo 2 一起提交。

- [x] 2. 冻结 typed Strategy / Policy / Run / Result contract

  **问题分析：** Strategy 存储字段很多，但 backtest 没有“可执行策略”概念；result 也没有 run provenance、decision/order counts、warnings 或 mode。若先修 loop 再定义 contract，会继续把随机 Agent 输出当策略。

  **解决方案：**

  - 新建最小 ACTIVE owner `agent/backtest_policy.py`，定义 frozen Pydantic models：`BacktestPolicySnapshot`、`momentum` / `sma_crossover` deterministic variants、experimental agent policy、`StrategyEligibilityError`。
  - 扩展 `BacktestRequest`：保留现有字段并增加显式 `mode`，默认 deterministic；不增加多 ticker/intraday。
  - 扩展 `BacktestConfigView`：strategy/policy/data hashes、engine version、initial capital、costs、timing、adjustment、risk-free、sample metadata。
  - 扩展 result：`outcome`（`completed|completed_no_trades`）、`warnings`、`progress`、`decisions`、`orders`/counts、`end_position`、closed-trade metrics 与 provenance。
  - 在 `BacktestJobService.create()` 同步通过 injected resolver 从 `ContextStore` 获取/validate/freeze `BacktestRunSpec`，transaction persist 后才 enqueue；`ActiveBacktestJobRunner` 只接 frozen spec，禁止 worker 再读 Strategy。
  - eligibility 逐项实现 Section 2.1：active/non-empty ticker universe/membership/capital/max-position/mode/model/capability；preflight mapping 固定为 missing strategy `404 strategy_not_found`，其余用户配置/eligibility 错误 `422`，缺 provider/key/capability `503`。eligible quant + typed rule -> deterministic；agent -> experimental only；hitl -> unsupported；hollow quant -> `strategy_not_backtestable`。
  - 把 request frequency 定义为 run override；Strategy execution frequency 只提供 frontend default，并同时回显。把 Strategy `max_position_pct` 从百分数转换为 broker decimal，canonical long-only。
  - 把 LLM preflight 从全局 `can_start` bool 改为 request/mode-aware；deterministic 无 key 也能运行，experimental 才需要 provider capability。
  - 在 Strategy New/Edit 的 quant 分支增加受支持 rule/typed params；不加入自然语言 compiler。
  - 更新 `docs/api-contracts.md`，写明 field units、gross/net、frequency/timing、zero-trade 和 experimental warnings。

  **Must NOT do：** 不把 Pydantic model 放在 frontend/route；不让 broker import storage；不创建任意 JSON bag 替代 typed policy。

  **References：** `storage/store.py:97-214`; `server/routes/strategies.py:81-141`; `frontend/app/strategies/new/page.tsx`; `frontend/app/strategies/[id]/page.tsx`; `frontend/lib/types/models.ts:123-141`; `agent/backtest_jobs.py:31-163`; `server/routes/agent.py:304-313`; `broker/views.py:173-214`。

  **验收标准：** request/result JSON round-trip；OpenAPI exposes new typed fields；hollow Tech Momentum-shaped fixture 不能进入 deterministic；inactive/empty universe/wrong ticker/invalid capital/invalid percent/mode-model 逐项返回上述 code/status；Strategy 在 enqueue 后即使被修改/删除也不改变 run spec；受支持 quant fixture生成 stable policy hash；删除 LLM key 后 deterministic API 仍可 run，experimental 得 actionable 503。

  **QA：** TestClient create/poll with eligible + ineligible strategies；Pydantic JSON snapshot；Evidence：`phase-1/task-2-contract.txt`。

  **Commit：** Y；`test: characterize and freeze backtest contracts`。

- [ ] 3. 持久化 per-decision progress 与 secret-safe failure evidence

  **问题分析：** 当前 `BacktestDecisionError` 抹掉 date/stage，failed job 只有通用 message；frequency 越高越需要知道第几个 decision 失败。没有 partial evidence 就无法区别 provider、schema、tool、timeout 与 logic failure。

  **解决方案：**

  - 在 `storage/store.py` 添加 idempotent schema migration 与 `backtest_decisions` table；以 `(job_id, sequence)` 唯一，保存 signal/execution dates、status、attempts、target/confidence、safe error category、feature/policy hash 和 timestamps。
  - 精确实现 Section 2.6 SQL contract：单个 content-addressed target+benchmark snapshot BLOB；`backtest_jobs` 固定增加 `contract_version/run_spec_json/input_snapshot_hash/progress_json`；`backtest_decisions` 使用 `(job_id, sequence)` PK 与 FK。不得自行换成未规划 schema。
  - 把 job_id/progress/decision sink 从 `BacktestJobService` 注入 runner；broker 不 import ContextStore。
  - `BacktestDecisionError` 变成 typed exception，至少含 `code`, `stage`, `decision_date`, `attempt`; outer service 只持久化 allowlisted fields。
  - GET response 返回 progress 和 safe decision summaries；实现内部 `BacktestJobService.replay(job_id)`，public replay 只由 Todo 9 route 委托。CSV 不泄漏 prompt/provider body。
  - 增加 migration/restart/concurrency tests；两个 job 的 decisions 不得串线。

  **Must NOT do：** 不保存 prompts、model raw output、API key、provider URL/query、stack trace；不 broad-except 后丢 stage。

  **References：** `storage/store.py` backtest job methods；`agent/backtest_jobs.py:163-321`; `test/server/test_job_service_lifecycle.py`; `server/main.py` recovery。

  **验收标准：** Nth decision failure 后 GET 返回 `failed` + exact safe stage/date/attempt，前 N-1 decisions 仍可读；重启后 evidence 与 normalized input snapshot 可 replay；legacy DB 无损迁移且旧 completed job 可读并带 warning；secret sentinel 不出现在 DB/API/log。

  **QA：** tmp ContextStore migration + TestClient poll/restart；failure sentinel scan；Evidence：`phase-2/task-3-observability.txt`。

  **Commit：** N；与 Todo 4 一起完成 Phase 2。

- [ ] 4. 用 strategy-aware typed policy executor 替换 per-date ReAct tool-call chain

  **问题分析：** current loop 让模型先选择 `get_price/get_indicators`，再选择 decision tool；exact-one contract 对 provider/tool-call 行为高度敏感。模型还看不到 Strategy。修 retry 只能缓解，不解决随机性、成本、速度和可复现性。

  **解决方案：**

  - deterministic mode：`BacktestPolicyExecutor` 接受 frozen policy + point-in-time features，纯函数返回 long-only typed target position；bar loop 不实例化 `AgentLoop`。
  - 先支持最小可验证 rule families（建议 `momentum` 与 `sma_crossover`），参数必须来自 policy snapshot；不要根据 name 选择。
  - experimental agent mode：由代码先构建 typed feature snapshot，将 Strategy description/beliefs/risk/mode 显式放入 single-decision input；使用 one-shot structured target-position output/forced decision capability，不暴露 read tools，也不让模型单独输出 action。
  - execution side 由 target-current delta 派生；锁定 `0→80` BUY、`80→50` SELL reduction、`50→0` SELL close、`50→50` HOLD/no order；v1 禁止负 target/short。
  - 对 experimental call 分类 `transient`, `schema`, `provider`, `policy`；每 decision 最多 3 total attempts，exponential retry 只用于 transient；schema 可做一次 constrained repair；不 silent HOLD。
  - provider 不支持可靠 structured output 时 job preflight 返回 `provider_capability_unsupported`，不进入 61-bar 循环。
  - 保留 `agent/backtest_adapter.py` 作为 experimental adapter 或重命名/收窄；删除 production canonical path 对 restricted ReAct 的依赖，并更新 architecture tests。
  - deterministic canonical economic payload/hash 必须 stable；完整 job/result JSON 保持独立 operational UUID/timestamps。experimental results 必须显示 model/mode/attempt warnings。

  **Must NOT do：** 不批量把未来 feature snapshots 一次发给 LLM；不让 earlier decision 看到 later data；不把重试 exhaustion 转 HOLD；不修改 shared normal AgentLoop 行为来迁就 backtest。

  **References：** `agent/backtest_adapter.py`; `agent/loop.py:229-510`; `agent/tools/backtest.py`; `agent/run_context.py`; `test/architecture/test_backtest_track_boundary.py`。

  **验收标准：** deterministic daily/weekly/monthly fixture 不调用 LLM 且都完成；不同 policy 产生预期不同 decisions；仓位迁移四例精确通过；experimental scripted provider 的 transient retry 成功、schema exhaustion typed fail；61 decisions 不再出现 tool-call exact-one failure class。

  **QA：** injected fake policy/provider；call counter assertion；Evidence：`phase-2/task-4-policy-executor.txt`。

  **Commit：** Y；`fix: make backtest decisions typed and strategy aware`。

- [ ] 5. 建立 policy-derived warm-up、explicit adjusted data 与 run fingerprint

  **问题分析：** current loader 只 preload evaluation window；早期 SMA 用 1-5 bars 计算且无 readiness；已有 cache 中碰巧存在的旧数据会改变结果。yfinance adjustment 依赖默认值，run 无 data provenance。

  **解决方案：**

  - `BacktestPolicySnapshot` 暴露 required lookbacks；`BacktestDatasetPreparer` 计算所需 trading-bar warm-up，而非固定 calendar days。
  - `DataServiceHistoryLoader` 支持 warm-up + evaluation window；next-open 必须仍在 `date_to` 内，不额外越界抓 execution bar。provider `end` exclusive semantics 用 test 固定。
  - `YFinance._get_price_history()` 固定 `interval="1d", auto_adjust=True, actions=False`；store/snapshot 记录 `corporate_actions_mode="provider_adjusted_prices"`、provider/library version 和完整 args，不让不同 adjustment mode 静默混写。
  - `BacktestDataService.get_indicators()` 计算完整 RSI14、MACD12/26/9、SMA20/50、ATR14，返回 per-feature `ready`; 不足 history 不使用 shorter mean 冒充 SMA20/50。
  - 生成 canonical fingerprint；cache hit、fresh preload、backend restart 后相同。
  - target/benchmark 无 date overlap、duplicate dates、NaN/inf、non-monotonic index、invalid OHLC/negative volume 都 typed fail；benchmark missing bar 由 comparison-layer past-only alignment 处理，不得删 target bar。
  - readiness contract：evaluation 内早期 cadence 不 ready 则持久化 `not_ready` 并继续；整个 evaluation 无任何可执行 ready signal 才 `insufficient_history`。加入 split/dividend synthetic fixture，证明 adjusted series 不重复派发 corporate-action cash/quantity。

  **Must NOT do：** 不在 historical decision 时 live fallback；不把 warm-up rows 计入 performance；不依赖 ambient cache。

  **References：** `broker/backtest_data.py`; `dataflow/history.py`; `dataflow/providers/YFinance.py`; `dataflow/store.py`; `test/dataflow/test_yfinance_provider.py`; `test/dataflow/test_market_data_store.py`。

  **验收标准：** first eligible decision 只在 required features ready 后发生；早期 `not_ready` 与终态 `insufficient_history` 分支均有精确 counts；空/热 cache fingerprints 与 features 相同；future sentinel 不可见；adjustment/provider args/corporate-action limitation 在 result 回显；benchmark 缺一日不改变 target decision/fill dates；input snapshot hash 能 replay identical normalized rows。

  **QA：** isolated SQLite + fake historical provider + future sentinel；Evidence：`phase-3/task-5-data.txt`。

  **Commit：** N；与 Todo 6 一起完成 Phase 3。

- [ ] 6. 修正 cadence、next-open execution、historical timestamps 与 end-of-window

  **问题分析：** current engine 先 publish close，再 decision，再 same close fill；Order/Fill 默认 runtime `_utc_now`。weekly/monthly 取 period first bar，且 timing 未定义。

  **解决方案：**

  - 将 runner event order 固定为：`on_bar(open)` 执行 pending -> mark/valuation -> at close evaluate selected signal date -> queue order。
  - `execution_timing="next_open"` 成为 backtest canonical；`close_bar` 只能保留给明确非 historical 的其他 broker tests，不得被 BacktestJobRunner 使用。
  - weekly/monthly signal dates 使用 period end；daily 使用每个 eligible bar close；最后无下一 bar 的 signal 不生成。
  - 按 Section 2.2 的 session-date algorithm 固定 week/month/holiday/partial-period；AAPL/SPY `2024-01-02..2024-03-29` 61-bar fixture GREEN 精确为 `60 daily / 12 weekly / 2 monthly`。
  - pending object 只保存 signal metadata + target-position intent；next open 用 pre-fill equity/cash、slipped open、commission 与整数股向下取整规则计算 affordable target shares，再派生 delta order。
  - 向 `MockBrokerEngine.on_bar` 传 historical bar timestamp，Order/Fill 在 backtest scope 使用 decision/execution timestamp；normal broker runtime defaults 不被破坏。
  - ledger snapshot 顺序保证 fill 后、close valuation；首个 evaluation bar 即使没有交易也记录 initial equity。
  - 记录 end open position，不强平；rejected/unfilled orders 进入 evidence。

  **Must NOT do：** 不通过 `shift` 文案或 prompt 假装防前视；必须由 runner/engine state order 强制。

  **References：** `broker/backtest_runner.py`; `broker/engine.py`; `broker/models.py`; `broker/config.py`; `test/broker/test_engine.py`; Backtrader/VectorBT official references in Section 2。

  **验收标准：** signal at 100 close, next open 109 时 buy fill=109*(1+slippage)，绝不为 100；fill date=next historical date；gap-up/down + fee affordability + `80→50` reduction fixtures 的 cash/shares 精确；61-bar cadence=`60/12/2`；timezone/holiday/partial period golden tests 通过；last signal policy 固定。

  **QA：** 3-bar gap fixture + weekly/month boundary + missing next bar；Evidence：`phase-3/task-6-execution.txt`。

  **Commit：** Y；`fix: enforce point-in-time next-open backtest execution`。

- [ ] 7. 重建 initial-capital accounting、positions 与 closed-trade ledger

  **问题分析：** return denominator 排除首日 costs；fills 被当 trades；entry fee 是 losing realized P/L；open positions 的 realized/unrealized/end state 不完整。

  **解决方案：**

  - `TradeLedger` 保存 initial snapshot / run initial capital；metrics 分母固定为 configured initial capital。
  - 引入/内聚 long-only average-cost episode reconstruction，不新建泛化 portfolio framework；严格按 Section 2.5 处理 scale-in、partial reduction、final flat、fees/slippage 与 holding period。
  - 分离 orders/fills/closed trades；opening fill 的 costs 进入 net position P/L，不单独计 loss。API/view 明确暴露 `executions`（fills）与 `closed_trades`，holding/win/PF 只基于后者。
  - 计算 realized/unrealized/net P&L、fees、slippage、turnover、exposure、rejections、end position。
  - 保持 session/strategy/account identity isolation；runner reuse 不串 ledger。
  - 用 Decimal 或精确 tolerance；units 在 views/docs 固定。

  **Must NOT do：** 不为 single-ticker scope 引入 speculative multi-asset accounting；不隐藏 open positions。

  **References：** `broker/ledger.py`; `broker/models.py`; `broker/views.py`; `test/broker/test_ledger.py`; `test/broker/test_views.py`。

  **验收标准：** Section 1 golden fixture total return=4.924975%；entry-only run closed trades=0 而 fills=1；scale-in/partial-exit/final-flat 的 average cost、net realized P/L、episode cost allocation、holding period、win rate/PF 与手算一致；ending open episode 只计 unrealized。

  **QA：** hand-calculated long/scale/partial-exit/flat/open-ending fixtures；Evidence：`phase-4/task-7-ledger.txt`。

  **Commit：** N；与 Todo 8 一起完成 Phase 4。

- [ ] 8. 修正 benchmark、risk metrics、sample warnings 与 zero-trade semantics

  **问题分析：** current benchmark 是简单 rebased closes；strategy/benchmark costs 不同；duration unit 不明；0 trades 被无警告显示为 completed。

  **解决方案：**

  - 按 Section 2.5 构建 investable benchmark：首日缺 bar 则 benchmark/excess 为 null；否则相同 full horizon，past-only ffill 最多 5 target sessions；首日 open integer shares、slippage、commission、fee-reserved cash、residual cash全部进入 golden fixture。
  - 修正 total/CAGR/volatility/Sharpe/drawdown/duration，risk-free 与 annualization factors 明示。
  - 添加 exposure、turnover、fees、slippage、closed trades、realized/unrealized；对 inf/NaN 定义 JSON-safe outcome，不把 `Infinity` 发到 frontend。
  - `completed_no_trades` + reason counts；`all_rejected` 与 `all_hold` 分开。
  - 添加 `<63`, `<252`, `<30 closed trades` warnings；61-bar screenshot case必须显示 insufficient sample + no trades。
  - 只返回后续稳健性分析所需的 sample warnings/metadata；本 Goal 不加 optimizer 或 walk-forward inputs。

  **Must NOT do：** 不用全 period optimize；不在 sample insufficient 时伪造 confidence/accuracy。

  **References：** `broker/ledger.py:235-340`; `broker/views.py:451-560`; `frontend/components/backtest/backtest-metrics.tsx`。

  **验收标准：** independent hand oracle 与 implementation 在每个 metric tolerance 内一致；zero trade 不再显示普通 completed；benchmark/excess gross/net contract test 固定。

  **QA：** flat/monotonic/drawdown/NaN/zero-trade fixtures；Evidence：`phase-4/task-8-metrics.txt`。

  **Commit：** Y；`fix: correct backtest accounting and performance metrics`。

- [ ] 9. 完成 persisted API migration、typed errors、progress 与 exports

  **问题分析：** 前面新增的 policy/provenance/decisions/metrics 必须稳定跨重启；旧 result rows 可能缺字段；CSV 当前只有 fills 且没有 decision/order export。

  **解决方案：**

  - 完成 `ContextStore` idempotent migrations 与 legacy result parsing policy；旧 completed result 仍可读但带 `legacy_result_unverified` warning，不伪装成新 contract。
  - `POST /api/agent/backtest` preflight mapping 固定：missing strategy=404；inactive/ineligible/ticker/config/request=422；experimental provider/key/capability unavailable=503；成功同步冻结 spec 后返回 202 `{id,status:"pending",contract_version:1}`。202 后 data/decision/execution/storage/interruption 不改 HTTP 状态，poll GET 返回 200 terminal job envelope。
  - `GET /api/agent/backtest/{job_id}` 固定 envelope：顶层 `id/status/request/config/progress/decisions/result/error/created_at/updated_at`；`progress={bars_total,bars_processed,decisions_total,decisions_eligible,decisions_not_ready,decisions_completed,current_decision_date}`；仅 failed 时 `error={code,stage,decision_date,attempt,message}`，仅 terminal success 时 `result={outcome,warnings,metrics,equity,orders,fills,closed_trades,end_position,provenance}`。不存在 job=404，非法 ID=422。
  - `POST /api/agent/backtest/{job_id}/replay` 只复用 frozen spec+input snapshot，成功 202 返回新 job identity；legacy/missing snapshot=409 `replay_unavailable`。普通 page Run 仍是重新 resolve/fetch 的 create，不得把两种语义都叫 Retry。
  - 保留 `GET /api/agent/backtest/{job_id}/trades.csv` legacy fills columns `date,ticker,side,quantity,price,realized_pl,equity_after`，但 UI 标为 Executions；新增 `GET .../closed-trades.csv` columns `entry_date,exit_date,ticker,quantity,entry_vwap,exit_vwap,net_realized_pl,fees,slippage,holding_period_trading_days`，`GET .../decisions.csv` columns `sequence,signal_date,execution_date,status,target_position_pct,confidence,attempts,error_code`，`GET .../decisions.json` 返回同字段 JSON array。CSV=`text/csv; charset=utf-8`，JSON=`application/json`，下载均有 sanitized `Content-Disposition: attachment; filename="backtest-{id}-<kind>.<ext>"`；非 terminal/export unavailable=409。
  - OpenAPI/docs 覆盖 error codes：`strategy_not_found`, `strategy_inactive`, `strategy_not_backtestable`, `strategy_type_unsupported`, `ticker_not_allowed`, `strategy_config_invalid`, `agent_model_missing`, `provider_capability_unsupported`, `insufficient_history`, `decision_transient_exhausted`, `decision_schema_invalid`, `execution_failed`, `storage_corrupt`, `interrupted`, `replay_unavailable`。
  - Strategy create/update boundary 同步用 discriminated typed quant policy models验证 rule/version/params；非法 payload 422，store 不再接受这些字段的 arbitrary dict。
  - API response/log secret sentinel tests。

  **Must NOT do：** 不把 raw exception/provider response 返回前端；不破坏 active job persistence hook。

  **References：** `agent/backtest_jobs.py`; `storage/store.py`; `server/routes/agent.py:304-334`; `frontend/lib/api/backtest.ts`; `frontend/lib/backtest-id.ts`。

  **验收标准：** create→progress→terminal→export→backend restart→same result；legacy row typed warning；invalid/traversal IDs 仍拒绝；two concurrent jobs isolation。

  **QA：** real FastAPI curl/TestClient + restart；Evidence：`phase-5/task-9-api/`。

  **Commit：** N；与 Todo 10 一起完成 Phase 5。

- [ ] 10. 把 Backtest UI 改成 strategy-aware、truthful、可诊断的结果面

  **问题分析：** 当前 UI 只显示通用 failed 或普通 completed；用户看不到 strategy 是否可执行、mode、progress、decision/rejection、costs、warnings、open position 与 reproducibility。

  **解决方案：**

  - 增加 explicit mode selector。quant + supported rule 默认/允许 deterministic；agent 只允许 agent experiment；hitl 无可选模式并禁用 Run。切换 Strategy 时清理不兼容 mode，不保留 stale eligibility。
  - strategy selector 显示 type + per-mode backtest eligibility；ineligible 时禁用 Run 并显示缺失字段/配置链接。
  - frequency 文案改为 rebalance cadence；显示 signal-at-close / fill-next-open、adjustment、costs、initial capital、mode。
  - running state 显示 `decisions_completed/total` 和 current date；保留现有 sessionStorage/URL persistence。
  - failed state 显示 safe stage/date/attempt 和针对性 action；按钮明确分成 `Replay same snapshot`（调用 replay endpoint）与 `Run with current strategy/data`（普通 create），不隐藏根因或混淆复现/重取数。
  - completed result 显示 warnings、outcome、fills/orders/closed trades、fees/slippage、end position、sample sufficiency、policy/data hashes 的短标识。
  - `completed_no_trades` 使用 warning/empty-state styling，不显示为普通成功；列出 no-signal/all-hold/all-rejected reason。
  - chart 保留 daily strategy/benchmark/drawdown；tooltips/units 与 contract 一致；decisions/trades table 区分。
  - 抽取 pure result-state helper 并用 Node test 覆盖 eligibility/outcome/warnings；不引入 Jest/Vitest。

  **Must NOT do：** 不在 frontend 重算 metrics；不把 experimental mode 警告藏在 tooltip；不破坏 390px viewport/keyboard/focus。

  **References：** `frontend/app/backtest/page.tsx`; `frontend/components/backtest/backtest-metrics.tsx`; `frontend/lib/types/models.ts`; `frontend/lib/use-persisted-backtest-id.ts`; `frontend/test/backtest-id.test.mjs`。

  **验收标准：** TypeScript/lint/build；real browser 能区分 quant deterministic、agent experimental、hitl unsupported、eligible/ineligible、running progress、typed failure、no-trades warning、traded result；deterministic 在无 LLM key 时可运行；reload/navigation 恢复同 job；zero console/page errors；390px 无 overflow。

  **QA：** agent-browser/Playwright production Chromium，desktop 1536x960 + mobile 390x844，network/console/error capture；Evidence：`phase-5/task-10-browser/`。

  **Commit：** Y；`feat: expose trustworthy backtest diagnostics and results`。

- [ ] 11. 固化 deterministic replay、canonical result hash 与 sample-truthfulness

  **问题分析：** 即使 simulation 正确，单窗口、单 ticker、少量 trades 仍不能证明策略有效。当前 Goal 能交付 engine fidelity 与 decision reproducibility；out-of-sample robustness 需要另一个明确选择 split/grid/objective/seed 的计划，不能在此保留研究提纲。

  **解决方案：**

  - 增加 deterministic replay check：同 frozen run spec + snapshot 重跑，canonical result hash、metrics、decisions、fills、closed trades、daily equity 完全一致。
  - canonical comparison payload 只包含 versioned policy/config/data hashes、ordered decision economics、ordered order/fill/closed-trade economics、equity/metrics/warnings；排除 job/session/account/order/fill/decision UUID、created/updated/provider-fetch/runtime timestamps、retry operational metadata。历史 signal/order/fill session dates是经济语义，必须包含。JSON canonicalization沿用 snapshot规则。
  - 运行 10 次时既断言 canonical hash 相同，也断言所有 operational UUID 唯一；不能通过复用 IDs 伪造稳定性。
  - UI 使用 “Backtest fidelity / Sample sufficiency”，并显示 “Out-of-sample robustness: not evaluated”；避免 “prediction accuracy”。
  - 另建 future-work 条目，明确 walk-forward、sensitivity、bootstrap/Monte Carlo、DSR/PBO 在独立 planning session 冻结后实施；本 Goal 不创建半成品 API/module。

  **Must NOT do：** 不实现或展示 walk-forward/Monte Carlo/parameter optimization/DSR/PBO；不把未评估写成通过；不把 UUID/timestamp 差异错误纳入 economic result hash。

  **References：** local `backtesting-frameworks` skill；Section 2 external research；canonicalization owner 放在 backtest result/domain owner，不耦合 route/UI。

  **验收标准：** 10-run stable fixture 的 canonical hash/经济字段一致且 operational IDs 唯一；修改一个 OHLC、policy param、cost 或 engine version 均改变 hash；insufficient sample 显示 warnings，OOS 明确 `not_evaluated`。

  **QA：** frozen-snapshot replay + one-field mutation matrix；Evidence：`phase-6/task-11-replay.txt`。

  **Commit：** N；与 Todo 12 完成最终 closeout。

- [ ] 12. 运行 frequency acceptance matrix、numerical oracle、真实 API/Browser 与 final reviews

  **问题分析：** 只有所有层同时通过，才能避免再次出现“测试绿、页面绿、经济语义错”。

  **解决方案与验收矩阵：**

  1. **Deterministic AAPL/SPY matrix**：同一个有明确可执行规则的 Strategy，运行至少 2 年窗口的 daily/weekly/monthly；每种 cadence 连续运行至少 10 次，全部 terminal、无 `agent_failed`；按 Todo 11 canonical payload 比较，hash/decisions/fills/closed trades/equity/metrics 完全一致且 operational IDs 唯一；decision dates 与 cadence contract 一致；至少一个 fixture 有 closed trades。
  2. **Original 2024 reproduction**：AAPL/SPY `2024-01-02..2024-03-29`、61 个 target sessions；现状 RED=`61/13/3`，修复后 GREEN 必须精确 `60/12/2`；三种 frequency 都不因结构化 decision 失败；若 Strategy hollow，三个都一致 typed ineligible；若使用 valid policy，三个都完成且显示 sample warnings。
  3. **Numerical oracle**：gap/open/fees/slippage/round-trip fixture逐字段对照手算；可选 vectorbt oracle仅在本地已存在时运行。
  4. **Failure matrix**：insufficient history、no overlap、provider unavailable、unsupported policy、all HOLD、all rejected、experimental transient exhaustion、restart interruption、storage corruption。
  5. **Persistence**：completed/failed/partial decisions 经过 backend restart 后相同；same-snapshot replay 不触发 provider/Strategy read；re-fetch Run 与 replay 在 UI/API 可区分；三类 CSV 与 decisions JSON 的 columns/content-type/disposition 正确。
  6. **Browser**：production Next + FastAPI，desktop/mobile；实际点击 Run、等待 terminal、检查 progress/warnings/chart/tables/download/reload；console/page/request failure 为空。
  7. **Debugging audit**：至少三条 runtime hypothesis，各有 observed evidence；包含 no-lookahead、strategy snapshot use、accounting denominator。
  8. **Review**：运行 `omo:review-work` 的 goal/quality/security/context/QA lanes，全部 unconditional PASS；运行 `omo:visual-qa`；任何 timeout/ack-only/inconclusive 都不算通过。
  9. **Docs/tracker**：更新 `PROGRESS.md`、`docs/api-contracts.md`、必要 architecture/data docs；只有上述全部通过后，才更新 `bugs/bug-and-issues-list.md`。

  **Must NOT do：** 不以 source inspection、mock browser 或旧 screenshot 替代真实运行；不因 provider credential 缺失伪造 experimental QA。若外部 LLM 未获授权，canonical deterministic matrix 仍必须完整通过，并把 experimental external probe 明确列为未验证而不是 blocker。

  **验收标准：** full gate 全绿；no secrets/unrelated files；plan compliance、code quality、manual QA、scope fidelity/security 全部批准。

  **Evidence：** `.omo/evidence/backtest-reliability-and-fidelity/final/`。

  **Commit：** Y；`fix: make backtests reliable reproducible and numerically sound`。本地 commit 后停止；不 push。

## 7. Final verification wave

- [ ] F1 **Plan compliance audit**：逐条核对 12 todos、Must NOT、frequency/timing/eligibility/metrics contract；拒绝用 experimental success 代替 deterministic core。
- [ ] F2 **Code quality + architecture**：检查 ACTIVE/SHARED boundaries、typed models、migration、concurrency、secret safety、无重复 owners/compat shims。
- [ ] F3 **Hands-on QA**：真实 FastAPI + production Chromium；original reproduction + deterministic 2-year matrix；下载/重启/mobile/console。
- [ ] F4 **Numerical and quant review**：独立手算 fill/cash/equity/P&L/benchmark/drawdown/Sharpe/sample warnings；检查 no-lookahead、warm-up、adjustment、OOS。
- [ ] F5 **Scope fidelity/security**：确认 `quick_ask/`、`server/routes/analyze.py`、`properties.env` 未变；无 secrets、data DB、runtime artifacts、provider raw body；无 push。

F5 必须把 session 开始记录的 `BASELINE_HEAD` 到 `HEAD`、staged、unstaged、untracked 四类路径合并检查，不能用 phase commit 后为空的单次 `git diff` 代替。

所有 F1-F5 必须 unconditional PASS。发现 defect 时回到对应 todo 写 RED、最小修复、重跑 phase gate 与 final wave；不得在 reviewer report 中把 blocker 降级为 future work。

## 8. Commit strategy

建议最多 6 个本地 atomic commits：

1. `test: characterize and freeze backtest contracts`
2. `fix: make backtest decisions typed and strategy aware`
3. `fix: enforce point-in-time next-open backtest execution`
4. `fix: correct backtest accounting and performance metrics`
5. `feat: expose trustworthy backtest diagnostics and results`
6. `fix: make backtests reliable reproducible and numerically sound`

每个 phase gate 通过后允许创建对应 atomic local commit；每个 commit 前更新本 phase `PROGRESS.md`、逐文件 `git add <owned-path>`、检查 staged diff。只有 final gate 后才更新 bug list并创建 final closeout commit。遵守 repo commit body/Co-Authored-By 约定。用户未授权 push；final local commit 后报告并停止。

## 9. Success criteria

- daily/weekly/monthly 不再因 decision 数量增加而出现架构性的 `agent_failed`；canonical deterministic path 不调用 LLM。
- original AAPL/SPY 窗口三种 cadence 行为一致且 truthful：valid policy 完成，hollow policy 一致 typed reject。
- selected Strategy 的 executable semantics、capital、risk、mode 被 frozen 和消费；不同 policy 有可验证不同 decisions。
- no look-ahead：signal close、next open fill；historical timestamps 正确；warm-up/PIT/adjustment/data hash 正确。
- returns/costs/closed trades/drawdown/benchmark 与独立手算一致；initial costs 不丢失；fills 不再冒充 closed trades。
- zero trades、all HOLD、all rejected、insufficient sample、open end position 和 experimental nondeterminism 都在 API/UI 明示。
- partial progress/decision/failure evidence 跨重启保留且不泄漏 secret。
- focused/full tests、type、lint、format、build、real API、production browser、numerical oracle、debug audit、visual/review lanes 全部通过。
- 没有修改禁区、没有无关 diff、没有 push/PR。

## 10. 最简 Goal-mode 启动提示词

在 `cwd=/home/eden/MasterGraduation/COMP7705-Agent-Quant`、branch=`dev` 上，严格按 `plans/backtest-reliability-and-fidelity/backtest-reliability-and-fidelity-plan.md` 从最早未完成 todo 开始执行；先读 repo guardrails 与本计划，首次 session 将 `BASELINE_HEAD` 写入 `PROGRESS.md`、continuation 只读取且禁止重算，并保留 dirty worktree；使用 TDD-first（Todo 1 仅固化当前 GREEN characterization；Todo 2 起每项现场 RED→最小 GREEN），不得修改 `quick_ask/`、`server/routes/analyze.py`、`properties.env`，不得 silent HOLD、same-bar fill 或把 0 trades/agent experiment 当可信绩效；每个 phase gate 通过后可做对应 atomic local commit并更新 `PROGRESS.md`，最终用 `BASELINE_HEAD..HEAD` + staged/unstaged/untracked 做 scope audit，运行真实 API/Chromium、numerical oracle、debugging audit、visual QA、review-work 与 full gate，全部 unconditional PASS 后才更新 bug list并做 final closeout commit，随后停止且不要 push/PR。
