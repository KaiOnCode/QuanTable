import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

# ======== 配置 / Config ========
PORTFOLIO_FILE = "portfolio_daily.csv"  # 你的回测输出
SP500_TICKER = "^GSPC"  # S&P 500 指数
NASDAQ100_TICKER = "^NDX"  # Nasdaq 100 指数（如果拉不下来可以改成 QQQ ETF）


def load_strategy_equity(portfolio_file: str) -> pd.Series:
    """
    从 portfolio_daily.csv 读取策略净值时间序列
    Read strategy equity curve from CSV.
    需要列: date, equity
    """
    df = pd.read_csv(portfolio_file, parse_dates=["date"])
    df = df.sort_values("date")
    df.set_index("date", inplace=True)
    equity = df["equity"].astype(float)
    return equity


def compute_returns_from_equity(equity: pd.Series):
    """
    由净值计算日收益率 & 累计收益
    Compute daily and cumulative returns from equity curve.
    """
    daily_ret = equity.pct_change().fillna(0.0)
    cum_ret = (1 + daily_ret).cumprod() - 1
    return daily_ret, cum_ret


def download_benchmarks(start_date, end_date):
    """
    从 yfinance 下载基准指数价格并计算收益
    Download benchmark prices and compute returns.
    """
    tickers = [SP500_TICKER, NASDAQ100_TICKER]
    data = yf.download(tickers=tickers, start=start_date, end=end_date)

    # 使用 Close（若没有则用 Adj Close）
    if "Close" in data.columns:
        prices = data["Close"]
    else:
        prices = data["Adj Close"]

    # 统一列名为简单字符串（有时是 MultiIndex）
    if isinstance(prices.columns, pd.MultiIndex):
        prices.columns = [c[1] for c in prices.columns]

    # 只保留我们需要的两个
    prices = prices[[SP500_TICKER, NASDAQ100_TICKER]]

    daily_ret = prices.pct_change().fillna(0.0)
    cum_ret = (1 + daily_ret).cumprod() - 1
    return prices, daily_ret, cum_ret


def align_to_strategy_index(
    strategy_index: pd.DatetimeIndex, bench_cum_ret: pd.DataFrame
) -> pd.DataFrame:
    """
    把基准的累计收益对齐到策略的日期索引（前向填充）
    Align benchmark cumulative returns to strategy date index.
    """
    aligned = bench_cum_ret.reindex(strategy_index).ffill()
    return aligned


def plot_cumulative_returns(strategy_cum: pd.Series, bench_cum: pd.DataFrame):
    """
    画策略 vs S&P 500 vs Nasdaq 100 的累计收益曲线
    Plot cumulative returns comparison.
    """
    plt.figure(figsize=(10, 6))

    # 策略
    strategy_cum.plot(label="Strategy", linewidth=1.5)

    # 基准
    bench_cum[SP500_TICKER].plot(label="S&P 500", linestyle="--")
    bench_cum[NASDAQ100_TICKER].plot(label="Nasdaq 100", linestyle=":")

    plt.ylabel("Cumulative Return")
    plt.xlabel("Date")
    plt.title("Strategy vs S&P 500 vs Nasdaq 100")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def main():
    # 1) 读取策略净值
    strategy_equity = load_strategy_equity(PORTFOLIO_FILE)

    # 2) 策略日收益 & 累计收益
    strategy_daily_ret, strategy_cum_ret = compute_returns_from_equity(strategy_equity)

    # 3) 基准时间范围：根据策略日期自动设置
    start_date = strategy_equity.index.min().strftime("%Y-%m-%d")
    # yfinance end 参数是“到这一天为止（不含）”，所以+1天更稳妥
    end_date = (strategy_equity.index.max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    # 4) 下载 S&P500 和 Nasdaq100
    _, bench_daily_ret, bench_cum_ret = download_benchmarks(start_date, end_date)

    # 5) 将基准的累计收益对齐到策略日期
    bench_cum_aligned = align_to_strategy_index(strategy_cum_ret.index, bench_cum_ret)

    # 6) 画累计收益曲线
    plot_cumulative_returns(strategy_cum_ret, bench_cum_aligned)

    # 7) 控制台简单打印最终收益对比
    print("=== Final Cumulative Return ===")
    print(f"Strategy   : {strategy_cum_ret.iloc[-1]:.2%}")
    print(f"S&P 500    : {bench_cum_aligned[SP500_TICKER].iloc[-1]:.2%}")
    print(f"Nasdaq 100 : {bench_cum_aligned[NASDAQ100_TICKER].iloc[-1]:.2%}")


if __name__ == "__main__":
    main()
