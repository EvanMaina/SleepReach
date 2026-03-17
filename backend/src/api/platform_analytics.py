"""
Platform Analytics API Endpoints.

High-performance REST API for platform performance analytics.
Designed for <200ms response times with millions of leads.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..services.platform_analytics import (
    PlatformAnalyticsService, 
    get_platform_analytics_service
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/platform-analytics", tags=["Platform Analytics"])


# =============================================================================
# Platform Summary Endpoints
# =============================================================================

@router.get("/summary")
async def get_platform_summary(
    response: Response,
    period: str = Query(
        default="30d",
        description="Time period for analytics",
        regex="^(7d|30d|90d|all)$"
    ),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive platform analytics summary.
    
    Returns aggregated metrics for all lead source platforms including:
    - Total leads per platform
    - Conversion rates
    - Quality distribution (hot/medium/low)
    - Contact rates
    - Growth metrics
    - Daily trends
    - AI-generated insights
    
    **Performance**: <200ms response time, cached for 5 minutes.
    
    **Periods**:
    - 7d: Last 7 days
    - 30d: Last 30 days (default)
    - 90d: Last 90 days
    - all: All time
    """
    try:
        service = get_platform_analytics_service(db)
        result = service.get_platform_summary(period)
        
        # Set cache headers for CDN/browser
        response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"
        response.headers["X-Data-Freshness"] = result.get("refreshedAt", "")
        
        return result
    except Exception as e:
        logger.error(f"Error fetching platform summary: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch platform analytics summary"
        )


@router.get("/platforms")
async def list_platforms(
    response: Response,
    db: Session = Depends(get_db)
):
    """
    List all configured platforms with their current status.
    
    Returns platform configurations including:
    - Platform ID and display name
    - Integration status (active, pending_integration, disabled)
    - Platform icon and color for UI
    """
    try:
        service = get_platform_analytics_service(db)
        configs = service._get_platform_configs()
        
        platforms = [
            {
                "id": platform_id,
                "displayName": config.get("display_name"),
                "icon": config.get("icon"),
                "color": config.get("color"),
                "status": config.get("status"),
            }
            for platform_id, config in configs.items()
        ]
        
        # Set cache headers
        response.headers["Cache-Control"] = "public, s-maxage=300, stale-while-revalidate=600"
        
        return {
            "platforms": platforms,
            "total": len(platforms),
            "activeCount": sum(1 for p in platforms if p["status"] == "active")
        }
    except Exception as e:
        logger.error(f"Error listing platforms: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list platforms"
        )


@router.get("/platforms/{platform_id}")
async def get_platform_details(
    platform_id: str,
    response: Response,
    period: str = Query(default="30d", regex="^(7d|30d|90d|all)$"),
    db: Session = Depends(get_db)
):
    """
    Get detailed analytics for a specific platform.
    
    Returns comprehensive metrics for the specified platform including:
    - All platform summary metrics
    - Status funnel distribution
    - Priority/quality distribution
    - Daily trend data
    - Week-over-week growth
    """
    try:
        service = get_platform_analytics_service(db)
        summary = service.get_platform_summary(period)
        
        # Find the specific platform
        platform_data = next(
            (p for p in summary.get("platforms", []) if p["id"] == platform_id),
            None
        )
        
        if not platform_data:
            raise HTTPException(
                status_code=404,
                detail=f"Platform '{platform_id}' not found"
            )
        
        # Set cache headers
        response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"
        
        return {
            "platform": platform_data,
            "period": summary.get("period"),
            "refreshedAt": summary.get("refreshedAt")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching platform details: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch platform details"
        )


# =============================================================================
# Trends & Growth Endpoints
# =============================================================================

