---
name: ma-cross
version: "1.0"
category: strategy
description: Moving average crossover strategy — buy when fast MA crosses above slow MA
tools: [get_price, get_indicators]
model: deepseek-chat
temperature: 0.0
params:
  fast_period: { type: int, default: 20, description: "Fast moving average period" }
  slow_period: { type: int, default: 50, description: "Slow moving average period" }
---

# 均线交叉策略

## 策略逻辑
- **买入信号**: 快线 (SMA_fast) 上穿慢线 (SMA_slow) → 金叉
- **卖出信号**: 快线下穿慢线 → 死叉
- **持仓**: 有信号时全仓，无信号时空仓

## 参数
- `fast_period`: 快线周期（默认 20）
- `slow_period`: 慢线周期（默认 50）

## 适用场景
- 趋势明显的市场
- 中长期操作周期

## 局限
- 震荡市场频繁假信号
- 信号滞后于价格转折
