from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.scanner_adapter import AgentRunResult, ScannerCompilationService
from agent.tools.scanner import ScanTrackedUniverseTool
from dataflow.store import MarketDataStore
from scanner.service import ScannerService
from scanner.universe import TrackedUniverseResolver
from server.routes import agent as agent_routes
from server.routes import scanner as scanner_routes
from storage.store import ContextStore


class _OneToolCallLoop:
    def __init__(self, tool_content: str) -> None:
        self._tool_content = tool_content

    def run(
        self,
        user_message: str,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> AgentRunResult:
        del user_message, session_id, system_prompt
        return {
            "messages": [
                {
                    "role": "tool",
                    "name": "scan_tracked_universe",
                    "content": self._tool_content,
                }
            ]
        }


class _NoToolCallLoop:
    def run(
        self,
        user_message: str,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> AgentRunResult:
        del user_message, session_id, system_prompt
        return {"messages": [{"role": "assistant", "content": "buy AAPL"}]}


def _seed_market(market_store: MarketDataStore) -> None:
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
                "volume": 1000 + index,
            }
            for index in range(51)
        ],
        source="scanner-api-seed",
    )
    market_store.upsert_fundamentals(
        "AAPL", "2026-02-20", {"ttm": {"pe": 12, "pb": 2, "market_cap": 10_000}}
    )
    market_store.upsert_ticker_meta("AAPL", sector="Technology", currency="USD")


@pytest.fixture
def scanner_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, ContextStore, ScannerService]]:
    store = ContextStore(tmp_path / "context")
    store.register_strategy(
        {
            "id": "strategy-a",
            "name": "Scanner Strategy",
            "tickers": ["AAPL"],
            "beliefs": ["Technology momentum"],
            "belief_weights": {"Technology momentum": 0.8},
        }
    )
    market_store = MarketDataStore(tmp_path / "market.db")
    _seed_market(market_store)
    scanner_service = ScannerService(
        TrackedUniverseResolver(store, market_store), market_store
    )
    monkeypatch.setattr(scanner_routes, "get_store", lambda: store)
    monkeypatch.setattr(scanner_routes, "get_scanner_service", lambda: scanner_service)
    monkeypatch.setattr(agent_routes, "get_store", lambda: store)
    app = FastAPI()
    app.include_router(scanner_routes.router, prefix="/api")
    app.include_router(agent_routes.router, prefix="/api")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, store, scanner_service
    store.close()


def test_rule_scan_persists_completed_run_and_survives_store_reopen(
    scanner_api: tuple[TestClient, ContextStore, ScannerService],
) -> None:
    # Given: a mounted SHARED route over a seeded tracked universe.
    client, store, _ = scanner_api
    payload = {
        "conditions": [{"field": "price", "operator": ">", "value": 140.0}],
    }

    # When: a typed rule scan is requested without any LLM configuration.
    created = client.post("/api/scanner/rule", json=payload)

    # Then: the deterministic result and its complete audit record are durable.
    assert created.status_code == 201
    body = created.json()
    assert body["mode"] == "rule"
    assert body["status"] == "completed"
    assert body["result"]["results"][0]["ticker"] == "AAPL"
    run_id = body["id"]
    listed = client.get("/api/scanner/runs")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [run_id]
    fetched = client.get(f"/api/scanner/runs/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["compiled_conditions"] == [
        {"field": "price", "operator": ">", "value": 140.0, "value2": None}
    ]

    data_dir = store.data_dir
    store.close()
    rebuilt_store = ContextStore(data_dir)
    persisted = rebuilt_store.get_scan_run(run_id)
    assert persisted is not None
    assert persisted.status == "completed"
    assert persisted.result_json is not None
    rebuilt_store.close()


