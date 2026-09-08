# Frontend Demo To Real Functionality Work Plan

<!-- markdownlint-disable MD013 -->

## TL;DR (For humans)

**What you'll get:** 把 Strategies/Memory、Backtest、Scanner、Risk、Reports 和 Notifications 从“看起来可用”收口为真实、可持久化、可失败、可复现的端到端功能；所有页面不再用固定示例冒充运行结果。

**Why this approach:** 先修复已经具备后端能力但缺前端接线的路径，再按 Backtest → Scanner → Risk → Reports 的真实依赖补齐后端；现有 broker、DataService、ContextStore、MemoryService 和通知 channel 保持各自 owner，不复制业务逻辑。

**What it will NOT do:** 不修改 frozen `quick_ask/`，不接真实券商，不引入 Redis/Celery，不伪造指数 universe、多资产 backtest 或 portfolio positions，不顺手实现当前 UI 中不存在的通知 channel。

**Effort:** XL

**Risk:** High - 跨 FastAPI、SQLite、agent track、历史数据隔离、React server state 和真实浏览器验收；其中 Backtest no-lookahead 与 Scanner Agent track 是主要风险。

**Decisions to sanity-check:** Backtest v1 只支持单 ticker；Scanner v1 只支持 tracked universe；Risk 明确计算“最新 decision target exposure”而不是不存在的 live broker portfolio；Sector Report 先产生并持久化 Scanner run，再消费该 run。

Your next move: 在新的 Goal-mode session 中把本文件作为唯一行动指南执行；若希望先提高计划置信度，可先运行 dual high-accuracy plan review，但不要在未读本文件和 `CLAUDE.md` 的情况下直接编码。

---

> TL;DR (machine): XL/high-risk; 7 个顺序 phase，TDD-first，每个 phase 完成后 commit + push `origin/dev`，最后才更新 issue tracker。

## Scope

### 目标

在当前 `dev` 分支上，处理 [bug-and-issues-list.md](../../bugs/bug-and-issues-list.md) 的 `Unimplemented Functions` 与 Notifications issue。最终状态必须满足：

1. 用户点击的控件要么调用真实 API 并展示真实状态，要么被删除/改名以准确表达当前能力；不保留 decorative success path。
2. 成功结果必须可通过现有存储边界重新读取；刷新页面或重启后，不得无理由恢复为 mock/default。
3. 缺数据、缺配置、失败和重启中断必须成为显式状态；禁止用空数组、零值或固定样例掩盖错误。
4. 每个 phase 都以测试、API 驱动和真实浏览器驱动三类证据中的适用项闭环，然后独立提交并推送到 `origin/dev`。

### Goal-mode 硬性工作规则

以下三条是用户对后续 Goal-mode 执行 agent 的显式授权和要求，必须原样保留、不得弱化：

- `agent 可以自行从本地 skills 中挑选最相关最合适的使用`
- `互联网检索工具和高级调试工具完全开放`
- `按照合适的线索将任务划分阶段, 在 goal 模式迭代过程中, 每完成一个阶段, 就用 git 向 origin/dev 分支提交并推送`

执行解释：

- 每个 phase 开始时，agent 可重新选择适用 skill；推荐但不限定 `omo:programming`、`omo:frontend`、`omo:debugging`、`omo:visual-qa`、`agent-browser`、`tdd`、`codebase-design`、`api-design-principles`、`omo:git-master`、`omo:review-work`。选中 skill 后必须完整读取其 `SKILL.md` 并服从本文件的范围锁。
- 可使用互联网检索、官方文档、浏览器自动化、Playwright/agent-browser、curl、OpenAPI、LSP、日志、临时 SQLite、pytest monkeypatch 和运行时 instrumentation。开放工具不等于开放 secrets 或破坏性操作：仍然禁止读取/打印真实 secret、编辑 `properties.env`、绕过 sandbox、安全边界或 force push。
- “每完成一个阶段”指本文件 Phase 1 至 Phase 7 的 phase gate 全部通过后；phase 内部不得为了制造进度而提交半成品。

### 当前实现事实与分类

| 清单项 | 当前事实 | 分类 | 本计划动作 |
| --- | --- | --- | --- |
| Backtest | `frontend/app/backtest/page.tsx:49-115` 直接使用 `MOCK_RESULT`；Run/Export 无 handler；`broker/backtest_runner.py:39-137` 和 `broker/views.py:191-213` 已有真实 core/view，但 runner 顶层默认导入旧 `agentgraph.orchestrator` | 前端 demo；domain core 可复用，但 agent track、不前视、job/API/persistence/frontend 均未闭环 | 让 broker runner 强制注入 agent；在 ACTIVE `AgentLoop` 建结构化 adapter；采用 canonical broker view，补 no-lookahead/job/UI/CSV |
| New Strategy 不更新 | `frontend/app/strategies/new/page.tsx:43-84`、`server/routes/strategies.py:28-142`、`storage/store.py:45-133` 已是真实 CRUD | 清单陈述已过时；不是缺实现 | 不重复实现 CRUD；补 regression、lifecycle/clone 和 query invalidation |
| Memories 不更新 | `frontend/app/memory-lab/page.tsx:33-50` 与 `server/routes/memory.py:16-56` 已真实读取 strategy-scoped memory；Quick Ask UI 未发送已有 `strategy_id` | 身份接线缺口，不是策略创建缺口 | Quick Ask 增加 strategy selector 并发送现有字段；创建策略本身不制造 memory |
| Scanner | `frontend/app/scanner/page.tsx:35-70,149-221` 静态结果，三个 scan 按钮无请求；只有 `frontend/lib/api/scanner.ts` stub | 前后端均缺真实闭环 | tracked universe、deterministic engine、ACTIVE agent compiler、run persistence、真实页面 |
| Risk | `frontend/app/risk/page.tsx:40-139` 及后续所有指标固定；切换 selector 只改控件值；无 production service/route | 前后端均缺；且没有 persistent live portfolio | 从真实 latest decision targets + 历史行情计算，清楚标注 source；无数据则 unavailable |
| Reports | `frontend/app/reports/page.tsx:28-182` 固定 history；buttons/download 无 handler；`utils/pdf_generator.py:201` 有 renderer 但无 repository/routes | renderer 已有，其余为 demo | 消费真实 analysis/scan artifacts，持久化 metadata/status，安全生成与下载 PDF |
| Notifications | `server/routes/settings.py:166-210` 与 `notification/channels.py:78-310` 已有 Email/Telegram/WeChat/WhatsApp 真实发送 | 不是 demo；问题是 onboarding/status/错误可理解性 | 补 configured-state、内联帮助、官方链接、测试反馈和文档；不扩 channel |

### 问题分析

#### A. Demo 数据与真实 domain contract 分叉

Backtest frontend/types/docs 仍描述 prediction accuracy/confusion matrix，而合并后的 broker domain 已输出 portfolio equity、drawdown、trades 和 performance metrics。继续为旧 UI 造 adapter 会把 mock contract 固化为第二个 source of truth。解决方向是删除旧契约，让 `BacktestResultView` 成为唯一结果 shape。

#### B. “有 client stub”被误认为“有 backend”

`frontend/lib/api/backtest.ts`、`scanner.ts`、`risk.ts`、`reports.ts` 只证明页面设计过接口，不证明 FastAPI 注册过路由。`server/main.py:127-137` 当前没有 backtest/scanner/risk/reports router。因此每个 slice 都必须从 OpenAPI 路径和 route-level test 证明，不以 TypeScript 方法存在作为完成证据。

#### C. Strategy/Memory 是 identity seam，不是创建 seam

Strategy CRUD 和 MemoryStore 已存在。Memory 只有在带正确 `strategy_id` 的分析完成后才应该出现；在创建 Strategy 时写一条假 memory 会破坏语义。现有 `AnalyzeRequest.strategy_id` 已在 `frontend/lib/types/models.ts:14-27` 和 `server/routes/analyze.py:48-55` 定义，所以最小正确动作是前端发送该字段，不修改 frozen route/legacy orchestrator。

#### D. Scanner universe 是真实产品边界

UI 当前承诺 S&P 500/Nasdaq 100/CSI 300，但 repo 没有指数成分 provider、缓存或 staleness contract。v1 采用 `tracked` universe：所有 Strategy tickers、Watchlist tickers 与 MarketDataStore 已知 tickers 的去重并集。没有数据的 ticker 明确记录 missing fields，不触发无界批量爬取，不用固定数组替代指数成分。

#### E. Risk 没有 live portfolio source

`MockBrokerEngine` 和 `TradeLedger` 的默认 backend 是进程内对象；`ContextStore` 当前持久化 sessions/decisions/reports，但没有可作为实时持仓 source 的 persistent broker account。Risk 页面不能继续声称展示 live portfolio，也不能用 Strategy tickers 等权重冒充。v1 读取每个 ticker 最新持久化 decision 的 `target_position_pct`，把响应和 UI 标为 `decision_target`；没有 decision 或有效价格历史时显示 unavailable/partial。

#### F. ACTIVE/LEGACY/SHARED track 必须显式隔离

`CLAUDE.md:5-37` 和 `server/routes/_TRACKS.md:1-19` 冻结 `quick_ask/`，并禁止 SHARED route 导入 ACTIVE/LEGACY agent。Rule Scanner、Risk、Report artifact consumption 是 deterministic shared domain；自然语言/belief Scanner 才进入 ACTIVE `AgentLoop`/tool。Shared scanner service不得反向 import `agent/`。

