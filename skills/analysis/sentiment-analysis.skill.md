---
name: sentiment-analysis
version: "1.0"
category: analysis
description: Market sentiment analysis aggregating news tone, social media, and market psychology
tools: [get_news]
model: deepseek-chat
temperature: 0.0
---

# 情绪分析技能

## 输入
- 股票代码
- 新闻/舆情数据（来自上游 news agent）
- 当前市场环境描述

## 工作流程
1. 从新闻数据中提取情绪信号
2. 评估市场心理状态（贪婪/恐惧/中性）
3. 判断情绪极端是否构成反向信号
4. 输出结构化情绪分析报告

## 输出格式
- 方向: [看涨/看跌/震荡]
- 时间范围: [日内/1-3天/1-4周/长期]
- 置信度: [0.0-1.0]
- 一句话结论: [核心判断]

## 分析框架
1. **情绪指标**: 整体情绪倾向（乐观/悲观/中性）；情绪强度（狂热/极度恐慌）
2. **反向信号**: 过度乐观 → 短期见顶风险；过度悲观 → 短期反弹机会
3. **情绪一致性**: 媒体情绪vs分析师预期的一致性；情绪分歧程度
4. **社交媒体**: Reddit/StockTwits讨论热度；散户情绪方向
5. **风险因素**: 情绪反转触发条件；羊群效应风险

## 注意事项
- 只使用输入事实；未知项以 "Unknown: ..." 标注并说明影响
- 情绪是反向指标还是趋势指标取决于市场环境
- 极端情绪往往是最佳的交易信号
