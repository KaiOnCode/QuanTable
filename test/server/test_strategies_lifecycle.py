from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Final
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import JsonValue, TypeAdapter

from server.routes import strategies
from storage.store import ContextStore

# fmt: off
type RejectionCase = tuple[str, str | None, dict[str, JsonValue] | None, int, str | None]
LIQUIDATION_DETAIL: Final = "Liquidation is not supported"
MISSING_DETAIL: Final = "Strategy missing-strategy not found"
SOURCE_CUSTOM_CONFIG: Final[dict[str, JsonValue]] = {"threshold": 0.7, "max_tokens": 4096, "api_key": "nested-secret", "memory": [{"content": "nested-source-only"}], "provider": {"model": "safe-model", "webhook": "https://secret.example/provider", "webhook_url": "https://secret.example/provider-url", "webhook_enabled": True, "credentials": {"token": "nested-token", "password": "nested-password", "secret": "nested-secret"}}, "nested_list": [{"client_secret": "list-secret", "provider_webhook": "https://secret.example/list", "max_tokens": 1024, "retry_limit": 3}, {"safe": True, "provider_webhook_url": "https://secret.example/list-url", "access_token": "list-token"}]}
EXPECTED_CLONE_CUSTOM_CONFIG: Final[dict[str, JsonValue]] = {"threshold": 0.7, "max_tokens": 4096, "provider": {"model": "safe-model", "webhook_enabled": True}, "nested_list": [{"max_tokens": 1024, "retry_limit": 3}, {"safe": True}]}
SOURCE_NON_CLONEABLE_FIELDS: Final[dict[str, JsonValue]] = {"memory": [{"content": "source-only"}], "history": [{"event": "source-only"}], "decisions": [{"action": "BUY"}], "runtime_state": {"worker": "running"}, "api_key": "source-secret", "openai_api_key": "provider-secret", "webhook": "https://secret.example/top", "webhook_url": "https://secret.example/top-url"}
FORBIDDEN_CLONE_FIELDS: Final = frozenset(("memory", "history", "decisions", "runtime_state", "api_key", "openai_api_key", "webhook", "webhook_url"))
REJECTION_CASES: Final[dict[str, RejectionCase]] = {
    "liquidate-existing": ("stop", "active", {"liquidate": True}, 409, LIQUIDATION_DETAIL),
    "liquidate-missing": ("stop", None, {"liquidate": True}, 409, LIQUIDATION_DETAIL),
    "stop-extra": ("stop", "draft", {"liquidation": True}, 422, None),
    "stop-type": ("stop", "draft", {"liquidate": "true"}, 422, None),
    "clone-blank": ("clone", "draft", {"name": "   "}, 422, None),
    "clone-extra": ("clone", "draft", {"name": "Clone", "unexpected": True}, 422, None),
    "clone-missing": ("clone", None, {"name": "Missing"}, 404, MISSING_DETAIL),
    "start-missing": ("start", None, None, 404, MISSING_DETAIL),
    "pause-missing": ("pause", None, None, 404, MISSING_DETAIL),
    "stop-missing": ("stop", None, {}, 404, MISSING_DETAIL),
    "start-archived": ("start", "archived", None, 409, "Cannot start strategy from status archived"),
    "pause-draft": ("pause", "draft", None, 409, "Cannot pause strategy from status draft"),
    "stop-archived": ("stop", "archived", {}, 409, "Cannot stop strategy from status archived"),
}
# fmt: on


@pytest.fixture
def strategy_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, ContextStore]]:
    store = ContextStore(tmp_path)
    monkeypatch.setattr(strategies, "get_store", lambda: store)
    app = FastAPI()
    app.include_router(strategies.router, prefix="/api")
    with TestClient(app) as client:
        yield client, store
    store.close()


