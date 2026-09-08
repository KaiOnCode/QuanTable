# 中期汇报总纲

用途: 2026-06-03 与导师线上交流时快速定位可讲内容。主口径是工作汇报, 不是夸大式贡献陈述。

## 一句话定位

项目已从"多智能体给出股票分析和 PM 决策"推进到"PM 决策可以进入可验证的本地模拟券商执行域"; 当前 `feat/broker-plus` 的核心产出是 broker-owned execution-domain contract, 为后续 FastAPI、React、HITL、审计、记忆和真实券商 adapter 留出稳定边界。

## 三分钟主线

1. 原始系统已经有市场、新闻、基本面、风险、PM 五类 Agent, 能输出投资建议, 但建议之后缺少交易执行、反馈和审计闭环。
2. `feat/broker` 先补齐 broker 基线: 模型、配置、事件、gateway、mock engine、风控、ledger、execution node、backtest runner 和 Streamlit 回测展示。
3. `feat/broker-plus` 再把执行域做成未来平台可消费的契约: 身份字段、账户隔离、事件 sink、账本 backend 协议、public views、结构化执行报告、回测 JSON、`as_of` 回测边界、幂等下单、确定性执行时机。
4. 当前分支验证结果: `uv run pytest -q` 为 `97 passed`, `ruff check`、`ruff format --check`、`basedpyright --baselinefile bugs/basedpyright/baseline.json` 均通过。
5. 下一步不是继续扩 broker 内核, 而是建立 integration branch: 接入前端/后端、HITL、memory、notification、no-lookahead data service, 再考虑真实券商 adapter。

## 推荐汇报顺序

| 顺序 | 内容 | 对应文件 |
| --- | --- | --- |
| 1 | 项目背景与当前阶段 | [01-project-stage.md](01-project-stage.md) |
| 2 | 已完成工作主线 | [02-work-mainline.md](02-work-mainline.md) |
| 3 | broker-plus 技术重点 | [03-broker-plus-technical-summary.md](03-broker-plus-technical-summary.md) |
| 4 | 测试、质量门与分支证据 | [04-validation-and-evidence.md](04-validation-and-evidence.md) |
| 5 | 后续计划与问答口径 | [05-next-plan-and-qa.md](05-next-plan-and-qa.md) |

## 可直接开场

我们这段时间主要补的是执行闭环。原系统的优势是多 Agent 分析, 但 PM 输出后没有标准化 broker 接口、订单生命周期、交易账本和执行结果反馈。因此我先在 `feat/broker` 做了本地模拟券商基线, 再在 `feat/broker-plus` 把它升级成执行域契约, 让后续 Web API、前端、HITL、审计和真实券商 adapter 都可以消费同一套语义。

## 会议中应避免的表述

- 不说"已经接入真实券商", 改说"已完成本地模拟券商和 adapter-ready contract"。
- 不说"完整 FastAPI/React 平台已完成", 改说"broker 执行域已准备好被平台层接入"。
- 不说"完整 HITL 系统已完成", 改说"执行报告中已固定审批快照语义, 完整审批队列和 UI 属后续集成"。
- 不说"全仓库类型债务清零", 改说"使用 baseline 隔离历史类型债务, 当前增量质量门通过"。
- 谨慎说"回测完全无前视偏差", 当前更稳妥的说法是"broker-plus 已加入 `as_of` 合同和 scoped harness, 下一步要把 data service 层也强制 no-lookahead"。
