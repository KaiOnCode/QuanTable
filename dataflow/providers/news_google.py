# dataflow/providers/news_google.py
import re
import time
import random
import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_result,
)

# 使用标准日志记录模块作为备用
logger = logging.getLogger(__name__)


# --- 日期解析辅助函数 ---
def parse_relative_date_to_iso(date_str: str) -> str:
    now = datetime.now()
    dt = now
    try:
        num_match = re.search(r"\d+", date_str)
        if not num_match:
            if "天前" in date_str or "day" in date_str:
                dt = now - timedelta(days=1)
            elif "小时前" in date_str or "hour" in date_str:
                dt = now - timedelta(hours=1)
        else:
            num = int(num_match.group(0))
            if "分钟前" in date_str or "minute" in date_str:
                dt = now - timedelta(minutes=num)
            elif "小时前" in date_str or "hour" in date_str:
                dt = now - timedelta(hours=num)
            elif "天前" in date_str or "day" in date_str:
                dt = now - timedelta(days=num)
            elif "周前" in date_str or "week" in date_str:
                dt = now - timedelta(weeks=num)
            else:
                try:
                    dt = datetime.strptime(date_str, "%b %d, %Y")
                except ValueError:
                    dt = now
    except Exception as e:
        logger.warning(f"无法解析日期字符串: '{date_str}'. 回退到当前时间. 错误: {e}")
        dt = now
    return dt.isoformat() + "Z"


# --- 辅助函数 ---
def is_rate_limited(response):
    return response.status_code == 429


@retry(
    retry=(
        retry_if_result(is_rate_limited)
        | retry_if_exception_type(requests.exceptions.ConnectionError)
        | retry_if_exception_type(requests.exceptions.Timeout)
    ),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
)
def make_request(url, headers):
    time.sleep(random.uniform(2, 6))
    response = requests.get(url, headers=headers, timeout=(10, 30))
    # 检查状态码，如果不是200，也抛出异常以触发重试
    response.raise_for_status()
    return response


# --- 核心功能函数 (最终版) ---
def get_company_news(
    ticker_or_query: str,
    days: int = 7,
    lang: str = "en",
    # 更改：添加可选的 end_date 参数 (ISO 格式字符串)
    end_date: Optional[str] = None,
) -> List[Dict]:
    query = urllib.parse.quote_plus(f"{ticker_or_query} stock")

    # 更改：解析 end_date
    end_date_dt: datetime
    if end_date:
        try:
            end_date_dt = datetime.fromisoformat(end_date.rstrip("Z"))
        except ValueError:
            logger.warning(f"无法解析 news end_date: {end_date}. 回退到当前时间。")
            end_date_dt = datetime.now()
    else:
        end_date_dt = datetime.now()

    start_date_dt = end_date_dt - timedelta(days=days)

    # 谷歌搜索使用 "MM/DD/YYYY" 格式
    start_date_str = start_date_dt.strftime("%m/%d/%Y")
    end_date_str = end_date_dt.strftime("%m/%d/%Y")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    }

    hl = "en-US" if lang == "en" else "zh-CN"
    gl = "US" if lang == "en" else "CN"

    news_results = []
    page = 0
    MAX_PAGES = 3  # 限制最多抓取3页，防止过多请求

    while page < MAX_PAGES:
        offset = page * 10
        url = (
            f"https://www.google.com/search?q={query}"
            f"&tbs=cdr:1,cd_min:{start_date_str},cd_max:{end_date_str}"
            f"&tbm=nws&start={offset}"
            f"&hl={hl}&gl={gl}"
        )

        try:
            logger.info(
                f"Scraping Google News page {page + 1} for query: {ticker_or_query} (lang={lang})"
            )
            response = make_request(url, headers)

            soup = BeautifulSoup(response.content, "html.parser")

            if (
                "Our systems have detected unusual traffic" in response.text
                or "Before you continue" in response.text
            ):
                logger.error("!!! Google 拦截了请求 (CAPTCHA) !!! 停止抓取。")
                break

            results_on_page = soup.select("div.n0jPhd, div.SoaBEf")  # 合并主要的选择器

            if not results_on_page:
                logger.warning("在页面上找不到任何新闻条目。")
                break

            for el in results_on_page:
                try:
                    link_el = el.find("a", href=True)
                    if not link_el:
                        continue
                    link_href = link_el["href"]

                    title_el = el.select_one("div.MBeuO, div.mCBkyc")
                    if not title_el:
                        continue
                    title_text = title_el.get_text()

                    snippet_el = el.select_one(".GI74Re, .s3v9rd")
                    snippet_text = snippet_el.get_text() if snippet_el else ""

                    date_el = el.select_one(".LfVVr, .S1FAPd")
                    date_text_str = date_el.get_text() if date_el else "now"

                    source_el = el.select_one(".NUnG9d span, .wEwyrc")
                    source_text = source_el.get_text() if source_el else "Unknown"

                    iso_timestamp = parse_relative_date_to_iso(date_text_str)

                    news_results.append(
                        {
                            "url": link_href,
                            "title": title_text,
                            "summary": snippet_text,
                            "published_at": iso_timestamp,
                            "source": source_text,
                        }
                    )
                except Exception as e:
                    logger.warning(f"处理单个结果条目时出错: {e}", exc_info=False)
                    continue

            next_link = soup.find("a", id="pnnext")
            if not next_link:
                logger.info("找不到 '下一页' 链接。")
                break
            page += 1

        except requests.exceptions.HTTPError as e:
            logger.error(
                f"HTTP 错误: {e.response.status_code}. Google 可能已屏蔽。停止抓取。"
            )
            break
        except Exception as e:
            logger.error(f"抓取期间发生意外错误: {e}", exc_info=True)
            break

    logger.info(
        f"抓取完成。共找到 {len(news_results)} 条新闻 (查询: {ticker_or_query})"
    )
    return news_results
