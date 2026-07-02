"""Compatibility shim for archived Streamlit tests.

The active Web/API shell lives under `server/` and `frontend/`; these exports keep
the broker-plus Streamlit dashboard tests importable while the UI remains archived.
"""

from archive.streamlit_app import (
    Backtester,
    BacktestMetricCard,
    build_backtest_dashboard_data,
    render_backtest_dashboard,
)

__all__ = [
    "Backtester",
    "BacktestMetricCard",
    "build_backtest_dashboard_data",
    "render_backtest_dashboard",
]
