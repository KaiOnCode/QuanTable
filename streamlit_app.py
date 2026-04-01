"""
IntelliFin Assistant - Streamlit Web 界面
股票分析多智能体系统的交互式网页界面
"""

import os
import re
import sys
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

# 加载配置
load_dotenv("properties.env")

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)


# 确保所有必要的目录都有 __init__.py 文件
def ensure_init_files():
    """确保所有Python包目录都有 __init__.py 文件"""
    directories = [
        os.path.join(project_root, "dataflow"),
        os.path.join(project_root, "dataflow", "providers"),
        os.path.join(project_root, "agentgraph"),
        os.path.join(project_root, "agents"),
        os.path.join(project_root, "agents", "utils"),
    ]

    for directory in directories:
        if os.path.exists(directory):
            init_file = os.path.join(directory, "__init__.py")
            if not os.path.exists(init_file):
                try:
                    with open(init_file, "w") as f:
                        f.write("# Auto-generated __init__.py\n")
                except Exception:
                    pass  # 如果无法创建，继续尝试导入


# 创建必要的 __init__.py 文件
ensure_init_files()

# 尝试导入依赖模块，如果失败则显示友好错误信息
DEPENDENCIES_OK = True
MISSING_DEPS = []
IMPORT_ERROR_MSG = ""

try:
    from agentgraph.orchestrator import IntelliFin_Assistant
    from dataflow.providers.YFinance import (
        df_get_fundamentals,
        df_get_indicators,
        df_get_prices,
    )
except ImportError as e:
    DEPENDENCIES_OK = False
    error_msg = str(e)
    IMPORT_ERROR_MSG = error_msg

    # 检测缺失的模块
    if "akshare" in error_msg:
        MISSING_DEPS.append("akshare")
    if "yfinance" in error_msg:
        MISSING_DEPS.append("yfinance")
    if "langchain" in error_msg:
        MISSING_DEPS.append("langchain-openai")
        MISSING_DEPS.append("langgraph")
    if "plotly" in error_msg:
        MISSING_DEPS.append("plotly")
    if "pandas_ta" in error_msg or "pandas-ta" in error_msg:
        MISSING_DEPS.append("pandas-ta")
    elif "pandas" in error_msg:
        MISSING_DEPS.append("pandas")

    # 如果没有识别出具体模块，显示完整错误
    if not MISSING_DEPS:
        MISSING_DEPS.append(error_msg)


