from __future__ import annotations

from memory import MemoryRecord, MemoryService, MemoryStore


def test_recall_context_returns_empty_advisory_text_when_no_records(tmp_path) -> None:
    store = MemoryStore(str(tmp_path / "memory.db"))
    service = MemoryService(store=store, strategy_id="strategy-a")

    assert service.recall_records("AAPL") == []
    assert "无相关历史记忆" in service.recall_context("AAPL")

    store.close()


def test_recall_records_are_strategy_scoped(tmp_path) -> None:
    store = MemoryStore(str(tmp_path / "memory.db"))
    store.remember(
        MemoryRecord(
            strategy_id="strategy-a",
            session_id="session-a",
            ticker="AAPL",
            confidence=0.8,
            episodic="strategy-a memory",
            trade_record={"action": "BUY"},
        )
    )
    store.remember(
        MemoryRecord(
            strategy_id="strategy-b",
            session_id="session-b",
            ticker="AAPL",
            confidence=0.8,
            episodic="strategy-b memory",
            trade_record={"action": "SELL"},
        )
    )

    service = MemoryService(store=store, strategy_id="strategy-a")

    records = service.recall_records("AAPL")

    assert [record.strategy_id for record in records] == ["strategy-a"]
    assert records[0].episodic == "strategy-a memory"

    store.close()


def test_remember_decision_parses_pm_report_metadata(tmp_path) -> None:
    store = MemoryStore(str(tmp_path / "memory.db"))
    service = MemoryService(store=store, strategy_id="strategy-a")

    memory_id = service.remember_decision(
        {
            "ticker": "AAPL",
            "date": "2026-07-02T00:00:00Z",
            "current_position_pct": 10.0,
            "strategy_id": "strategy-a",
            "session_id": "session-1",
            "account_id": "account-1",
            "decision_id": "decision-1",
            "Action": "BUY",
            "Target_position_pct": 25.0,
            "PM_report": (
                "方向: Bullish\n"
                "时间范围: 1-3d\n"
                "置信度: 0.73\n"
                "一句话结论: 当前证据支持小幅加仓\n"
                "正文"
            ),
            "market_report": "market ok",
            "fundamental_report": "fundamental ok",
            "news_report": "news ok",
            "risk_report": "risk ok",
        }
    )

    assert memory_id is not None
    record = store.get(memory_id)
    assert record is not None
    assert record.strategy_id == "strategy-a"
    assert record.confidence == 0.73
    assert record.semantic == "当前证据支持小幅加仓"
    assert record.trade_record["direction"] == "Bullish"
    assert record.trade_record["time_range"] == "1-3d"
    assert record.trade_record["current_position_pct"] == 10.0
    assert record.trade_record["target_position_pct"] == 25.0
    assert record.trade_record["decision_id"] == "decision-1"

    store.close()


def test_disabled_memory_does_not_recall_or_persist(tmp_path) -> None:
    store = MemoryStore(str(tmp_path / "memory.db"))
    store.remember(
        MemoryRecord(
            strategy_id="strategy-a",
            session_id="session-a",
            ticker="AAPL",
            episodic="existing memory",
            trade_record={"action": "BUY"},
        )
    )
    service = MemoryService(store=store, strategy_id="strategy-a", enabled=False)

    assert service.recall_records("AAPL") == []
    assert (
        service.remember_decision(
            {
                "ticker": "AAPL",
                "strategy_id": "strategy-a",
                "Action": "HOLD",
                "PM_report": "方向: Neutral\n置信度: 0.5\n一句话结论: 观望",
            }
        )
        is None
    )
    assert store.count("strategy-a") == 1

    store.close()
