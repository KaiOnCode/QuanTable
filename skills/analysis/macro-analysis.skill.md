---
name: macro-analysis
version: "1.0"
category: analysis
description: Macro environment analysis covering interest rates, economic calendar, and policy
tools: [get_macro_calendar]
model: deepseek-chat
temperature: 0.0
---

# 宏观分析技能

## 输入
- 当前日期
- 宏观经济日历
- 行业/板块信息

## 工作流程
1. 通过 `get_macro_calendar` 获取近期经济事件
2. 分析利率环境、货币政策方向
3. 评估宏观因素对目标股票的板块影响
4. 输出结构化宏观分析报告

## 输出格式
- 方向: [看涨/看跌/震荡]
- 时间范围: [日内/1-3天/1-4周/长期]
- 置信度: [0.0-1.0]
- 一句话结论: [核心判断]

## 分析框架
1. **货币政策**: 利率方向（加息/降息/维持）；美联储/央行最新表态
2. **经济数据**: GDP增速趋势；就业数据；通胀数据（CPI/PPI/PCE）
3. **板块轮动**: 当前宏观环境利好的板块；利空的板块
4. **地缘政治**: 贸易政策变化；地区冲突影响
5. **资金流向**: 北向资金/外资流向；板块资金配置

## 注意事项
- 只使用输入事实；未知项以 "Unknown: ..." 标注并说明影响
- 宏观因素影响周期较长，区分短期波动和长期趋势
- 政策预期比政策本身更重要（buy the rumor, sell the fact）
