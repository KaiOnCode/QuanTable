# Agentic-Quant 功能差距与工作量评估（基于当前代码与 proposal）

更新时间：2026-04-01

## 1. 评估范围与结论

本评估对比了两部分：
- 当前仓库已实现能力（`agentgraph`、`agents`、`dataflow`、`streamlit_app.py`、`test/trade.py`）
- `reports/detail-proposal/proposal (2).typ` 中提出的目标系统能力

结论：项目主体分析链路已可运行，但 proposal 中后续 5 项核心增强能力大多尚未工程化落地，当前离“可审计、可回放、可闭环执行”的目标仍有显著差距。

## 2. 当前已实现能力（简述）

- 多智能体工作流：Market / News / Fundamentals 并行，随后 Risk，再到 PM（LangGraph 编排）。
- 数据源接入：Yahoo Finance、Google News、AkShare（部分），可完成实时分析与部分历史查询。
- 交互层：Streamlit 支持实时报告、图表指标、历史回测模式、报告导出。
- 回测探索：存在 `test/trade.py` 的交易执行模拟脚本，但尚未形成可复用的“系统级 broker 模块”。

## 3. 与 proposal 目标的核心差距

### Gap A: 持久化上下文（Context Management / Memory）
- 现状：LangGraph 使用 `MemorySaver`，会话状态以内存形式存在；`thread_id` 固定写死，且无数据库落盘。
- 缺口：
  - 无统一 `ContextStore` 抽象层
  - 无 SQLite schema（session、agent_report、tool_log、pm_decision、approval、execution）
  - 无会话回放、按 ticker 查询历史决策、跨重启恢复能力

### Gap B: 人工审批闭环（HITL）
- 现状：PM 输出即最终决策，系统没有审批状态机。
- 缺口：
  - 无风险触发策略引擎（如仓位变化阈值、信号冲突阈值）
  - 无“待审批/通过/拒绝/修改”数据结构与流程
  - 前端与消息端均无审批入口

### Gap C: 模拟券商执行引擎（Broker Mock + Feedback）
- 现状：有测试脚本级别的交易逻辑，不在主应用链路中。
- 缺口：
  - 无标准化 Broker 接口（place/cancel/query/orderbook/position）
  - 无统一订单与成交生命周期（NEW/PARTIALLY_FILLED/FILLED/CANCELED）
  - 无“执行结果 -> 反馈回代理决策”的持续闭环

### Gap D: 多渠道通知（Telegram / WhatsApp）
- 现状：无通知模块。
- 缺口：
  - 无消息适配层（模板、重试、幂等）
  - 无 Telegram Bot / WhatsApp Business API 对接
  - 无审批消息交互协议（approve/reject/modify）

### Gap E: 决策流可视化（Auditability）
- 现状：有流程图导出能力（graph PNG），但不是“单次分析会话的可追踪链路”。
- 缺口：
  - 无“节点输入输出+工具调用+关键参数”的事件记录
  - 无 Streamlit 交互式决策流页面（时间轴/节点图/展开详情）
  - 无审计导出（JSON/CSV/PDF）

## 4. 技术构建清单（按模块）

## M1. ContextStore 持久化层（SQLite）
- 技术内容：
  - 设计 `ContextStore` 接口与 `InMemoryStore` / `SQLiteStore` 双实现
  - 设计并迁移 SQLite 表结构
  - 改造 orchestrator：每个 agent 节点执行前后写入事件
  - 提供查询 API（按 session/ticker/date range）
- 主要产出：
  - `storage/` 模块 + migration 脚本
  - replay 查询函数 + 单元测试
- 预估工作量：**80-110 小时**

## M2. HITL 策略与审批流程
- 技术内容：
  - 规则引擎（阈值策略 + 可配置）
  - PM 后置路由：auto-pass vs pending-approval
  - 审批状态机与数据模型
  - Streamlit 审批面板（查看上下文、审批操作）
- 主要产出：
  - `hitl/` 模块、策略配置、审批页面
  - 审批日志与结果回写
- 预估工作量：**60-90 小时**

