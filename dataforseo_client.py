"""
dataforseo_client.py

Thin wrapper around two DataForSEO APIs:

1. SERP API (Google Organic, Live Advanced) - one call returns:
   - Top organic results
   - People Also Ask (PAA) questions
   - Related searches (used here as "secondary keywords")

2. DataForSEO Labs API (Keyword Overview) - returns, per keyword:
   - Search volume
   - CPC
   - Competition level
   - Keyword difficulty
   - Search intent
   - Monthly search volume history (used to render a trend chart)

Credentials are read from environment variables (see .env.example) and are
never hardcoded.
"""

import os
import requests

DATAFORSEO_BASE_URL = "https://api.dataforseo.com/v3"
ORGANIC_LIVE_ENDPOINT = f"{DATAFORSEO_BASE_URL}/serp/google/organic/live/advanced"
KEYWORD_OVERVIEW_ENDPOINT = f"{DATAFORSEO_BASE_URL}/dataforseo_labs/google/keyword_overview/live"


class DataForSEOError(Exception):
    """Raised when the DataForSEO API returns an error or unexpected payload."""


def _get_credentials():
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise DataForSEOError(
            "Missing DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD. "
            "Add them to your .env file (see .env.example)."
        )
    return login, password


def _post(endpoint: str, payload: list):
    login, password = _get_credentials()
    try:
        response = requests.post(endpoint, json=payload, auth=(login, password), timeout=60)
    except requests.RequestException as exc:
        raise DataForSEOError(f"Could not reach DataForSEO API: {exc}") from exc

    if response.status_code != 200:
        raise DataForSEOError(
            f"DataForSEO API returned HTTP {response.status_code}: {response.text[:500]}"
        )

    data = response.json()

    if data.get("status_code") != 20000:
        raise DataForSEOError(
            f"DataForSEO API error: {data.get('status_message', 'Unknown error')}"
        )

    tasks = data.get("tasks") or []
    if not tasks:
        raise DataForSEOError("DataForSEO API returned no tasks.")

    task = tasks[0]
    if task.get("status_code") != 20000:
        raise DataForSEOError(
            f"DataForSEO task error: {task.get('status_message', 'Unknown error')}"
        )

    return task.get("result") or []


def _dedupe_preserve_order(items):
    seen = set()
    result = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result


def _monthly_searches_to_dict(raw_monthly):
    """
    Converts DataForSEO's monthly_searches array (list of
    {"year": 2026, "month": 5, "search_volume": 165000}) into a
    {"2026-05": 165000, ...} dict, sorted chronologically.
    """
    monthly = {}
    for entry in raw_monthly or []:
        year = entry.get("year")
        month = entry.get("month")
        volume = entry.get("search_volume")
        if year is None or month is None:
            continue
        monthly[f"{year}-{int(month):02d}"] = volume
    return dict(sorted(monthly.items()))


def fetch_serp_data(keyword: str, location_code: int, language_code: str, depth: int = 20) -> dict:
    """
    Calls DataForSEO's Google Organic Live Advanced endpoint for a single keyword.

    Returns a dict with three keys:
      - "organic_results": list of {position, title, url, description} (position
        is the sequential rank 1-10, not the raw absolute SERP position, which
        can skip numbers due to ads/featured snippets/etc. in between)
      - "people_also_ask": list of question strings
      - "related_keywords": list of related search strings (deduplicated)
    """
    payload = [
        {
            "keyword": keyword,
            "location_code": location_code,
            "language_code": language_code,
            "device": "desktop",
            "os": "windows",
            "depth": depth,
        }
    ]

    results = _post(ORGANIC_LIVE_ENDPOINT, payload)
    if not results:
        return {"organic_results": [], "people_also_ask": [], "related_keywords": []}

    items = results[0].get("items") or []

    organic_results = []
    people_also_ask = []
    related_keywords = []

    for item in items:
        item_type = item.get("type")

        if item_type == "organic" and len(organic_results) < 10:
            organic_results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "description": item.get("description"),
                }
            )

        elif item_type == "people_also_ask":
            for paa_item in item.get("items") or []:
                question = paa_item.get("title")
                if question:
                    people_also_ask.append(question)

        elif item_type == "related_searches":
            for related in item.get("items") or []:
                # related_searches items can be plain strings or dicts
                if isinstance(related, str):
                    related_keywords.append(related)
                elif isinstance(related, dict) and related.get("title"):
                    related_keywords.append(related["title"])

    # Assign clean sequential ranks (1-10) instead of the raw SERP position.
    for position, result in enumerate(organic_results, start=1):
        result["position"] = position

    return {
        "organic_results": organic_results,
        "people_also_ask": _dedupe_preserve_order(people_also_ask),
        "related_keywords": _dedupe_preserve_order(related_keywords),
    }


def fetch_keyword_overview(keywords, location_name: str, language_code: str) -> dict:
    """
    Calls DataForSEO Labs' Keyword Overview endpoint for a batch of keywords.

    Note: this endpoint is called with `location_name` (e.g. "United States"),
    not `location_code` - that's the parameter DataForSEO Labs expects for
    this specific endpoint.

    Returns a dict keyed by lowercased keyword, each value a dict:
      {
        "search_volume": int or None,
        "cpc": float or None,
        "competition_level": str or None,
        "keyword_difficulty": int or None,
        "search_intent": str or None,
        "monthly_searches": {"YYYY-MM": int, ...},
        "search_volume_trend": {"monthly": pct, "quarterly": pct, "yearly": pct},
      }

    Keywords DataForSEO has no data for are simply omitted from the result.
    """
    clean_keywords = [k.strip() for k in keywords if k and k.strip()]
    if not clean_keywords:
        return {}

    # De-dupe while preserving order, and respect the API's keyword cap.
    seen = set()
    deduped = []
    for k in clean_keywords:
        key = k.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(k)
    deduped = deduped[:700]

    payload = [
        {
            "keywords": deduped,
            "location_name": location_name,
            "language_code": language_code,
        }
    ]

    results = _post(KEYWORD_OVERVIEW_ENDPOINT, payload)

    # The API nests the actual per-keyword objects one level deeper: each
    # entry in `results` is a wrapper ({se_type, items_count, items: [...]})
    # for the batch, not a keyword object itself.
    items = []
    for result in results:
        items.extend(result.get("items") or [])

    overview = {}
    for item in items:
        keyword = item.get("keyword")
        if not keyword:
            continue

        info = item.get("keyword_info") or {}
        props = item.get("keyword_properties") or {}
        intent = item.get("search_intent_info") or {}

        overview[keyword.lower()] = {
            "search_volume": info.get("search_volume"),
            "cpc": info.get("cpc"),
            "competition_level": info.get("competition_level"),
            "keyword_difficulty": props.get("keyword_difficulty"),
            "search_intent": intent.get("main_intent"),
            "monthly_searches": _monthly_searches_to_dict(info.get("monthly_searches")),
            "search_volume_trend": info.get("search_volume_trend") or {},
        }

    return overview
