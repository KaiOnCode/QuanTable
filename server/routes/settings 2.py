"""Settings endpoints.

GET  /api/settings      — get system configuration
PUT  /api/settings      — update system configuration
POST /api/settings/test-email    — test email notification
POST /api/settings/test-telegram — test telegram notification
"""

from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(tags=["settings"])

DEFAULT_CONFIG = {
    "llm_api_key": "sk-****",
    "llm_base_url": os.getenv("OPENAI_API_BASE", "https://api.deepseek.com/v1"),
    "llm_model": os.getenv("OPENAI_MODEL", "deepseek-chat"),
    "deep_think_model": "deepseek-chat",
    "email_smtp_host": "",
    "email_smtp_port": 587,
    "email_recipients": [],
    "telegram_bot_token": "",
    "telegram_chat_ids": [],
    "wechat_webhook_url": "",
    "feishu_webhook_url": "",
    "discord_webhook_url": "",
    "slack_bot_token": "",
    "slack_channel_id": "",
    "data_cache_ttl_minutes": 15,
    "news_fetch_interval_minutes": 30,
    "max_concurrent_analyses": 3,
    "memory_enabled": True,
    "memory_retention_days": 365,
    "weekly_reflection_day": "sunday",
    "weekly_reflection_time": "18:00",
    "mcp_external_servers": {},
}


@router.get("/settings")
async def get_settings():
    """Get current system configuration (API keys masked)."""
    return DEFAULT_CONFIG


@router.put("/settings")
async def update_settings(config: dict):
    """Update system configuration (partial update supported)."""
    updated = {**DEFAULT_CONFIG, **config}
    # In production, persist to system.db via ContextStore
    return updated


@router.post("/settings/test-email")
async def test_email():
    """Send a test email notification."""
    return {"status": "ok", "message": "Test email would be sent (not implemented)"}


@router.post("/settings/test-telegram")
async def test_telegram():
    """Send a test Telegram notification."""
    return {"status": "ok", "message": "Test telegram would be sent (not implemented)"}
