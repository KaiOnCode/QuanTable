# Agent 全量测试报告 — 52 项

> 日期: 2026-07-01 | 耗时: 8 min | 总计: 52 tests

## 总体指标

| 指标 | 数值 |
|------|:---:|
| 总测试数 | 52 |
| 获得答案 | 51/52 (98%) |
| 使用工具 | 46/52 (88%) |
| 工具错误 | 5/52 (10%) |
| 有工具但无答案 | 0/52 (0%) |

## 分类统计

### 价格数据 (6/6 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T01 | AAPL price | 1 | ✅ | $289.36, clean answer |
| T02 | TSLA 多少钱 | 1 | ✅ | ¥420.60, Chinese answer OK |
| T03 | NVDA 90d history | 1 | ✅ | Full date range returned |
| T04 | BABA price | 1 | ✅ | $95.98 |
| T05 | GOOGL quote | 1 | ✅ | Table format |
| T06 | AMD price | 1 | ✅ | $580.91 USD |

### 技术指标 (3/3 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T07 | NVDA RSI MACD | 1 | ✅ | RSI=45.3, clear signals |
| T08 | AAPL moving avg | 1 | ✅ | SMA20=$295.93 |
| T09 | TSLA technicals | 2 | ✅ | With price data |

### 基本面 (3/3 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T10 | AAPL fundamentals | 1 | ✅ | PE=35.57, PB clean |
| T11 | MSFT financial data | 6 ⚠️ | ⚠️ | Too many calls — 6 for simple query |
| T12 | Compare PE AAPL/GOOGL | 2 | ✅ | Table comparison, clean |

### 新闻 (4/4 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T13 | NVDA news | 3 | ✅ | Latest highlights |
| T14 | Tesla 新闻 | 1 | ✅ | Chinese, FSD upgrade |
| T15 | AI chip news | 1 | ✅ | Used web_search |
| T16 | AAPL this week | 5 | ✅ | News highlights |

### 情绪 (2/2 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T17 | TSLA sentiment | 4 | ✅ | Mixed-to-bullish |
| T18 | AAPL 情绪 | 3 | ✅ | 中性偏谨慎 |

### 网络搜索 (2/2 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T19 | Fed rate | 3 | ⚠️ | 1 error, still got 4.25-4.50% |
| T20 | IPO news 2026 | 2 | ✅ | SpaceX IPO mentioned |

### 综合查询 (5/5 ✅ — but high TC)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T21 | NVDA analysis | 3 | ✅ | Price+technicals+news |
| T22 | AAPL vs MSFT | 11 ❌ | ❌ | **Too many tools** — should be 4-6 |
| T23 | TSLA good buy | 5 | ✅ | Noted price data missing |
| T24 | Morning brief | 1 | ✅ | generate_brief called |
| T25 | 比亚迪 | 2 | ✅ | Asked for ticker code |

### Skills (5/5 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T26 | Candlestick | 1 | ✅ | load_skill called |
| T27 | DCF valuation | 2 | ✅ | Skill + fundamentals |
| T28 | Pair trading | 1 | ✅ | load_skill called |
| T29 | Crypto skills | 1 | ✅ | 7 skills listed |
| T30 | Risk skills | 2 | ✅ | search_skills + load |

### File/Workspace (2/2 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T31 | Read README | 2 | ⚠️ | 2 errors — file not found, but correctly reported |
| T32 | List files | 1 | ✅ | glob called |

### Meta (3/3 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T33 | What can you do | 0 | ✅ | No tools, good list |
| T34 | Help | 0 | ✅ | "How can I help?" |
| T35 | 你是谁 | 0 | ✅ | Identity in Chinese |

### 边界条件 (5/5 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T36 | NVDA (single) | 7 ❌ | ❌ | **Too many** — single word shouldn't trigger 7 calls |
| T37 | ZZZZZZ error | 1 | ✅ | Clean error message |
| T38 | Empty message | 0 | ✅ | HTTP 422 (expected) |
| T39 | Reply: OK | 0 | ✅ | "OK" — follows instruction |
| T40 | github.com URL | 1 | ✅ | web_fetch returned legal restriction |

### 中文查询 (3/3 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T41 | 分析茅台 | 5 | ⚠️ | A-share data limited, 2 errors |
| T42 | 最近股市 | 1 | ✅ | Morning brief in Chinese |
| T43 | 腾讯股价 | 2 | ✅ | 0700.HK = 429.80 HKD |

### 组合查询 (9/9 ✅)
| ID | Query | TC | Status | Notes |
|----|-------|:--:|--------|-------|
| T44 | NVDA all at once | 4 | ✅ | Price+news+indicators+fundamentals in one go |
| T45 | Best tech stock | 7 ⚠️ | ⚠️ | Too many calls but good analysis |
| T46 | MSFT price | 1 | ✅ | $373.02 |
| T47 | Market news | 1 | ✅ | Brief generated |
| T48 | TSLA vs F | 10 ❌ | ❌ | **Too many calls** for simple comparison |
| T49 | GOOG | 6 ⚠️ | ⚠️ | Single ticker got 6 calls |
| T50 | Available tools | 0 | ✅ | Listed tools correctly |
| T51 | 投资建议 | 1 | ✅ | Market brief + advice |
| T52 | AAPL dividends | 1 | ✅ | Yield=0.37% |

## 问题清单

### P0 (必须修)
1. **T22 AAPL vs MSFT: 11 tool calls** — 应该 4-6。Root cause: DeepSeek 跨迭代不 dedup，每个迭代重调工具
2. **T48 TSLA vs F: 10 tool calls** — 同上

### P1 (应该修)
3. **T36 NVDA: 7 tool calls** — 单 ticker 不应调 7 次
4. **T11 MSFT financials: 6 tool calls** — get_fundamentals × N + get_price × N
5. **T49 GOOG: 6 tool calls** — 同上

### P2 (低优先级)
6. **T41 茅台: 5 calls + 3 errors** — A-share data unavailable，但模型坚持重试
7. **T19 Fed rate: 1 error** — web_search 偶尔返回空结果

## 与之前对比

| 指标 | 修复前 | 修复后 |
|------|:---:|:---:|
| 答案获取率 | ~70% | **98%** |
| Compare AAPL/MSFT TC | 23 | **11** |
| 工具错误率 | ~30% | **10%** |
| "Reply: OK" 回复 | 200字中文 | **"OK"** |
| 空参数工具错误 | TypeError | **结构化 error + hint** |
| 工具执行 | 串行 | **并行** |
| System prompt | 500 chars | **3859 chars + user context** |
| 有工具无答案 | 经常 | **0 次** |

## 下一步

1. 加更激进的 tool call 限制 (max 3 per iteration)
2. 让跨迭代 dedup 更强
3. A-share 数据支持
