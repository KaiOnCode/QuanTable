# 记忆自动注入 — 实现计划

## 当前状态

- `memory/store.py` — MemoryStore 已完整实现（OWM 评分、SQLite、recall/remember）
- `memory/models.py` — 5-layer MemoryRecord 已定义
- **问题**: MemoryStore 从未被 ACTIVE agent loop 使用。只有 LEGACY orchestrator 调用

## 目标

每一轮对话自动检索相关历史记忆并注入 system prompt，分析结束后自动保存记忆。

## 设计（参考 Claude Code）

Claude Code 的做法：
1. `findRelevantMemories()` — 轻量级 Sonnet side query，选 ≤5 条最相关记忆
2. 注入 system prompt 为 "## Relevant Memories"
3. 记忆漂移防御：告诉 AI 验证记忆是否过时

我们的适配：
1. 用关键词匹配代替 LLM call（零 API 成本）
2. 从 user message 提取 ticker → 查询 MemoryStore
3. 格式化为 Claude Code 风格的 memory section

## 实现步骤

### Step 1: `agent/memory_bridge.py` (新文件, ~60 lines)

连接 agent loop 和 MemoryStore 的桥梁模块。

```python
# agent/memory_bridge.py

def extract_tickers(message: str) -> list[str]:
    """从用户消息提取股票代码。纯正则，零 API 成本。"""
    import re
    # 匹配常见格式: AAPL, NVDA, 600519.SH, 0700.HK
    tickers = re.findall(r'\b[A-Z]{1,5}\b', message.upper())
    # 常见单词黑名单
    STOP_WORDS = {'A', 'I', 'OK', 'AI', 'US', 'HK', 'PE', 'PB', 'ROE',
                  'RSI', 'MACD', 'SMA', 'ETF', 'IPO', 'USD', 'CEO'}
    return [t for t in tickers if t not in STOP_WORDS and len(t) >= 2]

def retrieve_memories(user_message: str, limit: int = 5) -> str:
    """检索相关记忆并格式化为 prompt section。"""
    from memory.store import MemoryStore

    tickers = extract_tickers(user_message)
    if not tickers:
        return ""

    store = MemoryStore("data/memory.db")
    memories = []
    for ticker in tickers[:3]:  # 最多查 3 个 ticker
        memories.extend(store.recall(ticker=ticker, limit=3, min_score=0.3))

    if not memories:
        return ""

    # 去重 + 按 OWM score 排序
    seen = set()
    unique = []
    for m in sorted(memories, key=lambda m: m.owm_score, reverse=True):
        if m.id not in seen:
            seen.add(m.id)
            unique.append(m)

    unique = unique[:limit]

    lines = ["## Relevant Past Analysis"]
    lines.append("(Memories may be outdated — verify against current data before using.)")
    for m in unique:
        action = m.trade_record.get("action", "?")
        ticker = m.ticker
        date = m.created_at[:10]
        score = m.owm_score
        summary = m.episodic[:120].replace("\n", " ")
        lines.append(f"- [{ticker}] {date} | {action} | score={score:.2f} | {summary}")

    return "\n".join(lines)
```

### Step 2: 修改 `agent/prompts.py` (+5 lines)

在 `build_system_prompt()` 中注入记忆：

```python
# Dynamic: memory — retrieve relevant past analysis
memory_section = ""
if user_message:
    from agent.memory_bridge import retrieve_memories
    memory_section = retrieve_memories(user_message)
```

### Step 3: 修改 `agent/prompts.py` 输出组装 (+2 lines)

```python
return static + (memory_section or "") + (skill_section or "")
```

### Step 4: (可选) 分析后自动保存记忆

在 `agent/loop.py` 的 run() 完成时调用保存。初期跳过——先让检索工作。

## 测试计划

### T1: ticker 提取
```python
from agent.memory_bridge import extract_tickers
assert extract_tickers("AAPL price") == ["AAPL"]
assert extract_tickers("Compare AAPL and MSFT") == ["AAPL", "MSFT"]
assert extract_tickers("What is the current Fed rate?") == []
assert extract_tickers("分析茅台") == []  # 中文不匹配，后续加
assert extract_tickers("NVDA 600519 0700.HK") == ["NVDA"]
```

### T2: 记忆检索 (需要先插入测试数据)
```python
# 插入一条测试记忆
store = MemoryStore("data/memory.db")
record = MemoryRecord(
    id="test-001", strategy_id="default", ticker="AAPL",
    episodic="Analyzed AAPL. PE=35, strong buy signal.", owm_score=0.8,
    trade_record={"action": "BUY"}, created_at="2026-06-15T10:00:00Z"
)
store.remember(record)

# 检索
result = retrieve_memories("What is AAPL price?")
assert "AAPL" in result
assert "BUY" in result
```

### T3: prompt 集成
```python
p = build_system_prompt(registry, "AAPL price analysis")
assert "Relevant Past Analysis" in p  # 之前有 AAPL 记忆
p2 = build_system_prompt(registry, "What time is it")
assert "Relevant Past Analysis" not in p2  # 无 ticker
```

### T4: agent 对话验证
```bash
curl -d '{"message":"Analyze AAPL fundamentals"}' → 期望看到记忆被注入
```

## 涉及文件

| 文件 | 操作 | 行数 |
|------|------|:---:|
| `agent/memory_bridge.py` | 新建 | ~60 |
| `agent/prompts.py` | 修改 | +5 |
| `agent/loop.py` | 不变 | 0 |

总计：新建 1 文件，改 1 文件。loop.py 不动。
