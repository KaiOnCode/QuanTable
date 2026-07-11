from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from server.main import app
from server.routes import settings


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "CONFIG_PATH", tmp_path / "settings.json")
    with TestClient(app) as test_client:
        yield test_client


def test_settings_reports_channel_configuration_and_missing_fields(
    client: TestClient,
) -> None:
    response = client.get("/api/settings")

    assert response.status_code == 200
    statuses = response.json()["notification_status"]
    assert statuses == {
        "email": {
            "configured": False,
            "missing_fields": ["email_smtp_host", "email_sender", "email_recipients"],
        },
        "telegram": {
            "configured": False,
            "missing_fields": ["telegram_bot_token", "telegram_chat_ids"],
        },
        "wechat": {
            "configured": False,
            "missing_fields": ["wechat_webhook_url"],
        },
        "whatsapp": {
            "configured": False,
            "missing_fields": [
                "whatsapp_access_token",
                "whatsapp_phone_number_id",
                "whatsapp_recipients",
            ],
        },
    }


@pytest.mark.parametrize(
    ("channel", "partial", "missing"),
    [
        (
            "email",
            {"email_smtp_host": "smtp.example.test"},
            ["email_sender", "email_recipients"],
        ),
        ("telegram", {"telegram_bot_token": "secret"}, ["telegram_chat_ids"]),
        ("wechat", {"wechat_webhook_url": "https://example.test/hook"}, []),
        (
            "whatsapp",
            {"whatsapp_access_token": "secret", "whatsapp_phone_number_id": "id"},
            ["whatsapp_recipients"],
        ),
    ],
)
def test_settings_reports_partial_channel_configuration(
    client: TestClient, channel: str, partial: dict[str, object], missing: list[str]
) -> None:
    response = client.put("/api/settings", json=partial)

    assert response.status_code == 200
    status = response.json()["notification_status"][channel]
    assert status == {"configured": not missing, "missing_fields": missing}


@pytest.mark.parametrize(
    ("channel", "config", "missing"),
    [
        (
            "email",
            {
                "email_smtp_host": " \t ",
                "email_sender": "  ",
                "email_recipients": ["recipient@example.test"],
            },
            ["email_smtp_host", "email_sender"],
        ),
        (
            "telegram",
            {"telegram_bot_token": " \n ", "telegram_chat_ids": ["configured"]},
            ["telegram_bot_token"],
        ),
        (
            "wechat",
            {"wechat_webhook_url": "   "},
            ["wechat_webhook_url"],
        ),
        (
            "whatsapp",
            {
                "whatsapp_access_token": " \t ",
                "whatsapp_phone_number_id": "  ",
                "whatsapp_recipients": ["configured"],
            },
            ["whatsapp_access_token", "whatsapp_phone_number_id"],
        ),
    ],
)
def test_whitespace_only_required_values_remain_missing(
    client: TestClient,
    channel: str,
    config: dict[str, object],
    missing: list[str],
) -> None:
    response = client.put("/api/settings", json=config)

    assert response.status_code == 200
    assert response.json()["notification_status"][channel] == {
        "configured": False,
        "missing_fields": missing,
    }


def test_unconfigured_test_is_actionable_and_contains_no_values(
    client: TestClient,
) -> None:
    secret = "telegram-secret-token"
    client.put("/api/settings", json={"telegram_bot_token": secret})

    response = client.post("/api/settings/test-telegram")

    assert response.status_code == 200
    assert response.json() == {
        "channel": "telegram",
        "ok": False,
        "message": "Telegram configuration is incomplete. Missing: telegram_chat_ids.",
    }
    assert secret not in response.text


def test_settings_masks_notification_secrets_and_recipients(
    client: TestClient,
) -> None:
    values = {
        "telegram_bot_token": "token-value",
        "telegram_chat_ids": ["chat-value"],
        "wechat_webhook_url": "https://example.test/private-webhook",
        "whatsapp_access_token": "access-value",
        "whatsapp_recipients": ["recipient-value"],
        "email_password": "password-value",
        "email_recipients": ["mail-recipient-value"],
    }

    response = client.put("/api/settings", json=values)

    assert response.status_code == 200
    for value in (
        "token-value",
        "chat-value",
        "private-webhook",
        "access-value",
        "recipient-value",
        "password-value",
        "mail-recipient-value",
    ):
        assert value not in response.text


def test_masked_notification_values_do_not_replace_saved_configuration(
    client: TestClient,
) -> None:
    original = {
        "telegram_bot_token": "token-value",
        "telegram_chat_ids": ["chat-value"],
        "wechat_webhook_url": "https://example.test/private-webhook",
    }
    safe = client.put("/api/settings", json=original).json()

    response = client.put("/api/settings", json=safe)

    assert response.status_code == 200
    assert response.json()["notification_status"]["telegram"]["configured"] is True
    assert response.json()["notification_status"]["wechat"]["configured"] is True


@pytest.mark.parametrize(
    ("channel", "config"),
    [
        (
            "email",
            {
                "email_smtp_host": "smtp.example.test",
                "email_sender": "sender@example.test",
                "email_recipients": ["recipient@example.test"],
            },
        ),
        (
            "telegram",
            {"telegram_bot_token": "configured", "telegram_chat_ids": ["configured"]},
        ),
        ("wechat", {"wechat_webhook_url": "https://example.test/webhook"}),
        (
            "whatsapp",
            {
                "whatsapp_access_token": "configured",
                "whatsapp_phone_number_id": "configured",
                "whatsapp_recipients": ["configured"],
            },
        ),
    ],
)
def test_configured_channel_test_succeeds_with_local_transports(
    client: TestClient, channel: str, config: dict[str, object]
) -> None:
    client.put("/api/settings", json=config)

    with (
        patch("notification.channels._post_json", return_value={}),
        patch("smtplib.SMTP"),
    ):
        response = client.post(f"/api/settings/test-{channel}")

    assert response.status_code == 200
    assert response.json()["channel"] == channel
    assert response.json()["ok"] is True


def test_transport_failure_response_does_not_expose_provider_detail(
    client: TestClient,
) -> None:
    provider_detail = "private-provider-response"
    client.put(
        "/api/settings",
        json={
            "telegram_bot_token": "configured",
            "telegram_chat_ids": ["configured"],
        },
    )

    with patch(
        "notification.channels._post_json", side_effect=RuntimeError(provider_detail)
    ):
        response = client.post("/api/settings/test-telegram")

    assert response.status_code == 200
    assert response.json() == {
        "channel": "telegram",
        "ok": False,
        "message": "Telegram provider unavailable. Check configuration and try again.",
    }
    assert provider_detail not in response.text