Backtest 同样不能由 SHARED route 间接加载旧 orchestrator。`broker/backtest_runner.py` 必须移除 module-level `agentgraph.orchestrator.IntelliFin_Assistant` 和默认 agent construction，改为强制注入结构化 agent/scoped factory。HTTP endpoint 放入已注册的 ACTIVE `server/routes/agent.py`，实际 decision adapter 使用 ACTIVE `AgentLoop`、restricted financial tools 和显式 `submit_backtest_decision` tool；broker domain 仍保持 agent-agnostic。

#### G. “报告生成”不应暗中重跑分析

Stock Report 使用已完成、可审计的 analysis snapshot；Sector Report 先通过 Scanner 产生 persisted scan run，再消费该 run 与已有分析。缺少 source artifact 时返回 409/422，不静默启动另一个 legacy pipeline，也不生成貌似完整但没有证据的 PDF。

### Must have

- Strategy create/list regression；persisted status transition 和 clone；前端 mutation/error/query invalidation。
- Quick Ask strategy selector 发送真实 `strategy_id`；Memory Lab 区分 empty 与 backend error。
- Backtest 单 ticker ACTIVE async job、结构化 AgentLoop adapter、no-lookahead data boundary、真实 frequency、独立 benchmark、canonical result、reload recovery、CSV export。
- Scanner `tracked` universe、typed rule engine、rule/agent/belief 三种真实路径、persisted scan run、missing-data accounting。
- Risk decision-target exposure、historical VaR/CVaR、correlation、concentration、drawdown、可解释 stress；真实 strategy selector。
- Stock/Sector Reports 的 source validation、job status、metadata persistence、safe PDF artifact、history/download。
- Notifications 四 channel 的 configured-state、inline guide、test result 和 repo docs。
- 每 phase 的 TDD、API/manual QA、`PROGRESS.md`、commit、push、remote parity proof。
- 所有功能通过后，最后校正 `bugs/bug-and-issues-list.md`；不得提前移动条目。

### Must NOT have (guardrails, anti-slop, scope boundaries)

- 不修改 `quick_ask/`；不扩展 frozen `server/routes/analyze.py`；Quick Ask 只消费它已经支持的 request contract。
- `broker/`、SHARED route 和 storage 不得 import `agentgraph.orchestrator`、`quick_ask` 或 `agent/`；只有 ACTIVE `server/routes/agent.py`/`agent/` 负责 Backtest/Scanner 的 agent judgment。
- 不新增真实 broker adapter、Redis/Celery、分布式 worker、WebSocket、大规模指数成分 provider、多资产 portfolio backtest。
- 不把 Strategy status transition 伪装成自动调度：菜单文案必须明确为 `Mark Active / Pause / Stop` 等 persisted lifecycle；本计划不承诺 scheduled trading。
- `stop(liquidate=true)` 不得假成功；在没有 persistent broker account 时返回明确 409/422，并在 UI 不显示 liquidation 选项。
- 不把 strategy create、默认零值、equal-weight tickers、静态 fixtures 或 LLM 文本当作真实 memory/position/risk/result。
- 不保留 `MOCK_*` production constants、hard-coded strategy names、hard-coded report rows、static confusion matrix 或 placeholder chart copy。
- 不实现 Feishu/Slack/Discord 等当前 UI/backend 没有的 channel；`docs/api-contracts.md` 的旧 Feishu 漂移应修正为 WhatsApp。
- 不接受 report 文件路径作为 API 参数；不允许 `..`、absolute path、symlink escape 或任意文件下载。
- 不记录、打印、截图或提交 token/password/chat ID/recipient/API key；绝不编辑 `properties.env`。
- 不使用 `as any`、`@ts-ignore`、`@ts-expect-error`；不关闭 type/lint/test 规则换取通过。
- 不使用 `git add .`、`git push --force`、`git reset --hard`；不提交用户或其他 agent 的无关改动。

## Verification strategy

> Zero human intervention：验证由 Goal-mode agent 使用自动化和真实运行表面完成；用户只在 phase/最终 reviewer 要求确认时作产品所有者确认。

### Test decision

- **TDD-first**。每个 Python domain/API boundary 先写失败测试并保存 RED 输出，再做最小实现，最后保存 GREEN 输出。
- 当前 frontend 没有 unit-test script，不为本任务引入第二套 test runner。Frontend contract 由 TypeScript build、ESLint、真实 backend + browser flow、console/network inspection 覆盖。
- Browser QA 必须使用真实运行的 FastAPI + Next.js；不得用 source inspection、mock service worker 或静态截图替代。
- 所有 test/runtime evidence 写入 `.omo/evidence/frontend-demo-integration/phase-<N>/`；目录只用于 Goal-mode 证据，不纳入产品 commit，除非执行框架自动管理。

### 基线与通用门禁

开始 Phase 1 前运行并记录：

```bash
git branch --show-current
git status --short --branch
git fetch origin dev
git rev-parse HEAD
git rev-parse origin/dev
uv run pytest test/broker/test_backtest_runner.py test/memory/test_service.py test/quick_ask/test_memory_integration.py test/server/test_analyze_memory.py test/test_notification_channels.py test/test_watchlist_alerts.py -q
```

已知规划时基线为 `20 passed`；执行时必须以实时 checkout 结果为准。若 `HEAD != origin/dev`，先判断 ahead/behind/diverged；不得直接覆盖远端。

每 phase 至少运行：

```bash
uv run pytest <phase-focused-tests> -q
uv run basedpyright --baselinefile bugs/basedpyright/baseline.json
uv run ruff check <changed-python-paths>
uv run ruff format --check <changed-python-paths>
cd frontend && npm run lint -- <changed-frontend-paths-if-supported>
cd frontend && npm run build
git diff --check
```

最终运行完整门禁：

```bash
uv run pytest test -q
uv run basedpyright --baselinefile bugs/basedpyright/baseline.json
uv run ruff check .
uv run ruff format --check .
cd frontend && npm run lint
cd frontend && npm run build
git diff --check
```

若 Next/Turbopack 因 sandbox `EPERM` 失败，按环境规则申请一次必要的 escalated build；不得把 sandbox failure 误报为产品 failure，也不得跳过 build。

### 三类证据

1. **Test evidence**：RED/GREEN pytest、lint/type/build 原始退出码与摘要。
2. **API evidence**：OpenAPI path、curl happy/failure、重启恢复、响应中无 secret/path 泄漏。
3. **Manual surface evidence**：browser screenshot、network request/response、console errors、刷新/返回/切换 strategy 后的可观察行为。

## Execution strategy

### 启动协议

每个新的 Goal-mode session 或自动 continuation 首先：

1. 读取 `CLAUDE.md`、`PROGRESS.md`、`docs/development-plan.md`、本计划和当前 `bugs/bug-and-issues-list.md`。
2. 确认 branch 为 `dev`，remote 为 `origin`，记录 dirty worktree；保留所有非本任务改动。
3. 按本 phase 选择本地 skills；若 skill 与本计划冲突，以用户要求、本计划 scope lock、`CLAUDE.md` hard rule 的顺序处理。
4. 只进入当前最早未完成 phase；不得跨 phase 提前更新 tracker 或把后续 mock 临时当完成。

### Phase gate 与 Git 协议

Phase 1 至 Phase 7 都使用同一 gate：

1. 本 phase todos 全部 GREEN，匹配的 API/browser QA 已真实驱动，phase evidence 完整。
2. 更新 `PROGRESS.md`，记录完成内容、验证命令、结果与剩余风险。
3. `git status --short`，逐个 `git add <owned-path>`；禁止 `git add .`，确认 staged diff 无 secret/运行数据/无关文件。
4. commit 格式 `<type>: <description>`，body 引用本次 `PROGRESS.md` entry，并按 repo 约定加入 `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`。
5. 再次确认当前 branch 为 `dev` 且目标 upstream/remote branch 是 `origin/dev`；`git fetch origin dev`。若远端前进：在干净/已提交状态下检查差异并 rebase 到 `origin/dev`，解决仅本 scope 冲突，重跑本 phase gate；禁止 force push或改写 `dev` history。若 branch protection 拒绝直接 push，报告精确 blocker，不绕过保护。
6. `git push origin dev:dev`，然后证明：

   ```bash
   LOCAL=$(git rev-parse HEAD)
   REMOTE=$(git ls-remote --heads origin dev | awk '{print $1}')
   test "$LOCAL" = "$REMOTE"
   ```

7. 只有 push/parity 成功后，才在 plan/goal tracker 中把 phase 标为 complete 并进入下一 phase。临时网络失败时持续重试或记录 external blocker，不把仅本地 commit 当作 phase complete。

### 阶段顺序

