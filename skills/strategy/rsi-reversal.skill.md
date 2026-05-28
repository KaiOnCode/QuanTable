---
name: rsi-reversal
version: "1.0"
category: strategy
description: RSI mean reversion strategy — buy oversold, sell overbought
tools: [get_price, get_indicators]
model: deepseek-chat
temperature: 0.0
params:
  rsi_period: { type: int, default: 14, description: "RSI calculation period" }
  oversold: { type: int, default: 30, description: "Oversold threshold" }
  overbought: { type: int, default: 70, description: "Overbought threshold" }
---

# RSI 反转策略

## 策略逻辑
- **买入信号**: RSI 从下方突破 oversold 阈值
- **卖出信号**: RSI 从上方跌破 overbought 阈值
- **持仓管理**: 信号触发后分批建仓/减仓

## 参数
- `rsi_period`: RSI 计算周期（默认 14）
- `oversold`: 超卖阈值（默认 30）
- `overbought`: 超买阈值（默认 70）

## 适用场景
- 震荡/均值回归市场
- 短期交易（1-5天）

## 局限
- 强趋势市场过早逆势
- 需要配合趋势过滤