## M3. Broker Mock 执行引擎
- 技术内容：
  - 标准 BrokerGateway 接口
  - 订单撮合简化引擎（市价/限价，手续费、滑点）
  - 账户与仓位账本
  - 与主流程集成：PM 决策 -> 执行 -> 回写执行结果
- 主要产出：
  - `broker/` 模块 + 回测/仿真统一入口
  - 执行日志与绩效指标计算（PnL、胜率、回撤）
- 预估工作量：**100-140 小时**

## M4. 多渠道通知系统
- 技术内容：
  - NotificationAdapter 抽象层
  - Telegram Bot 对接（优先）
  - WhatsApp Business API 预留接口（可先 stub）
  - 消息模板与审批回调协议
- 主要产出：
  - `notification/` 模块
  - 审批请求通知、每日摘要通知、异常告警通知
- 预估工作量：**45-75 小时**

## M5. 决策流可视化与审计
- 技术内容：
  - 将 agent/tool/decision 事件结构化
  - Streamlit 决策流页面（节点图 + 时间轴 + 详情面板）
  - 导出审计报告（JSON/CSV）
- 主要产出：
  - `visualization/` 或 `ui/audit` 页面模块
  - 可追溯审计数据链路
- 预估工作量：**55-85 小时**

## M6. 质量保障与工程化补齐（建议新增）
- 技术内容：
  - 测试体系：模块单测、端到端集成测试、回归测试样例
  - 配置管理与 secrets 管理规范
  - 错误处理、重试、日志分级、监控指标
  - 文档与 demo 脚本更新
- 主要产出：
  - `tests/` 完整覆盖 + CI 基础流水线
  - 运维与开发文档
- 预估工作量：**60-90 小时**

## 5. 工作量统计（汇总）

按上面中位数估计：

- M1 ContextStore：95h
- M2 HITL：75h
- M3 Broker Mock：120h
- M4 Notification：60h
- M5 Visualization：70h
- M6 QA/工程化：75h

**合计中位数：495 小时**

区间估算（乐观-保守）：**400 - 590 小时**

> 若按 1 人每周有效 30 小时计算，约需 **13 - 20 周**。  
> 若 3 人并行（每人每周 20 小时），约需 **7 - 10 周**（含联调缓冲）。

## 6. 建议时间排期（可执行版本）

## Phase 1（第1-2周）：数据与状态底座
- 目标：完成 M1（ContextStore）+ 事件日志打点
- 里程碑：
  - SQLite schema 与迁移完成
  - 单次会话可查询与回放

## Phase 2（第3-4周）：审批闭环
- 目标：完成 M2（HITL）并接入主流程
- 里程碑：
  - 风险触发策略生效
  - Streamlit 审批页可执行 approve/reject/modify

## Phase 3（第5-7周）：执行引擎闭环
- 目标：完成 M3（Broker Mock）并形成执行反馈
- 里程碑：
  - PM 决策可自动生成订单并执行
  - 执行结果入库并进入下一轮上下文

## Phase 4（第8周）：通知接入
- 目标：完成 M4（先 Telegram，再 WhatsApp 预留）
- 里程碑：
  - 审批请求可消息触达并回传结果

## Phase 5（第9周）：可视化与审计
- 目标：完成 M5
- 里程碑：
  - 决策流图与时间轴可查看
  - 审计数据可导出

## Phase 6（第10周）：稳态化与交付
- 目标：完成 M6
- 里程碑：
  - 核心测试覆盖到位
  - Demo 剧本、文档、验收清单完成

## 7. 风险与缓冲建议

- 外部 API 风险：WhatsApp 审核与配额可能拖慢，建议 Telegram 先行。
- 数据一致性风险：事件日志、审批状态、执行账本必须统一 session_id 与幂等键。
- LLM 非确定性风险：建议固定评测样本集与温度参数，建立回归基线。
- 排期缓冲：建议总工时增加 15% 作为联调/返工 buffer。

## 8. 最小可交付（MVP）建议

如果时间有限，优先顺序建议：
1) M1 ContextStore  
2) M2 HITL  
3) M3 Broker Mock（先市价单）  
4) M5 可视化（先只读审计）  
5) M4 通知（先 Telegram）

这样可先达成“可回放 + 可审批 + 可执行 + 可追溯”的核心闭环，再扩展多渠道与高级策略。
