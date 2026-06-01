from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from server.routes import watchlists
except ModuleNotFoundError as exc:  # pragma: no cover - local env may lack FastAPI
    watchlists = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


class FakeResult:
    channel = "whatsapp"
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
        return {"whatsapp": FakeResult()}


class WatchlistAlertTest(unittest.IsolatedAsyncioTestCase):
    @unittest.skipIf(watchlists is None, f"missing project dependency: {IMPORT_ERROR}")
    async def test_check_alerts_sends_once_when_triggered(self):
        manager = FakeManager()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watchlists.json"
            with (
                patch.object(watchlists, "WATCHLISTS_PATH", path),
                patch.object(watchlists, "_load_settings", return_value={}),
                patch.object(watchlists, "build_manager", return_value=manager),
            ):
                alert = await watchlists.create_alert(
                    "my-positions",
                    watchlists.CreateAlertRequest(
                        ticker="AAPL",
                        type="price_above",
                        threshold_value=200,
                        notification_channels=["whatsapp"],
                    ),
                )

                first = await watchlists.check_alerts(
                    watchlists.AlertCheckRequest(snapshots={"AAPL": {"price": 205}})
                )
                second = await watchlists.check_alerts(
                    watchlists.AlertCheckRequest(snapshots={"AAPL": {"price": 210}})
                )

        self.assertEqual(alert["ticker"], "AAPL")
        self.assertEqual(first["triggered_count"], 1)
        self.assertEqual(second["triggered_count"], 0)
        self.assertEqual(len(manager.calls), 1)
        self.assertEqual(manager.calls[0]["channels"], ["whatsapp"])
        self.assertIn("AAPL price is 205.00", manager.calls[0]["message"])


if __name__ == "__main__":
    unittest.main()
