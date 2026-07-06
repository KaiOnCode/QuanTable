from __future__ import annotations

DEFAULT_QUICK_THINK_MODEL = "deepseek-v4-flash"
DEFAULT_DEEP_THINK_MODEL = "deepseek-v4-pro"

_QUICK_THINK_LEGACY_ALIASES = {
    "deepseek-chat",
    "deepseek-reasoner",
    "deepseek-reasoning",
}

_DEEP_THINK_LEGACY_ALIASES = {
    "deepseek-chat",
    "deepseek-reasoner",
    "deepseek-reasoning",
}


def normalize_quick_think_model(model: str | None) -> str:
    if not model:
        return DEFAULT_QUICK_THINK_MODEL
    stripped = model.strip()
    if stripped in _QUICK_THINK_LEGACY_ALIASES:
        return DEFAULT_QUICK_THINK_MODEL
    return stripped


def normalize_deep_think_model(model: str | None) -> str:
    if not model:
        return DEFAULT_DEEP_THINK_MODEL
    stripped = model.strip()
    if stripped in _DEEP_THINK_LEGACY_ALIASES:
        return DEFAULT_DEEP_THINK_MODEL
    return stripped


def migrate_model_config(config: dict) -> dict:
    migrated = dict(config)
    migrated["llm_model"] = normalize_quick_think_model(migrated.get("llm_model"))
    migrated["deep_think_model"] = normalize_deep_think_model(
        migrated.get("deep_think_model")
    )
    return migrated
