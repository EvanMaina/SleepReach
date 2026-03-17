"""
CallRail Integration API — READ-ONLY Call Analytics Proxy

Proxies requests to CallRail API so the API key is never exposed to the frontend.
All endpoints filter by company_id and support date range filtering.

Endpoints:
- GET /api/callrail/calls       — List calls with filtering/pagination
- GET /api/callrail/summary     — Aggregated metrics for metric cards
- GET /api/callrail/timeseries  — Call volume over time
- GET /api/callrail/sources     — Unique list of call sources

@module api/callrail
@version 1.0.0
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from ..core.config import settings
from ..services.cache import get_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/callrail", tags=["CallRail Analytics"])

# =============================================================================
# Constants
# =============================================================================

CALLRAIL_BASE_URL = f"https://api.callrail.com/v3/a/{settings.callrail_account_id}"
CALLRAIL_HEADERS = {
    "Authorization": f"Token token={settings.callrail_api_key}",
    "Content-Type": "application/json",
}
CACHE_TTL = 180  # 3 minutes cache


# =============================================================================
# Helper: Make CallRail API request
# =============================================================================

async def _callrail_request(endpoint: str, params: dict = None) -> dict:
    """
    Make an authenticated request to the CallRail API.
    
    Args:
        endpoint: API endpoint path (e.g., /calls.json)
        params: Query parameters
        
    Returns:
        JSON response dict
        
    Raises:
        HTTPException on API errors
    """
    if not settings.callrail_api_key or not settings.callrail_account_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CallRail is not configured. Set CALLRAIL_API_KEY and CALLRAIL_ACCOUNT_ID."
        )

    url = f"{CALLRAIL_BASE_URL}{endpoint}"

    # Always filter by company
    if params is None:
        params = {}
    params["company_id"] = settings.callrail_company_id

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=CALLRAIL_HEADERS, params=params)

        if response.status_code == 401:
            logger.error("CallRail API authentication failed")
            raise HTTPException(status_code=502, detail="CallRail authentication failed")

        if response.status_code == 429:
            logger.warning("CallRail API rate limited")
            raise HTTPException(status_code=429, detail="CallRail rate limit reached. Try again shortly.")

        if response.status_code != 200:
            logger.error(f"CallRail API error {response.status_code}: {response.text[:200]}")
            raise HTTPException(
                status_code=502,
                detail=f"CallRail API returned status {response.status_code}"
            )

        return response.json()

    except httpx.TimeoutException:
        logger.error("CallRail API request timed out")
        raise HTTPException(status_code=504, detail="CallRail API request timed out")
    except httpx.RequestError as e:
        logger.error(f"CallRail API connection error: {e}")
        raise HTTPException(status_code=502, detail="Failed to connect to CallRail API")


def _get_date_range(date_range: str, start_date: Optional[str], end_date: Optional[str]):
    """
    Parse date range parameter into start/end date strings.
    
    Returns:
        Tuple of (start_date_str, end_date_str) in YYYY-MM-DD format
    """
    now = datetime.utcnow()
    
    if date_range == "custom" and start_date and end_date:
        return start_date, end_date
    elif date_range == "today":
        d = now.strftime("%Y-%m-%d")
        return d, d
    elif date_range == "7days":
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        return start, now.strftime("%Y-%m-%d")
    elif date_range == "30days":
        start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        return start, now.strftime("%Y-%m-%d")
    elif date_range == "90days":
        start = (now - timedelta(days=90)).strftime("%Y-%m-%d")
        return start, now.strftime("%Y-%m-%d")
    else:
        # Default: last 30 days
        start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        return start, now.strftime("%Y-%m-%d")


def _previous_period(start_str: str, end_str: str):
    """Calculate the previous period of equal length for comparison."""
    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")
    delta = end - start
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - delta
    return prev_start.strftime("%Y-%m-%d"), prev_end.strftime("%Y-%m-%d")


def _normalize_call(call: dict) -> dict:
    """Normalize CallRail API field names to our frontend expected format."""
    return {
        "id": call.get("id"),
        "caller_name": call.get("customer_name"),
        "caller_number": call.get("customer_phone_number"),
        "city": call.get("customer_city"),
        "state": call.get("customer_state"),
        "duration": call.get("duration"),
        "answered": call.get("answered", False),
        "source_name": call.get("source_name"),
        "source": call.get("source"),
        "campaign": call.get("keywords") or call.get("medium") or None,
        "start_time": call.get("start_time"),
        "recording": call.get("recording"),
        "first_call": call.get("first_call", False),
        "voicemail": call.get("voicemail", False),
        "status": None,
        "direction": call.get("direction"),
        "tracking_phone_number": call.get("tracking_phone_number"),
    }


async def _fetch_all_calls(start_date: str, end_date: str, per_page: int = 250) -> list:
    """Fetch ALL calls for a date range, handling pagination."""
    all_calls = []
    page = 1

    while True:
        data = await _callrail_request("/calls.json", {
            "start_date": f"{start_date}T00:00:00Z",
            "end_date": f"{end_date}T23:59:59Z",
            "per_page": per_page,
            "page": page,
            "fields": "customer_name,customer_phone_number,customer_city,customer_state,duration,answered,source_name,start_time,recording,first_call,voicemail,direction,tracking_phone_number,source,medium,keywords,value"
        })

        calls = data.get("calls", [])
        all_calls.extend(calls)

        total_pages = data.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1

    return all_calls


# =============================================================================
# GET /api/callrail/calls — List calls with pagination and filters
# =============================================================================

@router.get("/calls")
async def get_calls(
    date_range: str = Query("30days", description="today|7days|30days|90days|custom"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (for custom range)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (for custom range)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status", description="answered|missed|voicemail"),
    source: Optional[str] = Query(None, description="Filter by source name"),
    search: Optional[str] = Query(None, description="Search by caller name or number"),
    sort_by: Optional[str] = Query(None, description="start_time|duration|status"),
    sort_dir: Optional[str] = Query("desc", description="asc|desc"),
):
    """
    Get paginated list of calls with filtering.
    Proxies to CallRail /calls.json with our company filter.
    """
    sd, ed = _get_date_range(date_range, start_date, end_date)
    
    # Build cache key
    cache_key = f"callrail:calls:{sd}:{ed}:{page}:{per_page}:{status_filter}:{source}:{search}:{sort_by}:{sort_dir}"
    cache = get_cache()
    cached = cache.get(cache_key)
    if cached:
        return cached

    params = {
        "start_date": f"{sd}T00:00:00Z",
        "end_date": f"{ed}T23:59:59Z",
        "per_page": per_page,
        "page": page,
        "fields": "customer_name,customer_phone_number,customer_city,customer_state,duration,answered,source_name,start_time,recording,first_call,voicemail,direction,tracking_phone_number,source,medium,keywords,value",
    }

    if status_filter:
        if status_filter == "answered":
            params["answered"] = "true"
        elif status_filter == "missed":
            params["answered"] = "false"

    if source:
        params["source"] = source

    if search:
        params["search"] = search

    if sort_by:
        sort_prefix = "-" if sort_dir == "desc" else ""
        params["sort"] = f"{sort_prefix}{sort_by}"

    data = await _callrail_request("/calls.json", params)

    result = {
        "calls": [_normalize_call(c) for c in data.get("calls", [])],
        "page": data.get("page", page),
        "per_page": data.get("per_page", per_page),
        "total_pages": data.get("total_pages", 1),
        "total_records": data.get("total_records", 0),
    }

    cache.set(cache_key, result, ttl=CACHE_TTL)
    return result


# =============================================================================
# GET /api/callrail/summary — Aggregated metrics for the metric cards
# =============================================================================

@router.get("/summary")
async def get_summary(
    date_range: str = Query("30days"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """
    Get aggregated summary metrics: total calls, answered rate,
    avg duration, first-time callers, missed calls.
    Includes comparison with previous period.
    """
    sd, ed = _get_date_range(date_range, start_date, end_date)

    cache_key = f"callrail:summary:{sd}:{ed}"
    cache = get_cache()
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Fetch ALL calls for current period
    current_calls = await _fetch_all_calls(sd, ed)

    # Fetch previous period for comparison
    prev_sd, prev_ed = _previous_period(sd, ed)
    prev_calls = await _fetch_all_calls(prev_sd, prev_ed)

    def compute_metrics(calls: list) -> dict:
        total = len(calls)
        answered = sum(1 for c in calls if c.get("answered"))
        missed = sum(1 for c in calls if not c.get("answered"))
        first_time = sum(1 for c in calls if c.get("first_call"))
        voicemail = sum(1 for c in calls if c.get("voicemail"))
        
        durations = [c.get("duration", 0) or 0 for c in calls if c.get("answered")]
        avg_duration = sum(durations) / len(durations) if durations else 0
        answered_rate = (answered / total * 100) if total > 0 else 0

        return {
            "total_calls": total,
            "answered": answered,
            "missed": missed,
            "first_time_callers": first_time,
            "voicemail": voicemail,
            "avg_duration_seconds": round(avg_duration),
            "answered_rate": round(answered_rate, 1),
        }

    current = compute_metrics(current_calls)
    previous = compute_metrics(prev_calls)

    def pct_change(curr_val, prev_val):
        if prev_val == 0:
            return 100.0 if curr_val > 0 else 0.0
        return round(((curr_val - prev_val) / prev_val) * 100, 1)

    result = {
        "current": current,
        "previous": previous,
        "changes": {
            "total_calls": pct_change(current["total_calls"], previous["total_calls"]),
            "answered_rate": round(current["answered_rate"] - previous["answered_rate"], 1),
            "avg_duration": pct_change(current["avg_duration_seconds"], previous["avg_duration_seconds"]),
            "first_time_callers": pct_change(current["first_time_callers"], previous["first_time_callers"]),
            "missed": pct_change(current["missed"], previous["missed"]),
        },
        "date_range": {"start": sd, "end": ed},
        "previous_range": {"start": prev_sd, "end": prev_ed},
    }

    cache.set(cache_key, result, ttl=CACHE_TTL)
    return result


# =============================================================================
# GET /api/callrail/timeseries — Call volume over time
# =============================================================================

@router.get("/timeseries")
async def get_timeseries(
    date_range: str = Query("30days"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """
    Get call volume time series for charts.
    Returns daily call counts grouped by date.
    """
    sd, ed = _get_date_range(date_range, start_date, end_date)

    cache_key = f"callrail:timeseries:{sd}:{ed}"
    cache = get_cache()
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Fetch all calls and aggregate by day
    calls = await _fetch_all_calls(sd, ed)

    # Group by date
    daily = {}
    start_dt = datetime.strptime(sd, "%Y-%m-%d")
    end_dt = datetime.strptime(ed, "%Y-%m-%d")

    # Initialize all dates
    current_dt = start_dt
    while current_dt <= end_dt:
        d = current_dt.strftime("%Y-%m-%d")
        daily[d] = {"date": d, "total": 0, "answered": 0, "missed": 0, "first_time": 0}
        current_dt += timedelta(days=1)

    for call in calls:
        st = call.get("start_time", "")
        if st:
            try:
                # Parse ISO format
                call_date = st[:10]  # Get YYYY-MM-DD part
                if call_date in daily:
                    daily[call_date]["total"] += 1
                    if call.get("answered"):
                        daily[call_date]["answered"] += 1
                    else:
                        daily[call_date]["missed"] += 1
                    if call.get("first_call"):
                        daily[call_date]["first_time"] += 1
            except (ValueError, IndexError):
                pass

    result = {
        "data": sorted(daily.values(), key=lambda x: x["date"]),
        "date_range": {"start": sd, "end": ed},
    }

    cache.set(cache_key, result, ttl=CACHE_TTL)
    return result


# =============================================================================
# GET /api/callrail/sources — Unique list of sources for filter dropdowns
# =============================================================================

@router.get("/sources")
async def get_sources(
    date_range: str = Query("90days"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """
    Get unique list of call sources from CallRail data.
    Used to populate filter dropdowns.
    """
    sd, ed = _get_date_range(date_range, start_date, end_date)

    cache_key = f"callrail:sources:{sd}:{ed}"
    cache = get_cache()
    cached = cache.get(cache_key)
    if cached:
        return cached

    calls = await _fetch_all_calls(sd, ed)

    sources = {}
    for call in calls:
        source = call.get("source_name") or call.get("source") or "Unknown"
        if source not in sources:
            sources[source] = 0
        sources[source] += 1

    result = {
        "sources": [
            {"name": name, "count": count}
            for name, count in sorted(sources.items(), key=lambda x: -x[1])
        ]
    }

    cache.set(cache_key, result, ttl=CACHE_TTL)
    return result


# =============================================================================
# GET /api/callrail/attribution — Full attribution data for charts
# =============================================================================

@router.get("/attribution")
async def get_attribution(
    date_range: str = Query("30days"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """
    Get full attribution data for the Attribution Reports tab.
    Includes source breakdown, caller type, campaign breakdown, geographic distribution.
    """
    sd, ed = _get_date_range(date_range, start_date, end_date)

    cache_key = f"callrail:attribution:{sd}:{ed}"
    cache = get_cache()
    cached = cache.get(cache_key)
    if cached:
        return cached

    calls = await _fetch_all_calls(sd, ed)

    # Source breakdown
    sources = {}
    for call in calls:
        source = call.get("source_name") or call.get("source") or "Unknown"
        if source not in sources:
            sources[source] = 0
        sources[source] += 1

    source_breakdown = [
        {"name": name, "value": count}
        for name, count in sorted(sources.items(), key=lambda x: -x[1])
    ]

    # Caller type (first-time vs repeat)
    first_time = sum(1 for c in calls if c.get("first_call"))
    repeat = len(calls) - first_time
    caller_type = [
        {"name": "First-Time Callers", "value": first_time},
        {"name": "Repeat Callers", "value": repeat},
    ]

    # Campaign breakdown (raw CallRail uses keywords/medium, not "campaign")
    campaigns = {}
    for call in calls:
        campaign = call.get("keywords") or call.get("medium") or "No Campaign"
        if campaign not in campaigns:
            campaigns[campaign] = {"total": 0, "answered": 0}
        campaigns[campaign]["total"] += 1
        if call.get("answered"):
            campaigns[campaign]["answered"] += 1

    campaign_breakdown = [
        {"name": name, "total": data["total"], "answered": data["answered"]}
        for name, data in sorted(campaigns.items(), key=lambda x: -x[1]["total"])
    ]

    # Geographic distribution (raw CallRail uses customer_state, not "state")
    geo = {}
    for call in calls:
        state = call.get("customer_state") or "Unknown"
        if state and state != "Unknown":
            if state not in geo:
                geo[state] = 0
            geo[state] += 1

    geo_breakdown = [
        {"name": name, "value": count}
        for name, count in sorted(geo.items(), key=lambda x: -x[1])
    ][:15]  # Top 15 states

    result = {
        "source_breakdown": source_breakdown,
        "caller_type": caller_type,
        "campaign_breakdown": campaign_breakdown,
        "geo_breakdown": geo_breakdown,
        "total_calls": len(calls),
        "date_range": {"start": sd, "end": ed},
    }

    cache.set(cache_key, result, ttl=CACHE_TTL)
    return result