# 页面配置
st.set_page_config(
    page_title="IntelliFin Assistant - Intelligent Stock Analysis",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# 简化的Backtester类（内嵌实现）
class Backtester:
    """简化的回测器，用于历史分析"""

    def __init__(self):
        pass

    def run_historical_analysis(
        self, ticker: str, analysis_date: str, forward_days: int = 30
    ):
        """运行历史分析"""
        from datetime import datetime, timedelta

        # 导入IntelliFin_Assistant
        agent = IntelliFin_Assistant()

        # 将日期转换为ISO格式
        date_iso = f"{analysis_date}T00:00:00Z"

        # 运行分析（使用历史日期）
        result = agent.run(ticker, date=date_iso, current_position_pct=0.0)

        # 提取新闻来源
        result["news_sources"] = extract_news_sources_from_result(result)

        # 计算验证期收益
        try:
            analysis_dt = datetime.strptime(analysis_date, "%Y-%m-%d")
            validation_end = analysis_dt + timedelta(days=forward_days)

            # 获取分析日期的价格
            analysis_data = df_get_prices(ticker, 5, end_date=date_iso)
            analysis_price = None
            if analysis_data and analysis_data.get("rows"):
                analysis_price = analysis_data["rows"][-1]["c"]

            # 获取验证期结束的价格
            validation_end_str = validation_end.strftime("%Y-%m-%dT00:00:00Z")
            validation_data = df_get_prices(ticker, 5, end_date=validation_end_str)
            future_price = None
            if validation_data and validation_data.get("rows"):
                future_price = validation_data["rows"][-1]["c"]

            # 计算实际收益
            actual_return = 0.0
            if analysis_price and future_price:
                actual_return = (future_price - analysis_price) / analysis_price

            result["backtest_validation"] = {
                "analysis_price": analysis_price or 0.0,
                "future_price": future_price or 0.0,
                "actual_return": actual_return,
                "forward_days": forward_days,
                "validation_date": validation_end.strftime("%Y-%m-%d"),
            }
        except Exception as e:
            st.warning(f"验证期收益计算失败: {str(e)}")
            result["backtest_validation"] = None

        return result


# 自定义 CSS
st.markdown(
    """
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .report-box {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .metric-card {
        background-color: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    .decision-buy {
        color: #00c853;
        font-weight: bold;
        font-size: 1.5rem;
    }
    .decision-sell {
        color: #d50000;
        font-weight: bold;
        font-size: 1.5rem;
    }
    .decision-hold {
        color: #ffa000;
        font-weight: bold;
        font-size: 1.5rem;
    }
</style>
""",
    unsafe_allow_html=True,
)


def check_config():
    """Check if configuration is correct"""
    if not os.path.exists("properties.env"):
        st.error("❌ Config file properties.env not found")
        st.info("Please create properties.env and configure OPENAI_API_KEY")
        st.stop()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        st.error("❌ Please configure a valid OPENAI_API_KEY in properties.env")
        st.stop()


def create_enhanced_chart(
    ticker: str,
    days: int = 90,
    show_sma=True,
    show_bollinger=False,
    show_rsi=True,
    show_macd=True,
    show_volume=True,
):
    """创建增强型价格图表"""
    try:
        data = df_get_prices(ticker, days)
        if not data or not data.get("rows"):
            return None

        rows = data["rows"]
        df = pd.DataFrame(rows)
        df["ts"] = pd.to_datetime(df["ts"])

        # 创建子图
        from plotly.subplots import make_subplots

        rows_count = 1
        if show_rsi:
            rows_count += 1
        if show_macd:
            rows_count += 1
        if show_volume:
            rows_count += 1

        row_heights = [0.5] + [0.15] * (rows_count - 1)

        fig = make_subplots(
            rows=rows_count,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=row_heights,
            subplot_titles=[f"{ticker} 价格走势"] + [""] * (rows_count - 1),
        )

        # K线图
        fig.add_trace(
            go.Candlestick(
                x=df["ts"],
                open=df["o"],
                high=df["h"],
                low=df["l"],
                close=df["c"],
                name=ticker,
            ),
            row=1,
            col=1,
        )

        # 添加均线
        if show_sma and len(df) >= 20:
            df["sma20"] = df["c"].rolling(window=20).mean()
            df["sma50"] = df["c"].rolling(window=50).mean()
            fig.add_trace(
                go.Scatter(
                    x=df["ts"],
                    y=df["sma20"],
                    name="SMA20",
                    line=dict(color="orange", width=1),
                ),
                row=1,
                col=1,
            )
            if len(df) >= 50:
                fig.add_trace(
                    go.Scatter(
                        x=df["ts"],
                        y=df["sma50"],
                        name="SMA50",
                        line=dict(color="blue", width=1),
                    ),
                    row=1,
                    col=1,
                )

        current_row = 2

        # RSI
        if show_rsi and len(df) >= 14:
            df["rsi"] = 100 - (
                100
                / (
                    1
                    + df["c"].diff().clip(lower=0).rolling(14).mean()
                    / (-df["c"].diff().clip(upper=0).rolling(14).mean())
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df["ts"], y=df["rsi"], name="RSI", line=dict(color="purple")
                ),
                row=current_row,
                col=1,
            )
            fig.add_hline(
                y=70, line_dash="dash", line_color="red", row=current_row, col=1
            )
            fig.add_hline(
                y=30, line_dash="dash", line_color="green", row=current_row, col=1
            )
            current_row += 1

        # MACD
        if show_macd and len(df) >= 26:
            exp1 = df["c"].ewm(span=12, adjust=False).mean()
            exp2 = df["c"].ewm(span=26, adjust=False).mean()
            df["macd"] = exp1 - exp2
            df["signal"] = df["macd"].ewm(span=9, adjust=False).mean()
            df["hist"] = df["macd"] - df["signal"]

            fig.add_trace(
                go.Scatter(
                    x=df["ts"], y=df["macd"], name="MACD", line=dict(color="blue")
                ),
                row=current_row,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df["ts"], y=df["signal"], name="Signal", line=dict(color="orange")
                ),
                row=current_row,
                col=1,
            )
            fig.add_trace(
                go.Bar(x=df["ts"], y=df["hist"], name="Histogram"),
                row=current_row,
                col=1,
            )
            current_row += 1

        # 成交量
        if show_volume:
            colors = [
                "red" if df["c"].iloc[i] < df["o"].iloc[i] else "green"
                for i in range(len(df))
            ]
            fig.add_trace(
                go.Bar(x=df["ts"], y=df["v"], name="成交量", marker_color=colors),
                row=current_row,
                col=1,
            )

        fig.update_layout(
            height=400 + 150 * (rows_count - 1),
            template="plotly_white",
            xaxis_rangeslider_visible=False,
            showlegend=True,
        )

        return fig
    except Exception as e:
        st.warning(f"无法加载图表数据: {str(e)}")
        return None


def create_metrics_summary(ticker: str):
    """创建指标摘要"""
    try:
        # 获取价格数据
        price_data = df_get_prices(ticker, 90)
        if not price_data or not price_data.get("rows"):
            return None

        rows = price_data["rows"]
        df = pd.DataFrame(rows)

        latest_price = df.iloc[-1]["c"]
        prev_price = df.iloc[-2]["c"] if len(df) > 1 else latest_price
        price_change_pct = (
            ((latest_price - prev_price) / prev_price * 100) if prev_price else 0
        )

        # 获取技术指标
        indicators = df_get_indicators(ticker, 90)

        # 获取基本面数据
        fundamentals = df_get_fundamentals(ticker)

        return {
            "price": {"latest": latest_price, "change_pct": price_change_pct},
            "technical": indicators,
            "fundamental": fundamentals,
        }
    except Exception as e:
        st.warning(f"无法加载指标数据: {str(e)}")
        return None


