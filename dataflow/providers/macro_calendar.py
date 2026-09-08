# dataflow/providers/macro_calendar.py
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Finnhub API configuration
BASE_URL = "https://finnhub.io/api/v1"


def _get_api_key() -> Optional[str]:
    """Safely retrieve Finnhub API key from environment."""
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        logger.error("[macro_calendar] FINNHUB_API_KEY not set in environment.")
        return None
    return api_key


def _transform_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Transform Finnhub event format to agent_design v1.0 spec format.
    """
    try:
        # Spec requires: {"type": "CPI_CORE_YOY", "actual": 3.6, "consensus": 3.8, ...}

        # Finnhub fields (example):
        # {'actual': 5.25, 'estimate': 5.25, 'event': 'FOMC Rate Decision', 'unit': '%', 'time': '2025-11-04 18:00:00'}

        event_name = event.get("event", "UNKNOWN")

        # Extract type code from event name
        # TODO: replace with a more robust mapping
        type_code = "UNKNOWN"
        if "cpi" in event_name.lower():
            type_code = "CPI_CORE_YOY"
        elif "fomc" in event_name.lower():
            type_code = "FOMC_DECISION"
        elif "unemployment" in event_name.lower():
            type_code = "UNEMPLOYMENT_RATE"

        # Convert "YYYY-MM-DD HH:MM:SS" to ISO Z-format "YYYY-MM-DDTHH:MM:SSZ"
        event_time_str = event.get("time", datetime.utcnow().isoformat())
        try:
            event_dt = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M:%S")
            iso_time = event_dt.isoformat() + "Z"
        except ValueError:
            iso_time = datetime.utcnow().isoformat() + "Z"  # fallback

        return {
            "type": type_code,
            "actual": event.get("actual"),
            "consensus": event.get("estimate"),  # Finnhub uses 'estimate'
            "unit": event.get("unit"),
            "time": iso_time,
        }
    except Exception as e:
        logger.warning(f"[macro_calendar] Error transforming event: {e}. Event: {event}")
        return None


def df_get_macro_calendar(window_days: int = 7) -> List[Dict]:
    """
    Fetch macroeconomic calendar from Finnhub.
    Matches agent_design v1.0 spec.
    """
    api_key = _get_api_key()
    if not api_key:
        return []

    # Calculate date range: today through today + window_days
    today = datetime.utcnow().date()
    end_date = today + timedelta(days=window_days)

    params = {"token": api_key, "from": today.isoformat(), "to": end_date.isoformat()}

    try:
        response = requests.get(
            f"{BASE_URL}/economic-calendar", params=params, timeout=10
        )
        response.raise_for_status()

        data = response.json()
        raw_events = data.get("economicCalendar", [])

        if not raw_events:
            logger.info("[macro_calendar] API returned no macro events.")
            return []

        # Transform to spec format
        transformed_events = []
        for event in raw_events:
            transformed = _transform_event(event)
            if transformed:
                transformed_events.append(transformed)

        return transformed_events

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"[macro_calendar] HTTP error: {http_err} - {response.text}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"[macro_calendar] Request error: {req_err}")
    except Exception as e:
        logger.error(f"[macro_calendar] Unexpected error: {e}")

    return []
