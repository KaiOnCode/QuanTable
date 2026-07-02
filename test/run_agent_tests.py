"""Batch test runner for agent analysis. Runs N tests and produces a report."""

import json
import urllib.request
from typing import Any, TypedDict

API = "http://localhost:8000/api/agent/chat"


class AgentTestResult(TypedDict):
    error: str
    tool_call: int
    tool_done: int
    tool_error: int
    answer: int
    iterations: int
    answer_text: str


TESTS = [
    # Price queries
    ("T01", "What is AAPL price?"),
    ("T02", "TSLA 多少钱"),
    ("T03", "Get NVDA price history for 90 days"),
    ("T04", "BABA current price"),
    ("T05", "GOOGL stock quote"),
    ("T06", "AMD price in USD"),
    # Indicators
    ("T07", "NVDA RSI MACD indicators"),
    ("T08", "AAPL moving average"),
    ("T09", "What are the technicals for TSLA"),
    # Fundamentals
    ("T10", "AAPL fundamentals PE PB ROE"),
    ("T11", "MSFT financial data"),
    ("T12", "Compare PE ratios of AAPL and GOOGL"),
    # News
    ("T13", "Latest news about NVDA"),
    ("T14", "Tesla 最近有什么新闻"),
    ("T15", "Search for AI chip news"),
    ("T16", "What is happening with AAPL this week"),
    # Sentiment
    ("T17", "What is the market sentiment for TSLA"),
    ("T18", "AAPL 市场情绪如何"),
    # Web search
    ("T19", "What is the current Fed interest rate"),
    ("T20", "Latest IPO news 2026"),
    # Comprehensive
    ("T21", "Analyze NVDA: price, technicals, and news"),
    ("T22", "Compare AAPL and MSFT as investments"),
    ("T23", "Is TSLA a good buy right now"),
    ("T24", "Give me a morning market brief"),
    ("T25", "Research 比亚迪 for me"),
    # Skills
    ("T26", "How to analyze stock using candlestick patterns"),
    ("T27", "Explain the DCF valuation method"),
    ("T28", "What is pair trading strategy"),
    ("T29", "List available skills for crypto"),
    ("T30", "Search for skills about risk management"),
    # File/workspace
    ("T31", "Read the README.md file"),
    ("T32", "List files in current directory"),
    # Meta
    ("T33", "What can you do"),
    ("T34", "Help"),
    ("T35", "你是谁"),
    # Edge cases
    ("T36", "NVDA"),
    ("T37", "Get price for ZZZZZZ"),
    ("T38", ""),
    ("T39", "Reply: OK"),
    ("T40", "https://github.com"),
    # Chinese queries
    ("T41", "分析一下茅台"),
    ("T42", "最近股市怎么样"),
    ("T43", "帮我看看腾讯的股价"),
    # Multi-tool
    ("T44", "NVDA price, news, indicators, and fundamentals all at once"),
    ("T45", "What is the best tech stock to buy now"),
    # Quick follow-ups (new session each)
    ("T46", "What is MSFT price?"),
    ("T47", "Show me the latest market news"),
    ("T48", "Compare TSLA and F"),
    # Edge
    ("T49", "GOOG"),
    ("T50", "What tools do you have available"),
    ("T51", "给我一个投资建议"),
    ("T52", "Does AAPL pay dividends"),
]


def run_test(url: str, body: dict[str, Any]) -> AgentTestResult:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read().decode()
    except Exception as e:
        return {
            "error": str(e),
            "tool_call": 0,
            "tool_done": 0,
            "tool_error": 0,
            "answer": 0,
            "iterations": 0,
            "answer_text": "",
        }

    lines = data.split("\n")
    events = [line for line in lines if line.startswith("event:")]
    counts: AgentTestResult = {
        "error": "",
        "tool_call": 0,
        "tool_done": 0,
        "tool_error": 0,
        "answer": 0,
        "iterations": 0,
        "answer_text": "",
    }
    for e in events:
        t = e[7:].strip()
        if t in counts:
            counts[t] += 1
    counts["iterations"] = (
        events.count("  thinking_start")
        if "thinking_start" in data
        else data.count("event: thinking_start\n")
    )

    # Extract answer text
    ans_text = ""
    for i, line in enumerate(lines):
        if line.startswith("event: answer") and i + 1 < len(lines):
            dl = lines[i + 1]
            if dl.startswith("data: "):
                try:
                    ans_text = str(json.loads(dl[6:]).get("text", ""))[:300]
                except Exception:
                    pass
            break
    counts["answer_text"] = ans_text
    return counts


if __name__ == "__main__":
    print(
        f"{'ID':>4} {'msg':<45} {'TC':>3} {'DONE':>4} {'ERR':>3} {'ANS':>3} {'ITER':>3} | Answer"
    )
    print("-" * 120)
    results = []
    for tid, msg in TESTS:
        body = {"message": msg}
        r = run_test(API, body)
        # Handle error display
        ans = r.get("error", "") or r.get("answer_text", "")[:100]
        if not ans and r.get("answer", 0) > 0:
            ans = "(answered)"
        print(
            f"{tid:>4} {msg[:44]:<45} {r['tool_call']:>3} {r['tool_done']:>4} {r['tool_error']:>3} {r['answer']:>3} {r['iterations']:>3} | {ans[:120]}"
        )
        results.append((tid, msg, r))

    # Summary
    total = len(results)
    has_answer = sum(1 for _, _, r in results if r["answer"] > 0)
    has_tools = sum(1 for _, _, r in results if r["tool_call"] > 0)
    errors = sum(1 for _, _, r in results if r["tool_error"] > 0)
    no_answer = sum(1 for _, _, r in results if r["answer"] == 0 and r["tool_call"] > 0)
    print("\n--- Summary ---")
    print(
        f"Total: {total}, Answer received: {has_answer}/{total}, Tools used: {has_tools}/{total}"
    )
    print(
        f"Errors: {errors} tests had tool errors, No answer despite tools: {no_answer}"
    )
