import csv
import time

import numpy as np
import pandas as pd
from nlp_test.save_agent_decision import save_agent_csv

from agentgraph.orchestrator import IntelliFin_Assistant

# ================== 参数设置 / Parameters ==================
INITIAL_CASH = 100000.0
COMMISSION_RATE = 0.001
SLIPPAGE = 0.0005
PRICE_FILE = "GOOG.csv"
TICKER = "GOOG"
START_DATE = "2025-07-01"
END_DATE = "2025-08-20"
AGENT_DECISION_FILE = "agent_decisions.csv"
TRADES_FILE = "trades.csv"
PORTFOLIO_FILE = "portfolio_daily.csv"


# ========== 读取价格 / Load price data ==========
def load_prices(price_file: str) -> pd.DataFrame:
    prices = pd.read_csv(price_file)
    prices["Date"] = pd.to_datetime(prices["Date"])
    prices = prices.set_index("Date").sort_index()
    return prices


# ========== 初始化输出文件 / Initialize CSV files ==========
def init_csv_files():
    # 交易明细文件
    with open(TRADES_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "trade_id",
                "date",
                "time",
                "ticker",
                "side",
                "quantity",
                "price",
                "fee",
                "slippage",
                "trade_value",
                "realized_pnl",
            ]
        )
    # trade_id：交易编号
    # date、time：成交日期和时间
    # ticker：股票代码
    # side：买入/卖出（BUY/SELL）
    # quantity：成交股数
    # price：成交价格
    # fee：手续费
    # slippage：滑点成本（货币单位）
    # trade_value：成交金额（绝对值）
    # realized_pnl：本次交易产生的已实现盈亏

    # 每日组合状态文件
    with open(PORTFOLIO_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "date",
                "ticker",
                "close",
                "cash",
                "position_shares",
                "position_value",
                "equity",
                "unrealized_pnl",
                "cum_realized_pnl",
                "trade_executed",
                "current_position_pct_input",
                "target_position_pct_output",
                "action",
            ]
        )
    # date：日期
    # ticker：股票代码
    # close：当天收盘价
    # cash：当天收盘后账户现金
    # position_shares：持有的股数，多头为正，空头为负（非常关键）
    # position_value：持仓市值 = position_shares * close
    # equity：总权益 = 现金 + 持仓市值（如果持空，持仓市值为负）
    # unrealized_pnl：浮动盈亏（基于 avg_cost）
    # cum_realized_pnl：累积已实现盈亏
    # trade_executed：当天是否有成交（0/1）
    # current_position_pct_input：当天传给 Agent 的仓位比例（单位：百分比）
    # target_position_pct_output：Agent 输出的目标仓位比例，已经缩放到 -1~1 之间的数
    # action：Agent 的动作（BUY / SELL / HOLD）


# ========== 实时写入函数 / append row to csv ==========
def append_trade_row(row: dict):
    with open(TRADES_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                row["trade_id"],
                row["date"],
                row["time"],
                row["ticker"],
                row["side"],
                row["quantity"],
                row["price"],
                row["fee"],
                row["slippage"],
                row["trade_value"],
                row["realized_pnl"],
            ]
        )


def append_portfolio_row(row: dict):
    with open(PORTFOLIO_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                row["date"],
                row["ticker"],
                row["close"],
                row["cash"],
                row["position_shares"],
                row["position_value"],
                row["equity"],
                row["unrealized_pnl"],
                row["cum_realized_pnl"],
                row["trade_executed"],
                row["current_position_pct_input"],
                row["target_position_pct_output"],
                row["action"],
            ]
        )