@router.get("/trends")
async def get_platform_trends(
    response: Response,
    period: str = Query(default="30d", regex="^(7d|30d|90d)$"),
    platform: Optional[str] = Query(default=None, description="Filter by platform"),
    group_by: str = Query(default="day", regex="^(day|week)$"),
    db: Session = Depends(get_db)
):
    """
    Get platform trend data for charting.
    
    Returns time-series data suitable for line/area charts:
    - Daily or weekly aggregations
    - Lead counts, conversions, and quality metrics
    - Optional filtering by platform
    """
    try:
        service = get_platform_analytics_service(db)
        summary = service.get_platform_summary(period)
        
        trends = {}
        for platform_data in summary.get("platforms", []):
            platform_id = platform_data["id"]
            
            # Skip if filtering by platform and doesn't match
            if platform and platform != platform_id:
                continue
            
            if group_by == "day":
                trends[platform_id] = platform_data.get("dailyTrend", [])
            else:
                trends[platform_id] = platform_data.get("growthMetrics", [])
        
        # Set cache headers
        response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"
        
        return {
            "trends": trends,
            "period": summary.get("period"),
            "groupBy": group_by,
            "refreshedAt": summary.get("refreshedAt")
        }
    except Exception as e:
        logger.error(f"Error fetching platform trends: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch platform trends"
        )


@router.get("/comparison")
async def get_platform_comparison(
    response: Response,
    period: str = Query(default="30d", regex="^(7d|30d|90d|all)$"),
    metric: str = Query(
        default="totalLeads",
        description="Metric to compare",
        regex="^(totalLeads|convertedLeads|conversionRate|hotLeads|contactRate|qualityScore)$"
    ),
    db: Session = Depends(get_db)
):
    """
    Get platform comparison data for specific metrics.
    
    Returns comparison data suitable for bar/pie charts:
    - Specified metric for each active platform
    - Sorted by metric value
    - Includes percentage of total
    """
    try:
        service = get_platform_analytics_service(db)
        summary = service.get_platform_summary(period)
        
        comparison = []
        total = 0
        
        for platform_data in summary.get("platforms", []):
            metrics = platform_data.get("metrics", {})
            value = metrics.get(metric, 0) or 0
            
            comparison.append({
                "platform": platform_data["id"],
                "displayName": platform_data["displayName"],
                "color": platform_data["color"],
                "value": value
            })
            
            if isinstance(value, (int, float)):
                total += value
        
        # Calculate percentages
        for item in comparison:
            if total > 0 and isinstance(item["value"], (int, float)):
                item["percentage"] = round(item["value"] * 100 / total, 2)
            else:
                item["percentage"] = 0
        
        # Sort by value descending
        comparison.sort(key=lambda x: x["value"] or 0, reverse=True)
        
        # Set cache headers
        response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"
        
        return {
            "comparison": comparison,
            "metric": metric,
            "total": total,
            "period": summary.get("period"),
            "refreshedAt": summary.get("refreshedAt")
        }
    except Exception as e:
        logger.error(f"Error fetching platform comparison: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch platform comparison"
        )


# =============================================================================
# Activity Feed Endpoints
# =============================================================================

@router.get("/activity")
async def get_platform_activity(
    response: Response,
    limit: int = Query(default=20, ge=1, le=100, description="Number of items"),
    cursor: Optional[str] = Query(default=None, description="Pagination cursor"),
    platform: Optional[str] = Query(default=None, description="Filter by platform"),
    db: Session = Depends(get_db)
):
    """
    Get recent lead activity with cursor-based pagination.
    
    Returns activity feed suitable for real-time updates:
    - Recent lead submissions
    - Lead status and priority
    - Cursor-based pagination for consistent performance
    
    **Performance**: Uses cursor pagination for O(1) performance regardless of offset.
    """
    try:
        service = get_platform_analytics_service(db)
        result = service.get_recent_activity(
            limit=limit,
            cursor=cursor,
            platform=platform
        )
        
        # Set cache headers (shorter TTL for activity)
        if not cursor:
            response.headers["Cache-Control"] = "public, s-maxage=30, stale-while-revalidate=60"
        else:
            response.headers["Cache-Control"] = "private, max-age=0"
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching platform activity: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch platform activity"
        )


# =============================================================================
# Insights Endpoints
# =============================================================================

