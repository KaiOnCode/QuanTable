"""Multi-channel notification adapters.

The adapters intentionally use only stdlib + requests so they fit the current
project dependency set. Each channel validates required config before sending.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

logger = logging.getLogger("notification.channels")

CHANNEL_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "email": ("email_smtp_host", "email_sender", "email_recipients"),
    "telegram": ("telegram_bot_token", "telegram_chat_ids"),
    "wechat": ("wechat_webhook_url",),
    "whatsapp": (
        "whatsapp_access_token",
        "whatsapp_phone_number_id",
        "whatsapp_recipients",
    ),
}


@dataclass
class ChannelResult:
    """Result returned by a notification channel."""

    channel: str
    ok: bool
    message: str


class NotificationChannel(ABC):
    """Base class for a concrete notification transport."""

    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Return whether the channel has enough config to send messages."""

    @abstractmethod
    async def send(
        self,
        message: str,
        title: str = "Agentic-Quant Alert",
        priority: str = "normal",
    ) -> ChannelResult:
        """Send a message to this channel."""

    async def test(self) -> ChannelResult:
        return await self.send(
            "This is a test notification from Agentic-Quant.",
            title="Agentic-Quant Test",
            priority="normal",
        )


def _post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str] | None = None
) -> dict[str, Any]:
    import requests

    response = requests.post(url, json=payload, headers=headers or {}, timeout=15)
    response.raise_for_status()
    try:
        body = response.json()
    except ValueError:
        body = {"text": response.text[:500]}
    return {
        "status_code": response.status_code,
        "body": body,
        "content_length": len(response.content or b""),
    }


def _format_text(title: str, message: str, priority: str) -> str:
    prefix = "[HIGH] " if priority.lower() == "high" else ""
    return f"{prefix}{title}\n\n{message}" if title else f"{prefix}{message}"


def _transport_failure(channel: str, status_code: int | None = None) -> ChannelResult:
    category = (
        "provider rejected the request" if status_code else "provider unavailable"
    )
    logger.warning(
        "notification_send_failed channel=%s category=%s status_code=%s",
        channel,
        category.replace(" ", "_"),
        status_code,
    )
    return ChannelResult(
        channel,
        False,
        f"{channel.title()} provider unavailable. Check configuration and try again.",
    )


class EmailChannel(NotificationChannel):
    name = "email"

    def __init__(
        self,
        host: str,
        port: int,
        recipients: list[str],
        username: str = "",
        password: str = "",
        sender: str = "",
        use_tls: bool = True,
    ):
        self.host = host
        self.port = port
        self.recipients = recipients
        self.username = username
        self.password = password
        self.sender = sender or username
        self.use_tls = use_tls

    def is_configured(self) -> bool:
        return bool(self.host and self.port and self.recipients and self.sender)

    async def send(
        self,
        message: str,
        title: str = "Agentic-Quant Alert",
        priority: str = "normal",
    ) -> ChannelResult:
        if not self.is_configured():
            return ChannelResult(
                self.name, False, "Email SMTP host, sender and recipients are required."
            )

        mail = EmailMessage()
        mail["Subject"] = title
        mail["From"] = self.sender
        mail["To"] = ", ".join(self.recipients)
        mail.set_content(_format_text(title, message, priority))

        def _send() -> None:
            with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                if self.use_tls:
                    smtp.starttls()
                if self.username and self.password:
                    smtp.login(self.username, self.password)
                smtp.send_message(mail)

        try:
            await asyncio.to_thread(_send)
            return ChannelResult(
                self.name, True, f"Email sent to {len(self.recipients)} recipient(s)."
            )
        except Exception:  # pragma: no cover - external boundary
            return _transport_failure(self.name)


class TelegramChannel(NotificationChannel):
    name = "telegram"

    def __init__(self, bot_token: str, chat_ids: list[str]):
        self.bot_token = bot_token
        self.chat_ids = chat_ids

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_ids)

    async def send(
        self,
        message: str,
        title: str = "Agentic-Quant Alert",
        priority: str = "normal",
    ) -> ChannelResult:
        logger.info(
            "telegram_send_start configured=%s chat_count=%s priority=%s message_chars=%s",
            self.is_configured(),
            len(self.chat_ids),
            priority,
            len(message),
        )
        if not self.is_configured():
            logger.warning(
                "telegram_send_rejected reason=missing_config has_token=%s chat_count=%s",
                bool(self.bot_token),
                len(self.chat_ids),
            )
            return ChannelResult(
                self.name, False, "Telegram bot token and chat IDs are required."
            )

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        text = _format_text(title, message, priority)
        try:
            for index, chat_id in enumerate(self.chat_ids, start=1):
                payload = {"chat_id": chat_id, "text": text}
                logger.info(
                    "telegram_send_chat_start index=%s text_chars=%s",
                    index,
                    len(text),
                )
                response_info = await asyncio.to_thread(_post_json, url, payload)
                body = response_info.get("body", {})
                logger.info(
                    "telegram_send_chat_done index=%s status_code=%s telegram_ok=%s response_keys=%s content_length=%s",
                    index,
                    response_info.get("status_code"),
                    body.get("ok") if isinstance(body, dict) else None,
                    sorted(body.keys()) if isinstance(body, dict) else [],
                    response_info.get("content_length"),
                )
            logger.info(
                "telegram_send_done chat_count=%s title=%s priority=%s",
                len(self.chat_ids),
                title,
                priority,
            )
            return ChannelResult(
                self.name, True, f"Telegram sent to {len(self.chat_ids)} chat(s)."
            )
        except Exception as exc:  # pragma: no cover - external boundary
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            return _transport_failure(self.name, status_code)