def extract_news_sources_from_result(result: dict) -> list:
    """从运行结果中提取新闻来源"""
    if not result:
        return []

    # 如果已经有 news_sources，直接返回
    if "news_sources" in result and result["news_sources"]:
        return result["news_sources"]

    news_sources = []

    # 从 news_analyst_messages 中查找工具调用结果
    messages = result.get("news_analyst_messages", [])
    if not messages:
        return []

    # 查找包含新闻数据的消息
    target_content = ""
    for msg in reversed(messages):
        # 检查是否是对象并有 content 属性
        if hasattr(msg, "content"):
            content = msg.content
        elif isinstance(msg, dict):
            content = msg.get("content", "")
        else:
            continue

        if "新闻数据" in content and "共找到" in content and "【新闻" in content:
            target_content = content
            break

    if not target_content:
        return []

    # 解析新闻内容
    try:
        # 分割成单独的新闻块
        parts = target_content.split("【新闻 ")

        for part in parts[1:]:  # 跳过第一个（头部信息）
            news_item = {}

            # 提取标题
            title_match = re.search(r"标题: (.*?)\n", part)
            if title_match:
                news_item["title"] = title_match.group(1).strip()

            # 提取来源
            source_match = re.search(r"来源: (.*?)\n", part)
            if source_match:
                news_item["source"] = source_match.group(1).strip()

            # 提取发布时间
            date_match = re.search(r"发布时间: (.*?)\n", part)
            if date_match:
                news_item["published_at"] = date_match.group(1).strip()

            # 提取链接
            url_match = re.search(r"链接: (.*?)\n", part)
            if url_match:
                news_item["url"] = url_match.group(1).strip()

            if news_item.get("title"):
                news_sources.append(news_item)

    except Exception as e:
        print(f"Error parsing news sources: {e}")

    return news_sources


def parse_decision(report: str):
    """从报告中提取关键信息 - 增强版，支持多种格式"""
    if not report or not isinstance(report, str):
        return {"direction": "Unknown", "timeframe": "Unknown", "summary": "Unknown"}

    decision_info = {
        "direction": "Unknown",
        "timeframe": "Unknown",
        "summary": "Unknown",
    }

    # 清理报告文本
    report_clean = report.replace("**", "").replace("*", "").replace("```", "")
    lines = report_clean.split("\n")

    # 方法1：逐行解析标准格式
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # 匹配 "方向:" 或 "方向："
        if ("方向" in line or "Direction" in line.lower()) and (
            ":" in line or "：" in line
        ):
            # 提取冒号后的内容
            separator = "：" if "：" in line else ":"
            parts = line.split(separator, 1)
            if len(parts) > 1:
                value = parts[1].strip()
                # 移除可能的标点符号和空格
                value = value.strip("。，、；").strip()
                if value and len(value) < 50:  # 合理长度
                    decision_info["direction"] = value

        # 匹配 "时间范围:" 或 "时间范围："
        elif ("时间范围" in line or "timeframe" in line.lower()) and (
            ":" in line or "：" in line
        ):
            separator = "：" if "：" in line else ":"
            parts = line.split(separator, 1)
            if len(parts) > 1:
                value = parts[1].strip()
                value = value.strip("。，、；").strip()
                if value and len(value) < 50:
                    decision_info["timeframe"] = value

        # 匹配 "一句话结论:" 或 "一句话结论："
        elif ("一句话结论" in line or "结论" in line or "summary" in line.lower()) and (
            ":" in line or "：" in line
        ):
            separator = "：" if "：" in line else ":"
            parts = line.split(separator, 1)
            if len(parts) > 1:
                value = parts[1].strip()
                # 一句话结论可能跨多行，尝试获取后续行
                summary_lines = [value]
                for j in range(i + 1, min(i + 3, len(lines))):
                    next_line = lines[j].strip()
                    # 如果下一行不是新的字段标识，则认为是结论的一部分
                    if next_line and not any(
                        keyword in next_line
                        for keyword in [
                            "方向",
                            "时间范围",
                            "置信度",
                            "##",
                            "###",
                            "---",
                        ]
                    ):
                        summary_lines.append(next_line)
                    else:
                        break
                value = " ".join(summary_lines).strip("。，、；").strip()
                if value and len(value) < 200:
                    decision_info["summary"] = value

    # 方法2：如果标准格式解析失败，尝试从整体内容推断
    if decision_info["direction"] == "Unknown":
        report_lower = report.lower()
        report_text = report

        # 推断方向
        if (
            "bullish" in report_lower
            or "看涨" in report_text
            or "买入" in report_text
            or "buy" in report_lower
        ):
            decision_info["direction"] = "Bullish"
        elif (
            "bearish" in report_lower
            or "看跌" in report_text
            or "卖出" in report_text
            or "sell" in report_lower
        ):
            decision_info["direction"] = "Bearish"
        elif (
            "neutral" in report_lower
            or "中性" in report_text
            or "持有" in report_text
            or "hold" in report_lower
        ):
            decision_info["direction"] = "Neutral"

        # 推断时间范围
        if "intraday" in report_lower or "日内" in report_text:
            decision_info["timeframe"] = "intraday"
        elif "1-3d" in report or "短期" in report_text:
            decision_info["timeframe"] = "1-3d"
        elif "1-4w" in report or "中期" in report_text:
            decision_info["timeframe"] = "1-4w"
        elif "long-term" in report_lower or "长期" in report_text:
            decision_info["timeframe"] = "long-term"

        # 尝试提取第一句话作为摘要
        if decision_info["summary"] == "Unknown":
            sentences = report_text.split("。")
            for sentence in sentences:
                sentence = sentence.strip()
                if sentence and len(sentence) > 10 and len(sentence) < 150:
                    # 跳过包含字段名的句子
                    if not any(
                        keyword in sentence
                        for keyword in [
                            "方向",
                            "时间范围",
                            "置信度",
                            "MARKET_REPORT",
                            "RISK_REPORT",
                        ]
                    ):
                        decision_info["summary"] = sentence
                        break

    return decision_info


