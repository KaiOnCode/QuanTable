"""Settings endpoints.

GET  /api/settings                 — get system configuration
PUT  /api/settings                 — update system configuration
POST /api/settings/test-{channel}  — test a notification channel
POST /api/notifications/send       — send a notification to selected channels
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from notification import build_manager, notification_status
from server.llm_defaults import (
    DEFAULT_DEEP_THINK_MODEL,
    DEFAULT_QUICK_THINK_MODEL,
    migrate_model_config,
)

router = APIRouter(tags=["settings"])

CONFIG_PATH = Path(os.getenv("AGENTIC_QUANT_SETTINGS_PATH", "data/settings.json"))

DEFAULT_CONFIG = {
    "llm_api_key": "",
    "llm_base_url": os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1"),
    "llm_model": os.getenv("OPENAI_MODEL", DEFAULT_QUICK_THINK_MODEL),
    "deep_think_model": DEFAULT_DEEP_THINK_MODEL,
    "email_smtp_host": "",
    "email_smtp_port": 587,
    "email_username": "",
    "email_password": "",
    "email_sender": "",
    "email_use_tls": True,
    "email_recipients": [],
    "telegram_bot_token": "",
    "telegram_chat_ids": [],
    "wechat_webhook_url": "",
    "whatsapp_access_token": "",
    "whatsapp_phone_number_id": "",
    "whatsapp_recipients": [],
    "data_cache_ttl_minutes": 15,
    "news_fetch_interval_minutes": 30,
    "max_concurrent_analyses": 3,
    "memory_enabled": True,
    "memory_retention_days": 365,
    "weekly_reflection_day": "sunday",
    "weekly_reflection_time": "18:00",
    "mcp_external_servers": {},
}

_LEGACY_SECRET_PLACEHOLDERS = {"sk-****", "********"}


class NotificationRequest(BaseModel):
    message: str = Field(..., min_length=1)
    title: str = "Agentic-Quant Alert"
    priority: str = "normal"
    channels: list[str] | None = None


def _is_masked_secret(value: object) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return stripped in _LEGACY_SECRET_PLACEHOLDERS or (
        bool(stripped) and set(stripped) == {"*"}
    )


def _effective_llm_api_key(config: dict[str, Any]) -> tuple[str, str]:
    saved = str(config.get("llm_api_key") or "")
    if saved and not _is_masked_secret(saved):
        return saved, "settings"
    env_key = os.getenv("OPENAI_API_KEY", "")
    if env_key:
        return env_key, "properties.env"
    return "", "missing"


def _mask_secret(value: str) -> str:
    return "*" * len(value) if value else ""


def _load_settings() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return migrate_model_config(DEFAULT_CONFIG.copy())
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fp:
            saved = json.load(fp)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500, detail=f"Invalid settings file: {exc}"
        ) from exc
    return migrate_model_config({**DEFAULT_CONFIG, **saved})


def _save_settings(config: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as fp:
        json.dump(config, fp, ensure_ascii=False, indent=2)


def _merge_settings_update(
    current: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    request_config = {
        key: value
        for key, value in config.items()
        if key
        not in {
            "notification_status",
            "llm_api_key_configured",
            "llm_api_key_source",
            "llm_api_key_length",
        }
    }
    updated = {**current, **request_config}

    for key in (
        "llm_api_key",
        "email_password",
        "telegram_bot_token",
        "whatsapp_access_token",
    ):
        if _is_masked_secret(request_config.get(key)):
            updated[key] = current.get(key, "")

    if _is_masked_secret(request_config.get("wechat_webhook_url")):
        updated["wechat_webhook_url"] = current.get("wechat_webhook_url", "")

    for key in ("email_recipients", "telegram_chat_ids", "whatsapp_recipients"):
        value = request_config.get(key)
        if (
            isinstance(value, list)
            and value
            and all(_is_masked_secret(item) for item in value)
        ):
            updated[key] = current.get(key, [])

    return migrate_model_config(updated)


def _safe_settings(config: dict[str, Any]) -> dict[str, Any]:
    masked = config.copy()
    llm_key, llm_source = _effective_llm_api_key(config)
    masked["llm_api_key"] = _mask_secret(llm_key)
    masked["llm_api_key_configured"] = bool(llm_key)
    masked["llm_api_key_source"] = llm_source
    masked["llm_api_key_length"] = len(llm_key)

    for key in (
        "email_password",
        "telegram_bot_token",
        "whatsapp_access_token",
    ):
        value = str(masked.get(key) or "")
        if value:
            masked[key] = "********"
    webhook = str(masked.get("wechat_webhook_url") or "")
    if webhook:
        masked["wechat_webhook_url"] = "********"
    for key in ("email_recipients", "telegram_chat_ids", "whatsapp_recipients"):
        value = masked.get(key)
        if isinstance(value, list) and value:
            masked[key] = ["********"]
    masked["notification_status"] = notification_status(config)
    return masked


def _result_payload(result) -> dict[str, Any]:
    return {"channel": result.channel, "ok": result.ok, "message": result.message}


async def _test_channel(channel: str) -> dict[str, Any]:
    config = _load_settings()
    status = notification_status(config)[channel]
    missing = status["missing_fields"]
    if missing:
        return {
            "channel": channel,
            "ok": False,
            "message": (
                f"{channel.title()} configuration is incomplete. "
                f"Missing: {', '.join(missing)}."
            ),
        }
    return _result_payload(await build_manager(config).test(channel))


@router.get("/settings")
async def get_settings():
    """Get current system configuration (API keys masked)."""
    return _safe_settings(_load_settings())


@router.put("/settings")
async def update_settings(config: dict):
    """Update system configuration (partial update supported)."""
    current = _load_settings()
    updated = _merge_settings_update(current, config)
    _save_settings(updated)
    return _safe_settings(updated)


@router.post("/settings/test-email")
async def test_email():
    """Send a test email notification."""
    return await _test_channel("email")


@router.post("/settings/test-telegram")
async def test_telegram():
    """Send a test Telegram notification."""
    return await _test_channel("telegram")


@router.post("/settings/test-wechat")
async def test_wechat():
    """Send a test Enterprise WeChat notification."""
    return await _test_channel("wechat")


@router.post("/settings/test-whatsapp")
async def test_whatsapp():
    """Send a test WhatsApp notification."""
    return await _test_channel("whatsapp")


@router.post("/notifications/send")
async def send_notification(request: NotificationRequest):
    """Send an alert/reminder to selected social notification channels."""
    results = await build_manager(_load_settings()).send(
        message=request.message,
        title=request.title,
        priority=request.priority,
        channels=request.channels,
    )
    return {
        "ok": any(result.ok for result in results.values()),
        "results": {name: _result_payload(result) for name, result in results.items()},
    }