| Phase | 交付 | 依赖 | Phase commit |
| --- | --- | --- | --- |
| 1 | Strategy lifecycle + Quick Ask strategy identity + Memory observability | baseline | `feat: connect strategy lifecycle and scoped memory` |
| 2 | Trusted single-ticker Backtest API/UI | Phase 1 identity | `feat: run persisted backtests from the web` |
| 3 | Tracked-universe Scanner rule/agent/belief | Phase 1 strategies；可复用 Phase 2 job patterns | `feat: implement the tracked-universe scanner` |
| 4 | Decision-target Risk analytics | Phase 1 decisions + market data；可与 Reports 前置分析独立 | `feat: add strategy risk analytics` |
| 5 | Stock/Sector report generation/history/download | Phase 3 persisted scan runs | `feat: generate reports from persisted analysis artifacts` |
| 6 | Notifications onboarding/config state | Phase 1 settings conventions；功能上独立 | `docs: add notification setup and status guidance` |
| 7 | Integrated verification + issue truth | Phase 1-6 | `docs: close frontend demo integration issues` |

### Parallel execution waves

由于用户要求每个 phase 都 push `origin/dev`，phase 之间顺序执行；phase 内只并行互不写同一文件的验证/研究 lane。

- **Wave 1:** Todos 1-5，完成 Phase 1-2。
- **Wave 2:** Todos 6-10，完成 Phase 3-4。
- **Wave 3:** Todos 11-14，完成 Phase 5-7。

### Dependency matrix

| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | baseline | 2 | none，和 2 改同一 frontend/API family |
| 2 | 1 | 3 | phase 内 browser fixture 准备 |
| 3 | Phase 1 | 4,5 | no-lookahead unit tests 可与 job schema test 设计并行 |
| 4 | 3 contract | 5 | frontend mock removal inventory |
| 5 | 3,4 | 6 | none，必须完成 Phase 2 push |
| 6 | Phase 1 | 7,8,12 | scanner UI audit |
| 7 | 6 + Phase 2 tool allowlist | 8,12 | ACTIVE AgentLoop restriction tests 与 route tests 可并行 |
| 8 | 6,7 | 9 | none，必须完成 Phase 3 push |
| 9 | Phase 1 + market store | 10 | Phase 3 完成后的 report renderer audit |
| 10 | 9 | 14 | none，必须完成 Phase 4 push |
| 11 | Phase 3 scan persistence | 12 | Notification docs research |
| 12 | 11 | 14 | none，必须完成 Phase 5 push |
| 13 | current notification backend | 14 | Phase 5 后独立执行 |
| 14 | 1-13 | final | F1-F4 reviewer lanes |

## Todos

> Implementation + Test 是同一个 todo。以下 references 是执行入口，不是只读清单；worker 必须在编辑前重新读取实时文件。

- [ ] 1. 为 Strategy persisted lifecycle/clone 建立真实后端 contract

  **问题分析：** CRUD 已真实存在，但 `frontend/lib/api/strategies.ts:57-74` 声明的 clone/start/pause/stop 没有对应 route。直接返回 200 或只改前端会继续制造 demo。自动调度不在当前架构闭环内，因此 lifecycle 必须诚实定义为 persisted config status。

  **解决方案：**

  - 先创建 `test/server/test_strategies_lifecycle.py`，覆盖 create→list regression、合法/非法 transition、idempotent transition、clone 隔离和 `liquidate=true` 拒绝。
  - 在 `server/routes/strategies.py` 使用 Pydantic request model，增加：
    - `POST /api/strategies/{id}/clone`：复制配置，new UUID/name/timestamps，`status="draft"`，`parent_strategy_id=source.id`；不得复制 per-strategy DB、decisions 或 memory。
    - `POST /api/strategies/{id}/start`：`draft|paused|stopped -> active`；`active -> active` 幂等；`archived` 返回 409。
    - `POST /api/strategies/{id}/pause`：仅 `active -> paused`；paused 幂等，其余 409。
    - `POST /api/strategies/{id}/stop`：`draft|active|paused -> stopped`；stopped 幂等；`liquidate=true` 返回 409，绝不假装平仓。
  - 所有更新通过 `ContextStore.update_strategy()`；404 与 409 response 具有稳定 `detail`。
  - 同步 `docs/api-contracts.md:87-123`，把 “resumes scheduling/liquidate” 改成当前真实 persisted lifecycle contract。

  **Must NOT do：** 不新增 Strategy scheduler，不修改 `quick_ask/`，不在 clone 时复制 memory/history。

  **References：** `server/routes/strategies.py:28-207`；`storage/store.py:45-133,961-973`；`frontend/lib/types/models.ts:123-141`；`frontend/lib/api/strategies.ts:21-74`；`docs/api-contracts.md:87-123`。

  **验收标准：** 新 focused test 在实现前因 404/缺 route RED；实现后全部 GREEN；OpenAPI 包含四个 route；创建的策略立即能 GET/list；clone 与 source ID/status/data DB 相互隔离；非法 transition 返回 409；liquidation 不能返回成功。

  **QA：** happy：TestClient create→start→pause→stop→clone，并重建 `ContextStore` 后重读；failure：unknown ID、archived start、draft pause、`liquidate=true`。Evidence：`.omo/evidence/frontend-demo-integration/phase-1/task-1-strategy-api.txt`。

  **Commit：** N；与 Todo 2 一起完成 Phase 1 commit。

- [ ] 2. 把 Strategies、Quick Ask 和 Memory Lab 接到真实 strategy identity，并完成 Phase 1 gate

  **问题分析：** Strategy list/create 已能变化；菜单 action 无 handler。Quick Ask 的 `AnalyzeRequest` 已支持 `strategy_id`，但 `frontend/app/quick-ask/page.tsx` 发起请求时未提供，因此 UI 分析都落到 backend default strategy。Memory Lab 不能从 Strategy create 自动出现 memory，这是错误期待；它应显示所选 strategy 真正分析产生的记录。

  **解决方案：**

  - `frontend/app/strategies/page.tsx` 为 lifecycle/clone 建立 TanStack mutations；pending 时禁用同一 row action；成功后 invalidate `['strategies']`；失败展示可见错误。菜单文案使用 persisted lifecycle 语义，不能暗示 scheduler。
  - 保留 `frontend/app/strategies/new/page.tsx` 现有 create path；加入/create-list browser regression，不重写表单。
  - `frontend/app/quick-ask/page.tsx` 使用 `strategiesApi.list()` 加 strategy selector；默认优先 URL/history snapshot 的 strategy，否则首个真实 strategy，否则显式 `default`。调用现有 `analyzeApi` 时发送 `strategy_id`；不得编辑 `server/routes/analyze.py` 或 `quick_ask/`。
  - 分析 pending/history restore 时保留并显示 strategy identity；必要时只扩展 frontend snapshot type，backend payload 已有字段才消费，不发明值。
  - 修复与本问题直接相关的 Memory route truth：`server/routes/memory.py` 的 list/detail 都通过统一 helper 读取 `MEMORY_DB_PATH`（与 `MemoryService` 一致），不再写死 `data/memory.db`；detail 找到 record 后必须校验 `record.strategy_id == path strategy_id`，否则 404；list 的 storage exception 返回可观察 5xx，不得 broad-except 成空列表。
  - 在 `test/server/test_memory_routes.py` 先写 RED tests：临时 `MEMORY_DB_PATH` 被 list/detail 一致使用、Strategy A 无法按 ID 读取 Strategy B record、store error 是 5xx。
  - `frontend/app/memory-lab/page.tsx` 使用 typed `memoryApi`，区分 loading、backend error、no strategy、selected strategy has no memory；backend 500 不得显示成 “no memories”。加入显式 Refresh，并在 Quick Ask analysis completed 后使相关 strategy memory query 可重新获取；不得只依赖页面 remount 偶然刷新。
  - 更新 `docs/api-contracts.md` 和 `plans/dev-branch-merge/dev-acceptance-cases.md:159-163` 的 Quick Ask selector limitation。
  - Browser QA 创建 `QA Strategy <timestamp>`，验证无 reload 出现在 list；切换 status/clone；使用该 strategy 跑一次短 Quick Ask；到 Memory Lab 选择它并观察真实 record；清理 QA strategy。

  **Must NOT do：** 不在 create handler 写 synthetic memory；不修改 MemoryService 的 OWM 语义；不吞 mutation/API/storage error。

  **References：** `frontend/app/strategies/page.tsx:58-257`；`frontend/app/strategies/new/page.tsx:32-84`；`frontend/app/quick-ask/page.tsx:333-341`（执行时重新定位 request construction）；`frontend/app/memory-lab/page.tsx:20-154`；`frontend/lib/types/models.ts:14-27,149-155`；`server/routes/analyze.py:48-55,154-244,361-385`；`server/routes/memory.py:16-56`；`memory/service.py:25-147`；`test/memory/test_service.py`；`test/server/test_analyze_memory.py`。

  **验收标准：** browser network 显示 create/lifecycle/clone 请求；Quick Ask POST body 包含所选真实 strategy UUID；完成分析后 memory API 只在相同 strategy 下返回该 record，另一个 strategy list/detail 都不返回；临时 `MEMORY_DB_PATH` 生效；store failure 是 5xx；Refresh 可观察；刷新/导航后 selector 与数据一致；frontend lint/build 通过。

  **QA：** happy：真实 browser 全流程 + API 交叉读取两个 strategy；failure：lifecycle 409 显示错误、memory API 强制失败时显示 error state、无策略时仍可选择明确 default。Evidence：`.omo/evidence/frontend-demo-integration/phase-1/task-2-browser/` 与 `task-2-network.json`。

  **Commit：** Y；`feat: connect strategy lifecycle and scoped memory`；执行完整 Phase 1 gate、更新 `PROGRESS.md`、push `origin/dev` 并证明 parity。

