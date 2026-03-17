"""
Google Ads Analytics API

Provides endpoints for Google Ads campaign performance metrics.
These endpoints are used by the frontend analytics dashboard to display
ad spend, conversions, ROI, and campaign-level performance data.

ENDPOINTS:
- GET /api/analytics/google-ads/overview - Account-level metrics summary
- GET /api/analytics/google-ads/campaigns - Campaign-level performance
- GET /api/analytics/google-ads/daily - Daily metrics trend
- GET /api/analytics/google-ads/status - Connection status check

@module api/google_ads_analytics
@version 1.0.0
"""

import time
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from ..services.google_ads_service import get_google_ads_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics/google-ads",
                   tags=["Google Ads Analytics"])


# =============================================================================
# Response Models
# =============================================================================

class CampaignMetricsResponse(BaseModel):
    """Response model for individual campaign metrics."""
    campaign_id: str = Field(..., description="Google Ads campaign ID")
    campaign_name: str = Field(..., description="Campaign name")
    status: str = Field(...,
                        description="Campaign status (ENABLED, PAUSED, etc.)")
    impressions: int = Field(..., description="Total impressions")
    clicks: int = Field(..., description="Total clicks")
    cost: float = Field(..., description="Total cost in dollars")
    conversions: float = Field(..., description="Total conversions")
    ctr: float = Field(..., description="Click-through rate (%)")
    avg_cpc: float = Field(..., description="Average cost per click ($)")
    cost_per_conversion: Optional[float] = Field(
        None, description="Cost per conversion ($)")
    conversion_rate: float = Field(..., description="Conversion rate (%)")


class GoogleAdsOverviewResponse(BaseModel):
    """Response model for Google Ads account overview."""
    account_id: str = Field(..., description="Google Ads account ID")
    account_name: str = Field(..., description="Account name")

    # Summary metrics
    total_impressions: int = Field(...,
                                   description="Total impressions across all campaigns")
    total_clicks: int = Field(...,
                              description="Total clicks across all campaigns")
    total_cost: float = Field(..., description="Total ad spend in dollars")
    total_conversions: float = Field(..., description="Total conversions")

    # Calculated metrics
    overall_ctr: float = Field(...,
                               description="Overall click-through rate (%)")
    overall_avg_cpc: float = Field(..., description="Overall average CPC ($)")
    overall_cost_per_conversion: Optional[float] = Field(
        None, description="Overall cost per conversion ($)")
    overall_conversion_rate: float = Field(...,
                                           description="Overall conversion rate (%)")

    # Campaign counts
    active_campaigns: int = Field(...,
                                  description="Number of active campaigns")
    paused_campaigns: int = Field(...,
                                  description="Number of paused campaigns")
    total_campaigns: int = Field(..., description="Total number of campaigns")

    # Date range
    date_range_start: str = Field(..., description="Start of date range")
    date_range_end: str = Field(..., description="End of date range")

    # Metadata
    is_configured: bool = Field(...,
                                description="Whether Google Ads credentials are configured")
    is_mock_data: bool = Field(...,
                               description="Whether this is mock/demo data")
    query_time_ms: float = Field(
        default=0, description="Query execution time in ms")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])


class CampaignsListResponse(BaseModel):
    """Response model for campaigns list."""
    campaigns: List[CampaignMetricsResponse] = Field(
        ..., description="List of campaign metrics")
    total_campaigns: int = Field(..., description="Total number of campaigns")
    date_range_start: str = Field(..., description="Start of date range")
    date_range_end: str = Field(..., description="End of date range")
    is_mock_data: bool = Field(...,
                               description="Whether this is mock/demo data")
    query_time_ms: float = Field(default=0)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DailyMetricsDataPoint(BaseModel):
    """Single day's metrics."""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    label: str = Field(..., description="Display label (e.g., 'Jan 15')")
    impressions: int = Field(..., description="Impressions for the day")
    clicks: int = Field(..., description="Clicks for the day")
    cost: float = Field(..., description="Cost for the day ($)")
    conversions: float = Field(..., description="Conversions for the day")
    ctr: float = Field(..., description="CTR for the day (%)")
    cpc: float = Field(..., description="CPC for the day ($)")


