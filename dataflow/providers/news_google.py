# dataflow/providers/news_google.py
import logging
import random
import re
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


# --- Date parsing helpers ---
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
        logger.warning(f"Cannot parse date string: '{date_str}'. Falling back to now. Error: {e}")
        dt = now
    return dt.isoformat() + "Z"


# --- Helper functions ---
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
    # Raise on non-200 to trigger retry
    response.raise_for_status()
    return response


# --- Core functions ---
def get_company_news(
    ticker_or_query: str,
    days: int = 7,
    lang: str = "en",
    # Accept optional end_date parameter (ISO format string)
    end_date: Optional[str] = None,
) -> List[Dict]:
    query = urllib.parse.quote_plus(f"{ticker_or_query} stock")

    # Parse end_date
    end_date_dt: datetime
    if end_date:
        try:
            end_date_dt = datetime.fromisoformat(end_date.rstrip("Z"))
        except ValueError:
            logger.warning(f"Cannot parse news end_date: {end_date}. Falling back to now.")
            end_date_dt = datetime.now()
    else:
        end_date_dt = datetime.now()

    start_date_dt = end_date_dt - timedelta(days=days)

    # Google search uses "MM/DD/YYYY" format
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
    MAX_PAGES = 3  # Limit to 3 pages to avoid excessive requests

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
                logger.error("Google blocked the request (CAPTCHA). Stopping scrape.")
                break

            results_on_page = soup.select("div.n0jPhd, div.SoaBEf")

            if not results_on_page:
                logger.warning("No news entries found on page.")
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
                    logger.warning(f"Error processing single result entry: {e}", exc_info=False)
                    continue

            next_link = soup.find("a", id="pnnext")
            if not next_link:
                logger.info("No 'next page' link found.")
                break
            page += 1

        except requests.exceptions.HTTPError as e:
            logger.error(
                f"HTTP error: {e.response.status_code}. Google may have blocked. Stopping scrape."
            )
            break
        except Exception as e:
            logger.error(f"Unexpected error during scrape: {e}", exc_info=True)
            break

    logger.info(
        f"Scrape complete. Found {len(news_results)} articles (query: {ticker_or_query})"
    )
    return news_results
