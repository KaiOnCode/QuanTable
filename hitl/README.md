# HITL (Human-in-the-Loop) 人工审批闭环

HITL 模块负责拦截高风险 AI 交易决策，将其提交给人类审批后再执行。

---

## 架构

```
PM 输出决策
    │
    ▼
┌─────────────────┐
│   规则引擎       │  ← 评估是否需要人工审批
│  (rules.py)     │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
auto-pass   pending
(直接执行)   (进入审批队列)
                │
                ▼
         ┌──────────────┐
         │  审批状态机    │
         │(state_machine)│
         └──────┬───────┘
                │
    ┌─────┬─────┴─────┬─────┐
    ▼     ▼           ▼     ▼
approved rejected  modified timeout
    │       │          │      │
    ▼       ▼          ▼      ▼
执行原参数  不执行    执行修改后 不执行
```

---

## 文件说明

| 文件 | 职责 | 行数 |
|------|------|------|
| `models.py` | Pydantic 数据模型：规则配置、PM 决策、审批请求、审批决策 | ~130 |
| `rules.py` | 规则引擎：评估 PM 决策是否需要人工审批 | ~80 |
| `state_machine.py` | 状态机：管理 pending → approved/rejected/modified 的转换 | ~100 |
| `executor.py` | 执行器：根据审批结果输出最终执行参数 | ~130 |
| `__init__.py` | 包入口，统一导出公共 API | ~50 |

---

## 触发规则（3 条）

| 规则 | 阈值 | 说明 |
|------|------|------|
| `position_change` | 20% | 目标仓位与当前仓位差距超过 20% |
| `low_confidence` | 0.5 | PM 置信度低于 50% |
| `high_concentration` | 30% | 单票目标仓位超过 30% |

所有阈值通过 `HITLRuleConfig` 配置，可在 `server/routes/analyze.py` 中调整。

> **注意**：`HOLD` + 目标仓位 0% 被视为"无操作"（`is_noop`），不触发审批。如需改变此行为，修改 `rules.py` 第 48-49 行。

---

## 使用方式

### 后端代码中触发 HITL

```python
from hitl import HITLRuleEngine, HITLRuleConfig, PMDecision

config = HITLRuleConfig(position_change_threshold_pct=20)
engine = HITLRuleEngine(config)

decision = PMDecision(action="BUY", target_position_pct=60, confidence=0.8)
needs_approval, rules = engine.evaluate(decision, current_position_pct=0)

if needs_approval:
    # 创建审批记录，等待人工处理
    store.create_approval("default", {...})
```

### 人工审批（通过 API）

```bash
# 查看待审批列表
GET /api/approvals?status=pending

# 通过审批
POST /api/approvals/{id}/approve
{"reviewer": "user"}

# 拒绝审批
POST /api/approvals/{id}/reject
{"reviewer": "user", "notes": "风险过高"}

# 修改后审批
POST /api/approvals/{id}/modify
{
  "reviewer": "user",
  "modified_action": "BUY",
  "modified_target_position_pct": 30,
  "notes": "降低仓位"
}
```

---

## 状态转换规则

```
PENDING → APPROVED   ✓
PENDING → REJECTED   ✓
PENDING → MODIFIED   ✓
PENDING → TIMED_OUT  ✓ (超时自动)

APPROVED → REJECTED  ✗ (非法)
REJECTED → APPROVED  ✗ (非法)
任何终态 → PENDING   ✗ (非法)
```

非法转换会抛出 `InvalidTransitionError`。

---

## 与现有系统的集成

| 集成点 | 文件 | 说明 |
|--------|------|------|
| 数据存储 | `storage/store.py` | `{strategy_id}.db` 中新增 `approvals` 表 |
| 分析流程 | `server/routes/analyze.py` | PM 输出后调用规则引擎，触发时在 SSE result 中返回 `approval_status: "pending"` |
| API 路由 | `server/routes/approvals.py` | 4 个端点：list/get/approve/reject/modify |
| 前端页面 | `frontend/app/approvals/page.tsx` | 展示审批列表，支持通过/拒绝/修改操作 |

---

## 已知限制

1. **执行器当前只记录结果，不调用 Broker**（由 Gap C 负责交易执行）
2. **HITL 配置硬编码在 analyze.py 中**，尚未接入策略配置系统
3. **审批超时功能未实现**（`timeout_at` 字段已预留）

---

## 调试

### 查看审批数据

```bash
# 命令行
sqlite3 data/default.db "SELECT id, ticker, status, reviewer FROM approvals;"

# 或 DB Browser for SQLite 打开 data/default.db
```

### 测试 HITL 触发

修改 `server/routes/analyze.py` 中的阈值，降低触发门槛：

```python
hitl_config = HITLRuleConfig(
    position_change_threshold_pct=5.0,   # 原本 20
    min_confidence_threshold=0.9,         # 原本 0.5
    max_single_ticker_pct=10.0,           # 原本 30
)
```

修改后**重启后端**，再分析任意股票，几乎一定会触发 HITL。

---

## 测试脚本

```bash
# 运行交互式测试（你来做审批人）
uv run python test_hitl_interactive.py
```
