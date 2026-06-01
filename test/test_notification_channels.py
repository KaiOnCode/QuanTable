from __future__ import annotations

import unittest
from unittest.mock import patch

from notification.channels import TelegramChannel, WebhookChannel, build_manager


class NotificationChannelTest(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_requires_complete_config(self):
        channel = TelegramChannel(bot_token="", chat_ids=["123456"])

        result = await channel.test()

        self.assertFalse(result.ok)
        self.assertEqual(result.channel, "telegram")
        self.assertIn("bot token", result.message)

    async def test_webhook_sends_expected_payload(self):
        channel = WebhookChannel("wechat", "https://example.com/webhook", "wechat")

        with patch("notification.channels._post_json") as post_json:
            result = await channel.send("AAPL crossed 200", title="Price Alert", priority="high")

        self.assertTrue(result.ok)
        post_json.assert_called_once()
        _, payload = post_json.call_args.args[:2]
        self.assertEqual(payload["msgtype"], "markdown")
        self.assertEqual(payload["markdown"]["content"], "[HIGH] Price Alert\n\nAAPL crossed 200")

    async def test_manager_reports_unregistered_channel(self):
        manager = build_manager({})

        results = await manager.send("hello", channels=["email", "telegram", "wechat", "whatsapp", "webhook"])

        self.assertIn("webhook", results)
        self.assertFalse(results["webhook"].ok)
        self.assertIn("not registered", results["webhook"].message)


if __name__ == "__main__":
    unittest.main()
