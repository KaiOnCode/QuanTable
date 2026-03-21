#!/usr/bin/env python3
"""
IntelliFin Assistant - CLI 入口
股票分析多智能体系统的命令行界面
"""

import argparse
import os
import sys

import pandas as pd

from agentgraph.orchestrator import IntelliFin_Assistant


def main():
    parser = argparse.ArgumentParser(
        description="IntelliFin Assistant - 基于多智能体的股票分析系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python app.py AAPL              # 分析苹果公司股票
  python app.py TSLA --visualize  # 分析特斯拉并生成工作流可视化图
  python app.py NVDA --output report.txt  # 分析英伟达并保存报告到文件
        """,
    )

    parser.add_argument(
        "ticker", type=str, help="股票代码（如 AAPL, TSLA, NVDA, MSFT 等）"
    )

    parser.add_argument(
        "--visualize",
        "-v",
        action="store_true",
        help="生成工作流可视化图（保存为 graph.png）",
    )

    parser.add_argument(
        "--output", "-o", type=str, metavar="FILE", help="将分析报告保存到指定文件"
    )

    parser.add_argument("--verbose", action="store_true", help="显示详细的分析过程")

    args = parser.parse_args()

    # 检查配置文件
    if not os.path.exists("properties.env"):
        print("❌ 错误: 未找到配置文件 properties.env")
        print("请创建 properties.env 文件并配置 OPENAI_API_KEY")
        print("参考 .env.example 文件")
        sys.exit(1)

    # 检查 API Key
    from dotenv import load_dotenv

    load_dotenv("properties.env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        print("❌ 错误: 请在 properties.env 中配置有效的 OPENAI_API_KEY")
        sys.exit(1)

    print("🚀 IntelliFin Assistant 启动中...")
    print(f"📊 分析股票: {args.ticker.upper()}")
    print("-" * 60)

    try:
        # 创建智能体
        agent = IntelliFin_Assistant()

        # 运行分析
        if args.verbose:
            print("📈 正在并行执行市场分析、新闻分析、基本面分析...")

        result = agent.run(args.ticker.upper())

        # 获取最终报告
        final_report = result.get("PM_report", "")

        if not final_report:
            print("⚠️  警告: 未能生成完整的分析报告")
            sys.exit(1)

        # 输出报告
        print("\n" + "=" * 60)
        print("📋 最终投资决策报告")
        print("=" * 60)
        print(final_report)
        print("=" * 60)

        # 保存到文件
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(f"股票代码: {args.ticker.upper()}\n")
                f.write("=" * 60 + "\n\n")
                f.write(final_report)
                f.write("\n\n" + "=" * 60 + "\n")
                f.write("报告生成时间: " + str(pd.Timestamp.now()) + "\n")
            print(f"\n✅ 报告已保存到: {args.output}")

        # 生成可视化
        if args.visualize:
            agent.visualize()
            print("\n✅ 工作流可视化图已保存到: graph.png")

        print("\n✨ 分析完成！")

    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断分析")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
