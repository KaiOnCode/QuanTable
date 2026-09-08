from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from memory import MemoryRecord, MemoryStore
from server.routes import memory


def _memory_client() -> TestClient:
    app = FastAPI()
    app.include_router(memory.router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False)


def test_list_memories_uses_configured_memory_db_path(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    db_path = tmp_path / "memory.db"
    store = MemoryStore(str(db_path))
    store.remember(
        MemoryRecord(
            id="memory-a",
            strategy_id="strategy-a",
            ticker="AAPL",
            episodic="configured store record",
        )
    )
    store.close()
    monkeypatch.setenv("MEMORY_DB_PATH", str(db_path))
    client = _memory_client()

    # When
    response = client.get("/api/strategies/strategy-a/memory")

    # Then
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["memories"]] == ["memory-a"]


def test_get_memory_uses_configured_memory_db_path(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    db_path = tmp_path / "memory.db"
    store = MemoryStore(str(db_path))
    store.remember(
        MemoryRecord(
            id="memory-a",
            strategy_id="strategy-a",
            ticker="AAPL",
            episodic="configured store record",
        )
    )
    store.close()
    monkeypatch.setenv("MEMORY_DB_PATH", str(db_path))
    client = _memory_client()

    # When
    response = client.get("/api/strategies/strategy-a/memory/memory-a")

    # Then
    assert response.status_code == 200
    assert response.json()["id"] == "memory-a"


def test_get_memory_hides_record_owned_by_another_strategy(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    db_path = tmp_path / "memory.db"
    store = MemoryStore(str(db_path))
    store.remember(
        MemoryRecord(
            id="memory-b",
            strategy_id="strategy-b",
            ticker="MSFT",
            episodic="strategy-b record",
        )
    )
    store.close()
    monkeypatch.setenv("MEMORY_DB_PATH", str(db_path))
    client = _memory_client()

    # When
    response = client.get("/api/strategies/strategy-a/memory/memory-b")

    # Then
    assert response.status_code == 404
    assert response.json() == {"detail": "Memory memory-b not found"}


def test_list_memories_returns_server_error_for_corrupt_store(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    db_path = tmp_path / "corrupt-memory.db"
    db_path.write_bytes(b"not a sqlite database")
    monkeypatch.setenv("MEMORY_DB_PATH", str(db_path))
    client = _memory_client()

    # When
    response = client.get("/api/strategies/strategy-a/memory")

    # Then
    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to read memory"}
    assert str(db_path) not in response.text
