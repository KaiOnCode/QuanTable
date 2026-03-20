# dataflow/providers/macro_calendar.py
import os
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging

# 使用标准日志记录
logger = logging.getLogger(__name__)

# 1. Finnhub API 配置
BASE_URL = "https://finnhub.io/api/v1"


def _get_api_key() -> Optional[str]:
    """安全地从环境变量获取 Finnhub API 密钥"""
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        logger.error("[macro_calendar] 环境变量 FINNHUB_API_KEY 未设置。")
        return None
    return api_key


def _transform_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    将 Finnhub 事件格式转换为 agent_design v1.0 规范格式
    """
    try:
        # 规范要求: {"type": "CPI_CORE_YOY", "actual": 3.6, "consensus": 3.8, ...}

        # Finnhub 字段 (示例):
        # {'actual': 5.25, 'estimate': 5.25, 'event': 'FOMC Rate Decision', 'unit': '%', 'time': '2025-11-04 18:00:00'}

        event_name = event.get('event', 'UNKNOWN')

        # 简化版：尝试从事件名称中提取代码
        # TODO: 替换为更健壮的映射逻辑
        type_code = "UNKNOWN"
        if 'cpi' in event_name.lower():
            type_code = "CPI_CORE_YOY"  # 示例
        elif 'fomc' in event_name.lower():
            type_code = "FOMC_DECISION"
        elif 'unemployment' in event_name.lower():
            type_code = "UNEMPLOYMENT_RATE"

        # 将 "YYYY-MM-DD HH:MM:SS" 转换为 ISO Z-format "YYYY-MM-DDTHH:MM:SSZ"
        event_time_str = event.get('time', datetime.utcnow().isoformat())
        try:
            event_dt = datetime.strptime(event_time_str, '%Y-%m-%d %H:%M:%S')
            iso_time = event_dt.isoformat() + "Z"
        except ValueError:
            iso_time = datetime.utcnow().isoformat() + "Z"  # 兜底

        return {
            "type": type_code,
            "actual": event.get('actual'),
            "consensus": event.get('estimate'),  # Finnhub 使用 'estimate'
            "unit": event.get('unit'),
            "time": iso_time
        }
    except Exception as e:
        logger.warning(f"[macro_calendar] 转换事件时出错: {e}. Event: {event}")
        return None


def df_get_macro_calendar(window_days: int = 7) -> List[Dict]:
    """
    从 Finnhub 获取宏观经济日历。
    匹配 agent_design v1.0 规范。
    """
    api_key = _get_api_key()
    if not api_key:
        return []

    # 1. 计算日期范围
    # 我们获取从今天到未来 window_days 的数据
    today = datetime.utcnow().date()
    end_date = today + timedelta(days=window_days)

    params = {
        "token": api_key,
        "from": today.isoformat(),
        "to": end_date.isoformat()
    }

    try:
        # 2. 发起 API 请求
        response = requests.get(
            f"{BASE_URL}/economic-calendar",
            params=params,
            timeout=10
        )
        response.raise_for_status()  # 如果状态码不是 2xx，则引发异常

        data = response.json()
        raw_events = data.get('economicCalendar', [])

        if not raw_events:
            logger.info("[macro_calendar] API 未返回任何宏观事件。")
            return []

        # 3. 转换数据格式
        transformed_events = []
        for event in raw_events:
            transformed = _transform_event(event)
            if transformed:
                transformed_events.append(transformed)

        return transformed_events

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"[macro_calendar] HTTP 错误: {http_err} - {response.text}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"[macro_calendar] 请求异常: {req_err}")
    except Exception as e:
        logger.error(f"[macro_calendar] 处理宏观日历时发生意外错误: {e}")

    return []