---
name: fundamental-analysis
version: "1.0"
category: analysis
description: Fundamental analysis of financial statements, valuation, and business quality
tools: [get_fundamentals]
model: deepseek-chat
temperature: 0.0
---

# 基本面分析技能

## 输入
- 股票代码
- 分析日期（默认今天）
- 当前持仓比例

## 工作流程
1. 通过 `get_fundamentals` 获取财务数据
2. 分析盈利能力、成长性、估值水平、财务健康度
3. 输出结构化基本面分析报告

## 输出格式
- 方向: [看涨/看跌/震荡]
- 时间范围: [日内/1-3天/1-4周/长期]
- 置信度: [0.0-1.0]
- 一句话结论: [核心判断]

## 分析框架
1. **盈利能力**: EPS趋势；毛利率/净利率水平与趋势；ROE杜邦分解
2. **成长性**: 营收YoY增速；EPS YoY增速；增长质量（有机vs并购）
3. **估值水位**: PE/PB/PS 历史分位数；EV/EBITDA 行业比较；PEG合理性
4. **财务健康**: 资产负债率；流动比率；自由现金流；商誉风险
5. **护城河评估**: 行业地位；竞争格局；客户/供应商集中度

## 注意事项
- 只使用输入事实；未知项以 "Unknown: ..." 标注并说明影响
- 估值需结合行业平均和公司历史区间
- 关注财务数据的质量和一致性
