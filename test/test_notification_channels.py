from __future__ import annotations

import unittest
import logging
from unittest.mock import patch

from notification.channels import (
    EmailChannel,
    TelegramChannel,
    WebhookChannel,
    WhatsAppChannel,
    build_manager,
)


class NotificationChannelTest(unittest.IsolatedAsyncioTestCase):
    async def test_transport_failure_never_exposes_notification_identifiers(self):
        secrets = {
            "telegram": "123456:secret-token",
            "chat": "-100987654321",
            "email": "person@example.test",
            "wechat": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret-key",
            "whatsapp_token": "whatsapp-secret-token",
            "whatsapp_recipient": "+15551234567",
            "provider_body": "provider-private-response-body",
        }
        channels = [
            TelegramChannel(secrets["telegram"], [secrets["chat"]]),
            EmailChannel(
                "smtp.example.test",
                587,
                [secrets["email"]],
                sender="sender@example.test",
            ),
            WebhookChannel("wechat", secrets["wechat"], "wechat"),
            WhatsAppChannel(
                secrets["whatsapp_token"], "phone-id", [secrets["whatsapp_recipient"]]
            ),
        ]
        failure = RuntimeError(
            f"403 {secrets['provider_body']} {secrets['wechat']} {secrets['chat']}"
        )

        with self.assertLogs(
            "notification.channels", level=logging.WARNING
        ) as captured:
            with (
                patch("notification.channels._post_json", side_effect=failure),
                patch("smtplib.SMTP", side_effect=failure),
            ):
                results = [await channel.test() for channel in channels]

        combined = "\n".join(captured.output + [result.message for result in results])
        for secret in secrets.values():
            self.assertNotIn(secret, combined)
        self.assertTrue(all(not result.ok for result in results))
        self.assertTrue(
            all(
                "configuration" in result.message.lower()
                or "provider" in result.message.lower()
                for result in results
            )
        )

    async def test_telegram_requires_complete_config(self):
        channel = TelegramChannel(bot_token="", chat_ids=["123456"])

        result = await channel.test()

        self.assertFalse(result.ok)
        self.assertEqual(result.channel, "telegram")
        self.assertIn("bot token", result.message)

    async def test_webhook_sends_expected_payload(self):
        channel = WebhookChannel("wechat", "https://example.com/webhook", "wechat")

        with patch("notification.channels._post_json") as post_json:
            result = await channel.send(
                "AAPL crossed 200", title="Price Alert", priority="high"
            )

        self.assertTrue(result.ok)
        post_json.assert_called_once()
        _, payload = post_json.call_args.args[:2]
        self.assertEqual(payload["msgtype"], "markdown")
        self.assertEqual(
            payload["markdown"]["content"], "[HIGH] Price Alert\n\nAAPL crossed 200"
        )

    async def test_manager_reports_unregistered_channel(self):
        manager = build_manager({})

        results = await manager.send(
            "hello", channels=["email", "telegram", "wechat", "whatsapp", "webhook"]
        )

        self.assertIn("webhook", results)
        self.assertFalse(results["webhook"].ok)
        self.assertIn("not registered", results["webhook"].message)


if __name__ == "__main__":
    unittest.main()