- [ ] 3. 解除 Backtest 对旧 orchestrator 的依赖，并建立 ACTIVE AgentLoop/no-lookahead canonical contract

  **问题分析：** `BacktestRunner` 每个 bar 调 agent 并传 `as_of`，但 prompt 参数不是权限边界；`DataService.get_prices()` 还会忽略 `end_date`。更关键的是 `broker/backtest_runner.py:11` 顶层默认导入旧 `agentgraph.orchestrator.IntelliFin_Assistant`，让 broker/shared HTTP 路径违反 track。ACTIVE `AgentLoop.run(user_message,...)` 又不能直接满足 runner 所需的结构化 decision/broker execution contract，必须先定义 adapter，而不是留给 executor 临场决定。

  **解决方案：**

  - 先扩展 `test/broker/test_backtest_runner.py`，创建 `test/broker/test_backtest_data.py`、`test/agent/test_backtest_adapter.py`、`test/agent/test_tool_allowlist.py` 和 `test/architecture/test_backtest_track_boundary.py`。架构 test 必须证明 import `broker.backtest_runner`/shared services 不加载或引用 `agentgraph.orchestrator`、`quick_ask`、`agent`。
  - 修改 `broker/backtest_runner.py`：删除旧 orchestrator module import 和默认 construction；`agent` 与 `scoped_agent_factory` 仍互斥，但现在必须恰好提供一个，否则 fail fast。Broker runner 只依赖一个结构化 protocol：`.run(ticker,date,as_of,current_position_pct,execution_enabled,strategy_id,account_id,session_id)`。
  - 新建 `broker/backtest_data.py`：`BacktestDataService(as_of, market_store)` 实现 `ToolDataService` 协议，所有 price/indicator/fundamental/news 返回先 clamp 到 `as_of`；缺历史数据显式失败，不回退 live “now”。
  - 新建 `agent/run_context.py` 的 context-local `AgentRunContext`，至少含 `data_service/as_of/broker/strategy_id/account_id/session_id/ticker`；修改 ACTIVE `agent/tools/financial.py` 通过该 context 获取 data service，正常 agent chat 无 context 时才使用普通 `DataService()`。不得修改 `quick_ask/` 或它的 tool mirror。
  - 在本 phase 就为 `AgentConfig`/`ToolRegistry` 增加显式 `allowed_tools`/subset contract，并在 `test/agent/test_tool_allowlist.py` 先写回归：普通 agent chat 默认工具集合不变，restricted loop 的 model schema/system prompt/executor 只包含 allowlist。Scanner Phase 3 必须复用这一 owner，不能再实现第二套过滤。
  - 新建 ACTIVE `agent/tools/backtest.py` 的 `submit_backtest_decision`：typed args 只允许 `BUY|SELL|HOLD`、0..100 `target_position_pct`、0..1 confidence 和 rationale；从 `AgentRunContext` 读取 broker/identity，复用 broker public order/risk semantics 把目标仓位转换为订单。没有 context 时 tool unavailable/fails safely。
  - 新建 `agent/backtest_adapter.py`：每个 decision date 创建 restricted `AgentLoop`，只暴露 scoped financial tools、必要 read-only skill tool 和 `submit_backtest_decision`；system prompt 要求恰好一次 structured decision tool call；从 tool message 验证执行结果，LLM 无 tool call/多次 call/invalid args 均 fail job，不从 prose 猜 action。
  - 使用 `BacktestRunner.scoped_agent_factory` 注入上述 adapter；context 在一次 run 后 reset，即使异常也不能泄漏到并发 job。
  - 新建/内聚 `BacktestDatasetPreparer`：job 开始时只为 target 与 benchmark 预载 request date window 的 OHLCV；历史 fundamentals/news 只读 MarketDataStore 中 `as_of_date/published_at <= as_of` 的 PIT records，缺失就向 agent 返回 unavailable，绝不回退今天的 live snapshot。预载完整价格窗口不构成泄漏，因为所有 ACTIVE tools 只能经 scoped service 获取当日切片。
  - `BacktestRunner.run()` 增加真实 `frequency` 与独立 `benchmark_df/benchmark_symbol`：daily/weekly/monthly 只控制 decision/rebalance date，但每天仍记录 equity snapshot；benchmark 必须使用独立 OHLCV、与 strategy 日期 inner-align 后计算，不能再把被测 ticker buy-and-hold 当 SPY；非法 frequency/无日期交集 fail fast。
  - `BacktestConfigView` 增加 frequency；保持 result 为 `status/config/summary/series/trades`，不添加 prediction/confusion fields。所有 return/drawdown 字段遵守 `broker.views` 现有小数/百分数约定，并由 Python/TS contract test 固定。
  - v1 request 定义为 `strategy_id`、单个 `ticker`、`date_from`、`date_to`、`frequency`、`benchmark`；删除 `forward_days` 与 plural tickers。

  **Must NOT do：** 不依赖 prompt 要求 LLM 自觉传 end_date；不把 full historical dataframe 暴露给 scoped tools；不把多个单 ticker 结果相加成“portfolio”；不让 broker/shared route import ACTIVE/LEGACY；不复用 `RunAnalysisTool` 的 quick_ask bridge 做 backtest。

  **References：** `broker/backtest_runner.py:1-137,204-258`；`broker/views.py:174-213,450-491`；`agent/loop.py:50-148,381-504`；`agent/tools/financial.py:17-249,420-449`；`agent/tools/base.py:44-163`；`agent/tools/registry.py:20-172`；`agentgraph/execution_node.py`（只参考目标仓位→broker public API 语义，不从 ACTIVE import）；`dataflow/service.py:51-114,231-291`；`dataflow/store.py:1-12,178-277`；`plans/future-works/future-works.md:12-19`。

  **验收标准：** future sentinel 已写入 DB 但任一回测日 ACTIVE financial tool 都看不到；两个并发 scoped contexts 不串 as_of/broker/identity；restricted AgentLoop schema 不含 shell/workspace/unscoped tools；恰好一个 decision tool 调用才有效；frequency 决策次数准确；独立 ticker/benchmark fixture 得到不同收益；canonical Pydantic view 可 JSON round-trip；import-boundary 和现有 broker/agent tests 不回归。

  **QA：** happy：seeded store 上 weekly run 输出真实 series/trades/metrics；failure：future-only data、空数据、反向日期、非法 frequency、agent exception 都形成 typed failure。Evidence：`.omo/evidence/frontend-demo-integration/phase-2/task-3-no-lookahead.txt`。

  **Commit：** N；与 Todos 4-5 一起完成 Phase 2 commit。

- [ ] 4. 为 ACTIVE Backtest 增加可恢复的 SQLite job/API，而不是 request-thread 假运行

  **问题分析：** Backtest 可能包含多次 LLM/agent decision，不能在 request thread 同步阻塞。项目是单机 FastAPI + SQLite，不需要分布式队列，但必须处理 refresh/restart 后 stuck running。

  **解决方案：**

  - 先创建 `test/server/test_backtest_api.py`，通过 injectable fake runner 测试 POST→pending/running→completed、failed、GET not found、restart recovery、CSV content-disposition。
  - 在 `storage/store.py` 的 `system.db` 初始化 `backtest_jobs` table：`id/request_json/status/result_json/error/created_at/started_at/completed_at/updated_at`；增加 typed CRUD，不把 job 存在 module global dict。
  - 新建 `agent/backtest_jobs.py`：Pydantic request/response、bounded in-process executor、状态 transition；它组合 ACTIVE adapter、agent-agnostic runner、DataService/store，不把 worker 放进 shared storage。
  - 在已注册的 ACTIVE `server/routes/agent.py` 增加：
    - `POST /api/agent/backtest` → 202 `{backtest_id,status}`；校验 strategy/ticker/date/frequency/benchmark；unknown strategy 404，未配置 LLM 422/503，重复 request 默认产生独立 job 并返回独立 ID（v1 不做 implicit dedupe）。
    - `GET /api/agent/backtest/{id}` → persisted job envelope；只有 `completed.result` 是 canonical `BacktestResultView`。
    - `GET /api/agent/backtest/{id}/trades.csv` → completed only，safe generated CSV response。
  - `server/main.py` lifespan 只调用 storage-level `recover_interrupted_backtest_jobs()`，把遗留 pending/running 标为 `failed` + stable code `interrupted`；main/shared 不能 import ACTIVE worker/adapter。
  - 在 `server/routes/_TRACKS.md` 和 `docs/api-contracts.md` 把 Backtest 明确归到 `/api/agent/*` ACTIVE；不再创建 `/api/backtest` SHARED route，也不保留旧空壳 client path。
  - 错误 response 只含 safe message；不得包含 prompt、token、absolute path、raw stack 或 settings。

  **Must NOT do：** 不引入 Celery/Redis；不依赖进程内 dict 保存结果；不在 tests 调真实 LLM/公网。

  **References：** `server/main.py:34-76,113-137`；`server/routes/agent.py:34-160`；`server/routes/_TRACKS.md:1-19`；`server/analysis_runs.py:19-158`（状态/持久化 pattern）；`storage/store.py:45-133,940-1035`；`frontend/lib/api/backtest.ts:1-12`；`docs/api-contracts.md:528-575`。

  **验收标准：** OpenAPI 只出现三个 ACTIVE backtest endpoint，不出现误分类的 shared `/api/backtest`；TestClient job 完整 transition；重建 app/store 后 completed 仍可读，interrupted 变 failed；CSV 只对 completed 返回 200；反向日期、空价格窗口、unknown strategy/job、无 LLM、runner failure 都有稳定 4xx/failed contract；route test 不需真实 LLM。

  **QA：** happy：curl create→poll→completed→CSV；failure：invalid ticker/date、missing strategy、fake runner exception、server restart mid-job。Evidence：`.omo/evidence/frontend-demo-integration/phase-2/task-4-api/`。

  **Commit：** N；与 Todo 5 一起完成 Phase 2 commit。