# ========== 回测主流程 / Backtest ==========
def backtest_with_agent():
    init_csv_files()
    prices = load_prices(PRICE_FILE)
    prices = prices.loc[START_DATE:END_DATE].copy()

    cash = INITIAL_CASH
    position = 0  # 持仓股数：多头>0，空头<0
    avg_cost = 0.0  # 单股平均成本价（不带方向符号）
    cum_realized_pnl = 0.0
    trade_id = 1

    for current_date, row in prices.iterrows():
        close_price = float(row["Close"])

        # 当前组合市值 / Current portfolio value
        position_value = position * close_price
        equity = cash + position_value
        # 当前仓位比例（-1~1，对应 -100%~100%）
        current_position_pct = position_value / equity if equity != 0 else 0.0

        # === 调用智能体 / Call agent ===
        date_iso = current_date.strftime("%Y-%m-%dT00:00:00Z")
        time.sleep(15)
        trade_agent = IntelliFin_Assistant()

        # 智能体的输入是百分比，例如 1 表示 1%
        current_position_pct *= 100.0
        print(
            "Agent input:", date_iso, "current_position_pct(%) =", current_position_pct
        )

        result = trade_agent.run(TICKER, date_iso, current_position_pct)
        action = str(result.get("Action", "HOLD")).upper()
        raw_target_pct = float(result.get("Target_position_pct", current_position_pct))
        # raw 和 target的区别，raw是百分比，target是-1到1的数
        target_pos_pct = raw_target_pct / 100.0
        target_pos_pct = max(min(target_pos_pct, 1.0), -1.0)
        print(
            "Agent output:",
            date_iso,
            "action =",
            action,
            "raw_target_pct =",
            raw_target_pct,
            "=> target_pos_pct =",
            target_pos_pct,
        )

        pm_report = result.get("PM_report", "")
        save_agent_csv(TICKER, date_iso, pm_report, action, target_pos_pct)

        # === 交易执行 / Order execution ===
        trade_executed = False
        realized_pnl = 0.0
        position_value_before = position_value
        equity_before = equity

        if action in ["BUY", "SELL"] and equity_before > 0:
            # 根据目标仓位比例，计算目标市值 & 股数
            target_position_value = equity_before * target_pos_pct
            target_shares = np.floor(target_position_value / close_price)
            trade_shares = int(target_shares - position)

            if trade_shares != 0:
                side = "BUY" if trade_shares > 0 else "SELL"

                # 滑点：买入加价，卖出减价
                exec_price = (
                    close_price * (1 + SLIPPAGE)
                    if side == "BUY"
                    else close_price * (1 - SLIPPAGE)
                )

                # 带符号的成交金额：买入为正（现金流出），卖出为负（现金流入）
                signed_trade_value = exec_price * trade_shares
                fee = abs(signed_trade_value) * COMMISSION_RATE

                # 理想价格 vs 滑点价格，用于计算滑点成本
                ideal_trade_value = close_price * trade_shares
                slippage_cost = abs(ideal_trade_value - signed_trade_value)

                # ===== 多空统一 Position & PnL 逻辑 =====
                pos_before = position
                realized_pnl_gross = 0.0

                if pos_before == 0:
                    # 完全新开仓：可能是多头，也可能是空头
                    position = trade_shares
                    avg_cost = exec_price

                else:
                    pos_sign = np.sign(pos_before)
                    trade_sign = np.sign(trade_shares)

                    if pos_sign == trade_sign:
                        # 加仓（多头加多 / 空头加空）
                        total_before = abs(pos_before)
                        total_after = abs(pos_before + trade_shares)

                        total_cost = avg_cost * total_before + exec_price * abs(
                            trade_shares
                        )
                        avg_cost = total_cost / total_after
                        position = pos_before + trade_shares

                    else:
                        # 平仓（多头 + 卖出 / 空头 + 买入）
                        # 这部分会产生已实现盈亏
                        close_shares = min(abs(pos_before), abs(trade_shares))

                        if pos_before > 0 > trade_shares:
                            # 平多：收益 = (平仓价 - 成本价) * 股数
                            realized_pnl_gross += (exec_price - avg_cost) * close_shares
                        elif pos_before < 0 < trade_shares:
                            # 平空：收益 = (开空价 - 平空价) * 股数
                            # 开空时大致以 avg_cost 卖出，平仓时以 exec_price 买回
                            realized_pnl_gross += (avg_cost - exec_price) * close_shares

                        # 更新剩余仓位：可能从多头变空头，或者从空头变多头
                        position = pos_before + trade_shares
                        if position == 0:
                            avg_cost = 0.0
                        else:
                            # 对于反向之后的新仓位，重新以当前成交价作为成本
                            avg_cost = exec_price

                # 净已实现盈亏 = 毛利 - 手续费 - 滑点成本
                realized_pnl = realized_pnl_gross - fee - slippage_cost
                cum_realized_pnl += realized_pnl

                # 现金更新：买入现金减少，卖出现金增加
                cash -= signed_trade_value
                cash -= fee

                # 写入交易明细
                append_trade_row(
                    {
                        "trade_id": trade_id,
                        "date": current_date.strftime("%Y-%m-%d"),
                        "time": "15:59:00",
                        "ticker": TICKER,
                        "side": side,
                        "quantity": abs(trade_shares),
                        "price": round(exec_price, 4),
                        "fee": round(fee, 4),
                        "slippage": round(slippage_cost, 4),
                        "trade_value": round(exec_price * abs(trade_shares), 4),
                        "realized_pnl": round(realized_pnl, 4),
                    }
                )
                trade_executed = True
                trade_id += 1

        # === 日终组合 / End-of-day portfolio ===
        position_value_after = position * close_price
        equity_after = cash + position_value_after

        # 浮动盈亏：
        # 多头： (现价 - 成本价) * 正股数
        # 空头： (现价 - 成本价) * 负股数  → 价格下跌时为正，价格上涨时为负
        if position != 0:
            unrealized_pnl = (close_price - avg_cost) * position
        else:
            unrealized_pnl = 0.0

        # 写入每日组合状态
        append_portfolio_row(
            {
                "date": current_date.strftime("%Y-%m-%d"),
                "ticker": TICKER,
                "close": round(close_price, 4),
                "cash": round(cash, 4),
                "position_shares": position,
                "position_value": round(position_value_after, 4),
                "equity": round(equity_after, 4),
                "unrealized_pnl": round(unrealized_pnl, 4),
                "cum_realized_pnl": round(cum_realized_pnl, 4),
                "trade_executed": int(trade_executed),
                # 注意：current_position_pct 这里仍然是“百分比”形式（例如 100 = 100%）
                "current_position_pct_input": round(current_position_pct, 4),
                # 输出的是 -1~1 范围的小数比例，便于区分多空
                "target_position_pct_output": round(target_pos_pct, 4),
                "action": action,
            }
        )

    print("Backtest finished — daily CSV updated incrementally.")


if __name__ == "__main__":
    backtest_with_agent()