def _create_strategy(
    client: TestClient, payload: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    response = client.post("/api/strategies", json=payload)
    assert response.status_code == 201
    return TypeAdapter(dict[str, JsonValue]).validate_python(response.json())


def test_create_strategy_is_immediately_listed(
    strategy_api: tuple[TestClient, ContextStore],
) -> None:
    # Given: an isolated real strategy registry exposed through the public API.
    client, _ = strategy_api

    # When: a strategy is created and the collection is read back.
    created_response = client.post(
        "/api/strategies",
        json={
            "name": "Momentum Baseline",
            "tickers": ["AAPL"],
            "tags": ["characterization"],
        },
    )
    listed_response = client.get("/api/strategies")

    # Then: the stored representation is immediately observable in the list.
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["name"] == "Momentum Baseline"
    assert created["status"] == "draft"
    assert created["tickers"] == ["AAPL"]
    assert listed_response.status_code == 200
    assert listed_response.json() == {"items": [created], "total": 1, "page": 1}


def test_strategy_boundary_rejects_unknown_create_and_update_fields(
    strategy_api: tuple[TestClient, ContextStore],
) -> None:
    client, store = strategy_api

    create_response = client.post(
        "/api/strategies",
        json={"name": "Secret Probe", "tickers": ["AAPL"], "api_key": "secret"},
    )

    assert create_response.status_code == 422
    assert store.list_strategies() == []

    created = _create_strategy(client, {"name": "Typed Strategy", "tickers": ["AAPL"]})
    update_response = client.put(
        f"/api/strategies/{created['id']}",
        json={"webhook_url": "https://secret.example"},
    )

    assert update_response.status_code == 422
    assert client.get(f"/api/strategies/{created['id']}").json() == created


def test_strategy_boundary_does_not_echo_secret_unknown_input(
    strategy_api: tuple[TestClient, ContextStore],
) -> None:
    client, _ = strategy_api

    response = client.post(
        "/api/strategies",
        json={"name": "Secret Probe", "api_key": "SECRET_VALUE"},
    )

    assert response.status_code == 422
    assert "SECRET_VALUE" not in response.text


@pytest.mark.parametrize(
    ("policy_fields", "code", "message"),
    [
        (
            {"quant_strategy_name": "unknown", "quant_params": {}},
            "strategy_not_backtestable",
            "Quant Strategy requires a supported executable definition",
        ),
        (
            {"quant_strategy_name": "momentum", "quant_params": {}},
            "strategy_config_invalid",
            "target_position_pct must be a finite percent",
        ),
        (
            {
                "quant_strategy_name": "momentum",
                "quant_params": {
                    "lookback_bars": 1,
                    "entry_threshold": 0.05,
                    "exit_threshold": -0.02,
                    "target_position_pct": 40,
                },
            },
            "strategy_config_invalid",
            "Quant Strategy parameters are invalid",
        ),
        (
            {
                "quant_strategy_name": "sma_crossover",
                "quant_params": {
                    "fast_window": 80,
                    "slow_window": 20,
                    "target_position_pct": 40,
                },
            },
            "strategy_config_invalid",
            "Quant Strategy parameters are invalid",
        ),
        (
            {
                "quant_strategy_name": "sma_crossover",
                "quant_params": {
                    "fast_window": 10,
                    "slow_window": 20,
                    "target_position_pct": 60,
                },
            },
            "strategy_config_invalid",
            "target_position_pct must not exceed Strategy max_position_pct",
        ),
        (
            {
                "quant_strategy_name": "sma_crossover",
                "quant_params": {
                    "fast_window": 10,
                    "slow_window": 20,
                    "target_position_pct": 999,
                },
            },
            "strategy_config_invalid",
            "Quant Strategy parameters are invalid",
        ),
    ],
)
def test_invalid_quant_create_is_rejected_without_persistence(
    strategy_api: tuple[TestClient, ContextStore],
    policy_fields: dict[str, JsonValue],
    code: str,
    message: str,
) -> None:
    client, store = strategy_api

    response = client.post(
        "/api/strategies",
        json={
            "name": "Invalid Quant",
            "type": "quant",
            "max_position_pct": 50,
            **policy_fields,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": code,
        "message": message,
    }
    assert store.list_strategies() == []


def test_invalid_quant_partial_update_is_rejected_without_mutation(
    strategy_api: tuple[TestClient, ContextStore],
) -> None:
    client, store = strategy_api
    created = _create_strategy(
        client,
        {
            "name": "Valid SMA",
            "type": "quant",
            "max_position_pct": 50,
            "quant_strategy_name": "sma_crossover",
            "quant_params": {
                "fast_window": 10,
                "slow_window": 50,
                "target_position_pct": 40,
            },
        },
    )
    strategy_id = TypeAdapter(str).validate_python(created["id"])

    response = client.put(
        f"/api/strategies/{strategy_id}",
        json={
            "quant_params": {
                "fast_window": 80,
                "slow_window": 20,
                "target_position_pct": 999,
            }
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "strategy_config_invalid",
        "message": "Quant Strategy parameters are invalid",
    }
    assert store.get_strategy(strategy_id) == created


@pytest.mark.parametrize("strategy_type", ["agent", "hitl"])
def test_non_quant_create_preserves_existing_semantics(
    strategy_api: tuple[TestClient, ContextStore], strategy_type: str
) -> None:
    client, _ = strategy_api

    response = client.post(
        "/api/strategies",
        json={"name": f"Valid {strategy_type}", "type": strategy_type},
    )

    assert response.status_code == 201
    assert response.json()["type"] == strategy_type


@pytest.mark.parametrize(
    ("rule", "params"),
    [
        (
            "momentum",
            {
                "lookback_bars": 20,
                "entry_threshold": 0.05,
                "exit_threshold": -0.02,
                "target_position_pct": 40,
            },
        ),
        (
            "sma_crossover",
            {
                "fast_window": 10,
                "slow_window": 50,
                "target_position_pct": 40,
            },
        ),
    ],
)
def test_valid_quant_policy_create_and_partial_update_round_trip(
    strategy_api: tuple[TestClient, ContextStore],
    rule: str,
    params: dict[str, JsonValue],
) -> None:
    client, store = strategy_api

    created = client.post(
        "/api/strategies",
        json={
            "name": "Valid Quant",
            "type": "quant",
            "max_position_pct": 50,
            "quant_strategy_name": rule,
            "quant_params": params,
        },
    )
    strategy_id = created.json()["id"]
    updated = client.put(
        f"/api/strategies/{strategy_id}", json={"description": "Still valid"}
    )

    assert created.status_code == 201
    assert updated.status_code == 200
    assert updated.json()["quant_strategy_name"] == rule
    assert updated.json()["quant_params"] == params
    assert store.get_strategy(strategy_id) == updated.json()


def test_clone_strategy_copies_config_without_strategy_data(
    strategy_api: tuple[TestClient, ContextStore],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an active strategy with persisted decision history.
    client, store = strategy_api
    timestamps = iter(["2026-07-10T01:00:00Z", "2026-07-10T02:00:00Z"])
    monkeypatch.setattr(strategies, "_now", lambda: next(timestamps))
    source = _create_strategy(
        client,
        {
            "name": "Source Strategy",
            "description": "Clone this configuration only",
            "status": "active",
            "tickers": ["AAPL", "MSFT"],
        },
    )
    source_id = TypeAdapter(str).validate_python(source["id"])
    store.update_strategy(
        source_id,
        {"custom_config": SOURCE_CUSTOM_CONFIG, **SOURCE_NON_CLONEABLE_FIELDS},
    )
    source = store.get_strategy(source_id)
    assert source is not None
    store.record_decision(
        source_id,
        {
            "id": "source-decision",
            "session_id": "source-session",
            "ticker": "AAPL",
            "action": "BUY",
        },
    )

    # When: the strategy is cloned through the public route.
    clone_response = client.post(
        f"/api/strategies/{source_id}/clone",
        json={"name": "Isolated Clone"},
    )

    # Then: only configuration is copied into a fresh draft registry record.
    assert clone_response.status_code == 201
    clone = clone_response.json()
    clone_id = TypeAdapter(str).validate_python(clone["id"])
    UUID(clone_id)
    assert clone_id != source_id
    assert clone["name"] == "Isolated Clone"
    assert clone["status"] == "draft"
    assert clone["parent_strategy_id"] == source_id
    assert clone["created_at"] == "2026-07-10T02:00:00Z"
    assert clone["updated_at"] == "2026-07-10T02:00:00Z"
    assert clone["tickers"] == ["AAPL", "MSFT"]
    assert clone["custom_config"] == EXPECTED_CLONE_CUSTOM_CONFIG
    assert FORBIDDEN_CLONE_FIELDS.isdisjoint(clone)
    assert client.get(f"/api/strategies/{source_id}").json() == source
    assert not (tmp_path / f"{clone_id}.db").exists()
    clone_decisions = client.get(f"/api/strategies/{clone_id}/decisions")
    source_decisions = client.get(f"/api/strategies/{source_id}/decisions")
    assert clone_decisions.json() == {"decisions": [], "total": 0}
    assert source_decisions.json()["total"] == 1

    store.close()
    reconstructed = ContextStore(tmp_path)
    monkeypatch.setattr(strategies, "get_store", lambda: reconstructed)
    persisted_clone = client.get(f"/api/strategies/{clone_id}")
    persisted_list = client.get("/api/strategies")
    assert persisted_clone.json() == clone
    assert {item["id"] for item in persisted_list.json()["items"]} == {
        source_id,
        clone_id,
    }
    assert reconstructed.get_decisions(clone_id) == []
    reconstructed.close()


@pytest.mark.parametrize(
    ("action", "initial_status", "expected_status", "payload"),
    [
        pytest.param("start", "draft", "active", None, id="start-draft"),
        pytest.param("start", "paused", "active", None, id="start-paused"),
        pytest.param("start", "stopped", "active", None, id="start-stopped"),
        pytest.param("pause", "active", "paused", None, id="pause-active"),
        pytest.param("stop", "draft", "stopped", {}, id="stop-draft"),
        pytest.param("stop", "active", "stopped", {}, id="stop-active"),
        pytest.param("stop", "paused", "stopped", {}, id="stop-paused"),
    ],
)
def test_lifecycle_transition_persists_allowed_state(
    strategy_api: tuple[TestClient, ContextStore],
    action: str,
    initial_status: str,
    expected_status: str,
    payload: dict[str, bool] | None,
) -> None:
    # Given: a persisted strategy in a state allowed for the requested action.
    client, _ = strategy_api
    created = _create_strategy(
        client, {"name": "Allowed Transition", "status": initial_status}
    )

    # When: the lifecycle transition is requested.
    response = client.post(f"/api/strategies/{created['id']}/{action}", json=payload)

    # Then: the new state is returned and persisted.
    assert response.status_code == 200
    assert response.json()["status"] == expected_status
    persisted = client.get(f"/api/strategies/{created['id']}")
    assert persisted.json()["status"] == expected_status


@pytest.mark.parametrize(
    ("action", "status", "payload"),
    [
        pytest.param("start", "active", None, id="start-active"),
        pytest.param("pause", "paused", None, id="pause-paused"),
        pytest.param("stop", "stopped", {}, id="stop-stopped"),
    ],
)
def test_lifecycle_transition_is_idempotent_without_write(
    strategy_api: tuple[TestClient, ContextStore],
    action: str,
    status: str,
    payload: dict[str, bool] | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a strategy already in the requested lifecycle state.
    client, store = strategy_api
    created = _create_strategy(
        client, {"name": "Idempotent Transition", "status": status}
    )

    def fail_update_strategy(_strategy_id: str, _updates: dict[str, JsonValue]) -> None:
        raise AssertionError("idempotent transition attempted a persistence write")

    monkeypatch.setattr(store, "update_strategy", fail_update_strategy)

    # When: the same lifecycle action is requested again.
    response = client.post(f"/api/strategies/{created['id']}/{action}", json=payload)

    # Then: the existing record is returned without changing updated_at.
    assert response.status_code == 200
    assert response.json() == created


@pytest.mark.parametrize(
    ("action", "initial_status", "payload", "expected_status", "detail"),
    [
        pytest.param(action, status, payload, expected, detail, id=case_id)
        for case_id, (
            action,
            status,
            payload,
            expected,
            detail,
        ) in REJECTION_CASES.items()
    ],
)
def test_lifecycle_request_rejections_are_stable_and_non_mutating(
    strategy_api: tuple[TestClient, ContextStore],
    action: str,
    initial_status: str | None,
    payload: dict[str, JsonValue] | None,
    expected_status: int,
    detail: str | None,
) -> None:
    # Given: either a persisted strategy or an unknown identifier.
    client, _ = strategy_api
    strategy_id = "missing-strategy"
    if initial_status is not None:
        created = _create_strategy(
            client, {"name": "Rejection Probe", "status": initial_status}
        )
        strategy_id = TypeAdapter(str).validate_python(created["id"])

    # When: a rejected lifecycle request crosses the HTTP boundary.
    response = client.post(f"/api/strategies/{strategy_id}/{action}", json=payload)

    # Then: the stable error is returned without changing persisted state.
    assert response.status_code == expected_status
    if detail is not None:
        assert response.json() == {"detail": detail}
    if initial_status is not None:
        assert (
            client.get(f"/api/strategies/{strategy_id}").json()["status"]
            == initial_status
        )


def test_openapi_exposes_exactly_four_strategy_action_routes(
    strategy_api: tuple[TestClient, ContextStore],
) -> None:
    # Given: the mounted public strategy router.
    client, _ = strategy_api

    # When: its generated OpenAPI schema is inspected.
    schema = client.get("/openapi.json").json()
    action_routes = {
        path
        for path, operations in schema["paths"].items()
        if path.startswith("/api/strategies/{strategy_id}/") and "post" in operations
    }

    # Then: only the four planned lifecycle and clone actions are present.
    assert action_routes == {
        "/api/strategies/{strategy_id}/clone",
        "/api/strategies/{strategy_id}/start",
        "/api/strategies/{strategy_id}/pause",
        "/api/strategies/{strategy_id}/stop",
    }
