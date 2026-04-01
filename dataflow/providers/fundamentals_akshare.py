# dataflow/providers/fundamentals_akshare.py
from typing import Any, Dict

import akshare as ak
import pandas as pd


def _is_us_stock(ticker: str) -> bool:
    """
    一个简单的启发式方法来检测美股 (如 'AAPL', 'MSFT')。
    A股通常是数字 (如 '600519', '000001')。
    """
    return ticker.isalpha() and ticker.isupper()


def _get_akshare_a_symbol(ticker: str) -> str:
    """
    (V3) 根据A股代码规则转换为 AkShare 需要的后缀。
    """
    if ticker.startswith("6"):
        return f"{ticker}.SH"
    if ticker.startswith("00") or ticker.startswith("30"):
        return f"{ticker}.SZ"
    # 默认兜底
    return f"{ticker}.SH"


def _map_akshare_to_spec(report: pd.Series, is_us: bool) -> Dict[str, Any]:
    """
    将 AkShare 的数据行 (pd.Series) 映射到 agent_design v1.0 规范。

    V4 修复：
    1. A 股列名基于 A 股文档 ("EPSJB", "XSMLL" 等)。
    2. 美股列名基于美股文档 ("BASIC_EPS", "GROSS_PROFIT_RATIO" 等)。
    3. 美股 TTM 估值 (PE, PB, PS) 在此接口中不存在，映射为 None。
    """

    # V4 修正：(A股列名, 美股列名)
    MAP_KEYS = {
        # TTM 估值 (A股保留猜测；美股此接口不提供)
        "pe": ("PE_TTM", None),
        "pb": ("PB_TTM", None),
        "ps": ("PS_TTM", None),
        "ev_ebitda": ("EVEBITDA_TTM", None),
        # 基础指标 (A股/美股均已确认)
        "eps": ("EPSJB", "BASIC_EPS"),
        "gross_margin": ("XSMLL", "GROSS_PROFIT_RATIO"),
        "op_margin": ("OPERATING_PROFIT_MARGIN", None),  # A股保留猜测；美股不提供
        # 增长指标 (A股/美股均已确认)
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

    # 按照 agent_design v1.0 规范构建字典
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

    # 清理空字典
    data["ttm"] = {k: v for k, v in data["ttm"].items() if v is not None}
    data["growth"] = {k: v for k, v in data["growth"].items() if v is not None}
    data["balance"] = {k: v for k, v in data["balance"].items() if v is not None}
    data["sector_bench"] = {
        k: v for k, v in data["sector_bench"].items() if v is not None
    }

    return {k: v for k, v in data.items() if v}


def df_get_fundamentals_pit(ticker: str, end_date: str) -> Dict[str, Any]:
    """
    V4 修复版：
    1. (A股) V3 逻辑已正确 (e.g., "600519.SH", "按报告期")。
    2. (美股) V4 添加 indicator="累计季报"。
    3. (美股) V4 保持 .O 的重试逻辑。
    """
    try:
        end_date_dt = pd.to_datetime(end_date.split("T")[0])
        is_us = _is_us_stock(ticker)

        # AkShare 文档确认，日期列均为 'REPORT_DATE'
        date_col = "REPORT_DATE"

        if is_us:
            # --- 美股路径 ---
            # V4 修复：添加 indicator="累计季报"
            # "累计季报" 提供了 Q1, HY1, Q3, 年报, 最适合 PIT 分析
            indicator = "累计季报"
            symbol = ticker
            try:
                df = ak.stock_financial_us_analysis_indicator_em(
                    symbol=symbol, indicator=indicator
                )
                if df is None or df.empty:
                    print(f"[akshare] 尝试 {ticker}.O (NASDAQ)...")
                    symbol = f"{ticker}.O"  # 尝试纳斯达克后缀
                    df = ak.stock_financial_us_analysis_indicator_em(
                        symbol=symbol, indicator=indicator
                    )
            except Exception as e:
                print(f"[akshare] 尝试 {symbol} (indicator={indicator}) 时出错: {e}")
                df = None
        else:
            # --- A股路径 (V3 逻辑已正确) ---
            symbol = _get_akshare_a_symbol(ticker)
            print(f"[akshare] 转换A股代码: {ticker} -> {symbol}")
            indicator = "按报告期"
            df = ak.stock_financial_analysis_indicator_em(
                symbol=symbol, indicator=indicator
            )

        # 检查 None
        if df is None:
            print(
                f"[akshare] AkShare 为 {symbol} (indicator={indicator}) 返回了 None。"
            )
            return {}

        # 检查 empty 和 日期列
        if df.empty or date_col not in df.columns:
            print(f"[akshare] 未找到 {symbol} 的财务数据或 {date_col} 日期列。")
            return {}

        # 3. Point-in-Time (PIT) 逻辑
        df[date_col] = pd.to_datetime(df[date_col])
        df_pit = df[df[date_col] <= end_date_dt].copy()

        if df_pit.empty:
            print(f"[akshare] 在 {end_date} 之前未找到 {symbol} 的历史财报。")
            return {}

        # 4. 获取最新的那条报告
        df_pit = df_pit.sort_values(by=date_col, ascending=False)
        latest_report: pd.Series = df_pit.iloc[0]

        # 5. 映射到 agent_design 规范
        return _map_akshare_to_spec(latest_report, is_us)

    except Exception as e:
        print(f"[akshare] 获取 {ticker} 在 {end_date} 的基本面数据时出错: {e}")
        return {}