- [ ] 5. 重写 Backtest page 以展示真实 job、equity/drawdown/trades，并完成 Phase 2 gate

  **问题分析：** 页面当前加载时直接显示结果；strategy/tickers 固定；chart、confusion matrix、export 都是装饰。Frontend type 仍固化旧 prediction contract。

  **解决方案：**

  - 重写 `frontend/lib/types/models.ts:348-367`，TypeScript type 与 `BacktestResultView`/job response 同名字段对齐；禁止双重 adapter。
  - 更新 `frontend/lib/api/backtest.ts` 支持 create/get/CSV URL；用 TanStack Query 根据 `pending|running` polling，completed/failed 停止。
  - `frontend/app/backtest/page.tsx`：真实 strategies query；单 ticker input；date/frequency/benchmark controlled state；初始 empty；Run mutation；pending/running progress；failed retry；completed metrics。
  - 用已安装 `recharts` 画真实 `series` equity 和 drawdown；trade table 读 canonical `trades`；删除 prediction timeline、confusion matrix、forward validation、多 ticker 文案、PDF decorative button。
  - 把 `backtest_id` 写到 URL query；刷新/导航返回后重新 GET job，不依赖 component local `hasRun`。
  - Export CSV 通过 backend URL；未完成时按钮不可见/禁用且有原因。
  - 更新 `docs/api-contracts.md:528-575` 为单 ticker canonical contract。

  **Must NOT do：** 不保留 `MOCK_RESULT` 或 hard-coded counts；不使用 `as any` 绕过 chart typing；不把 polling failure 当 completed empty result。

  **References：** `frontend/app/backtest/page.tsx:49-475`；`frontend/lib/types/models.ts:348-367`；`frontend/lib/api/backtest.ts:1-12`；`frontend/components/quick-ask/ticker-preview.tsx:244-319`（Recharts pattern）；`broker/views.py:174-213`。

  **验收标准：** 首次进入无结果；Run 产生真实 POST/GET；reload 同 job；strategy/ticker/date 改变反映在 request/config；图表点数等于 series；trades/metrics 来自 API；failed job 显示 server error；lint/build GREEN。

  **QA：** happy：browser run 一个小日期区间、观察 network polling、reload、下载 CSV；failure：空 ticker、date_from > date_to、缺数据/缺 LLM config 的 failed state、断开 backend 时可见错误。Evidence：`.omo/evidence/frontend-demo-integration/phase-2/task-5-browser/`。

  **Commit：** Y；`feat: run persisted backtests from the web`；执行完整 Phase 2 gate、更新 `PROGRESS.md`、push `origin/dev` 并证明 parity。

- [ ] 6. 建立 tracked-universe、typed snapshot 和 deterministic Scanner engine

  **问题分析：** Scanner 的正确性依赖明确 universe、字段语义和 missing-data contract。直接在 route 中写 dict/if 或让 LLM 返回结果会不可测试、不可复用、不可审计。

  **解决方案：**

  - 新建 deep module：`scanner/models.py`、`scanner/universe.py`、`scanner/service.py`；创建 `test/scanner/test_service.py` 与 `test/scanner/test_universe.py`，先 RED。
  - `dataflow/store.py` 增加 `list_known_tickers()`：从 ohlcv/fundamentals/ticker_meta 的 distinct union 获取，不返回固定 ticker。
  - `storage/store.py` 增加 public `list_watchlist_tickers()`；Scanner 不 import `server/routes/watchlist.py` 的 private helper。
  - `TrackedUniverseResolver` 合并 `ContextStore.list_strategies()` 中 tickers、watchlists、MarketDataStore known tickers；uppercase/strip/dedupe/sort；空 universe 是合法 empty，不回退 S&P fixtures。
  - `ScannerSnapshotBuilder` 是 cached-only adapter，只从 MarketDataStore 获取最近 OHLCV、fundamentals、meta；单次 scan 不得触发 provider。v1 allowlist 与单位固定为：`price`（ticker currency absolute）、`change_pct`（百分数点，例如 2.5 表示 2.5%）、`volume`（shares）、`rsi14`（0..100）、`sma20/sma50`（ticker currency）、`pe_ratio/pb_ratio`（倍数）、`market_cap`（absolute currency units）、`sector`（string equality only）。响应同时给 currency/source/as-of；不开放语义未冻结的 growth/ROE 字段。
  - Typed `ScanCondition` operators 限定 `< > <= >= == between`；`between` 必须 value/value2 且 low≤high；string equality 仅允许 allowlisted string field；NaN/None 视为 missing，不视为 0。
  - Rule semantics 固定为 AND；每 result 包含真实 matched conditions、snapshot、source dates；universe/result 均带每 ticker provenance（strategy/watchlist/market_store，可多值）；response 额外含 `scanned_count/matched_count/missing_data_count/warnings/scanned_at`。
  - 单次 scan 不做无界公网抓取。缺缓存数据写 warnings/missing；由现有 DataCollector/watchlist fetch 负责补数据。

  **Must NOT do：** 不支持 UI 中伪造的 `sp500/nasdaq100/csi300`；不 eval 用户表达式；不让 LLM 计算 match；不把 missing 当 zero。

  **References：** `frontend/app/scanner/page.tsx:35-280`；`frontend/lib/types/models.ts:285-300,396-398`；`dataflow/store.py:29-205,251-277,422-490`；`storage/store.py:74-133`；`server/routes/watchlist.py:44-123,237-280`；`docs/development-plan.md:82-86`。

  **验收标准：** seeded temp DB 的 tracked union 精确；所有 operator boundary 和 missing behavior GREEN；结果排序固定（match score desc、ticker asc）；空 universe/无数据不会返回 mock；engine 不 import frontend/agent/routes。

  **QA：** happy：三个 source 各贡献 ticker 并匹配组合条件；failure：unsupported universe/field/operator、invalid between、空 universe、partial snapshot。Evidence：`.omo/evidence/frontend-demo-integration/phase-3/task-6-engine.txt`。

  **Commit：** N；与 Todos 7-8 一起完成 Phase 3 commit。

- [ ] 7. 增加 Scanner run persistence、Rule shared route 和 Agent/Belief ACTIVE route

  **问题分析：** Rule scan 是 shared deterministic service；natural-language/belief 到 typed conditions 的转换是 agent judgment。若 `server/routes/scanner.py` import `agent/`，将违反 track；若 LLM 直接生成 result，会绕过 rule engine。

  **解决方案：**

  - 先建 `test/server/test_scanner_api.py`、`test/agent/test_scanner_tool.py`，并复用 Phase 2 已有 `test/agent/test_tool_allowlist.py` 扩展 scanner-specific assertions。
  - `storage/store.py` 增加 `scan_runs` table/CRUD：input、compiled_conditions、result、status/error、mode、strategy_id、timestamps；completed run 能重启后读取。
  - 新建 `server/routes/scanner.py`（SHARED）：
    - `POST /api/scanner/rule` 执行 typed service 并持久化。
    - `GET /api/scanner/runs` 与 `GET /api/scanner/runs/{id}` 供 UI/Reports。
    - route 不能 import `agent/`、`quick_ask/` 或 LLM。
  - 新建 `agent/tools/scanner.py` 的 `scan_tracked_universe`，唯一输入为 typed conditions，唯一执行 owner 为 `ScannerService`；注册于 `agent/tools/__init__.py`。
  - 使用 Phase 2 的 tool allowlist/subset，保证 scanner compilation run 只看到 `scan_tracked_universe` 和必要的 read-only skill tool，不暴露 shell/workspace/write tools；不得在 scanner service/route 实现第二套过滤。
  - 在 ACTIVE `server/routes/agent.py` 增加 `POST /api/agent/scanner`：
    - `mode=agent` 使用 query；`mode=belief` 必须提供真实 `strategy_id + belief_text`，后端确认该 text 精确属于该 strategy 的 beliefs，再结合对应 weight 构造 prompt；不接受不存在的 belief UUID，也不默默使用所有 beliefs。
    - 使用 restricted `AgentLoop` system prompt 要求恰好调用 scanner tool；从 returned tool message 解析 JSON，再用 Pydantic 验证；没有 tool call/invalid result 为 failed run，不从 final prose 猜条件。
    - 持久化原始 query/belief source、compiled conditions 和 scan result；不得持久化 chain-of-thought。
  - 更新 `server/routes/_TRACKS.md`、`server/main.py`、`docs/api-contracts.md`；Rule 和 ACTIVE endpoint 分开记录。

  **Must NOT do：** shared route 不 import ACTIVE；AgentLoop 不拥有 raw provider；不执行任意代码/SQL；belief 模式不引用不存在的 `belief_id` API。

  **References：** `CLAUDE.md:5-37,82-86`；`server/routes/_TRACKS.md:1-19`；`server/routes/agent.py:34-160`；`agent/loop.py:50-148,381-504`；`agent/tools/base.py:44-163`；`agent/tools/registry.py:20-172`；`agent/tools/__init__.py:35-51`；`storage/store.py:45-133`。

  **验收标准：** OpenAPI 显示 shared/active endpoints；rule request 不启动 LLM；agent/belief 只经 typed tool result；allowlist test 证明 scanner agent 看不到 bash/workspace tools；invalid/no-tool LLM response 成为 explicit failure；run 重启可读。

  **QA：** happy：fake LLM tool call→真实 seeded scanner result；failure：missing query/strategy/belief_text、belief 不属于 strategy、invalid tool args、LLM 未配置/超时/未调用 tool、engine partial data。Evidence：`.omo/evidence/frontend-demo-integration/phase-3/task-7-routes.txt`。

  **Commit：** N；与 Todo 8 一起完成 Phase 3 commit。

