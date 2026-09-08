# 项目背景与当前阶段

## 项目背景

本项目是 HKU MSc CS 毕业设计中的智能股票分析系统。基础形态是基于 LangGraph 的多智能体工作流:

```text
START -> 市场分析师 / 新闻分析师 / 基本面分析师并行 -> 风险分析师 -> PM Agent -> END
```

原有系统能给出股票分析、方向判断和 PM 决策, 但 PM 决策之后缺少统一交易执行层。也就是说, 系统可以回答"建议买入/持有/卖出", 但还不能稳定回答"如何下单、是否成交、账户如何变化、交易结果如何回写、后续如何审计"。

## 为什么优先做 Broker

当前优先方向是 Gap C: Broker Mock + Feedback。它解决的是从建议系统到执行闭环的中间层:

- 标准化 broker gateway, 为未来真实券商 adapter 留接口。
- 把订单、成交、持仓、账户、风控、事件、账本纳入统一执行域。
- 让 PM 决策进入 `execution_node`, 输出结构化 execution report。
- 让回测结果可以导出为 trades、portfolio、metrics 和 public JSON view。

这个方向适合中期汇报, 因为它既是功能推进, 也是系统架构边界的补强。

## 当前阶段判断

当前 `feat/broker-plus` 不是完整产品闭环, 但已经完成执行域底座:

- 已完成: 本地 `MockBrokerEngine`、风控、订单/成交、账户隔离、事件、账本、执行报告、回测结果视图、测试回归。
- 已完成: 面向未来 API/前端/审计的 broker-owned view/serializer contract。
- 已完成: `strategy_id`、`account_id`、`session_id`、`decision_id` 贯穿 broker 执行域。
- 未完成: 完整 FastAPI/React 产品层、真实券商接入、生产持久化、完整 HITL manager、MemoryStore、通知系统、权限/合规审计。

更准确的阶段表述:

> 我们已经把"PM 决策到模拟交易执行"的核心执行域做成可测试、可序列化、可审计的 contract。下一阶段重点是平台集成, 而不是继续把所有平台职责塞进 broker。

## 分支溯源

已在本地刷新 `origin` 和 `upstream` 远端引用。当前关键状态:

| 分支 | Tip | 说明 |
| --- | --- | --- |
| `feat/broker-plus` | `8988e4b` | 当前工作分支 |
| `origin/feat/broker-plus` | `8988e4b` | 与当前分支一致 |
| `upstream/feat/broker-plus` | `8988e4b` | 与当前分支一致 |
| `feat/broker` / `origin/feat/broker` | `69ea315` | broker-plus 的前导分支 |
| `upstream/feat/broker` | `400e0aa` | 较早的 broker 分支祖先 |

分支关系:

- `upstream/feat/broker...feat/broker` 为 `0/4`, 说明本地/`origin` 的 `feat/broker` 在 upstream 旧 broker 线上多 4 个提交。
- `feat/broker...feat/broker-plus` 为 `0/24`, 说明 `feat/broker-plus` 是 `feat/broker` 的直接后继, 多 24 个提交。
- `origin/feat/broker-plus...upstream/feat/broker-plus` 为 `0/0`, 说明两个远端的 broker-plus 跟踪引用一致。

谨慎点: `feat/broker` / `feat/broker-plus` 与当前 `upstream/main`、`upstream/feat/frontend-foundation` 是平行演进, 不能说 broker-plus 已经基于最新 upstream main 完成集成。

## 时间线

| 时间 | 工作线 | 可汇报内容 |
| --- | --- | --- |
| 2026-04-13 | `feat/broker` | broker Phase 1-5: 模型、引擎、风控、账本、执行节点、回测和 Streamlit 展示 |
| 2026-05-29 至 2026-05-30 | `feat/broker` planning | broker-plus 方向分析、premerge 调整、冻结契约与实施计划 |
| 2026-05-30 | `feat/broker-plus` | 身份字段、账户隔离、event sink、public serializers、结构化 execution report、测试目录重组 |
| 2026-06-02 | `feat/broker-plus` integration-owned | `as_of` 回测合同、identity filters、`client_order_id` 幂等、事件 vocabulary、execution outcome view、确定性执行时机、contract mapping |
