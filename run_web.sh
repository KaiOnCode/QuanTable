#!/bin/bash
# IntelliFin Assistant Web 界面启动脚本

echo "🚀 启动 IntelliFin Assistant Web 界面..."
echo ""

# 检查 uv
if ! command -v uv >/dev/null 2>&1; then
    echo "❌ 未检测到 uv，请先安装 uv 后再运行本脚本。"
    echo "安装说明: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# 首次初始化项目环境
if [ ! -d ".venv" ]; then
    echo "📦 未找到项目环境，正在初始化..."
    uv sync || exit 1
    echo "✅ 项目环境初始化完成"
    echo ""
fi

# 检查配置文件
if [ ! -f "properties.env" ]; then
    echo "❌ 未找到配置文件 properties.env"
    echo "请创建 properties.env 文件并配置 OPENAI_API_KEY"
    exit 1
fi

# 启动 Streamlit
echo "🌐 正在启动 Web 服务器..."
echo "浏览器将自动打开 http://localhost:8501"
echo ""
uv run streamlit run streamlit_app.py

