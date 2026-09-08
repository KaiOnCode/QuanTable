from __future__ import annotations

from typing import Final, Literal, assert_never

from pydantic import BaseModel, ConfigDict, Field, JsonValue

type LifecycleAction = Literal["start", "pause", "stop"]

IDENTITY_FIELDS: Final = frozenset(
    "id name status created_at updated_at parent_strategy_id".split()
)
STATE_KEY_SUFFIXES: Final = (
    "memory",
    "history",
    "decisions",
    "runtime",
    "runtime_state",
    "database_path",
    "database_uri",
    "database_url",
    "db_path",
    "per_strategy_db",
)
SENSITIVE_KEY_SUFFIXES: Final = (
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "password",
    "secret",
    "secrets",
    "token",
    "webhook",
    "webhook_url",
)


class CloneStrategyRequest(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, str_strip_whitespace=True
    )

    name: str = Field(min_length=1, max_length=200)


class StopStrategyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    liquidate: bool = False


def _normalized_key(key: str) -> str:
    return key.casefold().replace("-", "_").replace(" ", "_")


def _is_noncloneable_key(key: str, *, top_level: bool = False) -> bool:
    normalized = _normalized_key(key)
    return (
        (top_level and normalized in IDENTITY_FIELDS)
        or normalized.startswith("runtime_")
        or normalized.endswith(STATE_KEY_SUFFIXES)
        or normalized.endswith(SENSITIVE_KEY_SUFFIXES)
    )


def _sanitize_json_value(value: JsonValue) -> JsonValue:
    match value:
        case dict() as mapping:
            return {
                key: _sanitize_json_value(item)
                for key, item in mapping.items()
                if not _is_noncloneable_key(key)
            }
        case list() as items:
            return [_sanitize_json_value(item) for item in items]
        case None | bool() | int() | float() | str():
            return value
        case unreachable:
            assert_never(unreachable)


def sanitize_clone_config(
    source: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    return {
        key: _sanitize_json_value(value)
        for key, value in source.items()
        if not _is_noncloneable_key(key, top_level=True)
    }