class DailyMetricsResponse(BaseModel):
    """Response model for daily metrics trend."""
    data: List[DailyMetricsDataPoint] = Field(
        ..., description="Daily metrics data points")
    period_days: int = Field(..., description="Number of days in the period")

    # Period totals
    total_impressions: int = Field(...,
                                   description="Total impressions for period")
    total_clicks: int = Field(..., description="Total clicks for period")
    total_cost: float = Field(..., description="Total cost for period ($)")
    total_conversions: float = Field(...,
                                     description="Total conversions for period")

    is_mock_data: bool = Field(...,
                               description="Whether this is mock/demo data")
    query_time_ms: float = Field(default=0)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GoogleAdsStatusResponse(BaseModel):
    """Response model for Google Ads connection status."""
    is_configured: bool = Field(...,
                                description="Whether credentials are configured")
    account_id: Optional[str] = Field(
        None, description="Connected account ID (if configured)")
    status: str = Field(..., description="Connection status message")
    last_sync: Optional[str] = Field(
        None, description="Last successful data sync")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "/overview",
    response_model=GoogleAdsOverviewResponse,
    summary="Get Google Ads Overview",
    description="Get account-level summary metrics from Google Ads including total spend, clicks, conversions, and ROI metrics.",
)
async def get_google_ads_overview(
    days_back: int = Query(default=30, ge=1, le=365,
                           description="Number of days to analyze"),
) -> GoogleAdsOverviewResponse:
    """
    Get Google Ads account overview with aggregated metrics.

    Returns summary metrics across all campaigns including:
    - Total impressions, clicks, cost, and conversions
    - CTR, CPC, cost per conversion, and conversion rate
    - Active/paused campaign counts

    If Google Ads credentials are not configured, returns realistic mock data
    for development and demo purposes.
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]

    logger.info(
        f"[{request_id}] Google Ads overview request: days_back={days_back}")

    try:
        service = get_google_ads_service()
        metrics = await service.get_campaign_metrics(days_back=days_back)

        query_time = round((time.time() - start_time) * 1000, 2)

        return GoogleAdsOverviewResponse(
            account_id=metrics.account_id,
            account_name=metrics.account_name,
            total_impressions=metrics.total_impressions,
            total_clicks=metrics.total_clicks,
            total_cost=metrics.total_cost,
            total_conversions=metrics.total_conversions,
            overall_ctr=round(metrics.overall_ctr, 2),
            overall_avg_cpc=round(metrics.overall_avg_cpc, 2),
            overall_cost_per_conversion=round(
                metrics.overall_cost_per_conversion, 2) if metrics.overall_cost_per_conversion else None,
            overall_conversion_rate=round(metrics.overall_conversion_rate, 2),
            active_campaigns=metrics.active_campaigns,
            paused_campaigns=metrics.paused_campaigns,
            total_campaigns=len(metrics.campaigns),
            date_range_start=metrics.date_range_start,
            date_range_end=metrics.date_range_end,
            is_configured=service.is_configured(),
            is_mock_data=not service.is_configured(),
            query_time_ms=query_time,
            request_id=request_id,
        )

    except Exception as e:
        logger.error(
            f"[{request_id}] Error fetching Google Ads overview: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch Google Ads data. Request ID: {request_id}"
        )


@router.get(
    "/campaigns",
    response_model=CampaignsListResponse,
    summary="Get Campaign Performance",
    description="Get performance metrics for individual Google Ads campaigns.",
)
async def get_campaigns_performance(
    days_back: int = Query(default=30, ge=1, le=365,
                           description="Number of days to analyze"),
    status_filter: Optional[str] = Query(
        default=None, description="Filter by status (ENABLED, PAUSED)"),
) -> CampaignsListResponse:
    """
    Get detailed performance metrics for each campaign.

    Returns a list of campaigns with individual metrics including:
    - Impressions, clicks, cost, conversions
    - CTR, CPC, cost per conversion, conversion rate
    - Campaign status

    Optionally filter by campaign status.
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]

    logger.info(
        f"[{request_id}] Campaigns performance request: days_back={days_back}, status={status_filter}")

    try:
        service = get_google_ads_service()
        metrics = await service.get_campaign_metrics(days_back=days_back)

        # Convert to response format
        campaigns = []
        for campaign in metrics.campaigns:
            # Apply status filter if provided
            if status_filter and campaign.status != status_filter.upper():
                continue

            campaigns.append(CampaignMetricsResponse(
                campaign_id=campaign.campaign_id,
                campaign_name=campaign.campaign_name,
                status=campaign.status,
                impressions=campaign.impressions,
                clicks=campaign.clicks,
                cost=round(campaign.cost, 2),
                conversions=campaign.conversions,
                ctr=round(campaign.ctr, 2),
                avg_cpc=round(campaign.avg_cpc, 2),
                cost_per_conversion=round(
                    campaign.cost_per_conversion, 2) if campaign.cost_per_conversion else None,
                conversion_rate=round(campaign.conversion_rate, 2),
            ))

        # Sort by cost descending (highest spend first)
        campaigns.sort(key=lambda x: x.cost, reverse=True)

        query_time = round((time.time() - start_time) * 1000, 2)

        return CampaignsListResponse(
            campaigns=campaigns,
            total_campaigns=len(campaigns),
            date_range_start=metrics.date_range_start,
            date_range_end=metrics.date_range_end,
            is_mock_data=not service.is_configured(),
            query_time_ms=query_time,
        )

    except Exception as e:
        logger.error(
            f"[{request_id}] Error fetching campaigns: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch campaign data. Request ID: {request_id}"
        )


