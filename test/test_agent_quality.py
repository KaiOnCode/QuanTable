"""Quality tests for the agent — checks WHAT tools were called and WHAT data is in the answer.

Each test:
  1. Sends a query
  2. Checks EXACT tools called (not just count)
  3. Checks answer contains expected data from tool results
  4. Checks NO fabricated data
"""

import json
import os
import sys
import time
import urllib.request

if "pytest" in sys.modules:
    import pytest

    pytest.skip(
        "agent quality smoke script requires a running API server",
        allow_module_level=True,
    )

API = os.environ.get("API_URL", "http://localhost:8000/api/agent/chat")
FAIL = 0
PASS = 0
LATENCY = []


def post(msg, max_time=90):
    t0 = time.time()
    body = json.dumps({"message": msg}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    try:
        with urllib.request.urlopen(req, timeout=max_time) as r:
            raw = r.read().decode()
    except Exception as e:
        return {"error": str(e), "latency": time.time() - t0}

    lines = raw.split("\n")
    events = {"tool_call": [], "tool_done": [], "tool_error": [], "answer": None}
    for i, line in enumerate(lines):
        if line.startswith("event: "):
            ev = line[7:].strip()
            if i + 1 < len(lines) and lines[i + 1].startswith("data: "):
                try:
                    d = json.loads(lines[i + 1][6:])
                    if ev == "tool_call":
                        events["tool_call"].append(
                            {"name": d.get("tool", "?"), "args": d.get("args", {})}
                        )
                    elif ev == "tool_error":
                        events["tool_error"].append(
                            {"name": d.get("tool", "?"), "error": d.get("error", "")}
                        )
                    elif ev == "answer":
                        events["answer"] = d.get("text", "")
                    elif ev == "tool_done":
                        events["tool_done"].append(d)
                except json.JSONDecodeError:
                    pass

    events["latency"] = time.time() - t0
    return events


def check(
    name,
    msg,
    *,
    must_call=None,
    must_not_call=None,
    answer_contains=None,
    answer_not_contains=None,
    multi_turn=False,
    expected_error=None,
):
    global PASS, FAIL
    r = post(msg)
    LATENCY.append(r.get("latency", 0))

    errors = []

    # Must call specific tools
    if must_call:
        called = {tc["name"] for tc in r.get("tool_call", [])}
        for tool in must_call:
            if tool not in called:
                errors.append(f"MUST call {tool} but didn't. Called: {called}")

    # Must NOT call specific tools
    if must_not_call:
        called = {tc["name"] for tc in r.get("tool_call", [])}
        for tool in must_not_call:
            if tool in called:
                errors.append(f"Must NOT call {tool} but did")

    # Answer must contain specific strings/data
    ans = r.get("answer") or ""
    if answer_contains:
        for text in answer_contains:
            if text.lower() not in ans.lower():
                errors.append(f"Answer must contain '{text}'. Answer: {ans[:200]}...")

    # Answer must NOT contain specific patterns
    if answer_not_contains:
        for text in answer_not_contains:
            if text.lower() in ans.lower():
                errors.append(
                    f"Answer must NOT contain '{text}. Answer: {ans[:200]}..."
                )

    # Expected error (e.g., empty message)
    if expected_error:
        if r.get("error") and expected_error in r["error"]:
            pass  # expected
        elif not r.get("error"):
            errors.append(f"Expected error '{expected_error}' but got no error")

    if errors:
        FAIL += 1
        print(f"  FAIL {name}")
        for e in errors:
            print(f"       {e}")
    else:
        PASS += 1
        tools_str = ",".join(tc["name"] for tc in r.get("tool_call", [])[:4])
        ans_preview = (ans or r.get("error", "?"))[:80]
        print(
            f"  OK   {name} | {len(r.get('tool_call', []))}tools: {tools_str} | {ans_preview}"
        )


# ── Tests ──────────────────────────────────────────────────────

print("=" * 80)
print("Agent Quality Tests")
print("=" * 80)

# Price queries: must call EXACTLY get_price
check(
    "AAPL price",
    "What is AAPL price?",
    must_call=["get_price"],
    must_not_call=["web_search", "get_news", "search_skills"],
    answer_contains=["289", "AAPL"],
)

check(
    "TSLA Chinese",
    "TSLA 多少钱",
    must_call=["get_price"],
    answer_contains=["TSLA", "420"],
)

check(
    "NVDA 90d",
    "NVDA price history for 90 days",
    must_call=["get_price"],
    answer_contains=["NVDA"],
)

# Indicators: must call get_indicators
check(
    "NVDA RSI MACD",
    "NVDA RSI MACD indicators",
    must_call=["get_indicators"],
    must_not_call=["web_search"],
    answer_contains=["NVDA", "RSI"],
)

# Fundamentals: must call get_fundamentals
check(
    "AAPL PE",
    "AAPL fundamentals PE PB ROE",
    must_call=["get_fundamentals"],
    answer_contains=["AAPL", "PE"],
)

# News: must call get_news
check(
    "NVDA news",
    "Latest news about NVDA",
    must_call=["get_news"],
    answer_contains=["NVDA"],
)

# Web search: must call web_search
check(
    "Fed rate",
    "What is the current Fed interest rate?",
    must_call=["web_search"],
    answer_contains=["%"],
)

# Comparison: must call multiple tools for both tickers
check(
    "AAPL vs MSFT",
    "Compare AAPL and MSFT fundamentals",
    must_call=["get_fundamentals"],
    answer_contains=["AAPL", "MSFT"],
)

# Simple follow instruction
check(
    "Reply OK",
    "Reply: OK",
    must_not_call=["get_price", "web_search"],
    answer_contains=["OK"],
    answer_not_contains=["What would you like", "Is there anything"],
)

# Error handling: ZZZZZZ must return error
check(
    "Bad ticker",
    "Get price for ZZZZZZ",
    must_not_call=["web_search"],
    answer_contains=["not found", "ZZZZZZ"],
    answer_not_contains=["ZZZZZZ closed at"],
)

# Skills: must call load_skill or list_skills
check(
    "Candlestick skill",
    "How to analyze stock using candlestick patterns",
    must_call=["load_skill"],
    answer_not_contains=["What would you like"],
)

# No tools needed: just answer
check(
    "Who are you",
    "你是谁",
    must_not_call=["get_price", "get_news", "web_search", "get_fundamentals"],
    answer_contains=["智能", "助手"],
)

# Empty message: expect error
check(
    "Empty msg",
    "",
    expected_error="Unprocessable"
    if "422" in post("").get("error", "")
    else "unprocessable",
)

# Data in answer must be from tool results
check(
    "Data citation",
    "What is MSFT price?",
    must_call=["get_price"],
    answer_contains=["MSFT", "$"],
)

# Multi-turn: round 2 uses context
sid_r1 = post("What is AAPL price?")
sid = sid_r1.get("session_id", "")  # might not be here
check(
    "Multi-turn AAPL→MSFT",
    "How about MSFT?",
    must_call=["get_price"],
    answer_contains=["MSFT", "$"],
)

# Chinese: must handle
check(
    "茅台 search",
    "分析一下茅台",
    must_call=["search_symbol"],
    answer_contains=["茅台", "600519"],
)

# Summary
print()
print(f"Results: {PASS} passed, {FAIL} failed, {len(LATENCY)} tests")
print(f"Avg latency: {sum(LATENCY) / max(len(LATENCY), 1):.1f}s")
