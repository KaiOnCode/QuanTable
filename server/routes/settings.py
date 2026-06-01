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

from notification import build_manager

router = APIRouter(tags=["settings"])

CONFIG_PATH = Path(os.getenv("AGENTIC_QUANT_SETTINGS_PATH", "data/settings.json"))

DEFAULT_CONFIG = {
    "llm_api_key": "sk-****",
    "llm_base_url": os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1"),
    "llm_model": os.getenv("OPENAI_MODEL", "deepseek-chat"),
    "deep_think_model": "deepseek-chat",
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
    "feishu_webhook_url": "",
    "discord_webhook_url": "",
    "slack_bot_token": "",
    "slack_channel_id": "",
    "whatsapp_access_token": "",
    "whatsapp_phone_number_id": "",
    "whatsapp_recipients": [],
    "social_webhook_url": "",
    "data_cache_ttl_minutes": 15,
    "news_fetch_interval_minutes": 30,
    "max_concurrent_analyses": 3,
    "memory_enabled": True,
    "memory_retention_days": 365,
    "weekly_reflection_day": "sunday",
    "weekly_reflection_time": "18:00",
    "mcp_external_servers": {},
}


class NotificationRequest(BaseModel):
    message: str = Field(..., min_length=1)
    title: str = "Agentic-Quant Alert"
    priority: str = "normal"
    channels: list[str] | None = None


def _load_settings() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fp:
            saved = json.load(fp)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid settings file: {exc}") from exc
    return {**DEFAULT_CONFIG, **saved}


def _save_settings(config: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as fp:
        json.dump(config, fp, ensure_ascii=False, indent=2)


def _safe_settings(config: dict[str, Any]) -> dict[str, Any]:
    masked = config.copy()
    for key in (
        "llm_api_key",
        "email_password",
        "telegram_bot_token",
        "slack_bot_token",
        "whatsapp_access_token",
    ):
        if masked.get(key):
            masked[key] = "********"
    return masked


def _result_payload(result) -> dict[str, Any]:
    return {"channel": result.channel, "ok": result.ok, "message": result.message}


@router.get("/settings")
async def get_settings():
    """Get current system configuration (API keys masked)."""
    return _safe_settings(_load_settings())


@router.put("/settings")
async def update_settings(config: dict):
    """Update system configuration (partial update supported)."""
    current = _load_settings()
    updated = {**current, **config}

    # Keep existing secrets when the frontend sends the masked placeholder back.
    for key in ("email_password", "telegram_bot_token", "slack_bot_token", "whatsapp_access_token"):
        if config.get(key) == "********":
            updated[key] = current.get(key, "")

    _save_settings(updated)
    return _safe_settings(updated)


@router.post("/settings/test-email")
async def test_email():
    """Send a test email notification."""
    result = await build_manager(_load_settings()).test("email")
    return _result_payload(result)


@router.post("/settings/test-telegram")
async def test_telegram():
    """Send a test Telegram notification."""
    result = await build_manager(_load_settings()).test("telegram")
    return _result_payload(result)


@router.post("/settings/test-wechat")
async def test_wechat():
    """Send a test Enterprise WeChat notification."""
    result = await build_manager(_load_settings()).test("wechat")
    return _result_payload(result)


@router.post("/settings/test-feishu")
async def test_feishu():
    """Send a test Feishu notification."""
    result = await build_manager(_load_settings()).test("feishu")
    return _result_payload(result)


@router.post("/settings/test-discord")
async def test_discord():
    """Send a test Discord notification."""
    result = await build_manager(_load_settings()).test("discord")
    return _result_payload(result)


@router.post("/settings/test-slack")
async def test_slack():
    """Send a test Slack notification."""
    result = await build_manager(_load_settings()).test("slack")
    return _result_payload(result)


@router.post("/settings/test-whatsapp")
async def test_whatsapp():
    """Send a test WhatsApp notification."""
    result = await build_manager(_load_settings()).test("whatsapp")
    return _result_payload(result)


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