@router.get(
    "/daily",
    response_model=DailyMetricsResponse,
    summary="Get Daily Metrics Trend",
    description="Get daily breakdown of Google Ads metrics for trend analysis.",
)
async def get_daily_metrics(
    days_back: int = Query(default=30, ge=7, le=90,
                           description="Number of days to analyze"),
) -> DailyMetricsResponse:
    """
    Get daily metrics breakdown for trend visualization.

    Returns daily data points with:
    - Impressions, clicks, cost, conversions
    - CTR and CPC for each day

    Useful for charting performance trends over time.
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]

    logger.info(f"[{request_id}] Daily metrics request: days_back={days_back}")

    try:
        service = get_google_ads_service()
        daily_data = await service.get_daily_metrics(days_back=days_back)

        # Convert to response format
        data_points = [
            DailyMetricsDataPoint(
                date=day["date"],
                label=day["label"],
                impressions=day["impressions"],
                clicks=day["clicks"],
                cost=round(day["cost"], 2),
                conversions=day["conversions"],
                ctr=round(day.get("ctr", 0), 2),
                cpc=round(day.get("cpc", 0), 2),
            )
            for day in daily_data
        ]

        # Calculate totals
        total_impressions = sum(d.impressions for d in data_points)
        total_clicks = sum(d.clicks for d in data_points)
        total_cost = sum(d.cost for d in data_points)
        total_conversions = sum(d.conversions for d in data_points)

        query_time = round((time.time() - start_time) * 1000, 2)

        return DailyMetricsResponse(
            data=data_points,
            period_days=days_back,
            total_impressions=total_impressions,
            total_clicks=total_clicks,
            total_cost=round(total_cost, 2),
            total_conversions=round(total_conversions, 1),
            is_mock_data=not service.is_configured(),
            query_time_ms=query_time,
        )

    except Exception as e:
        logger.error(
            f"[{request_id}] Error fetching daily metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch daily metrics. Request ID: {request_id}"
        )


@router.get(
    "/status",
    response_model=GoogleAdsStatusResponse,
    summary="Get Connection Status",
    description="Check Google Ads API connection status and configuration.",
)
async def get_connection_status() -> GoogleAdsStatusResponse:
    """
    Check if Google Ads is properly configured and connected.

    Returns:
    - Whether credentials are configured
    - Connected account ID (if configured)
    - Status message
    """
    service = get_google_ads_service()
    is_configured = service.is_configured()

    if is_configured:
        return GoogleAdsStatusResponse(
            is_configured=True,
            account_id=service.customer_id,
            status="Connected and ready",
            last_sync=datetime.now(timezone.utc).isoformat(),
        )
    else:
        return GoogleAdsStatusResponse(
            is_configured=False,
            account_id=None,
            status="Not configured - using demo data. Set GOOGLE_ADS_* environment variables to connect.",
            last_sync=None,
        )


@router.get(
    "/roi-summary",
    summary="Get ROI Summary",
    description="Get return on investment summary comparing ad spend to lead value.",
)
async def get_roi_summary(
    days_back: int = Query(default=30, ge=1, le=365,
                           description="Number of days to analyze"),
) -> Dict[str, Any]:
    """
    Get ROI summary comparing Google Ads spend to lead generation.

    This endpoint combines Google Ads cost data with lead conversion data
    to calculate marketing ROI metrics.
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]

    logger.info(f"[{request_id}] ROI summary request: days_back={days_back}")

    try:
        service = get_google_ads_service()
        metrics = await service.get_campaign_metrics(days_back=days_back)

        # Calculate ROI metrics
        # Note: In production, you would also query the leads database
        # to get actual lead values and conversion data

        total_cost = metrics.total_cost
        total_conversions = metrics.total_conversions

        # Estimated lead value (this would come from actual data in production)
        estimated_lead_value = 500.0  # Average value per converted lead
        estimated_revenue = total_conversions * estimated_lead_value

        roi_percentage = ((estimated_revenue - total_cost) /
                          total_cost * 100) if total_cost > 0 else 0

        query_time = round((time.time() - start_time) * 1000, 2)

        return {
            "period_days": days_back,
            "total_ad_spend": round(total_cost, 2),
            "total_conversions": total_conversions,
            "cost_per_conversion": round(total_cost / total_conversions, 2) if total_conversions > 0 else None,
            "estimated_lead_value": estimated_lead_value,
            "estimated_revenue": round(estimated_revenue, 2),
            "roi_percentage": round(roi_percentage, 2),
            "roi_status": "positive" if roi_percentage > 0 else "negative",
            "is_mock_data": not service.is_configured(),
            "note": "Revenue estimates based on average lead value. Connect to CRM for actual values.",
            "query_time_ms": query_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
        }

    except Exception as e:
        logger.error(
            f"[{request_id}] Error calculating ROI: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to calculate ROI. Request ID: {request_id}"
        )
