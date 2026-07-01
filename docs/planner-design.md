# Planner 模块设计

## 目标

让 Agent 在执行工具前**先规划再行动**，而不是看到请求就直接调工具。

## 设计原则

1. **零改动 loop.py** — 通过 system prompt 注入实现，不碰核心循环
2. **分类触发** — 简单查询跳过规划（"AAPL price"不需要规划），复杂查询才注入
3. **无额外 API 调用** — 规划指令作为 system prompt 的一部分，不增加延迟
4. **参考 Claude Code plan mode** — 但适配 DeepSeek 的能力水平

## 实现方案

### 新文件: `agent/planner.py`

```
agent/planner.py
├── COMPLEX_KEYWORDS        — 触发复杂分类的关键词列表
├── QueryClassifier         — 判断查询是否需要规划
│   └── is_complex(msg) → bool
└── get_plan_instruction()  — 返回规划指令文本
```

### 修改: `agent/prompts.py`

在 `build_system_prompt()` 中，对复杂查询在 task_rules 后插入:

```python
if QueryClassifier.is_complex(user_message):
    sections.insert(2, get_plan_instruction())
```

## 分类逻辑

`QueryClassifier.is_complex()` 返回 True 当:
- 消息长度 > 50 chars，或
- 包含复杂关键词: "analyze/compare/research/分析/对比/研究/评估/推荐/which is better/should I buy/comprehensive/detailed"

## 规划指令内容

```
## Planning
Before calling tools, briefly state your plan: what data you need, in what
order you will get it, and why. Keep it to 1-2 sentences. Then call the tools.

Example: "I need NVDA price, indicators, and news. I'll call get_price,
get_indicators, and get_news simultaneously, then analyze the results."
```

## 预期效果

| 指标 | 之前 | 之后 |
|------|:---:|:---:|
| 复杂查询首轮 tool call 数量 | 3-4 (盲目) | 2-3 (有目的) |
| 迭代次数 | 2-3 | 1-2 |
| "不知道调什么" | 偶尔 | 大幅减少 |
| 简单查询影响 | N/A | **零影响** (跳过规划) |

## 实施步骤

1. 创建 `agent/planner.py` (40 lines)
2. 修改 `agent/prompts.py` `build_system_prompt()` (3 lines added)
3. 单元测试: 验证分类逻辑
4. Live test: 对比复杂查询的 tool call 模式

## 边界情况

- T39 ("Reply: OK") → len=9, no keywords → skip plan ✓
- T01 ("AAPL price") → len=10, no keywords → skip plan ✓
- T22 ("Compare AAPL and MSFT") → "compare" → trigger plan ✓
- T24 ("Give me a morning market brief") → "brief" not in keywords, len>30 → trigger ✓
- T41 ("分析一下茅台") → "分析" → trigger plan ✓