def get_decision_color(direction: str):
    """根据方向返回颜色类"""
    direction_lower = direction.lower()
    if "bullish" in direction_lower or "看涨" in direction_lower:
        return "decision-buy"
    elif "bearish" in direction_lower or "看跌" in direction_lower:
        return "decision-sell"
    else:
        return "decision-hold"


def main():
    # Check dependencies first
    if not DEPENDENCIES_OK:
        st.error("❌ 缺少必要的依赖库")

        st.markdown("### 🔧 错误信息：")
        with st.expander("查看详细错误", expanded=True):
            st.code(IMPORT_ERROR_MSG)

        if MISSING_DEPS:
            st.markdown("### 📦 缺少以下依赖：")
            for dep in MISSING_DEPS:
                st.code(dep)

        st.markdown("### 🛠️ 解决方法：")
        st.markdown("**方法 1：安装所有依赖（推荐）**")
        st.code("uv sync", language="bash")

        st.markdown("**方法 2：单独安装缺失的包**")
        if "akshare" in str(MISSING_DEPS):
            st.code("uv add akshare", language="bash")
        if "yfinance" in str(MISSING_DEPS):
            st.code("uv add yfinance", language="bash")
        if "langchain" in str(MISSING_DEPS):
            st.code("uv add langchain-openai langgraph", language="bash")

        st.markdown("### 📋 常见问题：")
        st.info("""
        **Q: 为什么会出现导入错误？**
        
        A: 可能的原因：
        1. 缺少必要的 Python 包（如 akshare、yfinance 等）
        2. Python 环境配置问题
        3. 包版本不兼容
        
        **解决步骤：**
        1. 确保使用正确的 Python 环境（建议使用虚拟环境）
        2. 运行 `uv sync` 安装所有依赖
        3. 如果问题仍然存在，删除 `.venv` 后重新执行 `uv sync`
        4. 重新运行应用：`uv run streamlit run streamlit_app.py`
        """)

        st.stop()

    # Check configuration
    check_config()

    # Title
    st.markdown(
        '<div class="main-header">📈 IntelliFin Assistant</div>', unsafe_allow_html=True
    )
    st.markdown(
        '<div class="sub-header">Multi-Agent Based Intelligent Stock Analysis System</div>',
        unsafe_allow_html=True,
    )

    # Initialize session state
    if "analysis_history" not in st.session_state:
        st.session_state.analysis_history = []
    if "current_mode" not in st.session_state:
        st.session_state.current_mode = "Real-time Analysis"

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Analysis Settings")

        # Mode selection
        mode = st.radio(
            "Analysis Mode",
            ["Real-time Analysis", "Backtest Mode"],
            key="mode_selector",
        )
        st.session_state.current_mode = mode

        st.divider()

        # Ticker input
        ticker = st.text_input(
            "Ticker Symbol",
            value="AAPL",
            help="Enter US stock ticker, e.g., AAPL, TSLA, NVDA, MSFT",
            max_chars=10,
        ).upper()

        # Backtest settings (only shown in backtest mode)
        backtest_date = None
        forward_days = 30
        if mode == "Backtest Mode":
            st.subheader("📅 Backtest Settings")
            backtest_date = st.date_input(
                "Analysis Date",
                value=datetime.now() - timedelta(days=60),
                max_value=datetime.now() - timedelta(days=31),
                help="Select a historical date for analysis",
            )
            forward_days = st.selectbox(
                "Validation Period (Days)",
                [7, 14, 30, 60, 90],
                index=2,
                help="Days to validate future performance after analysis",
            )
            st.caption(
                f"💡 The system will predict based on data from {backtest_date}, then validate actual performance for the next {forward_days} days."
            )

        st.divider()

        # Chart settings
        st.subheader("📊 Chart Settings")
        show_chart = st.checkbox("Show Price Chart", value=True)

        if show_chart:
            chart_days = st.selectbox(
                "Time Range",
                [30, 60, 90, 180, 365],
                index=2,
                help="Select the number of days to display",
            )

            with st.expander("Technical Indicators"):
                show_sma = st.checkbox("SMA (Moving Average)", value=True)
                show_bollinger = st.checkbox("Bollinger Bands", value=False)
                show_rsi = st.checkbox("RSI", value=True)
                show_macd = st.checkbox("MACD", value=True)
                show_volume = st.checkbox("Volume", value=True)
        else:
            chart_days = 90
            show_sma = show_bollinger = show_rsi = show_macd = show_volume = False

        st.divider()

        # Display options
        st.subheader("📋 Display Options")
        show_metrics = st.checkbox("Show Metrics Dashboard", value=True)
        show_details = st.checkbox("Show Detailed Report", value=True)

        # 调试选项
        with st.expander("🔧 Advanced Options"):
            show_debug = st.checkbox("Show Debug Info", value=False)
            if "show_debug" not in st.session_state:
                st.session_state.show_debug = False
            st.session_state.show_debug = show_debug

        st.divider()

        # Analyze button
        if mode == "Real-time Analysis":
            analyze_button = st.button(
                "🚀 Start Analysis", type="primary", use_container_width=True
            )
        else:
            analyze_button = st.button(
                "🔄 Run Backtest", type="primary", use_container_width=True
            )

        st.divider()

        # System Info
        st.subheader("ℹ️ System Info")
        st.info("""
        **Agent Architecture:**
        - Market Analyst (Technical)
        - News Analyst (Sentiment)
        - Fundamental Analyst (Financial)
        - Risk Analyst (Risk Control)
        - PM Agent (Final Decision)
        
        **Data Sources:**
        - Yahoo Finance
        - Google News
        """)

        st.caption(f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Main Interface
    if not ticker:
        st.warning("⚠️ Please enter a stock ticker")
        return

    # Display Price Chart
    if show_chart:
        with st.spinner(f"Loading price data for {ticker}..."):
            fig = create_enhanced_chart(
                ticker,
                days=chart_days,
                show_sma=show_sma,
                show_bollinger=show_bollinger,
                show_rsi=show_rsi,
                show_macd=show_macd,
                show_volume=show_volume,
            )
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(f"Unable to load chart data for {ticker}")

    # Display Metrics Dashboard
    if show_metrics:
        with st.spinner("Loading metrics data..."):
            metrics = create_metrics_summary(ticker)
            if metrics:
                st.subheader("📊 Key Metrics Dashboard")

                # Price Metrics
                col1, col2, col3, col4 = st.columns(4)

                price_info = metrics.get("price", {})
                latest_price = price_info.get("latest")
                price_change = price_info.get("change_pct")

                with col1:
                    if latest_price:
                        st.metric(
                            "Latest Price",
                            f"${latest_price:.2f}",
                            f"{price_change:+.2f}%" if price_change else None,
                        )
                    else:
                        st.metric("Latest Price", "N/A")

                # Technical Metrics
                tech = metrics.get("technical", {})

                with col2:
                    rsi = tech.get("rsi14")
                    if rsi:
                        rsi_status = (
                            "Overbought"
                            if rsi > 70
                            else ("Oversold" if rsi < 30 else "Normal")
                        )
                        st.metric("RSI(14)", f"{rsi:.1f}", rsi_status)
                    else:
                        st.metric("RSI(14)", "N/A")

                with col3:
                    macd_data = tech.get("macd", {})
                    if macd_data:
                        signal_cross = macd_data.get("signal_cross", False)
                        st.metric(
                            "MACD Signal", "Golden Cross" if signal_cross else "Normal"
                        )
                    else:
                        st.metric("MACD Signal", "N/A")

                with col4:
                    ma_data = tech.get("ma", {})
                    sma20 = ma_data.get("sma20")
                    sma50 = ma_data.get("sma50")
                    if sma20 and sma50:
                        trend = "Bullish" if sma20 > sma50 else "Bearish"
                        st.metric("MA Trend", trend)
                    else:
                        st.metric("MA Trend", "N/A")

                # Fundamental Metrics
                fundamental = metrics.get("fundamental", {})
                if fundamental:
                    st.markdown("---")
                    st.markdown("**Fundamental Metrics**")

                    col1, col2, col3, col4 = st.columns(4)

                    ttm = fundamental.get("ttm", {})
                    growth = fundamental.get("growth", {})

                    with col1:
                        pe = ttm.get("pe")
                        st.metric("P/E Ratio", f"{pe:.2f}" if pe else "N/A")

                    with col2:
                        pb = ttm.get("pb")
                        st.metric("P/B Ratio", f"{pb:.2f}" if pb else "N/A")

                    with col3:
                        eps_growth = growth.get("eps_yoy")
                        st.metric(
                            "EPS Growth", f"{eps_growth:.1f}%" if eps_growth else "N/A"
                        )

                    with col4:
                        rev_growth = growth.get("rev_yoy")
                        st.metric(
                            "Rev Growth", f"{rev_growth:.1f}%" if rev_growth else "N/A"
                        )

                st.divider()

    # Analyze button clicked
    if analyze_button:
        if not ticker:
            st.error("❌ Please enter a stock ticker")
            return

        # Initialize session state
        if "analysis_result" not in st.session_state:
            st.session_state.analysis_result = None

        # Display status details
        try:
            if mode == "Backtest Mode" and backtest_date:
                # Backtest Mode - Detailed progress
                with st.status(f"🔄 Backtesting {ticker}...", expanded=True) as status:
                    import time

                    st.write("⏳ Initializing backtest system...")
                    time.sleep(0.5)
                    backtester = Backtester()
                    st.write("  ✅ Backtest system initialized")

                    analysis_date_str = backtest_date.strftime("%Y-%m-%d")
                    st.write("")
                    st.write(f"📅 Analysis Date: {analysis_date_str}")
                    st.write(f"📊 Validation Period: {forward_days} days")

                    st.write("")
                    st.write("📚 Fetching historical data...")
                    time.sleep(0.3)
                    st.write("  ├─ 📈 Fetching price history...")
                    time.sleep(0.2)
                    st.write("  ├─ 📰 Fetching historical news...")
                    time.sleep(0.2)
                    st.write("  └─ 💼 Fetching financial data...")
                    st.write("  ✅ Historical data fetched")

                    st.write("")
                    st.write("🔄 Running multi-agent analysis...")
                    st.write("")

                    # Market Analyst
                    st.write(
                        "  📈 **Market Analyst** - Analyzing historical technicals..."
                    )
                    time.sleep(0.3)
                    st.write("    ├─ 📊 Calculating historical indicators...")
                    time.sleep(0.2)
                    st.write("    └─ 🔬 Identifying historical trends...")

                    # News Analyst
                    st.write("")
                    st.write("  📰 **News Analyst** - Analyzing historical news...")
                    time.sleep(0.3)
                    st.write("    ├─ 📝 Parsing historical news...")
                    time.sleep(0.2)
                    st.write("    └─ 😊 Evaluating sentiment...")

                    # Fundamental Analyst
                    st.write("")
                    st.write(
                        "  💼 **Fundamental Analyst** - Analyzing historical financials..."
                    )
                    time.sleep(0.3)
                    st.write("    ├─ 💰 Analyzing historical financials...")
                    time.sleep(0.2)
                    st.write("    └─ 📊 Evaluating valuation...")

                    st.write("")
                    st.write("  ⏳ Waiting for AI agents to complete analysis...")

                    # Run historical analysis
                    result = backtester.run_historical_analysis(
                        ticker, analysis_date_str, forward_days=forward_days
                    )

                    st.write("")
                    st.write("  ✅ **Historical Analysis Completed**")

                    st.write("")
                    st.write("⚖️ **Risk Analyst** - Assessing historical risk...")
                    time.sleep(0.2)
                    st.write("  ✅ **Risk Assessment Completed**")

                    st.write("")
                    st.write("🎯 **PM Agent** - Generating historical decision...")
                    time.sleep(0.2)
                    st.write("  ✅ **Investment Decision Completed**")

                    st.write("")
                    st.write("📈 Calculating validation period returns...")
                    time.sleep(0.3)
                    st.write("  ├─ 📊 Fetching validation period prices...")
                    time.sleep(0.2)
                    st.write("  ├─ 💹 Calculating actual returns...")
                    time.sleep(0.2)
                    st.write("  └─ 🎯 Evaluating prediction accuracy...")
                    st.write("  ✅ **Validation Calculation Completed**")

                    st.write("")
                    st.write("✅ Backtest Analysis Completed!")
                    status.update(
                        label=f"✅ {ticker} Backtest Completed!",
                        state="complete",
                        expanded=False,
                    )

                # Save results
                result["is_backtest"] = True
                result["backtest_date"] = analysis_date_str
                result["forward_days"] = forward_days
                st.session_state.analysis_result = result

            else:
                # Real-time Analysis Mode - Detailed progress
                with st.status(f"🔄 Analyzing {ticker}...", expanded=True) as status:
                    st.write("⏳ Initializing agent system...")
                    import time

                    time.sleep(0.5)
                    agent = IntelliFin_Assistant()
                    st.write("  ✅ Agent system initialized")

                    st.write("")
                    st.write("📊 Executing parallel analysis...")
                    st.write("")

                    # Market Analyst
                    st.write("  📈 **Market Analyst** - Starting...")
                    time.sleep(0.3)
                    st.write("    ├─ 🔍 Fetching historical prices...")
                    time.sleep(0.2)
                    st.write(
                        "    ├─ 📊 Calculating technical indicators (RSI, MACD, SMA)..."
                    )
                    time.sleep(0.2)
                    st.write("    ├─ 📉 Identifying support & resistance...")
                    time.sleep(0.2)
                    st.write("    └─ 🔬 Analyzing trends & signals...")

                    # News Analyst
                    st.write("")
                    st.write("  📰 **News Analyst** - Starting...")
                    time.sleep(0.3)
                    st.write("    ├─ 🌐 Scraping latest news...")
                    time.sleep(0.2)
                    st.write("    ├─ 📝 Parsing news content...")
                    time.sleep(0.2)
                    st.write("    ├─ 😊 Analyzing sentiment...")
                    time.sleep(0.2)
                    st.write("    └─ 📊 Assessing market impact...")

                    # Fundamental Analyst
                    st.write("")
                    st.write("  💼 **Fundamental Analyst** - Starting...")
                    time.sleep(0.3)
                    st.write("    ├─ 💰 Fetching financial data...")
                    time.sleep(0.2)
                    st.write("    ├─ 📈 Calculating valuation metrics (PE, PB, PS)...")
                    time.sleep(0.2)
                    st.write("    ├─ 📊 Analyzing growth rates...")
                    time.sleep(0.2)
                    st.write("    └─ 🏢 Evaluating industry position...")

                    st.write("")
                    st.write("  ⏳ Waiting for AI agents to complete analysis...")

                    # Run analysis - 传递当前日期
                    current_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
                    result = agent.run(
                        ticker, date=current_date, current_position_pct=0.0
                    )

                    # 提取新闻来源
                    result["news_sources"] = extract_news_sources_from_result(result)

                    st.write("")
                    st.write("  ✅ **Market Analysis Completed**")
                    st.write("  ✅ **News Analysis Completed**")
                    st.write("  ✅ **Fundamental Analysis Completed**")

                    st.write("")
                    st.write("⚖️ **Risk Analyst** - Synthesizing assessment...")
                    time.sleep(0.3)
                    st.write("    ├─ 📊 Fetching position info...")
                    time.sleep(0.2)
                    st.write("    ├─ ⚠️ Checking risk limits...")
                    time.sleep(0.2)
                    st.write("    ├─ 🔍 Analyzing upstream reports...")
                    time.sleep(0.2)
                    st.write("    └─ 📝 Generating risk assessment...")
                    st.write("  ✅ **Risk Assessment Completed**")

                    st.write("")
                    st.write(
                        "🎯 **PM Agent** - Generating final investment decision..."
                    )
                    time.sleep(0.3)
                    st.write("    ├─ 📋 Synthesizing four analysis reports...")
                    time.sleep(0.2)
                    st.write("    ├─ ⚖️ Weighing factors...")
                    time.sleep(0.2)
                    st.write("    ├─ 🎯 Determining investment direction...")
                    time.sleep(0.2)
                    st.write("    └─ 📝 Generating final decision...")
                    st.write("  ✅ **Investment Decision Completed**")

                    st.write("")
                    status.update(
                        label=f"✅ {ticker} Analysis Completed!",
                        state="complete",
                        expanded=False,
                    )

                # Save results
                result["is_backtest"] = False
                result["analysis_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.session_state.analysis_result = result

            # 添加到历史记录
            history_entry = {
                "ticker": ticker,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "mode": mode,
                "result": result,
            }
            st.session_state.analysis_history.append(history_entry)

            # 限制历史记录数量
            if len(st.session_state.analysis_history) > 20:
                st.session_state.analysis_history = st.session_state.analysis_history[
                    -20:
                ]

        except Exception as e:
            st.error(f"❌ Error during analysis: {str(e)}")
            st.exception(e)
            return

    # 显示分析结果
    if st.session_state.get("analysis_result"):
        result = st.session_state.analysis_result

        st.divider()

        # 回测验证结果（仅回测模式）
        if result.get("is_backtest") and result.get("backtest_validation"):
            validation = result["backtest_validation"]

            st.header("📊 Backtest Validation Results")

            # 显示验证指标
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Analysis Date Price", f"${validation['analysis_price']:.2f}")

            with col2:
                st.metric(
                    "Validation End Price",
                    f"${validation['future_price']:.2f}",
                    f"{validation['actual_return']:+.2%}",
                )

            with col3:
                actual_return = validation["actual_return"]
                st.metric(
                    "Actual Return",
                    f"{actual_return:.2%}",
                    "Profit" if actual_return > 0 else "Loss",
                )

            with col4:
                st.metric(
                    "Validation Period",
                    f"{validation['forward_days']}days",
                    validation["validation_date"],
                )

            # 预测准确性评估
            st.markdown("---")
            st.subheader("🎯 Prediction Accuracy Evaluation")

            # 解析预测方向
            pm_report = result.get("PM_report", "")
            if pm_report:
                decision_info = parse_decision(pm_report)
                predicted_direction = decision_info["direction"]

                # 判断预测是否准确
                actual_return = validation["actual_return"]
                if actual_return > 0.02:
                    actual_direction = "Bullish"
                elif actual_return < -0.02:
                    actual_direction = "Bearish"
                else:
                    actual_direction = "Neutral"

                is_correct = (predicted_direction == actual_direction) or (
                    predicted_direction == "Neutral" and abs(actual_return) < 0.02
                )

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.markdown(
                        f"""
                    <div class="metric-card">
                        <h4>Predicted Direction</h4>
                        <p class="{get_decision_color(predicted_direction)}">{predicted_direction}</p>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )

                with col2:
                    st.markdown(
                        f"""
                    <div class="metric-card">
                        <h4>Actual Direction</h4>
                        <p class="{get_decision_color(actual_direction)}">{actual_direction}</p>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )

                with col3:
                    result_color = "decision-buy" if is_correct else "decision-sell"
                    result_text = (
                        "✅ Predicted Accurate"
                        if is_correct
                        else "❌ Predicted Inaccurate"
                    )
                    st.markdown(
                        f"""
                    <div class="metric-card">
                        <h4>Accuracy</h4>
                        <p class="{result_color}">{result_text}</p>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )

            st.divider()

        st.header("📋 Analysis Report")

        # 最终决策
        final_report = result.get("PM_report", "")

        # 调试：显示原始报告（可选，用于调试）
        if st.session_state.get("show_debug", False):
            with st.expander("🔍 调试：原始PM报告", expanded=False):
                st.text(f"报告类型: {type(final_report)}")
                st.text(f"报告长度: {len(final_report) if final_report else 0}")
                st.code(final_report if final_report else "空报告")

        if final_report:
            decision_info = parse_decision(final_report)

            # 显示关键指标卡片
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown(
                    f"""
                <div class="metric-card">
                    <h4>Direction</h4>
                    <p class="{get_decision_color(decision_info["direction"])}">{decision_info["direction"]}</p>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            with col2:
                st.markdown(
                    f"""
                <div class="metric-card">
                    <h4>Timeframe</h4>
                    <p style="font-size: 1.2rem; font-weight: bold;">{decision_info["timeframe"]}</p>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            with col3:
                # 下载按钮列
                # TXT报告下载
                report_text = f"""Ticker: {ticker}
Analysis Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

{"=" * 60}
Final Investment Decision Report
{"=" * 60}

{final_report}

{"=" * 60}
"""
                st.download_button(
                    label="📥 TXT Report",
                    data=report_text,
                    file_name=f"{ticker}_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

                # PDF报告下载
                if st.button("📄 PDF Report", use_container_width=True):
                    try:
                        from utils.pdf_generator import generate_pdf_report

                        with st.spinner("Generating PDF Report..."):
                            pdf_path = generate_pdf_report(result, ticker)

                            # 读取PDF文件
                            with open(pdf_path, "rb") as f:
                                pdf_data = f.read()

                            # 提供下载
                            st.download_button(
                                label="⬇️ Download PDF",
                                data=pdf_data,
                                file_name=f"{ticker}_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                            )

                            st.success("✅ PDF Report Generated Successfully!")
                    except Exception as e:
                        st.error(f"❌ PDF Generation Failed: {str(e)}")
                        st.info(
                            "💡 Tip: PDF 导出依赖 fpdf2 与可用的中文字体；如环境异常，请先执行 uv sync，并确认系统已安装中文字体。"
                        )

            # 一句话结论
            st.markdown(
                f"""
            <div class="report-box">
                <h3>💡 One-Line Conclusion</h3>
                <p style="font-size: 1.1rem; line-height: 1.6;">{decision_info["summary"]}</p>
            </div>
            """,
                unsafe_allow_html=True,
            )

            # 完整报告
            st.subheader("📄 Complete Investment Decision Report")
            st.markdown(
                f'<div class="report-box">{final_report.replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )

        # 详细报告（可折叠）
        if show_details:
            st.divider()

            with st.expander("📊 Market Analysis Report (Technical)", expanded=False):
                market_report = result.get("market_report", "暂无数据")
                st.markdown(market_report)

            with st.expander("📰 News Analysis Report (Sentiment)", expanded=False):
                news_report = result.get("news_report", "no news data")
                st.markdown(news_report)

            with st.expander(
                "💼 Fundamental Analysis Report (Financial)", expanded=False
            ):
                fundamental_report = result.get(
                    "fundamental_report", "no fundamental data"
                )
                st.markdown(fundamental_report)

            with st.expander("⚖️ Risk Analysis Report", expanded=False):
                risk_report = result.get("risk_report", "no risk data")
                st.markdown(risk_report)

        # 新闻来源展示
        news_sources = result.get("news_sources", [])
        if news_sources:
            st.divider()
            with st.expander(
                f"📰 Reference News Sources ({len(news_sources)} items)", expanded=False
            ):
                for idx, news in enumerate(news_sources, 1):
                    with st.container():
                        st.markdown(f"**{idx}. {news.get('title', '无标题')}**")

                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.caption(
                                f"📍 Source: {news.get('source', 'Unknown')} | 🕐 {news.get('published_at', '')[:10]}"
                            )
                        with col2:
                            url = news.get("url", "")
                            if url:
                                st.link_button(
                                    "🔗 View Original", url, use_container_width=True
                                )

                        if idx < len(news_sources):
                            st.markdown("---")

    # 历史记录面板
    if st.session_state.analysis_history:
        st.divider()
        with st.expander(
            f"📜 Analysis History ({len(st.session_state.analysis_history)} items)",
            expanded=False,
        ):
            # 添加导出按钮
            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("🗑️ Clear History"):
                    st.session_state.analysis_history = []
                    st.rerun()

            # 显示历史记录
            for idx, entry in enumerate(reversed(st.session_state.analysis_history)):
                with st.container():
                    col1, col2, col3 = st.columns([2, 2, 1])

                    with col1:
                        st.text(f"📊 {entry['ticker']}")

                    with col2:
                        st.text(f"🕐 {entry['timestamp']}")

                    with col3:
                        mode_badge = (
                            "🔄 Backtest"
                            if entry["mode"] == "Backtest Mode"
                            else "📈 Real-time"
                        )
                        st.text(mode_badge)

                    # 显示简要结果
                    result = entry.get("result", {})
                    pm_report = result.get("PM_report", "")
                    if pm_report:
                        decision_info = parse_decision(pm_report)
                        st.caption(
                            f"Direction: {decision_info['direction']} | Timeframe: {decision_info['timeframe']}"
                        )

                    if idx < len(st.session_state.analysis_history) - 1:
                        st.markdown("---")

            # 导出为CSV
            if st.session_state.analysis_history:
                # 准备CSV数据
                csv_data = []
                for entry in st.session_state.analysis_history:
                    result = entry.get("result", {})
                    pm_report = result.get("PM_report", "")
                    decision_info = parse_decision(pm_report) if pm_report else {}

                    csv_data.append(
                        {
                            "股票代码": entry["ticker"],
                            "时间": entry["timestamp"],
                            "模式": entry["mode"],
                            "方向": decision_info.get("direction", "Unknown"),
                            "时间范围": decision_info.get("timeframe", "Unknown"),
                            "结论": decision_info.get("summary", "Unknown"),
                        }
                    )

                df_history = pd.DataFrame(csv_data)
                csv = df_history.to_csv(index=False, encoding="utf-8-sig")

                st.download_button(
                    label="📥 Export History (CSV)",
                    data=csv,
                    file_name=f"analysis_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    # 页脚
    st.divider()
    st.caption(
        "⚠️ Disclaimer: The analysis provided by this system is for reference only and does not constitute investment advice. Investing involves risks, and decisions should be made with caution."
    )


if __name__ == "__main__":
    main()