def test_active_agent_scan_persists_only_tool_derived_typed_result(
    scanner_api: tuple[TestClient, ContextStore, ScannerService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an ACTIVE fake loop returns the real tool's structured output.
    client, _, scanner_service = scanner_api
    tool_content = ScanTrackedUniverseTool(scanner_service).execute(
        conditions=[{"field": "price", "operator": ">", "value": 140.0}]
    )
    compiler = ScannerCompilationService(
        loop_factory=lambda: _OneToolCallLoop(tool_content)
    )
    monkeypatch.setattr(
        agent_routes, "get_scanner_compilation_service", lambda: compiler
    )

    # When: the ACTIVE route compiles a natural-language scanner request.
    response = client.post(
        "/api/agent/scanner", json={"mode": "agent", "query": "find strong prices"}
    )

    # Then: the returned run is completed only through the typed tool result.
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "agent"
    assert body["compiled_conditions"] == [
        {"field": "price", "operator": ">", "value": 140.0, "value2": None}
    ]
    assert body["result"]["results"][0]["ticker"] == "AAPL"


def test_belief_requires_exact_persisted_text_and_no_tool_result_is_failed_run(
    scanner_api: tuple[TestClient, ContextStore, ScannerService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a mounted ACTIVE endpoint with a loop that never makes a scanner tool call.
    client, store, _ = scanner_api
    compiler = ScannerCompilationService(loop_factory=_NoToolCallLoop)
    monkeypatch.setattr(
        agent_routes, "get_scanner_compilation_service", lambda: compiler
    )

    # When: callers provide an unowned belief and then an owned belief with no tool call.
    unowned = client.post(
        "/api/agent/scanner",
        json={
            "mode": "belief",
            "strategy_id": "strategy-a",
            "belief_text": "Unowned belief",
        },
    )
    failed = client.post(
        "/api/agent/scanner",
        json={
            "mode": "belief",
            "strategy_id": "strategy-a",
            "belief_text": "Technology momentum",
        },
    )

    # Then: ownership is exact and prose never masquerades as compiled conditions.
    assert unowned.status_code == 422
    assert failed.status_code == 422
    failed_runs = store.list_scan_runs(status="failed")
    assert len(failed_runs) == 1
    assert failed_runs[0].error_json is not None
    assert "tool" in failed_runs[0].error_json


def test_active_scanner_persists_explicit_unconfigured_and_invalid_tool_failures(
    scanner_api: tuple[TestClient, ContextStore, ScannerService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: no configured LLM, followed by a fake model with invalid tool arguments.
    client, store, _ = scanner_api
    unavailable = ScannerCompilationService(llm_available=False)
    monkeypatch.setattr(
        agent_routes, "get_scanner_compilation_service", lambda: unavailable
    )

    # When: compilation is attempted without credentials and with invalid tool output.
    unavailable_response = client.post(
        "/api/agent/scanner", json={"mode": "agent", "query": "prices above 140"}
    )
    invalid = ScannerCompilationService(
        loop_factory=lambda: _OneToolCallLoop('{"status":"ok","conditions":[]}')
    )
    monkeypatch.setattr(
        agent_routes, "get_scanner_compilation_service", lambda: invalid
    )
    invalid_response = client.post(
        "/api/agent/scanner", json={"mode": "agent", "query": "prices above 140"}
    )

    # Then: no LLM prose or malformed tool payload can create a completed scan run.
    assert unavailable_response.status_code == 422
    assert invalid_response.status_code == 422
    failures = store.list_scan_runs(status="failed")
    assert {json.loads(run.error_json or "{}")["code"] for run in failures} == {
        "llm_unavailable",
        "invalid_tool_output",
    }


def test_scanner_openapi_surfaces_keep_shared_and_active_tracks_separate(
    scanner_api: tuple[TestClient, ContextStore, ScannerService],
) -> None:
    # Given: routes from both tracks mounted in one FastAPI application.
    client, _, _ = scanner_api

    # When: the generated contract is inspected.
    paths = client.get("/openapi.json").json()["paths"]

    # Then: shared deterministic and ACTIVE judgment endpoints remain distinct.
    assert "/api/scanner/rule" in paths
    assert "/api/scanner/runs" in paths
    assert "/api/scanner/runs/{scan_run_id}" in paths
    assert "/api/agent/scanner" in paths


def test_application_registers_scanner_routes() -> None:
    # Given: the production FastAPI application.
    from server.main import app

    # When: its OpenAPI contract is generated.
    paths = app.openapi()["paths"]

    # Then: both Scanner tracks are reachable outside an isolated test mount.
    assert "/api/scanner/rule" in paths
    assert "/api/agent/scanner" in paths
