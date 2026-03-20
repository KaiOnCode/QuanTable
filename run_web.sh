#!/bin/bash
# IntelliFin Assistant Web 界面启动脚本

echo "🚀 启动 IntelliFin Assistant Web 界面..."
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "❌ 未找到虚拟环境，正在创建..."
    python3 -m venv venv
    echo "✅ 虚拟环境创建完成"
    echo ""
    echo "📦 安装依赖..."
    ./venv/bin/pip install -r requirements.txt
    ./venv/bin/pip install streamlit plotly
    echo "✅ 依赖安装完成"
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
./venv/bin/streamlit run streamlit_app.py

