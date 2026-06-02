# WIP

## 已确认集成提醒

- 未来 HITL manager 应薄接 broker-owned `ExecutionReportView` / execution report 合同，消费 broker-plus 已定义的 approval snapshot、execution status 和 execution-domain events；不要让 HITL manager 绕过 broker report、重写 execution semantics，或把审批队列、通知、UI、interrupt/resume 提前塞进 `feat/broker-plus`。
- Partial fills、流动性/成交量约束、复杂成交模型属于 deferred contract-breaking enhancement。后续 integration/platform 分支不要因为前端草案中出现 `partially_filled` 就默认 broker-plus 已支持该 public status；若要启用，必须先单独冻结 `OrderView`、`ExecutionReportView`、ledger/outcome、event vocabulary 和回归门，再实现 broker engine 行为。
- Async broker callbacks 和完整 adapter lifecycle 不阻塞当前 upstream 分支合并。`feat/broker-plus` 只应先提供 `client_order_id` / idempotency 级别的最小 adapter-readiness；真实 broker adapter、SDK/network calls、external order update replay、accepted/partial/cancel-pending 等完整生命周期状态应在 integration/platform branch 单独冻结合同后实现。
