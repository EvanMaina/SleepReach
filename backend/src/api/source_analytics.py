"""
Source Analytics API

Provides analytics by lead source (Widget, Google Ads, Jotform, Referral)
Tracks performance metrics per platform for marketing attribution.

PLATFORMS SUPPORTED:
- Widget: Embedded website widget (direct traffic)
- Google Ads: Paid advertising campaigns
- Jotform: Form submissions from Jotform
- Referral: Referral links/programs

@module api/source_analytics
@version 2.0.0 - Added Referral platform + error handling + retry logic
"""

import time
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case, text
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..models.lead import Lead, PriorityType, LeadStatus, LeadSource
from ..services.cache import get_cache
from ..core.auth import get_current_user


logger = logging.getLogger(__name__)

# Require authentication on all source-analytics endpoints.
# Previously this router had NO auth, meaning these endpoints were publicly
# accessible — a security gap and a vector for unauthenticated DB hammering.
router = APIRouter(
    prefix="/api/analytics/sources",
    tags=["Source Analytics"],
    dependencies=[Depends(get_current_user)],
)


# =============================================================================
# PLATFORM CONFIGURATION - ALL 4 PLATFORMS
# =============================================================================

# Supported platforms - Widget, Google Ads, Jotform, Referral
ALLOWED_PLATFORMS = ["Widget", "Google Ads", "Jotform", "Referral"]

# Map UTM sources/mediums to platform names
SOURCE_MAPPING = {
    # Widget leads (embedded intake form) - DEFAULT for direct/unknown traffic
    "widget": "Widget",
    "intake_widget": "Widget",
    "embedded": "Widget",
    "direct": "Widget",
    None: "Widget",  # Default/direct traffic
    
    # Google Ads
    "google": "Google Ads",
    "google_ads": "Google Ads",
    "googleads": "Google Ads",
    "cpc": "Google Ads",
    "ppc": "Google Ads",
    "adwords": "Google Ads",
    
    # Jotform
    "jotform": "Jotform",
    "jotforms": "Jotform",
    "form": "Jotform",
    "external_form": "Jotform",
    
    # Referral
    "referral": "Referral",
    "ref": "Referral",
    "partner": "Referral",
    "affiliate": "Referral",
    "friend": "Referral",
    "word_of_mouth": "Referral",
}

# Colors for all 4 platforms
PLATFORM_COLORS = {
    "Widget": "#3B82F6",       # Blue
    "Google Ads": "#EA4335",   # Google Red
    "Jotform": "#FF8A00",      # Orange
    "Referral": "#10B981",     # Emerald Green
}

# Icons for all 4 platforms
PLATFORM_ICONS = {
    "Widget": "layout",
    "Google Ads": "search",
    "Jotform": "file-text",
    "Referral": "users",
}

# Default empty metrics for platforms with no data
def get_empty_platform_metrics(platform: str) -> Dict[str, Any]:
    """Return empty metrics structure for a platform with no data."""
    return {
        "platform": platform,
        "total_leads": 0,
        "hot_leads": 0,
        "medium_leads": 0,
        "low_leads": 0,
        "converted_leads": 0,
        "conversion_rate": 0.0,
        "scheduled_leads": 0,
        "percentage_of_total": 0.0,
        "avg_score": 0.0,
        "color": PLATFORM_COLORS.get(platform, "#6B7280"),
        "icon": PLATFORM_ICONS.get(platform, "globe"),
        "trend": 0.0,
        "cost_per_lead": None,
        "has_data": False,  # Flag to indicate no data yet
    }


def get_platform_from_source(utm_source: Optional[str], utm_medium: Optional[str] = None) -> str:
    """Map UTM source/medium to platform name."""
    if utm_source:
        source_lower = utm_source.lower()
        if source_lower in SOURCE_MAPPING:
            return SOURCE_MAPPING[source_lower]
    
    if utm_medium:
        medium_lower = utm_medium.lower()
        if medium_lower in SOURCE_MAPPING:
            return SOURCE_MAPPING[medium_lower]
    
    # Check for partial matches
    if utm_source:
        source_lower = utm_source.lower()
        for key, value in SOURCE_MAPPING.items():
            if key and key in source_lower:
                return value
    
    return "Widget"  # Default to Widget for direct/unknown


# =============================================================================
# Response Models
# =============================================================================