@router.get("/insights")
async def get_platform_insights(
    response: Response,
    period: str = Query(default="30d", regex="^(7d|30d|90d|all)$"),
    db: Session = Depends(get_db)
):
    """
    Get AI-generated insights about platform performance.
    
    Returns actionable insights including:
    - Best converting platform
    - Fastest growing platform
    - Highest quality lead source
    - Platforms needing attention
    """
    try:
        service = get_platform_analytics_service(db)
        summary = service.get_platform_summary(period)
        
        # Set cache headers
        response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"
        
        return {
            "insights": summary.get("insights", []),
            "period": summary.get("period"),
            "refreshedAt": summary.get("refreshedAt")
        }
    except Exception as e:
        logger.error(f"Error fetching platform insights: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch platform insights"
        )


# =============================================================================
# Distribution Endpoints
# =============================================================================

@router.get("/status-funnel")
async def get_status_funnel(
    response: Response,
    platform: Optional[str] = Query(default=None, description="Filter by platform"),
    db: Session = Depends(get_db)
):
    """
    Get lead status funnel distribution by platform.
    
    Returns funnel stages:
    - NEW → CONTACTED → SCHEDULED → CONSULTATION_COMPLETE → TREATMENT_STARTED
    - Lost and Disqualified counts
    - Drop-off percentages between stages
    """
    try:
        service = get_platform_analytics_service(db)
        summary = service.get_platform_summary("all")
        
        funnel_data = {}
        for platform_data in summary.get("platforms", []):
            platform_id = platform_data["id"]
            
            if platform and platform != platform_id:
                continue
            
            funnel_data[platform_id] = {
                "displayName": platform_data["displayName"],
                "color": platform_data["color"],
                "distribution": platform_data.get("statusDistribution", [])
            }
        
        # Set cache headers
        response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"
        
        return {
            "funnel": funnel_data,
            "refreshedAt": summary.get("refreshedAt")
        }
    except Exception as e:
        logger.error(f"Error fetching status funnel: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch status funnel"
        )


@router.get("/quality-distribution")
async def get_quality_distribution(
    response: Response,
    platform: Optional[str] = Query(default=None, description="Filter by platform"),
    db: Session = Depends(get_db)
):
    """
    Get lead quality (priority) distribution by platform.
    
    Returns quality breakdown:
    - HOT (high priority)
    - MEDIUM
    - LOW
    - DISQUALIFIED
    """
    try:
        service = get_platform_analytics_service(db)
        summary = service.get_platform_summary("all")
        
        quality_data = {}
        for platform_data in summary.get("platforms", []):
            platform_id = platform_data["id"]
            
            if platform and platform != platform_id:
                continue
            
            quality_data[platform_id] = {
                "displayName": platform_data["displayName"],
                "color": platform_data["color"],
                "distribution": platform_data.get("priorityDistribution", []),
                "qualityScore": platform_data.get("metrics", {}).get("qualityScore", 0)
            }
        
        # Set cache headers
        response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=300"
        
        return {
            "quality": quality_data,
            "refreshedAt": summary.get("refreshedAt")
        }
    except Exception as e:
        logger.error(f"Error fetching quality distribution: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch quality distribution"
        )


# =============================================================================
# Admin/Maintenance Endpoints
# =============================================================================

@router.post("/refresh")
async def refresh_analytics(
    db: Session = Depends(get_db)
):
    """
    Manually refresh platform analytics materialized views.
    
    **Note**: This is automatically done every 5 minutes via Celery.
    Use this endpoint for immediate refresh after significant data changes.
    
    **Admin only** - should be protected in production.
    """
    try:
        service = get_platform_analytics_service(db)
        result = service.refresh_materialized_views()
        
        return result
    except Exception as e:
        logger.error(f"Error refreshing analytics: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh analytics"
        )


@router.get("/health")
async def analytics_health(
    db: Session = Depends(get_db)
):
    """
    Check platform analytics health and data freshness.
    
    Returns:
    - Last refresh timestamp
    - View freshness status
    - Cache health
    """
    try:
        service = get_platform_analytics_service(db)
        summary = service.get_platform_summary("30d")
        
        # Get cache health
        cache_health = service.cache.health_check()
        
        return {
            "status": "healthy",
            "dataFreshness": summary.get("refreshedAt"),
            "cache": cache_health,
            "platformCount": len(summary.get("platforms", [])),
            "totalLeads": summary.get("totals", {}).get("totalLeads", 0)
        }
    except Exception as e:
        logger.error(f"Analytics health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }
