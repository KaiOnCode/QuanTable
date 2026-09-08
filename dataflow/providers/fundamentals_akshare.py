# dataflow/providers/fundamentals_akshare.py
from typing import Any, Dict

import akshare as ak
import pandas as pd


def _is_us_stock(ticker: str) -> bool:
    """
    Simple heuristic to detect US stocks (e.g. 'AAPL', 'MSFT').
    A-share tickers are typically numeric (e.g. '600519', '000001').
    """
    return ticker.isalpha() and ticker.isupper()


def _get_akshare_a_symbol(ticker: str) -> str:
    """
    Convert A-share ticker to AkShare-required suffix format.
    """
    if ticker.startswith("6"):
        return f"{ticker}.SH"
    if ticker.startswith("00") or ticker.startswith("30"):
        return f"{ticker}.SZ"
    return f"{ticker}.SH"  # default fallback


def _map_akshare_to_spec(report: pd.Series, is_us: bool) -> Dict[str, Any]:
    """
    Map AkShare data row (pd.Series) to agent_design v1.0 spec.

    V4 fixes:
    1. A-share column names based on A-share docs ("EPSJB", "XSMLL", etc.).
    2. US stock column names based on US docs ("BASIC_EPS", "GROSS_PROFIT_RATIO", etc.).
    3. US TTM valuations (PE, PB, PS) not available in this endpoint, mapped to None.
    """

    # Column name mapping: (A-share column, US stock column)
    MAP_KEYS = {
        # TTM valuations (A-share guess; US endpoint does not provide these)
        "pe": ("PE_TTM", None),
        "pb": ("PB_TTM", None),
        "ps": ("PS_TTM", None),
        "ev_ebitda": ("EVEBITDA_TTM", None),
        # Core metrics (confirmed for both A-share and US)
        "eps": ("EPSJB", "BASIC_EPS"),
        "gross_margin": ("XSMLL", "GROSS_PROFIT_RATIO"),
        "op_margin": ("OPERATING_PROFIT_MARGIN", None),  # A-share guess; US not provided
        # Growth metrics (confirmed for both A-share and US)
        "eps_yoy": ("PARENTNETPROFITTZ", "BASIC_EPS_YOY"),
        "rev_yoy": ("TOTALOPERATEREVETZ", "OPERATE_INCOME_YOY"),
        "net_debt_to_ebitda": (None, None),
        "sector_pe": (None, None),
    }

    def get_val(key):
        col_name = MAP_KEYS[key][1] if is_us else MAP_KEYS[key][0]
        if col_name and col_name in report:
            val = report[col_name]
            return val if pd.notna(val) else None
        return None

    # Build dictionary per agent_design v1.0 spec
    data = {
        "ttm": {
            "pe": get_val("pe"),
            "pb": get_val("pb"),
            "ps": get_val("ps"),
            "ev_ebitda": get_val("ev_ebitda"),
            "eps": get_val("eps"),
            "gross_margin": get_val("gross_margin"),
            "op_margin": get_val("op_margin"),
        },
        "growth": {"eps_yoy": get_val("eps_yoy"), "rev_yoy": get_val("rev_yoy")},
        "balance": {"net_debt_to_ebitda": get_val("net_debt_to_ebitda")},
        "sector_bench": {"pe": get_val("sector_pe")},
    }

    # Remove empty sub-dicts
    data["ttm"] = {k: v for k, v in data["ttm"].items() if v is not None}
    data["growth"] = {k: v for k, v in data["growth"].items() if v is not None}
    data["balance"] = {k: v for k, v in data["balance"].items() if v is not None}
    data["sector_bench"] = {
        k: v for k, v in data["sector_bench"].items() if v is not None
    }

    return {k: v for k, v in data.items() if v}


def df_get_fundamentals_pit(ticker: str, end_date: str) -> Dict[str, Any]:
    """
    V4 fixed version:
    1. (A-share) V3 logic is correct (e.g. "600519.SH", indicator="按报告期").
    2. (US stock) V4 adds indicator="累计季报".
    3. (US stock) V4 retains .O retry logic.
    """
    try:
        end_date_dt = pd.to_datetime(end_date.split("T")[0])
        is_us = _is_us_stock(ticker)

        # AkShare confirms date column is always 'REPORT_DATE'
        date_col = "REPORT_DATE"

        if is_us:
            # --- US stock path ---
            # V4 fix: add indicator="累计季报"
            # "累计季报" provides Q1, HY1, Q3, annual -- best for PIT analysis
            indicator = "累计季报"
            symbol = ticker
            try:
                df = ak.stock_financial_us_analysis_indicator_em(
                    symbol=symbol, indicator=indicator
                )
                if df is None or df.empty:
                    print(f"[akshare] Trying {ticker}.O (NASDAQ)...")
                    symbol = f"{ticker}.O"  # try NASDAQ suffix
                    df = ak.stock_financial_us_analysis_indicator_em(
                        symbol=symbol, indicator=indicator
                    )
            except Exception as e:
                print(f"[akshare] Error trying {symbol} (indicator={indicator}): {e}")
                df = None
        else:
            # --- A-share path (V3 logic is correct) ---
            symbol = _get_akshare_a_symbol(ticker)
            print(f"[akshare] Converting A-share code: {ticker} -> {symbol}")
            indicator = "按报告期"
            df = ak.stock_financial_analysis_indicator_em(
                symbol=symbol, indicator=indicator
            )

        # Check None
        if df is None:
            print(
                f"[akshare] AkShare returned None for {symbol} (indicator={indicator})."
            )
            return {}

        # Check empty and date column
        if df.empty or date_col not in df.columns:
            print(f"[akshare] No financial data or {date_col} column for {symbol}.")
            return {}

        # Point-in-Time (PIT) logic
        df[date_col] = pd.to_datetime(df[date_col])
        df_pit = df[df[date_col] <= end_date_dt].copy()

        if df_pit.empty:
            print(f"[akshare] No historical filings for {symbol} before {end_date}.")
            return {}

        # Get the most recent report
        df_pit = df_pit.sort_values(by=date_col, ascending=False)
        latest_report: pd.Series = df_pit.iloc[0]

        # Map to agent_design spec
        return _map_akshare_to_spec(latest_report, is_us)

    except Exception as e:
        print(f"[akshare] Error fetching fundamentals for {ticker} at {end_date}: {e}")
        return {}
