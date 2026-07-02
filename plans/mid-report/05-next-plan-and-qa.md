# 后续计划与问答口径

## 后续主线

下一阶段建议建立 integration branch, 以 `feat/broker-plus` 为执行底座, 手工融合其他功能分支。原则是 broker-plus 不被覆盖, 平台层通过 contract 消费 broker。

推荐顺序:

1. No-lookahead data service: 把 `as_of` 从 broker/backtest contract 推进到 data tools/provider 层, 强制回测只能读取历史可见数据。
2. FastAPI / React 集成: 以 broker views 作为 API schema 来源或映射来源, 不让前端直接依赖内部 broker 模型。
3. HITL 接入: HITL manager 负责审批生命周期, broker 只接收审批结果和 modified target。
4. Memory / outcome loop: 执行完成后从 `ExecutionOutcomeView` 和 ledger 更新 decision memory / trade outcome memory。
5. Notification / monitor: 接 analysis complete、approval pending、execution complete、risk rejected 等事件。
6. 真实券商 adapter: 在稳定 mock + contract 后再接 sandbox, 不在当前 broker-plus 分支硬接 SDK。

## 当前风险

| 风险 | 当前状态 | 建议表述 |
| --- | --- | --- |
| 真实交易 | 未接真实券商 | 已具备 adapter-ready broker gateway 和幂等键 |
| 生产持久化 | event/ledger 仍是 in-memory | 已有 protocol boundary, 后续接 SQLite/ContextStore |
| HITL | 只有执行时审批映射和 placeholder | 完整 queue、timeout、UI、interrupt/resume 属后续 |
| 回测前视偏差 | 已有 `as_of` contract, data service 强制门控待做 | 下一步重点补 no-lookahead data sandbox |
| 前端产品闭环 | Streamlit 可展示, FastAPI/React 未在本分支完成 | 后续 integration branch 接入 |
| 多资产组合风险 | `max_total_position_pct` 仍是预留 | 单票风险已覆盖, 组合级风控后续实现 |
| 部分成交 | internal enum 预留, public view 暂不暴露 | 真实 broker adapter 前再定义 lifecycle |

## 导师可能问什么

### Q1: 现在系统到底能做什么?

可以说:

> 当前系统可以从多 Agent 分析走到 PM 决策, 并在启用 execution 时通过本地 mock broker 生成订单、成交、账户变化、事件和结构化执行报告。回测侧可以输出 trades、portfolio、metrics 和 public result view。

不要说:

> 已经可以实盘交易。

### Q2: Broker-plus 相比原 broker 的增量是什么?

可以说:

> 原 broker 解决"能不能模拟执行"; broker-plus 解决"执行结果如何被未来平台稳定消费"。增量主要是身份字段、账户隔离、事件 sink、账本 backend 协议、public serializers、结构化 execution report、回测 JSON、`as_of` 合同、幂等下单和确定性执行时机。

### Q3: 为什么不直接先做前端或真实券商?

可以说:

> 因为前端、HITL、memory、真实券商都依赖同一套执行语义。如果 broker contract 不稳定, 后续每个层都会重复解释订单状态、成交、账户、拒单和审批结果。先固定执行域, 后续集成风险更低。

### Q4: HITL 做到什么程度?

可以说:

> 当前 broker-plus 固定的是 execution-time mapping: pending、rejected、timed_out、modified 会以结构化 report 和 event 进入执行域。完整审批队列、通知、UI、interrupt/resume 不是 broker 职责, 放在后续 HITL manager。

### Q5: 回测有没有前视偏差?

可以说:

> 当前已把 `as_of` 纳入 BacktestRunner 和 orchestrator contract, 并有测试锁定每个交易日调用 agent 时的时间边界。下一步还要把 data service/provider 层做成强制 no-lookahead sandbox, 让工具读取也不能越过 `as_of`。

### Q6: 质量怎么保证?

可以说:

> 当前分支有 97 个 pytest 用例, 覆盖 broker、agentgraph、dataflow、agents、streamlit 五个域。本地最新验证中 pytest、ruff、format check 和 basedpyright baseline 检查全部通过。

### Q7: 这些工作怎么和团队其他分支合并?

可以说:

> broker-plus 与 upstream main/frontend 分支是平行演进, 不能直接说已经集成完成。下一步应建 integration branch, 以 broker-plus 作为执行域底座, 手工融合 FastAPI、React、HITL、memory、notification 等平台层。

## 结束语口径

> 中期阶段我们最重要的进展是把智能分析系统从"生成建议"推进到"建议可执行、执行可记录、结果可序列化、后续可审计"。接下来的工作会围绕集成闭环展开: 数据时点隔离、Web 平台、审批、人机协同、记忆反馈和通知追踪。