class PlatformMetrics(BaseModel):
    """Metrics for a single platform/source."""
    platform: str = Field(..., description="Platform name")
    total_leads: int = Field(..., description="Total leads from this platform")
    hot_leads: int = Field(..., description="Hot priority leads")
    medium_leads: int = Field(..., description="Medium priority leads")
    low_leads: int = Field(..., description="Low priority leads")
    converted_leads: int = Field(..., description="Leads that converted")
    conversion_rate: float = Field(..., description="Conversion rate %")
    scheduled_leads: int = Field(..., description="Leads with scheduled appointments")
    percentage_of_total: float = Field(..., description="% of all leads")
    avg_score: float = Field(..., description="Average lead score")
    color: str = Field(..., description="Platform color for charts")
    icon: str = Field(..., description="Platform icon name")
    trend: float = Field(default=0, description="Week-over-week trend %")
    cost_per_lead: Optional[float] = Field(None, description="Cost per lead (if available)")
    has_data: bool = Field(default=True, description="Whether platform has actual data")


class SourceAnalyticsResponse(BaseModel):
    """Complete source analytics response."""
    platforms: List[PlatformMetrics] = Field(..., description="Metrics by platform")
    totals: Dict[str, Any] = Field(..., description="Total metrics across all platforms")
    top_performing: str = Field(..., description="Best performing platform")
    trending_up: List[str] = Field(default_factory=list, description="Platforms with positive trends")
    cache_hit: bool = Field(default=False)
    query_time_ms: float = Field(default=0)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])


class PlatformTrendDataPoint(BaseModel):
    """Single data point for platform trend."""
    date: str
    label: str
    widget: int = 0
    google_ads: int = 0
    jotform: int = 0
    referral: int = 0


class PlatformTrendResponse(BaseModel):
    """Platform trend over time."""
    period_days: int
    data: List[PlatformTrendDataPoint]
    cache_hit: bool = False
    query_time_ms: float = 0
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HotLeadsByPlatformResponse(BaseModel):
    """Hot leads breakdown by platform."""
    platforms: List[Dict[str, Any]]
    total_hot_leads: int
    cache_hit: bool = False
    query_time_ms: float = 0
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# =============================================================================
# Error Handling Helpers
# =============================================================================