- [ ] 8. 把 Scanner page 三种模式全部接到真实 run，并完成 Phase 3 gate

  **问题分析：** 当前 Add Condition 不改变表单，三个 Scan button 都无 handler，`hasScanned=true` 让页面进入即显示 mock。即使后端完成，若 UI 仍展示旧 fields/universe 就会形成 contract drift。

  **解决方案：**

  - 重写 `frontend/lib/types/models.ts:285-300,396-398` 和 `frontend/lib/api/scanner.ts` 对齐 typed request/result/run。
  - Rule mode 使用 field/operator/value/value2 controlled rows；Add/Remove 真实更新 state；基于 field/operator 做客户端边界校验，但 server 仍是最终校验 owner。
  - Universe 只显示 `Tracked universe`，旁边解释三类来源和实际 scanned count；删除三个指数 option。
  - Agent mode 发 `POST /api/agent/scanner` query；Belief mode 加载真实 strategies 和其 belief text，提交 `strategy_id + belief_text`；只允许选择真实存在的 belief；返回 compiled conditions 给用户审计。
  - 三种 mode 都有 mutation pending、error、empty、partial warnings、real result table；初始不显示结果；切 mode 不复用另一 mode 的 stale result。
  - result table 只渲染 API snapshot 有的字段；missing 显示 `Unknown`，不显示 `0`/假 market cap。
  - 保存 `scan_run_id` 到 URL，使 refresh 可通过 GET restore；Report Phase 消费该 ID。

  **Must NOT do：** 不保留 `MOCK_RESULTS`、`hasScanned=true`、硬编码 market caps；不在 frontend 重算规则；不吞 4xx/5xx。

  **References：** `frontend/app/scanner/page.tsx:35-280`；`frontend/lib/api/scanner.ts:1-35`；`frontend/lib/api/strategies.ts:21-36`；`frontend/lib/types/models.ts:285-300,396-398`。

  **验收标准：** Add Condition DOM row count 变化；Rule/Agent/Belief 分别发正确 endpoint；结果、warnings、compiled conditions 与 API 相同；refresh restore；无结果显示真实 empty；lint/build 通过。

  **QA：** happy：browser 三 mode 各运行一次并检查 network/DOM；failure：invalid between、空 query、无 belief、empty universe、backend unavailable；console 无 uncaught error。Evidence：`.omo/evidence/frontend-demo-integration/phase-3/task-8-browser/`。

  **Commit：** Y；`feat: implement the tracked-universe scanner`；执行完整 Phase 3 gate、更新 `PROGRESS.md`、push `origin/dev` 并证明 parity。

- [ ] 9. 从真实 decision target exposure 构建 deterministic Risk analytics

  **问题分析：** 当前没有 persistent live portfolio，直接实现文档中的 “portfolio risk” 会迫使代码虚构权重。已有真实数据是 strategy decisions 的 target percentages 与 MarketDataStore 历史 OHLCV/meta。

  **解决方案：**

  - 新建 `risk/models.py`、`risk/service.py`（或同等 deep module）及 `test/risk/test_service.py`，先用 seeded temp stores 写 RED tests。
  - `DecisionTargetExposureResolver`：按 ticker 取最新 decision；读取 `target_position_pct`，限定 0..100；相同 ticker 只用最新；总 exposure >100% 返回 invalid，不悄悄 normalize；cash 为剩余。
  - response 必须带 `source="decision_target"`、decision IDs/timestamps、`as_of`、weights、cash、warnings；UI 不能称为 executed holdings。
  - 使用默认最多 252 个、至少 60 个共同交易日的 close，先按 ticker 计算 simple daily return，再按 decision weights 求和；所有 risk/return/stress impact API 值统一为 decimal return（`-0.023` 表示 -2.3%，UI 只在显示层 ×100）。
  - 精确算法：common-date inner intersection；`var_95 = numpy.quantile(portfolio_returns, 0.05, method="linear")`，`var_99` 使用 0.01；`cvar_95` 是 `returns <= var_95` 的算术平均；保持 loss-tail 为负数，不在 backend 取绝对值。
  - 计算：
    - daily weighted returns；historical VaR95/VaR99；CVaR95。
    - cumulative curve 与 peak-to-trough drawdown。
    - ticker correlation response 明确 labels + 对称 matrix + diagonal 1；样本不足标 null/Unknown。
    - ticker/sector concentration；sector 从 ticker meta，缺失归 `Unknown`。
    - stress：`historical_worst_day` 来自真实 series；`uniform_market_shock` 输入/输出也使用 decimal return，impact = shock × gross decision exposure，并明确标为 model assumption。
  - 不支持当前没有 factor model 的 `vix_spike/rate_change_bps`；删除 contract/UI 或对非零值返回 422。
  - 无 decisions、全 0 exposure、历史不足分别返回 typed unavailable/partial，不用全 0 metrics 冒充计算成功。

  **Must NOT do：** 不调用 LLM；不使用 equal-weight fallback；不把 BUY/SELL 文本直接变成未定义 short exposure；不在缺数据时返回 mock。

  **References：** `storage/store.py:140-385`；`server/routes/strategies.py:148-207`；`dataflow/store.py:178-277,448-490`；`frontend/app/risk/page.tsx:40-319`；`frontend/lib/types/models.ts:369-377`；`docs/api-contracts.md:778-809`。

  **验收标准：** 手算 fixture 的 returns/VaR/CVaR/correlation/concentration/drawdown 在 tolerance 内；响应单位/负号固定；matrix 对称、labels 对齐、对角线 1；两个 strategy 不同 decisions 得不同结果；无 data/over-100%/insufficient overlap typed 状态准确；没有 LLM/import agent。

  **QA：** happy：两个 seeded strategy 的 risk result 可复算；failure：无 decisions、invalid weights、单 ticker correlation、missing sector、少于 60 bars。Evidence：`.omo/evidence/frontend-demo-integration/phase-4/task-9-risk-domain.txt`。

  **Commit：** N；与 Todo 10 一起完成 Phase 4 commit。

- [ ] 10. 实现 Risk API/真实 strategy page，并完成 Phase 4 gate

  **问题分析：** 旧 API client 的四个 `unknown` response 与页面固定数据都没有完整 data-state。一次 overview 能保持同一个 as_of/weight snapshot，避免四个请求各自读取不同数据。

  **解决方案：**

  - 先建 `test/server/test_risk_api.py`，覆盖 overview/stress、404 strategy、unavailable、invalid exposure、insufficient data。
  - 新建 `server/routes/risk.py`（SHARED deterministic）：
    - `GET /api/risk/{strategy_id}/overview?lookback_days=252`
    - `POST /api/risk/{strategy_id}/stress`
  - 注册 `server/main.py`，更新 `docs/api-contracts.md:778-809`；frontend `riskApi` 使用 typed overview/stress，不保留 `unknown`。
  - `frontend/app/risk/page.tsx` 加载真实 strategies；strategy ID 是 query key；切换时显示 loading，绝不显示上一 strategy 的 stale result。
  - 用 Recharts 或现有 typed chart pattern 展示真实 return distribution/drawdown；table 展示 correlation；concentration 展示 ticker/sector；source badge 明确 `Decision target exposure` 与 as-of。
  - Stress UI 只提供支持的 uniform market shock；历史最差日从 overview 展示；无 data/partial/invalid 分开。
  - 删除 `Tech Momentum`/`Value Hunter` hard-code、`MOCK_VAR/STRESS/CORRELATION/CONCENTRATION` 和 placeholder copy。

  **Must NOT do：** 不在切换时保留前一 strategy 数据；不把 null correlation 渲染为 0；不称 decision targets 为 current holdings。

  **References：** `frontend/app/risk/page.tsx:40-319`；`frontend/lib/api/risk.ts:1-28`；`frontend/lib/types/models.ts:369-377`；`server/main.py:113-137`；Todo 9 新 module。

  **验收标准：** selector options 来自 strategies API；network URL 含真实 ID；切换两个 fixture strategy 指标/weights 改变；无 decisions 显示 instruction；stress request/response 可解释；lint/build/API tests GREEN。

  **QA：** happy：browser 切换两个有不同 decision targets 的 strategy、运行 -10% stress；failure：无 decision strategy、overweight data、backend 500、partial market history。Evidence：`.omo/evidence/frontend-demo-integration/phase-4/task-10-browser/`。

  **Commit：** Y；`feat: add strategy risk analytics`；执行完整 Phase 4 gate、更新 `PROGRESS.md`、push `origin/dev` 并证明 parity。

- [ ] 11. 建立 Report source validation、job repository 和 safe PDF artifact boundary

  **问题分析：** PDF renderer 能输出文件，但固定 sections、无 source provenance、无 metadata/status、无 safe download owner。直接保存 frontend 提供的 path 或从缺失数据生成会造成安全和可信度问题。

  **解决方案：**

  - 新建 `reporting/models.py`、`reporting/repository.py`、`reporting/service.py` 与 `test/reporting/test_service.py`；使用 `data/generated-reports/` 作为 runtime root，并加入 `.gitignore`。
  - 在 `storage/store.py` 的 `system.db` 增加 report jobs/metadata：id/type/title/tickers/source_type/source_ids/parameters/status/artifact_name/error/timestamps；只存 artifact basename，不存/返回 `content_path` 或用户 path；browser contract 只暴露 report ID/status/download URL。
  - `ReportSourceResolver`：
    - Stock：按显式 analysis `session_id`，或 ticker+strategy 找最新 completed snapshot；必须 completed 且 ticker/strategy 一致。
    - Sector：必须提供 completed `scan_run_id`；tickers 只来自该 run；聚合其 snapshot/explanation 与可用 completed analyses，缺少 analysis 的 ticker 标 data gap。
  - 以 typed `ReportPayload/ReportSection` adapter 扩展 `utils/pdf_generator.py:201`，而不是继续依赖仅含旧 `PM_report` 的 loose dict；支持 allowlisted sections，不支持的 section 在 API boundary 422；renderer 不重新抓数据、不调用 LLM；空 required source 返回 error，不输出空壳 PDF。
  - 增加 PDF preflight：启动 job 前验证 renderer 与可用 Unicode/CJK font；生产缺字体返回稳定可行动错误，不暴露 absolute font path；tests 注入已知 test font/renderer，不依赖开发机偶然字体。
  - 文件写入 `.<report_id>.tmp`，flush/close/验证 `%PDF-` 与非零 size 后用 atomic `replace()` 成 `<report_id>.pdf`，最后才把 metadata 标 completed；异常删除本 job temp，不能留下可下载半文件。
  - `ReportRepository.resolve_artifact(report_id)` 拼接 internal root/basename 后 `resolve()` 并验证 parent；reject missing/symlink escape；下载 filename 从 sanitized metadata 生成。
  - bounded background worker 与 Backtest job recovery pattern 一致：pending/running/completed/failed；重启中断不永远 running。

  **Must NOT do：** 不接受 `content_path`/absolute path；不把 HTML/user input 直接交给 shell；不在 shared service import ACTIVE/LEGACY agent；不把 thesis `reports/` 目录当 runtime artifact root。

  **References：** `utils/pdf_generator.py:1-260`；`frontend/lib/types/models.ts:316-320`；`server/analysis_runs.py:53-158`；Todo 7 的 scan run repository；`.gitignore:225-234`；repo 根 `reports/` 是论文资产，禁止复用。

  **验收标准：** stock/sector fixture 生成有效 PDF magic `%PDF-` 和非零页/size；metadata 重启可读；completed 前不存在 final artifact；renderer/CJK preflight failure 不留下 temp/final；missing/wrong source 4xx/failed；path traversal/symlink test 拒绝；selected sections 反映在文档，不选 sections 不出现。

  **QA：** happy：completed analysis/scan fixtures 生成并读取 PDF；failure：running/failed analysis、missing scan、empty match、`../` artifact、deleted artifact、renderer exception。Evidence：`.omo/evidence/frontend-demo-integration/phase-5/task-11-report-service.txt`。

  **Commit：** N；与 Todo 12 一起完成 Phase 5 commit。

- [ ] 12. 实现 Stock/Sector Report API、history/download page，并完成 Phase 5 gate

  **问题分析：** Stock sections、Sector Generate、history/download 全部 decorative。Sector 的 “auto-discover” 必须通过已实现 Scanner ACTIVE path，而不是 shared report route 偷偷启动 agent。

  **解决方案：**

  - 先建 `test/server/test_reports_api.py`，覆盖 create/poll/list/download/source error/path safety。
  - 新建 `server/routes/reports.py`（SHARED）：
    - `POST /api/reports/stock`
    - `POST /api/reports/sector`
    - `GET /api/reports`
    - `GET /api/reports/{id}`
    - `GET /api/reports/{id}/download`
  - `frontend/lib/api/reports.ts` 改为 typed requests/job/list；download 仍只由 ID 组成 URL。
  - Stock UI：ticker、strategy、completed analysis source、真实 toggle sections；若没有 completed analysis，明确引导 Quick Ask，不生成假 report。
  - Sector UI：一次 click 先调用 `scannerApi.scanAgent(theme)` 获取 persisted `scan_run_id`，成功且有 matches 后调用 report sector endpoint；UI 展示两个阶段状态与各自错误；不得在 frontend 伪造 ticker list。
  - Report History 使用 API，显示 pending/running/failed/completed；poll unfinished；completed 才能 download；failed 显示 safe error；refresh 保留。
  - 删除 `MOCK_REPORTS`、固定 sections badge 和无 handler button；页面文案从 “10-15 page” 改为实际 source-driven report，不承诺固定页数。
  - 注册 route，更新 `docs/api-contracts.md:813-823`。

  **Must NOT do：** Sector report 不绕过 Scanner；未完成 report 无下载；不把 frontend `content_path` 当链接；不自动打开用户文件系统路径。

  **References：** `frontend/app/reports/page.tsx:28-195`；`frontend/lib/api/reports.ts:1-22`；`frontend/lib/types/models.ts:316-320`；`server/main.py:113-137`；`docs/api-contracts.md:813-823`；Todos 7-8/11。

  **验收标准：** Stock selected sections 真实影响 PDF；Sector network 顺序为 agent scanner→persisted scan→report；history reload 仍存在；download response `application/pdf`、safe filename；失败/empty source 可见；lint/build/API tests GREEN。

  **QA：** happy：browser 从已有 analysis 生成 Stock，theme 生成 Sector，reload history，下载并验证 PDF；failure：无 analysis、scanner zero matches/LLM failure、renderer failure、download pending/missing。Evidence：`.omo/evidence/frontend-demo-integration/phase-5/task-12-browser/`。

  **Commit：** Y；`feat: generate reports from persisted analysis artifacts`；执行完整 Phase 5 gate、更新 `PROGRESS.md`、push `origin/dev` 并证明 parity。

- [ ] 13. 为四个真实 Notifications channel 补安全 configured-state、使用指引和 Phase 6 gate

  **问题分析：** Email/Telegram/WeChat/WhatsApp 已有真实 adapter 和 test endpoints，不能归入“未实现”。用户困惑来自配置字段没有 provider-specific guidance、无法一眼判断 configured、错误不够行动化，以及 docs contract 仍写 Feishu。

  **解决方案：**

  - 先扩展 `test/test_notification_channels.py` 和 route tests（新建 `test/server/test_notification_settings.py`），覆盖每 channel configured/unconfigured/test response、secret masking 和 partial config。
  - `server/routes/settings.py` 的 safe response 增加每 channel `configured` 与 `missing_fields`（只列 field name，不列 value）；test endpoint 保留真实发送逻辑，但错误 message 要能指向缺失字段。
  - 在 notification boundary 增加统一 safe error/redaction helper：Telegram tokenized URL、bot token、chat IDs、Email/WhatsApp recipients、access token、WeChat webhook URL、provider response body 都不得进入 logger、API response、UI 或 evidence。`TelegramChannel` 当前会记录原始 chat_id，必须先写会失败的 caplog regression；requests/http exceptions 只映射为稳定 provider/status/category 文案，不能返回原始 exception URL/body。
  - `frontend/lib/types/models.ts` 增加 typed notification status；`frontend/app/settings/page.tsx` 每 channel 显示 Configured/Incomplete、必填字段、Test pending/success/failure。
  - 新建 `docs/notifications.md`，执行阶段使用开放互联网工具核验并链接 provider 官方文档：
    - Telegram：BotFather token、用户先与 bot 对话/加入群、取得 chat ID、保存并 Test。
    - Email：SMTP host/port/TLS/username/password/sender/recipients，提醒 provider app password 差异。
    - WeChat：企业微信群机器人 webhook URL。
    - WhatsApp：Meta Cloud API access token、phone number ID、E.164 recipients 与模板/会话限制。
  - Settings 内联简版帮助链接到 repo docs/官方 docs；说明分析完成/失败、approval、watchlist alert 的现有触发点。
  - 修正 `docs/api-contracts.md:839-859`：列出 test-email/telegram/wechat/whatsapp，删除未实现 Feishu。
  - Browser QA 使用 unconfigured/monkeypatched local test，不向真实 recipient 发消息，不截取 secrets。

  **Must NOT do：** 不添加 Feishu/Slack/Discord；不返回 secret 长度以外的可识别信息；不把 bot token/chat ID 写文档、fixture、截图；不编辑 `properties.env`。

  **References：** `server/routes/settings.py:61-210`；`notification/channels.py:78-310`；`notification/manager.py`；`frontend/app/settings/page.tsx:402-459`；`frontend/lib/types/models.ts:328-346`；`server/routes/analyze.py:460-535`；`server/routes/approvals.py:237-260`；`server/routes/watchlist.py:417-471`；`test/test_notification_channels.py`；`test/test_watchlist_alerts.py`。

  **验收标准：** 四 channel configured state 与 missing fields 准确；masked secrets 永不回传 raw；caplog/API/UI/evidence 均不含 token、chat ID、recipient、webhook、provider body；test endpoint 的 unconfigured/transport failure 稳定且可行动；UI 帮助和 test feedback 可见；官方 links 执行时可访问/已核验；现有 notification consumers tests 不回归。

  **QA：** happy：monkeypatched transports 对四 channel 返回 success；failure：逐字段缺失、transport 4xx/timeout、invalid recipient；browser 不泄 secret。Evidence：`.omo/evidence/frontend-demo-integration/phase-6/task-13-notifications/`。

  **Commit：** Y；`docs: add notification setup and status guidance`；执行完整 Phase 6 gate、更新 `PROGRESS.md`、push `origin/dev` 并证明 parity。