class WebhookChannel(NotificationChannel):
    """Generic webhook channel for bots using JSON payloads."""

    def __init__(self, name: str, webhook_url: str, payload_style: str):
        self.name = name
        self.webhook_url = webhook_url
        self.payload_style = payload_style

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    def _payload(self, message: str, title: str, priority: str) -> dict[str, Any]:
        text = _format_text(title, message, priority)
        if self.payload_style == "wechat":
            return {"msgtype": "markdown", "markdown": {"content": text}}
        return {"title": title, "message": message, "priority": priority}

    async def send(
        self,
        message: str,
        title: str = "Agentic-Quant Alert",
        priority: str = "normal",
    ) -> ChannelResult:
        if not self.is_configured():
            return ChannelResult(
                self.name, False, f"{self.name} webhook URL is required."
            )

        try:
            await asyncio.to_thread(
                _post_json,
                self.webhook_url,
                self._payload(message, title, priority),
            )
            return ChannelResult(self.name, True, f"{self.name} webhook sent.")
        except Exception as exc:  # pragma: no cover - external boundary
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            return _transport_failure(self.name, status_code)


class WhatsAppChannel(NotificationChannel):
    """WhatsApp Cloud API sender."""

    name = "whatsapp"

    def __init__(self, access_token: str, phone_number_id: str, recipients: list[str]):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.recipients = recipients

    def is_configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id and self.recipients)

    async def send(
        self,
        message: str,
        title: str = "Agentic-Quant Alert",
        priority: str = "normal",
    ) -> ChannelResult:
        if not self.is_configured():
            return ChannelResult(
                self.name,
                False,
                "WhatsApp access token, phone number ID and recipients are required.",
            )

        url = f"https://graph.facebook.com/v20.0/{self.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        text = _format_text(title, message, priority)
        try:
            for recipient in self.recipients:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "text",
                    "text": {"preview_url": False, "body": text},
                }
                await asyncio.to_thread(_post_json, url, payload, headers)
            return ChannelResult(
                self.name,
                True,
                f"WhatsApp sent to {len(self.recipients)} recipient(s).",
            )
        except Exception as exc:  # pragma: no cover - external boundary
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            return _transport_failure(self.name, status_code)


def notification_status(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return channel readiness without exposing configuration values."""
    statuses: dict[str, dict[str, Any]] = {}
    for channel, fields in CHANNEL_REQUIRED_FIELDS.items():
        missing = [
            field for field in fields if not _configured_value(config.get(field))
        ]
        statuses[channel] = {"configured": not missing, "missing_fields": missing}
    return statuses


def _configured_value(value: Any) -> bool:
    if isinstance(value, list):
        return bool(_csv(value))
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


class NotificationManager:
    """Build and fan out notifications across configured channels."""

    def __init__(self):
        self.channels: dict[str, NotificationChannel] = {}

    def register(self, channel: NotificationChannel) -> None:
        self.channels[channel.name] = channel

    async def send(
        self,
        message: str,
        title: str = "Agentic-Quant Alert",
        priority: str = "normal",
        channels: list[str] | None = None,
    ) -> dict[str, ChannelResult]:
        targets = channels or list(self.channels)
        results: dict[str, ChannelResult] = {}
        for name in targets:
            channel = self.channels.get(name)
            if channel is None:
                results[name] = ChannelResult(
                    name, False, f"Channel '{name}' is not registered."
                )
                continue
            results[name] = await channel.send(message, title, priority)
        return results

    async def test(self, channel_name: str) -> ChannelResult:
        channel = self.channels.get(channel_name)
        if channel is None:
            return ChannelResult(
                channel_name, False, f"Channel '{channel_name}' is not registered."
            )
        return await channel.test()


def _csv(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def build_manager(config: dict[str, Any]) -> NotificationManager:
    manager = NotificationManager()
    manager.register(
        EmailChannel(
            host=str(config.get("email_smtp_host") or ""),
            port=int(config.get("email_smtp_port") or 587),
            recipients=_csv(config.get("email_recipients")),
            username=str(config.get("email_username") or ""),
            password=str(config.get("email_password") or ""),
            sender=str(config.get("email_sender") or ""),
            use_tls=bool(config.get("email_use_tls", True)),
        )
    )
    manager.register(
        TelegramChannel(
            str(config.get("telegram_bot_token") or ""),
            _csv(config.get("telegram_chat_ids")),
        )
    )
    manager.register(
        WebhookChannel("wechat", str(config.get("wechat_webhook_url") or ""), "wechat")
    )
    manager.register(
        WhatsAppChannel(
            access_token=str(config.get("whatsapp_access_token") or ""),
            phone_number_id=str(config.get("whatsapp_phone_number_id") or ""),
            recipients=_csv(config.get("whatsapp_recipients")),
        )
    )
    return manager
