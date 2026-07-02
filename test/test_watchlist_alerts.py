from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from server.routes import watchlist as watchlists
from storage.store import ContextStore


class FakeResult:
    channel = "telegram"
    ok = True
    message = "sent"


class FakeManager:
    def __init__(self):
        self.calls = []

    async def send(self, message, title, priority, channels=None):
        self.calls.append(
            {
                "message": message,
                "title": title,
                "priority": priority,
                "channels": channels,
            }
        )
        return {"telegram": FakeResult()}


class WatchlistAlertTest(unittest.IsolatedAsyncioTestCase):
    async def test_check_alerts_sends_once_when_triggered(self):
        manager = FakeManager()
        with tempfile.TemporaryDirectory() as tmp:
            store = ContextStore(tmp)
            with (
                patch.object(watchlists, "get_store", return_value=store),
                patch.object(watchlists, "_load_settings", return_value={}),
                patch.object(watchlists, "build_manager", return_value=manager),
            ):
                created = await watchlists.create_watchlist(
                    {"name": "My Positions", "tickers": ["AAPL"]}
                )
                alert = await watchlists.create_alert(
                    created["id"],
                    watchlists.CreateAlertRequest(
                        ticker="AAPL",
                        type="price_above",
                        threshold_value=200,
                        notification_channels=["telegram"],
                    ),
                )

                first = await watchlists.check_alerts(
                    watchlists.AlertCheckRequest(snapshots={"AAPL": {"price": 205}})
                )
                second = await watchlists.check_alerts(
                    watchlists.AlertCheckRequest(snapshots={"AAPL": {"price": 210}})
                )
            store.close()

        self.assertEqual(alert["ticker"], "AAPL")
        self.assertEqual(first["triggered_count"], 1)
        self.assertEqual(second["triggered_count"], 0)
        self.assertEqual(len(manager.calls), 1)
        self.assertEqual(manager.calls[0]["channels"], ["telegram"])
        self.assertIn("AAPL price is 205.00", manager.calls[0]["message"])


if __name__ == "__main__":
    unittest.main()
