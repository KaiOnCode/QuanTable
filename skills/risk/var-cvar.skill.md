---
name: var-cvar
version: "1.0"
category: risk
description: Value at Risk and Conditional VaR calculation using historical method
tools: [get_price]
model: deepseek-chat
temperature: 0.0
params:
  confidence: { type: float, default: 0.95, description: "VaR confidence level" }
  lookback_days: { type: int, default: 252, description: "Historical lookback in trading days" }
---

# VaR/CVaR 风险度量

## 方法
- **计算方式**: 历史模拟法
- **VaR**: 在给定置信度下，未来N天的最大预期损失
- **CVaR**: 超过VaR阈值后的平均损失（尾部风险）

## 参数
- `confidence`: 置信水平（默认 0.95）
- `lookback_days`: 历史回看天数（默认 252，约1年）

## 输出
- VaR_95: 95%置信度下的最大日损失
- CVaR_95: 尾部条件期望损失
- VaR_99: 99%置信度下的极端损失

## 局限
- 历史不必然重演
- 对极端事件（黑天鹅）估计不足
- 假设收益率分布稳定