- [ ] 14. 完成跨页面真实验收、runtime debugging/review、issue truth 更新和 Phase 7 push

  **问题分析：** 单模块 tests 不能证明 demo 已移除，也不能证明刷新、切换 identity、job recovery、下载和通知指引在真实 UI 中成立。Issue tracker 只能在这一阶段按证据更新。

  **解决方案：**

  - 启动真实 backend/frontend，记录 OpenAPI；确认 backtest/scanner/risk/reports paths 已注册，strategy/memory/settings paths 保持。
  - 建立一个可清理的 QA dataset：两个 strategy、不同 ticker/decision targets、watchlist、stored OHLCV/fundamentals/meta、一个 completed analysis；不依赖 production secrets，QA 完成后删除创建的业务实体/runtime artifacts。
  - 依次驱动 `/strategies`、`/quick-ask`、`/memory-lab`、`/backtest`、`/scanner`、`/risk`、`/reports`、`/settings`：happy path + 至少一个 failure/empty path + refresh/navigation restore；检查 browser console/network。
  - `rg` production frontend，确保清单相关页面不存在 `MOCK_`、hard-coded demo strategy names、`hasRun=true`/`hasScanned=true`、fixed report rows；grep 只是补充，不能代替 browser。
  - 运行完整 gate；再运行 `omo:review-work` 与 `omo:debugging` runtime audit。Debug ledger 至少提出三条不同 hypothesis，并各用运行证据证伪/确认，例如：
    1. job 仅存在内存，backend restart 后丢失；
    2. strategy query key 缺 ID，切换时展示 stale data；
    3. report download 可被 path traversal 或 pending status 绕过。
  - 四个 final reviewer lane 全部 APPROVE 后，才修改 `bugs/bug-and-issues-list.md`：
    - Strategy New Strategy 条目注明经 regression 已真实实现；不要声称本计划才首次实现 CRUD。
    - Memory 条目改为 strategy selector/identity 接线已验证；说明 create 本身不生成 memory。
    - Backtest/Scanner/Risk/Reports 只在各自 browser/API evidence 通过时移到 Fixed。
    - Notifications issue 标为“真实 channel + 指引完成”，不是“backend newly implemented”。
  - 更新 `PROGRESS.md` 最终 entry；只 stage 本 phase docs/必要 closeout 文件；commit/push/parity。

  **Must NOT do：** 不因 full suite green 就跳过 browser；不保留 QA secrets/data；不修改 unrelated bug entries；不把 reviewer timeout/ack-only 当 APPROVE。

  **References：** `bugs/bug-and-issues-list.md:3-42`；`CLAUDE.md:39-59`；`plans/dev-branch-merge/dev-acceptance-cases.md:104-216,370-383`；Todos 1-13 的 evidence；所有变更页面和 routes。

  **验收标准：** 完整 tests/type/lint/build 全绿或仅有明确记录且与本 scope 无关的 pre-existing failure；每页真实 QA 有 evidence；三条 debug hypothesis 有 runtime evidence；F1-F4 全部 APPROVE；issue list 逐项与证据一致；final commit 已 push `origin/dev` 且 remote HEAD 等于 local HEAD；worktree 不含本任务临时文件/secret/QA artifact。

  **QA：** happy：完整用户旅程；failure：server restart、backend unavailable、empty data、invalid inputs、download not ready、notification unconfigured；Evidence：`.omo/evidence/frontend-demo-integration/phase-7/`。

  **Commit：** Y；`docs: close frontend demo integration issues`；执行完整 Phase 7 gate、push `origin/dev`、证明 parity。

## Final verification wave

> 在 Todo 14 的完整 gate 后并行运行；ALL 必须无条件 APPROVE。任何 timeout、ack-only、`BLOCKED`、缺 evidence 或“看起来可以”都不算批准。结果先呈现给用户；只有用户确认 closeout 后才宣告整个 Goal 完成。

- [ ] F1. **Plan compliance audit**：逐条映射 Must have/Must NOT have/Todos/phase commits/evidence；证明没有漏掉 decorative control、没有提前更新 tracker、七个 `origin/dev` phase commits 均存在。
- [ ] F2. **Code quality review**：重点审查 track imports、Pydantic/TypeScript contract、SQLite transaction/thread safety、job recovery、no-lookahead、missing-data semantics、secret/path safety、无 `as any`/ignored errors。
- [ ] F3. **Real manual QA**：独立 reviewer 重跑真实 browser + curl，不复用 worker 自述；覆盖 strategy identity、job refresh/restart、Scanner 三 mode、Risk strategy switch、Report download、Notification unconfigured guide。
- [ ] F4. **Scope fidelity**：确认未修改 `quick_ask/`/`properties.env`，未加真实 broker/Redis/index fixtures/unsupported channels，未提交运行数据/QA artifacts/unrelated dirty files。

Reviewer receipts 写入 `.omo/evidence/frontend-demo-integration/final-review/`，并在 `PROGRESS.md` 只记录结论和 evidence path，不粘贴 secrets 或大段运行日志。

## Commit strategy

### 必须形成的 phase commits

1. `feat: connect strategy lifecycle and scoped memory`
2. `feat: run persisted backtests from the web`
3. `feat: implement the tracked-universe scanner`
4. `feat: add strategy risk analytics`
5. `feat: generate reports from persisted analysis artifacts`
6. `docs: add notification setup and status guidance`
7. `docs: close frontend demo integration issues`

若执行时因代码自然边界必须调整 message，可保持 `<type>: <description>` 且一 phase 一 commit；不得把多个 phase squash 成一个，也不得把一个未完成 phase 拆成“WIP”推送。每个 commit body 引用对应 `PROGRESS.md` entry 和主要验证命令。

### Remote 安全

- 目标仅为 `origin/dev`；本计划不要求同步 `upstream/dev`。
- 每 phase 开工和 push 前 fetch；remote ahead 时先检查差异，再安全 rebase/integrate + rerun phase gate；禁止 `--force`/`--force-with-lease` 和任何历史重写。
- 只 stage 本 phase owned files；若发现并发改动触碰同一文件，重新读取、保留双方正确内容、重跑相应 tests；无法无损合并时才向用户报告一个精确 blocker。
- push 后必须 `git ls-remote --heads origin dev` 对比 local HEAD；仅看到 `git status` clean 不构成远端成功证明。

## Success criteria

1. `bugs/bug-and-issues-list.md` 中列出的 Backtest、Scanner、Risk、Reports 控件都经过真实 backend/browser 驱动；不存在 production mock/fixed result fallback。
2. Strategy create/list 被证明原本已真实可用；新增 lifecycle/clone 是 persisted 且 UI 可观察；没有虚假 scheduler/liquidation 承诺。
3. Quick Ask 发送所选 `strategy_id`，Memory Lab 能观察同 strategy 的真实 memory，且跨 strategy 隔离；create 不制造 memory。
4. Backtest no-lookahead test 能抓到未来 sentinel，API job 跨 refresh/restart 状态合理，result 只使用 canonical broker view，CSV 可下载。
5. Scanner universe 只来自真实 tracked sources；Rule/Agent/Belief 最终调用同一 typed deterministic engine；missing data 与 LLM/tool failure 明确。
6. Risk 明确标记 decision-target source，计算值可由历史行情/weights 复算；不同 strategy 数据确实不同；无数据不显示零值 mock。
7. Stock/Sector reports 有可追溯 source IDs、持久化 history/status、安全 PDF 下载；Sector 使用 persisted Scanner run。
8. Email/Telegram/WeChat/WhatsApp 的 backend truth、configured state、test feedback、官方指引一致；没有 secret 泄漏或未实现 channel 漂移。
9. 七个 phase 均有独立 commit、`PROGRESS.md` entry、验证 evidence，且每次已 push 到 `origin/dev` 并证明 parity。
10. 完整 pytest/BasedPyright/Ruff/frontend lint/build、真实 manual QA、三 hypothesis runtime audit、F1-F4 review 全部通过；issue tracker 最后更新；worktree 无本任务临时 artifact 或无关变更。
