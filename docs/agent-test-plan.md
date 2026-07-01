# Agent 功能测试计划 — 50 项

> 每个测试用 curl 直接调用 /api/agent/chat，验证结果

## 价格数据 (5)

T1.  "What is AAPL price?" → 期望: get_price 被调用，返回价格
T2.  "TSLA 多少钱" → 期望: get_price(TSLA) + 中文回答
T3.  "600519 股价" → 期望: get_price(600519) — A股
T4.  "Get me the price history of NVDA for 90 days" → 期望: get_price(NVDA, days=90)
T5.  "沪深300现在多少点" → 期望: 尝试搜索或价格查询

## 技术指标 (3)

T6.  "NVDA RSI MACD" → 期望: get_indicators(NVDA) + 解释指标
T7.  "AAPL moving average" → 期望: get_indicators(AAPL) + SMA
T8.  "What are the technicals for TSLA" → 期望: get_indicators(TSLA)

## 基本面 (3)

T9.  "AAPL fundamentals PE PB ROE" → 期望: get_fundamentals(AAPL)
T10. "MSFT 财务指标" → 期望: get_fundamentals(MSFT) + 中文
T11. "Compare PE ratios of AAPL and GOOGL" → 期望: 先 get_fundamentals(AAPL) 再 get_fundamentals(GOOGL)

## 新闻 (4)

T12. "Latest news about NVDA" → 期望: get_news(NVDA)
T13. "Tesla 最近有什么新闻" → 期望: get_news(TSLA)
T14. "Search for AI chip news" → 期望: search_news("AI chip") 或 web_search("AI chip")
T15. "What's happening with AAPL this week" → 期望: get_news(AAPL, days=7)

## 网络搜索 (3)

T16. "What is the current Fed interest rate" → 期望: web_search("Fed interest rate")
T17. "How is the US economy doing right now" → 期望: web_search
T18. "Latest IPO news 2026" → 期望: web_search 或 search_news

## 情绪分析 (2)

T19. "What is the market sentiment for TSLA" → 期望: get_sentiment(TSLA)
T20. "AAPL 市场情绪如何" → 期望: get_sentiment(AAPL)

## 综合查询 (5) — 最难，最需要验证

T21. "Analyze NVDA: price, technicals, fundamentals, and news" → 期望: 4 个工具被调用
T22. "Compare AAPL and MSFT as investments" → 期望: 价格+基本面 for both
T23. "Is TSLA a good buy right now" → 期望: 价格+技术面+情绪+新闻
T24. "Research 比亚迪 for me" → 期望: search_symbol + get_price + get_fundamentals
T25. "Give me a morning market brief" → 期望: generate_brief 被调用

## Skills (5)

T26. "How do I analyze a stock using candlestick patterns" → 期望: load_skill("candlestick")
T27. "Explain the DCF valuation method" → 期望: load_skill 相关技能或解释
T28. "What is pair trading strategy" → 期望: load_skill("pair-trading")
T29. "List available skills for crypto" → 期望: list_skills(category="crypto")
T30. "Search for skills about risk management" → 期望: search_skills("risk")

## 文件操作 (2)

T31. "List files in the current directory" → 期望: glob 或 read_file
T32. "Read the README.md file" → 期望: read_file("README.md")

## 元查询 (3)

T33. "What can you do" → 期望: 简短能力列表，不调工具
T34. "Help" → 期望: 简短帮助
T35. "你是谁" → 期望: 简短身份说明

## 错误处理 (3)

T36. "Get price for ZZZZZZ" → 期望: 工具返回错误，agent 说明找不到
T37. "Read file that does not exist" → 期望: 错误处理
T38. Empty message → 期望: 提示需要输入内容

## 边界条件 (5)

T39. "NVDA" (只有一个词) → 期望: get_price(NVDA) 被调用
T40. Very long message with multiple questions → 期望: 处理多步骤
T41. Message with special characters → 期望: 不崩溃
T42. Message with URL → 期望: 可能调用 web_fetch
T43. Chinese only query: "分析一下茅台" → 期望: search_symbol + get_price

## 多轮对话 (3)

T44. Round 1: "What is AAPL price" → Round 2: "How about MSFT" → 期望: round 2 调 MSFT
T45. Round 1: "Get NVDA news" → Round 2: "Now get its price" → 期望: round 2 调 get_price
T46. Round 1: "What tools do you have" → Round 2: "Use one to get TSLA price" → 期望: 调工具

## Session & 持久化 (3)

T47. Create session → send message → reload session → verify
T48. Delete session → verify gone
T49. Two concurrent sessions → verify isolation

## 前端集成 (2)

T50. Frontend build succeeds
T51. Frontend can load session history

---

## 测试方法论

每条测试:
1. curl 调用 → 检查 event 类型和 count
2. 如果 tool_call=0 且应该有: **记录为 FAIL, 分析原因**
3. 如果 tool_error > 0: **记录为 PARTIAL FAIL**
4. 如果 answer event 缺失: **记录为 FAIL**
5. 如果 answer 内容为"列出功能"而非实际操作: **记录为 FAIL (工具未使用)**

当前核心问题: **DeepSeek 有时不调用工具，而是描述自己能做什么**
修复方向: system prompt + tool description 优化
