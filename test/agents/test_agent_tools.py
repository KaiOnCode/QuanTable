from __future__ import annotations

from agents.utils import agent_tools


class StubDataService:
    def df_get_prices(
        self,
        ticker: str,
        lookback_days: int = 180,
        end_date: str | None = None,
    ) -> dict[str, object]:
        assert ticker == "AAPL"
        assert lookback_days == 5
        assert end_date == "2026-04-13T00:00:00Z"
        return {
            "ticker": "AAPL",
            "tz": "UTC",
            "rows": [
                {
                    "ts": "2026-04-13T00:00:00Z",
                    "o": 100.0,
                    "h": 101.0,
                    "l": 99.0,
                    "c": 100.5,
                    "v": 1_000,
                }
            ],
        }

    def df_get_indicators(
        self,
        ticker: str,
        lookback_days: int = 180,
        end_date: str | None = None,
    ) -> dict[str, object]:
        return {}

    def df_get_fundamentals(
        self,
        ticker: str,
        end_date: str | None = None,
    ) -> dict[str, object]:
        return {}

    def df_get_news(
        self,
        ticker: str,
        window_days: int = 7,
        max_items: int = 20,
        end_date: str | None = None,
    ) -> list[dict[str, object]]:
        return []


def test_get_price_uses_the_configured_data_service_factory() -> None:
    agent_tools.configure_data_service_factory(lambda: StubDataService())
    try:
        output = agent_tools.get_price.invoke(
            {
                "symbol": "AAPL",
                "lookback_days": 5,
                "end_date": "2026-04-13T00:00:00Z",
            }
        )
    finally:
        agent_tools.reset_data_service_factory()

    assert "股票代码: AAPL" in output
    assert "数据条数: 1" in output
