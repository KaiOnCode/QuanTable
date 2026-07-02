"""Compatibility shim for archived Streamlit tests.

The active Web/API shell lives under `server/` and `frontend/`; these exports keep
the broker-plus Streamlit dashboard tests importable while the UI remains archived.
"""

from typing import Any

from archive import streamlit_app as _archive

BacktestMetricCard = _archive.BacktestMetricCard
df_get_prices: Any = _archive.df_get_prices
df_get_indicators: Any = _archive.df_get_indicators
df_get_fundamentals: Any = _archive.df_get_fundamentals


def _sync_archive_providers() -> None:
    _archive.df_get_prices = df_get_prices
    _archive.df_get_indicators = df_get_indicators
    _archive.df_get_fundamentals = df_get_fundamentals


class Backtester(_archive.Backtester):
    def run_historical_analysis(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        _sync_archive_providers()
        return super().run_historical_analysis(*args, **kwargs)

    def run_execution_backtest(self, *args: Any, **kwargs: Any) -> Any:
        _sync_archive_providers()
        return super().run_execution_backtest(*args, **kwargs)


def build_backtest_dashboard_data(*args: Any, **kwargs: Any) -> Any:
    return _archive.build_backtest_dashboard_data(*args, **kwargs)


def render_backtest_dashboard(*args: Any, **kwargs: Any) -> Any:
    _sync_archive_providers()
    return _archive.render_backtest_dashboard(*args, **kwargs)


__all__ = [
    "Backtester",
    "BacktestMetricCard",
    "build_backtest_dashboard_data",
    "df_get_fundamentals",
    "df_get_indicators",
    "df_get_prices",
    "render_backtest_dashboard",
]
