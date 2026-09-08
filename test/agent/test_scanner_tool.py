from __future__ import annotations

import json
from datetime import date, timedelta

from dataflow.store import MarketDataStore
from scanner.service import ScannerService
from scanner.universe import TrackedUniverseResolver
from storage.store import ContextStore

from agent.tools.scanner import ScanTrackedUniverseTool


def test_scanner_tool_executes_only_typed_conditions_against_real_cached_service(
    tmp_path,
) -> None:
    # Given: a real ScannerService over a single ticker with cached OHLCV history.
    context_store = ContextStore(tmp_path / "context")
    context_store.register_strategy(
        {"id": "strategy-a", "name": "Scanner", "tickers": ["AAPL"]}
    )
    market_store = MarketDataStore(tmp_path / "market.db")
    start = date(2026, 1, 1)
    market_store.upsert_ohlcv(
        "AAPL",
        [
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": 100 + index,
                "high": 101 + index,
                "low": 99 + index,
                "close": 100 + index,
                "volume": 1000,
            }
            for index in range(51)
        ],
    )
    tool = ScanTrackedUniverseTool(
        ScannerService(
            TrackedUniverseResolver(context_store, market_store), market_store
        )
    )

    # When: the only allowed scanner tool receives frozen condition data.
    response = tool.execute(
        conditions=[{"field": "price", "operator": ">", "value": 140.0}]
    )

    # Then: it delegates to the deterministic service and returns auditable typed data.
    payload = json.loads(response)
    assert payload["status"] == "ok"
    assert payload["conditions"] == [
        {"field": "price", "operator": ">", "value": 140.0, "value2": None}
    ]
    assert payload["result"]["results"][0]["ticker"] == "AAPL"


def test_scanner_tool_rejects_invalid_conditions_at_its_boundary(tmp_path) -> None:
    # Given: a Scanner tool whose service would otherwise be available.
    context_store = ContextStore(tmp_path / "context")
    market_store = MarketDataStore(tmp_path / "market.db")
    tool = ScanTrackedUniverseTool(
        ScannerService(
            TrackedUniverseResolver(context_store, market_store), market_store
        )
    )

    # When: an untyped unsupported field crosses the tool boundary.
    response = tool.execute(
        conditions=[{"field": "roe", "operator": ">", "value": 10.0}]
    )

    # Then: the engine is not asked to reinterpret it as an arbitrary query.
    assert json.loads(response)["status"] == "error"