def handle_db_error(error: Exception, operation: str, request_id: str) -> None:
    """Log database errors with context."""
    logger.error(f"[{request_id}] Database error during {operation}: {str(error)}", exc_info=True)


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "/overview",
    response_model=SourceAnalyticsResponse,
    summary="Get Source Analytics Overview",
    description="Get comprehensive analytics broken down by lead source platform. Always returns all 4 platforms.",
)
async def get_source_analytics(
    response: Response,
    db: Session = Depends(get_db),
    days_back: int = Query(default=30, ge=1, le=365, description="Days to analyze"),
) -> SourceAnalyticsResponse:
    """
    Get analytics overview broken down by platform/source.
    
    ALWAYS returns all 4 platforms (Widget, Google Ads, Jotform, Referral)
    even if some have 0 leads.
    
    Platforms tracked:
    - Widget (embedded intake form)
    - Google Ads (paid search)
    - Jotform (external form submissions)
    - Referral (partner/affiliate/word-of-mouth)
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    cache = get_cache()
    
    logger.info(f"[{request_id}] Source analytics request: days_back={days_back}")
    
    # Try cache first
    cache_key = f"source_analytics:{days_back}"
    try:
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"[{request_id}] Cache hit for source analytics")
            response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=60"
            return SourceAnalyticsResponse(
                **cached, 
                cache_hit=True, 
                query_time_ms=round((time.time() - start_time) * 1000, 2),
                request_id=request_id
            )
    except Exception as e:
        logger.warning(f"[{request_id}] Cache read failed: {e}")
    
    try:
        # Calculate date range (use timezone-aware datetimes)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        last_week = datetime.now(timezone.utc) - timedelta(days=7)
        two_weeks_ago = datetime.now(timezone.utc) - timedelta(days=14)
        
        # Get all leads in period with source info
        # CRITICAL: Exclude soft-deleted leads (deleted_at IS NOT NULL)
        # This ensures consistency with metrics.py and All Leads table
        leads = db.query(
            Lead.utm_source,
            Lead.utm_medium,
            Lead.priority,
            Lead.status,
            Lead.score,
            Lead.created_at,
            Lead.is_referral,  # REFERRAL OVERRIDE: needed to classify referral leads correctly
        ).filter(
            Lead.created_at >= cutoff_date,
            Lead.deleted_at.is_(None),  # Exclude soft-deleted leads
            Lead.source != LeadSource.manual,  # Exclude coordinator-added manual leads from platform analytics
        ).all()
        
        logger.info(f"[{request_id}] Retrieved {len(leads)} leads for analysis")
        
        # Initialize ALL 4 platforms with empty data
        platform_data: Dict[str, Dict[str, Any]] = {}
        for platform in ALLOWED_PLATFORMS:
            platform_data[platform] = {
                "total": 0,
                "hot": 0,
                "medium": 0,
                "low": 0,
                "converted": 0,
                "scheduled": 0,
                "scores": [],
                "this_week": 0,
                "last_week": 0,
            }
        
        total_leads = len(leads)
        
        # Aggregate by platform
        for lead in leads:
            # REFERRAL OVERRIDE: If lead.is_referral is True, classify as Referral
            # regardless of utm_source/utm_medium. This fixes Widget/Jotform leads
            # that answered "Yes" to the referral question being misclassified.
            if lead.is_referral:
                platform = "Referral"
            else:
                platform = get_platform_from_source(lead.utm_source, lead.utm_medium)
            
            # Ensure platform exists (should always be one of the 4)
            if platform not in platform_data:
                platform = "Widget"  # Default fallback
            
            platform_data[platform]["total"] += 1
            platform_data[platform]["scores"].append(lead.score)
            
            # Priority breakdown
            if lead.priority == PriorityType.HOT:
                platform_data[platform]["hot"] += 1
            elif lead.priority == PriorityType.MEDIUM:
                platform_data[platform]["medium"] += 1
            elif lead.priority == PriorityType.LOW:
                platform_data[platform]["low"] += 1
            
            # Conversion tracking
            if lead.status in [LeadStatus.CONSULTATION_COMPLETE, LeadStatus.TREATMENT_STARTED]:
                platform_data[platform]["converted"] += 1
            if lead.status == LeadStatus.SCHEDULED:
                platform_data[platform]["scheduled"] += 1
            
            # Trend tracking
            if lead.created_at >= last_week:
                platform_data[platform]["this_week"] += 1
            elif lead.created_at >= two_weeks_ago:
                platform_data[platform]["last_week"] += 1
        
        # Build response - ALWAYS include all 4 platforms
        platforms: List[PlatformMetrics] = []
        top_conversion_rate = 0
        top_platform = "Widget"
        trending_up: List[str] = []
        
        for platform in ALLOWED_PLATFORMS:
            data = platform_data[platform]
            total = data["total"]
            converted = data["converted"]
            conversion_rate = round((converted / total * 100) if total > 0 else 0, 2)
            avg_score = round(sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0, 1)
            percentage = round((total / total_leads * 100) if total_leads > 0 else 0, 2)
            
            # Calculate trend
            this_week = data["this_week"]
            last_week_count = data["last_week"]
            if last_week_count > 0:
                trend = round(((this_week - last_week_count) / last_week_count) * 100, 1)
            else:
                trend = 100.0 if this_week > 0 else 0.0
            
            if trend > 0:
                trending_up.append(platform)
            
            # Track top performer (only consider platforms with data)
            if total > 0 and conversion_rate > top_conversion_rate:
                top_conversion_rate = conversion_rate
                top_platform = platform
            
            platforms.append(PlatformMetrics(
                platform=platform,
                total_leads=total,
                hot_leads=data["hot"],
                medium_leads=data["medium"],
                low_leads=data["low"],
                converted_leads=converted,
                conversion_rate=conversion_rate,
                scheduled_leads=data["scheduled"],
                percentage_of_total=percentage,
                avg_score=avg_score,
                color=PLATFORM_COLORS.get(platform, "#6B7280"),
                icon=PLATFORM_ICONS.get(platform, "globe"),
                trend=trend,
                has_data=total > 0,
            ))
        
        # Sort: platforms with data first, then by total leads descending
        platforms.sort(key=lambda x: (-1 if x.has_data else 0, -x.total_leads))
        
        # Calculate totals
        totals = {
            "total_leads": total_leads,
            "total_hot": sum(p.hot_leads for p in platforms),
            "total_medium": sum(p.medium_leads for p in platforms),
            "total_low": sum(p.low_leads for p in platforms),
            "total_converted": sum(p.converted_leads for p in platforms),
            "overall_conversion_rate": round(
                (sum(p.converted_leads for p in platforms) / total_leads * 100) if total_leads > 0 else 0, 2
            ),
            "total_scheduled": sum(p.scheduled_leads for p in platforms),
            "platform_count": len([p for p in platforms if p.has_data]),  # Only count platforms with data
        }
        
        result = {
            "platforms": [p.dict() for p in platforms],
            "totals": totals,
            "top_performing": top_platform,
            "trending_up": trending_up,
        }
        
        # Cache for 60 seconds
        try:
            cache.set(cache_key, result, ttl=60)
        except Exception as e:
            logger.warning(f"[{request_id}] Cache write failed: {e}")
        
        query_time = round((time.time() - start_time) * 1000, 2)
        logger.info(f"[{request_id}] Source analytics completed in {query_time}ms")
        
        response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=60"
        return SourceAnalyticsResponse(
            **result,
            cache_hit=False,
            query_time_ms=query_time,
            request_id=request_id,
        )
        
    except SQLAlchemyError as e:
        handle_db_error(e, "source_analytics", request_id)
        raise HTTPException(
            status_code=503,
            detail=f"Database temporarily unavailable. Request ID: {request_id}"
        )
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error. Request ID: {request_id}"
        )


@router.get(
    "/trend",
    response_model=PlatformTrendResponse,
    summary="Get Platform Trend",
    description="Get daily lead counts by platform over time.",
)
async def get_platform_trend(
    response: Response,
    db: Session = Depends(get_db),
    period: int = Query(default=30, ge=7, le=90, description="Days to include"),
) -> PlatformTrendResponse:
    """Get daily breakdown of leads by platform (all 4 platforms)."""
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    cache = get_cache()
    
    # Try cache
    cache_key = f"platform_trend:{period}"
    try:
        cached = cache.get(cache_key)
        if cached:
            response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=60"
            return PlatformTrendResponse(
                **cached, 
                cache_hit=True, 
                query_time_ms=round((time.time() - start_time) * 1000, 2)
            )
    except Exception as e:
        logger.warning(f"[{request_id}] Cache read failed: {e}")
    
    try:
        # Get date range
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=period)
        
        # Get leads with source info
        # Exclude soft-deleted leads for consistency
        leads = db.query(
            func.date(Lead.created_at).label('date'),
            Lead.utm_source,
            Lead.utm_medium,
            Lead.is_referral,  # REFERRAL OVERRIDE: needed to classify referral leads correctly
        ).filter(
            func.date(Lead.created_at) >= start_date,
            Lead.deleted_at.is_(None),  # Exclude soft-deleted leads
            Lead.source != LeadSource.manual,  # Exclude coordinator-added manual leads from platform analytics
        ).all()
        
        # Aggregate by date and platform (all 4 platforms)
        daily_data: Dict[str, Dict[str, int]] = {}
        
        current = start_date
        while current <= end_date:
            date_str = current.isoformat()
            daily_data[date_str] = {
                "Widget": 0,
                "Google Ads": 0,
                "Jotform": 0,
                "Referral": 0,
            }
            current += timedelta(days=1)
        
        for lead in leads:
            date_str = lead.date.isoformat() if lead.date else None
            if date_str and date_str in daily_data:
                # REFERRAL OVERRIDE: If lead.is_referral is True, classify as Referral
                # regardless of utm_source/utm_medium.
                if lead.is_referral:
                    platform = "Referral"
                else:
                    platform = get_platform_from_source(lead.utm_source, lead.utm_medium)
                if platform in daily_data[date_str]:
                    daily_data[date_str][platform] += 1
        
        # Build response
        data = []
        for date_str in sorted(daily_data.keys()):
            date_obj = datetime.fromisoformat(date_str).date()
            counts = daily_data[date_str]
            data.append(PlatformTrendDataPoint(
                date=date_str,
                label=date_obj.strftime("%b %d"),
                widget=counts.get("Widget", 0),
                google_ads=counts.get("Google Ads", 0),
                jotform=counts.get("Jotform", 0),
                referral=counts.get("Referral", 0),
            ))
        
        result = {
            "period_days": period,
            "data": [d.dict() for d in data],
        }
        
        # Cache for 60 seconds
        try:
            cache.set(cache_key, result, ttl=60)
        except Exception as e:
            logger.warning(f"[{request_id}] Cache write failed: {e}")
        
        response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=60"
        return PlatformTrendResponse(
            **result, 
            cache_hit=False, 
            query_time_ms=round((time.time() - start_time) * 1000, 2)
        )
        
    except SQLAlchemyError as e:
        handle_db_error(e, "platform_trend", request_id)
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/hot-leads",
    response_model=HotLeadsByPlatformResponse,
    summary="Get Hot Leads by Platform",
    description="Get hot leads breakdown by source platform (all 4 platforms).",
)
async def get_hot_leads_by_platform(
    response: Response,
    db: Session = Depends(get_db),
    days_back: int = Query(default=30, ge=1, le=365),
) -> HotLeadsByPlatformResponse:
    """Get hot leads breakdown by platform with details (all 4 platforms)."""
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    cache = get_cache()
    
    # Try cache
    cache_key = f"hot_leads_platform:{days_back}"
    try:
        cached = cache.get(cache_key)
        if cached:
            response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=60"
            return HotLeadsByPlatformResponse(
                **cached, 
                cache_hit=True, 
                query_time_ms=round((time.time() - start_time) * 1000, 2)
            )
    except Exception as e:
        logger.warning(f"[{request_id}] Cache read failed: {e}")
    
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        # Get hot leads with source info
        # Exclude soft-deleted leads for consistency
        hot_leads = db.query(
            Lead.utm_source,
            Lead.utm_medium,
            Lead.is_referral,  # REFERRAL OVERRIDE: needed to classify referral leads correctly
            Lead.status,
            Lead.score,
            Lead.condition,
        ).filter(
            and_(
                Lead.created_at >= cutoff_date,
                Lead.priority == PriorityType.HOT,
                Lead.deleted_at.is_(None),  # Exclude soft-deleted leads
                Lead.source != LeadSource.manual,  # Exclude coordinator-added manual leads from platform analytics
            )
        ).all()
        
        # Initialize all 4 platforms
        platform_data: Dict[str, Dict[str, Any]] = {}
        for platform in ALLOWED_PLATFORMS:
            platform_data[platform] = {
                "count": 0,
                "converted": 0,
                "scheduled": 0,
                "new": 0,
                "scores": [],
                "conditions": {},
            }
        
        for lead in hot_leads:
            # REFERRAL OVERRIDE: If lead.is_referral is True, classify as Referral
            # regardless of utm_source/utm_medium.
            if lead.is_referral:
                platform = "Referral"
            else:
                platform = get_platform_from_source(lead.utm_source, lead.utm_medium)
            
            if platform not in platform_data:
                platform = "Widget"
            
            platform_data[platform]["count"] += 1
            platform_data[platform]["scores"].append(lead.score)
            
            # Condition breakdown
            condition = lead.condition.value if hasattr(lead.condition, 'value') else str(lead.condition)
            platform_data[platform]["conditions"][condition] = platform_data[platform]["conditions"].get(condition, 0) + 1
            
            # Status breakdown
            if lead.status in [LeadStatus.CONSULTATION_COMPLETE, LeadStatus.TREATMENT_STARTED]:
                platform_data[platform]["converted"] += 1
            elif lead.status == LeadStatus.SCHEDULED:
                platform_data[platform]["scheduled"] += 1
            elif lead.status == LeadStatus.NEW:
                platform_data[platform]["new"] += 1
        
        # Build response - include all 4 platforms
        platforms = []
        for platform in ALLOWED_PLATFORMS:
            data = platform_data[platform]
            avg_score = round(sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0, 1)
            conversion_rate = round((data["converted"] / data["count"] * 100) if data["count"] > 0 else 0, 1)
            
            # Top condition for this platform
            top_condition = max(data["conditions"].items(), key=lambda x: x[1])[0] if data["conditions"] else "N/A"
            
            platforms.append({
                "platform": platform,
                "count": data["count"],
                "converted": data["converted"],
                "scheduled": data["scheduled"],
                "new_untouched": data["new"],
                "conversion_rate": conversion_rate,
                "avg_score": avg_score,
                "top_condition": top_condition,
                "color": PLATFORM_COLORS.get(platform, "#6B7280"),
                "icon": PLATFORM_ICONS.get(platform, "globe"),
                "has_data": data["count"] > 0,
            })
        
        # Sort: platforms with data first, then by count descending
        platforms.sort(key=lambda x: (-1 if x["has_data"] else 0, -x["count"]))
        
        result = {
            "platforms": platforms,
            "total_hot_leads": sum(p["count"] for p in platforms),
        }
        
        # Cache for 30 seconds
        try:
            cache.set(cache_key, result, ttl=30)
        except Exception as e:
            logger.warning(f"[{request_id}] Cache write failed: {e}")
        
        response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=60"
        return HotLeadsByPlatformResponse(
            **result, 
            cache_hit=False, 
            query_time_ms=round((time.time() - start_time) * 1000, 2)
        )
        
    except SQLAlchemyError as e:
        handle_db_error(e, "hot_leads_platform", request_id)
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/campaign-performance",
    summary="Get Campaign Performance",
    description="Get performance breakdown by UTM campaign.",
)
async def get_campaign_performance(
    response: Response,
    db: Session = Depends(get_db),
    days_back: int = Query(default=30, ge=1, le=365),
):
    """
    Get performance metrics by UTM campaign.

    Redis-cached for 60 s (same TTL as the other source-analytics endpoints).
    Cache-Control: private, max-age=30, stale-while-revalidate=60 is sent on
    every response so the browser can serve stale data while revalidating.
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    cache = get_cache()

    # ── Try Redis cache first ──────────────────────────────────────────────
    cache_key = f"campaign_performance:{days_back}"
    try:
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"[{request_id}] Cache hit for campaign performance")
            response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=60"
            return {
                **cached,
                "query_time_ms": round((time.time() - start_time) * 1000, 2),
                "cache_hit": True,
            }
    except Exception as e:
        logger.warning(f"[{request_id}] Cache read failed: {e}")

    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        # Get campaign data — exclude soft-deleted leads for consistency
        campaigns = db.query(
            Lead.utm_campaign,
            Lead.utm_source,
            func.count(Lead.id).label('total'),
            func.count(Lead.id).filter(Lead.priority == PriorityType.HOT).label('hot'),
            func.count(Lead.id).filter(
                Lead.status.in_([LeadStatus.CONSULTATION_COMPLETE, LeadStatus.TREATMENT_STARTED])
            ).label('converted'),
            func.avg(Lead.score).label('avg_score'),
        ).filter(
            and_(
                Lead.created_at >= cutoff_date,
                Lead.utm_campaign.isnot(None),
                Lead.deleted_at.is_(None),
                Lead.source != LeadSource.manual,  # Exclude coordinator-added manual leads from platform analytics
            )
        ).group_by(
            Lead.utm_campaign,
            Lead.utm_source,
        ).order_by(
            func.count(Lead.id).desc()
        ).limit(20).all()

        campaigns_list = []
        for campaign in campaigns:
            total = campaign.total or 0
            converted = campaign.converted or 0
            conversion_rate = round((converted / total * 100) if total > 0 else 0, 2)
            campaigns_list.append({
                "campaign": campaign.utm_campaign or "Direct",
                "source": campaign.utm_source or "Direct",
                "platform": get_platform_from_source(campaign.utm_source, None),
                "total_leads": total,
                "hot_leads": campaign.hot or 0,
                "converted_leads": converted,
                "conversion_rate": conversion_rate,
                "avg_score": round(float(campaign.avg_score or 0), 1),
            })

        result_to_cache = {
            "campaigns": campaigns_list,
            "total_campaigns": len(campaigns_list),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # ── Store in Redis for 60 s ────────────────────────────────────────
        try:
            cache.set(cache_key, result_to_cache, ttl=60)
        except Exception as e:
            logger.warning(f"[{request_id}] Cache write failed: {e}")

        response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=60"
        return {
            **result_to_cache,
            "query_time_ms": round((time.time() - start_time) * 1000, 2),
            "cache_hit": False,
        }

    except SQLAlchemyError as e:
        handle_db_error(e, "campaign_performance", request_id)
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
