"""Comprehensive agent quality tests — 49 tests, 11 categories."""

import json, time, urllib.request, os

API = os.environ.get("API_URL", "http://localhost:8000/api/agent/chat")
ALL = []

def call(msg, max_time=90):
    t0 = time.time()
    body = json.dumps({"message": msg}).encode()
    req = urllib.request.Request(API, data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=max_time) as r:
            raw = r.read().decode()
    except Exception as e:
        return {"error": str(e), "latency": time.time() - t0, "tools": [], "answer": None}
    lines = raw.split("\n")
    ev = {"tools": [], "answer": None, "latency": time.time() - t0}
    for i, l in enumerate(lines):
        if l.startswith("event: ") and i+1 < len(lines) and lines[i+1].startswith("data: "):
            e = l[7:].strip()
            try:
                d = json.loads(lines[i+1][6:])
                if e == "tool_call": ev["tools"].append(d.get("tool","?"))
                elif e == "answer": ev["answer"] = d.get("text","")
            except: pass
    return ev

def test(name, msg, checks):
    global ALL
    e = call(msg)
    failures = [n for n, fn in checks if not fn(e)]
    status = "FAIL" if failures else "OK"
    ans = (e.get("answer") or e.get("error","?"))[:100].replace("\n"," ")
    tools = ",".join(e["tools"][:5]) or "(none)"
    ALL.append((status, name, tools, ans, e["latency"]))
    print(f"  {status:4} {name:<35} | {tools:<35} | {ans}")
    for f in failures:
        print(f"       FAIL: {f}")

# Check helpers return (name, lambda)
def H(tool): return (f"tool_{tool}", lambda e: tool in e["tools"])
def N(tool): return (f"!tool_{tool}", lambda e: tool not in e["tools"])
def C(text): return (f"ans_{text[:20]}", lambda e: text.lower() in (e.get("answer") or "").lower())
def X(text): return (f"!ans_{text[:20]}", lambda e: text.lower() not in (e.get("answer") or "").lower())
def A(): return ("answered", lambda e: len(e.get("answer") or "") > 5)

# ── Tests ───────────────────────────────────────────────────────

print("=" * 80)
print("Agent Quality Tests — 49 tests, 11 categories" )
print("=" * 80)

suites = [
("金融-价格 (8)", [
    ("AAPL price", "What is AAPL price?", [H("get_price"), A(), C("AAPL")]),
    ("TSLA CN", "TSLA 多少钱", [H("get_price"), C("TSLA")]),
    ("NVDA 90d", "NVDA price history 90 days", [H("get_price"), C("NVDA")]),
    ("BABA", "BABA current price", [H("get_price"), C("BABA")]),
    ("GOOGL", "GOOGL stock quote", [H("get_price"), C("GOOGL")]),
    ("AMD", "AMD price in USD", [H("get_price"), C("AMD")]),
    ("MSFT", "MSFT price", [H("get_price"), C("MSFT")]),
    ("META", "META stock price today", [H("get_price"), C("META")]),
]),
("金融-技术面 (3)", [
    ("NVDA RSI", "NVDA RSI MACD", [H("get_indicators"), C("RSI")]),
    ("AAPL MA", "AAPL moving average", [H("get_indicators"), C("AAPL")]),
    ("TSLA techs", "TSLA technicals", [H("get_indicators"), C("TSLA")]),
]),
("金融-基本面 (3)", [
    ("AAPL PE", "AAPL PE PB ROE", [H("get_fundamentals"), C("PE")]),
    ("MSFT fin", "MSFT financial data", [H("get_fundamentals"), C("MSFT")]),
    ("NVDA val", "NVDA valuation metrics", [H("get_fundamentals")]),
]),
("金融-新闻 (3)", [
    ("NVDA news", "Latest NVDA news", [H("get_news"), C("NVDA")]),
    ("TSLA CN news", "Tesla 最近有什么新闻", [H("get_news"), C("TSLA")]),
    ("AAPL week", "AAPL news this week", [H("get_news"), C("AAPL")]),
]),
("搜索-通用 (4)", [
    ("Fed rate", "What is Fed interest rate right now", [A()]),
    ("AI chips", "Latest AI chip news 2026", [A()]),
    ("IPO 2026", "Biggest IPO in 2026", [A()]),
    ("SpaceX", "SpaceX latest news", [A()]),
]),
("非金融 (8)", [
    ("Python", "What is Python?", [A(), C("Python")]),
    ("Population", "World population 2026?", [A()]),
    ("Olympics", "Where will Olympics 2028 be?", [A()]),
    ("Tokyo weather", "Weather in Tokyo today?", [A()]),
    ("Einstein", "Who was Albert Einstein?", [A(), C("Einstein")]),
    ("Capital France", "Capital of France?", [A(), C("Paris")]),
    ("Math 2+2", "What is 2+2?", [A(), C("4")]),
    ("Time", "What time is it?", [A()]),
]),
("边界 (7)", [
    ("Empty", "", []),
    ("Single char", "?", [A()]),
    ("NVDA only", "NVDA", [A()]),
    ("Reply OK", "Reply: OK", [C("OK"), X("What would you")]),
    ("Help", "Help", [A()]),
    ("你是谁", "你是谁", [A()]),
    ("What can do", "What can you do?", [N("get_price"), A()]),
]),
("错误处理 (2)", [
    ("ZZZZZZ", "Get price for ZZZZZZ", [A(), X("closed at")]),
    ("Empty ticker", "Get price for   ", [A()]),
]),
("Skill (3)", [
    ("Candlestick", "How to use candlestick patterns", [H("load_skill")]),
    ("DCF", "Explain DCF valuation", [H("load_skill")]),
    ("Pair trading", "What is pair trading", [H("load_skill")]),
]),
("综合 (3)", [
    ("Analyze NVDA", "Analyze NVDA: price, technicals, news", [H("get_price"), A()]),
    ("AAPL vs MSFT", "Compare AAPL and MSFT", [H("get_price"), A()]),
    ("Morning brief", "Give me a morning market brief", [A()]),
]),
("中文 (5)", [
    ("腾讯股价", "帮我看看腾讯的股价", [A()]),
    ("茅台分析", "分析一下贵州茅台", [A()]),
    ("比亚迪", "比亚迪怎么样", [A()]),
    ("最近股市", "最近股市怎么样", [A()]),
    ("投资建议", "给我一个投资建议", [A()]),
]),
]

for cat_name, tests in suites:
    print(f"\n── {cat_name} ──")
    for name, msg, checks in tests:
        test(name, msg, checks)

passed = sum(1 for s,_,_,_,_ in ALL if s == "OK")
failed = sum(1 for s,_,_,_,_ in ALL if s == "FAIL")
avg = sum(r[4] for r in ALL) / max(len(ALL), 1)
print(f"\n{'='*80}")
print(f"  {passed} OK, {failed} FAIL, {len(ALL)} total | Avg: {avg:.1f}s")
print(f"{'='*80}")
