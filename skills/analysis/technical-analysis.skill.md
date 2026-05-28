---
name: technical-analysis
version: "1.0"
category: analysis
description: Technical analysis using price action, trends, support/resistance levels
tools: [get_price, get_indicators]
model: deepseek-chat
temperature: 0.0
---

# 技术分析技能

## 输入
- 股票代码
- 回看天数（默认 90 天）
- 当前持仓比例

## 工作流程
1. 通过 `get_price` 获取价格数据
2. 通过 `get_indicators` 计算技术指标（RSI, MACD, SMA, ATR）
3. 分析趋势方向、动量、支撑/阻力位
4. 输出结构化技术分析报告

## 输出格式
- 方向: [看涨/看跌/震荡]
- 时间范围: [日内/1-3天/1-4周/长期]
- 置信度: [0.0-1.0]
- 一句话结论: [核心判断]

## 分析框架
1. **趋势分析**: SMA20/50 排列判断多空排列；价格相对均线位置
2. **动量分析**: RSI(14) 超买超卖区间；MACD 金叉死叉信号
3. **支撑阻力**: 近期高低点识别的关键价位；ATR 波动率评估
4. **量价关系**: 放量突破/缩量回调的含义解读
5. **风险提示**: 背离信号；假突破风险；关键事件窗口

## 注意事项
- 只使用输入事实；未知项以 "Unknown: ..." 标注并说明影响
- 技术指标交叉验证，避免单一指标误判
- 趋势 > 动量 > 支撑阻力 > 量价 的优先级
