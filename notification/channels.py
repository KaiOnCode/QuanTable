"""Multi-channel notification adapters.

The adapters intentionally use only stdlib + requests so they fit the current
project dependency set. Each channel validates required config before sending.
"""

from __future__ import annotations

import asyncio
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any


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


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> None:
    import requests

    response = requests.post(url, json=payload, headers=headers or {}, timeout=15)
    response.raise_for_status()


def _format_text(title: str, message: str, priority: str) -> str:
    prefix = "[HIGH] " if priority.lower() == "high" else ""
    return f"{prefix}{title}\n\n{message}" if title else f"{prefix}{message}"


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
            return ChannelResult(self.name, False, "Email SMTP host, sender and recipients are required.")

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
            return ChannelResult(self.name, True, f"Email sent to {len(self.recipients)} recipient(s).")
        except Exception as exc:  # pragma: no cover - depends on external SMTP service
            return ChannelResult(self.name, False, f"Email send failed: {exc}")


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
        if not self.is_configured():
            return ChannelResult(self.name, False, "Telegram bot token and chat IDs are required.")

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        text = _format_text(title, message, priority)
        try:
            for chat_id in self.chat_ids:
                await asyncio.to_thread(_post_json, url, {"chat_id": chat_id, "text": text})
            return ChannelResult(self.name, True, f"Telegram sent to {len(self.chat_ids)} chat(s).")
        except Exception as exc:  # pragma: no cover - depends on external API
            return ChannelResult(self.name, False, f"Telegram send failed: {exc}")


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
        if self.payload_style == "feishu":
            return {"msg_type": "text", "content": {"text": text}}
        if self.payload_style == "discord":
            return {"content": text}
        if self.payload_style == "slack_webhook":
            return {"text": text}
        return {"title": title, "message": message, "priority": priority}

    async def send(
        self,
        message: str,
        title: str = "Agentic-Quant Alert",
        priority: str = "normal",
    ) -> ChannelResult:
        if not self.is_configured():
            return ChannelResult(self.name, False, f"{self.name} webhook URL is required.")

        try:
            await asyncio.to_thread(
                _post_json,
                self.webhook_url,
                self._payload(message, title, priority),
            )
            return ChannelResult(self.name, True, f"{self.name} webhook sent.")
        except Exception as exc:  # pragma: no cover - depends on external webhook
            return ChannelResult(self.name, False, f"{self.name} send failed: {exc}")


class SlackChannel(NotificationChannel):
    name = "slack"

    def __init__(self, bot_token: str, channel_id: str):
        self.bot_token = bot_token
        self.channel_id = channel_id

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.channel_id)

    async def send(
        self,
        message: str,
        title: str = "Agentic-Quant Alert",
        priority: str = "normal",
    ) -> ChannelResult:
        if not self.is_configured():
            return ChannelResult(self.name, False, "Slack bot token and channel ID are required.")

        headers = {"Authorization": f"Bearer {self.bot_token}"}
        payload = {"channel": self.channel_id, "text": _format_text(title, message, priority)}
        try:
            await asyncio.to_thread(_post_json, "https://slack.com/api/chat.postMessage", payload, headers)
            return ChannelResult(self.name, True, "Slack message sent.")
        except Exception as exc:  # pragma: no cover - depends on external API
            return ChannelResult(self.name, False, f"Slack send failed: {exc}")


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
            return ChannelResult(self.name, True, f"WhatsApp sent to {len(self.recipients)} recipient(s).")
        except Exception as exc:  # pragma: no cover - depends on external API
            return ChannelResult(self.name, False, f"WhatsApp send failed: {exc}")


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
                results[name] = ChannelResult(name, False, f"Channel '{name}' is not registered.")
                continue
            results[name] = await channel.send(message, title, priority)
        return results

    async def test(self, channel_name: str) -> ChannelResult:
        channel = self.channels.get(channel_name)
        if channel is None:
            return ChannelResult(channel_name, False, f"Channel '{channel_name}' is not registered.")
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
    manager.register(TelegramChannel(str(config.get("telegram_bot_token") or ""), _csv(config.get("telegram_chat_ids"))))
    manager.register(WebhookChannel("wechat", str(config.get("wechat_webhook_url") or ""), "wechat"))
    manager.register(WebhookChannel("feishu", str(config.get("feishu_webhook_url") or ""), "feishu"))
    manager.register(WebhookChannel("discord", str(config.get("discord_webhook_url") or ""), "discord"))
    manager.register(SlackChannel(str(config.get("slack_bot_token") or ""), str(config.get("slack_channel_id") or "")))
    manager.register(
        WhatsAppChannel(
            access_token=str(config.get("whatsapp_access_token") or ""),
            phone_number_id=str(config.get("whatsapp_phone_number_id") or ""),
            recipients=_csv(config.get("whatsapp_recipients")),
        )
    )
    webhook_url = str(config.get("social_webhook_url") or "")
    if webhook_url:
        manager.register(WebhookChannel("webhook", webhook_url, "generic"))
    return manager
