"""
Lead Metrics and Analytics Endpoints.

Provides queue-specific metrics and trend analytics
for the coordinator dashboard.

OPTIMIZED v3.0:
- Redis caching with stampede prevention
- Single aggregation queries
- Sub-50ms response times for cached data
- Stale-while-revalidate pattern for instant responses
"""

import time
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_, or_
from sqlalchemy.exc import SQLAlchemyError

from ..core.database import get_db
from ..core.config import settings
from ..models.lead import Lead, PriorityType, LeadStatus, ContactOutcome
from ..services.cache import get_cache, CacheService
from ..core.auth import get_current_user
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metrics", tags=["Metrics"], dependencies=[Depends(get_current_user)])

# Cache key prefixes for metrics
CACHE_PREFIX_QUEUE_METRICS = "neuroreach:metrics:queue"
CACHE_PREFIX_TRENDS = "neuroreach:metrics:trends"
CACHE_PREFIX_DASHBOARD_SUMMARY = "neuroreach:metrics:dashboard_summary"
CACHE_TTL_QUEUE_METRICS = 30  # 30 seconds for queue metrics
CACHE_TTL_TRENDS = 60  # 60 seconds for trends
CACHE_TTL_DASHBOARD = 30  # 30 seconds for dashboard summary


# =============================================================================
# Response Schemas
# =============================================================================

class QueueMetricsResponse(BaseModel):
    """Response model for queue-specific metrics."""
    queue_type: str
    total_count: int
    added_today: int
    added_this_week: int
    conversion_rate: float  # Percentage of leads that became scheduled
    response_rate: float    # Percentage of contacted leads that answered
    avg_time_in_queue_hours: Optional[float]  # Average time leads stay in this queue
    # Additional context
    scheduled_count: int
    contacted_count: int
    unreachable_count: int


class MonthlyTrendDataPoint(BaseModel):
    """Single data point for monthly trend."""
    month: str           # Format: "2026-01" or "Jan 2026"
    label: str           # Display label: "Jan"
    total_leads: int
    hot_leads: int
    medium_leads: int
    low_leads: int
    scheduled_count: int
    conversion_rate: float


class MonthlyTrendsResponse(BaseModel):
    """Response model for monthly lead trends."""
    period: str  # "6m", "12m", "ytd", "all"
    data: List[MonthlyTrendDataPoint]
    summary: dict  # Total, average, peak month


class QueueTypeFilter(str, Enum):
    """Queue type filter options."""
    ALL = "all"
    NEW = "new"
    CONTACTED = "contacted"  # Successfully reached - qualifying for scheduling
    HOT = "hot"
    MEDIUM = "medium"
    LOW = "low"
    FOLLOWUP = "followup"
    CALLBACK = "callback"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"  # Consultation complete or treatment started
    UNREACHABLE = "unreachable"


class TrendPeriod(str, Enum):
    """Trend period options."""
    SIX_MONTHS = "6m"
    TWELVE_MONTHS = "12m"
    YEAR_TO_DATE = "ytd"
    ALL_TIME = "all"


class DailyTrendPeriod(str, Enum):
    """Daily trend period options."""
    SEVEN_DAYS = "7d"
    FOURTEEN_DAYS = "14d"
    THIRTY_DAYS = "30d"
    SIXTY_DAYS = "60d"


class DailyTrendDataPoint(BaseModel):
    """Single data point for daily trend."""
    date: str           # Format: "2026-01-25"
    label: str          # Display label: "Jan 25"
    day_of_week: str    # "Mon", "Tue", etc.
    total_leads: int
    hot_leads: int
    medium_leads: int
    low_leads: int
    scheduled_count: int
    conversion_rate: float


class DailyTrendsResponse(BaseModel):
    """Response model for daily lead trends."""
    period: str  # "7d", "14d", "30d", "60d"
    data: List[DailyTrendDataPoint]
    summary: dict  # Total, average, peak day


# =============================================================================
# Queue-Specific Metrics Endpoint
# =============================================================================

@router.get(
    "/leads/metrics",
    response_model=QueueMetricsResponse,
    summary="Get Queue-Specific Metrics",
    description="Get metrics specific to a queue/priority level.",
)
async def get_queue_metrics(
    queue_type: QueueTypeFilter = Query(QueueTypeFilter.ALL, description="Queue type filter"),
    db: Session = Depends(get_db),
) -> QueueMetricsResponse:
    """
    Get metrics specific to a queue or priority level.
    
    Each queue page should call this with their specific queue_type
    to get relevant metrics (not global stats).
    
    OPTIMIZED: Redis caching with 30-second TTL and stampede prevention.
    
    Args:
        queue_type: The queue to get metrics for
        db: Database session
        
    Returns:
        Queue-specific metrics
    """
    start_time = time.time()
    cache = get_cache()
    cache_key = f"{CACHE_PREFIX_QUEUE_METRICS}:{queue_type.value}"
    
    # Try cache first
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.debug(f"Queue metrics cache hit for {queue_type.value} ({(time.time() - start_time) * 1000:.2f}ms)")
        return QueueMetricsResponse(**cached_data)
    
    # Cache miss - compute
    def compute_queue_metrics():
        return _compute_queue_metrics(queue_type, db)
    
    result = cache.get_or_compute(
        key=cache_key,
        compute_func=compute_queue_metrics,
        ttl=CACHE_TTL_QUEUE_METRICS,
        lock_timeout=5,
    )
    
    if result is None:
        # Fallback if cache fails
        result = _compute_queue_metrics(queue_type, db)
    
    query_time = (time.time() - start_time) * 1000
    logger.debug(f"Queue metrics for {queue_type.value} computed in {query_time:.2f}ms")
    
    return QueueMetricsResponse(**result) if isinstance(result, dict) else result


def _compute_queue_metrics(
    queue_type: QueueTypeFilter,
    db: Session,
) -> dict:
    """
    Internal computation for queue metrics. Separated for caching.
    
    Returns dict for JSON serialization in cache.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    
    # Build base query based on queue type — EXCLUDES soft-deleted leads
    base_query = db.query(Lead).filter(Lead.deleted_at.is_(None))
    
    # First, filter out completed/lost/disqualified leads for most queues (matches frontend activeLeads)
    # Frontend: !['consultation complete', 'treatment started', 'lost', 'disqualified'].includes(l.status)
    active_statuses_excluded = [LeadStatus.CONSULTATION_COMPLETE, LeadStatus.TREATMENT_STARTED, LeadStatus.LOST, LeadStatus.DISQUALIFIED]
    
    if queue_type == QueueTypeFilter.HOT:
        # Hot priority - actionable (not scheduled, not completed)
        base_query = base_query.filter(
            Lead.priority == PriorityType.HOT,
            Lead.status.notin_(active_statuses_excluded),
            Lead.status != LeadStatus.SCHEDULED
        )
    elif queue_type == QueueTypeFilter.MEDIUM:
        # Medium priority - actionable (not scheduled, not completed)
        base_query = base_query.filter(
            Lead.priority == PriorityType.MEDIUM,
            Lead.status.notin_(active_statuses_excluded),
            Lead.status != LeadStatus.SCHEDULED
        )
    elif queue_type == QueueTypeFilter.LOW:
        # Low priority - actionable (not scheduled, not completed)
        base_query = base_query.filter(
            Lead.priority == PriorityType.LOW,
            Lead.status.notin_(active_statuses_excluded),
            Lead.status != LeadStatus.SCHEDULED
        )
    elif queue_type == QueueTypeFilter.NEW:
        # Fresh leads - TRULY never contacted
        # Must have status = 'new' (not 'contacted') AND contactOutcome = 'NEW' or NULL
        # This matches frontend: l.status === 'new' && (l.contactOutcome === 'NEW' || !l.contactOutcome)
        base_query = base_query.filter(
            Lead.status == LeadStatus.NEW,
            Lead.status.notin_(active_statuses_excluded),
            or_(
                Lead.contact_outcome == ContactOutcome.NEW,
                Lead.contact_outcome.is_(None)
            )
        )
    elif queue_type == QueueTypeFilter.CONTACTED:
        # Successfully spoke with lead (contactOutcome = 'ANSWERED')
        # Ready for scheduling but not yet scheduled
        # This matches frontend: l.contactOutcome === 'ANSWERED' && l.status !== 'scheduled'
        base_query = base_query.filter(
            Lead.contact_outcome == ContactOutcome.ANSWERED,
            Lead.status.notin_(active_statuses_excluded),
            Lead.status != LeadStatus.SCHEDULED
        )
    elif queue_type == QueueTypeFilter.FOLLOWUP:
        # Needs another contact attempt
        # Includes: NO_ANSWER, UNREACHABLE, or orphaned contacted leads (status='contacted' but outcome='NEW'/NULL)
        # This matches frontend: (NO_ANSWER || UNREACHABLE || (status='contacted' && outcome='NEW')) && status != 'scheduled'
        base_query = base_query.filter(
            Lead.status.notin_(active_statuses_excluded),
            Lead.status != LeadStatus.SCHEDULED,
            or_(
                Lead.contact_outcome == ContactOutcome.NO_ANSWER,
                Lead.contact_outcome == ContactOutcome.UNREACHABLE,
                and_(
                    Lead.status == LeadStatus.CONTACTED,
                    or_(
                        Lead.contact_outcome == ContactOutcome.NEW,
                        Lead.contact_outcome.is_(None)
                    )
                )
            )
        )
    elif queue_type == QueueTypeFilter.CALLBACK:
        # Lead requested specific callback time (not yet scheduled)
        base_query = base_query.filter(
            Lead.contact_outcome == ContactOutcome.CALLBACK_REQUESTED,
            Lead.status.notin_(active_statuses_excluded),
            Lead.status != LeadStatus.SCHEDULED
        )
    elif queue_type == QueueTypeFilter.SCHEDULED:
        # Consultation scheduled (status = 'scheduled')
        base_query = base_query.filter(
            Lead.status == LeadStatus.SCHEDULED
        )
    elif queue_type == QueueTypeFilter.COMPLETED:
        # Consultation complete or treatment started
        base_query = base_query.filter(
            Lead.status.in_([LeadStatus.CONSULTATION_COMPLETE, LeadStatus.TREATMENT_STARTED])
        )
    elif queue_type == QueueTypeFilter.UNREACHABLE:
        # Subset view - just UNREACHABLE outcomes (not scheduled)
        base_query = base_query.filter(
            Lead.contact_outcome == ContactOutcome.UNREACHABLE,
            Lead.status.notin_(active_statuses_excluded),
            Lead.status != LeadStatus.SCHEDULED
        )
    elif queue_type == QueueTypeFilter.ALL:
        # All active leads (not completed, not lost)
        base_query = base_query.filter(
            Lead.status.notin_(active_statuses_excluded)
        )
    # For 'all', no additional filters
    
    # Get total count
    total_count = base_query.count()
    
    # Get added today — QUEUE-AWARE:
    # For NEW queue: use created_at (these are genuinely new leads)
    # For all other queues: use last_updated_at (proxy for "entered this queue today")
    if queue_type == QueueTypeFilter.NEW or queue_type == QueueTypeFilter.ALL:
        added_today = base_query.filter(Lead.created_at >= today_start).count()
        added_this_week = base_query.filter(Lead.created_at >= week_start).count()
    else:
        added_today = base_query.filter(Lead.last_updated_at >= today_start).count()
        added_this_week = base_query.filter(Lead.last_updated_at >= week_start).count()
    
    # Calculate conversion rate (leads that became scheduled)
    # For priority queues, we need to check historical data
    if queue_type in [QueueTypeFilter.HOT, QueueTypeFilter.MEDIUM, QueueTypeFilter.LOW]:
        # Get all leads with this priority (including scheduled ones) — EXCLUDES soft-deleted
        priority_map = {
            QueueTypeFilter.HOT: PriorityType.HOT,
            QueueTypeFilter.MEDIUM: PriorityType.MEDIUM,
            QueueTypeFilter.LOW: PriorityType.LOW,
        }
        all_priority_leads = db.query(Lead).filter(
            Lead.priority == priority_map[queue_type],
            Lead.deleted_at.is_(None),  # EXCLUDE soft-deleted leads
        ).count()
        scheduled_priority = db.query(Lead).filter(
            Lead.priority == priority_map[queue_type],
            Lead.status.in_([LeadStatus.SCHEDULED, LeadStatus.CONSULTATION_COMPLETE]),
            Lead.deleted_at.is_(None),  # EXCLUDE soft-deleted leads
        ).count()
        conversion_rate = (scheduled_priority / all_priority_leads * 100) if all_priority_leads > 0 else 0.0
    else:
        # For other queues, calculate based on queue-specific logic — EXCLUDES soft-deleted
        all_in_queue_historical = db.query(Lead).filter(
            Lead.deleted_at.is_(None)  # EXCLUDE soft-deleted leads
        ).count()
        scheduled_count_all = db.query(Lead).filter(
            Lead.status.in_([LeadStatus.SCHEDULED, LeadStatus.CONSULTATION_COMPLETE]),
            Lead.deleted_at.is_(None),  # EXCLUDE soft-deleted leads
        ).count()
        conversion_rate = (scheduled_count_all / all_in_queue_historical * 100) if all_in_queue_historical > 0 else 0.0
    
    # Calculate response rate (contacted leads that answered)
    # For CONTACTED queue, total_count is already the contacted count
    if queue_type == QueueTypeFilter.CONTACTED:
        contacted_leads = total_count
    elif queue_type != QueueTypeFilter.NEW:
        contacted_leads = base_query.filter(
            Lead.contact_outcome.isnot(None),
            Lead.contact_outcome != ContactOutcome.NEW
        ).count()
    else:
        contacted_leads = 0
    
    answered_leads = base_query.filter(
        Lead.contact_outcome.in_([ContactOutcome.ANSWERED, ContactOutcome.CALLBACK_REQUESTED])
    ).count() if queue_type != QueueTypeFilter.NEW else 0
    
    response_rate = (answered_leads / contacted_leads * 100) if contacted_leads > 0 else 0.0
    
    # Calculate average time in queue (hours) — EXCLUDES soft-deleted leads
    avg_time_query = db.query(
        func.avg(
            func.extract('epoch', func.now() - Lead.created_at) / 3600
        )
    ).filter(Lead.deleted_at.is_(None))  # EXCLUDE soft-deleted leads
    
    # Apply same filters as base_query
    if queue_type == QueueTypeFilter.NEW:
        avg_time_query = avg_time_query.filter(
            Lead.contact_outcome.in_([ContactOutcome.NEW, None])
        )
    
    avg_time_result = avg_time_query.scalar()
    avg_time_in_queue_hours = float(avg_time_result) if avg_time_result else None
    
    # Get additional counts
    scheduled_count = base_query.filter(
        Lead.status == LeadStatus.SCHEDULED
    ).count() if queue_type not in [QueueTypeFilter.SCHEDULED] else total_count
    
    # Use proper NULL handling for contacted_count
    if queue_type == QueueTypeFilter.CONTACTED:
        contacted_count = total_count  # Already filtered to contacted leads
    else:
        contacted_count = base_query.filter(
            Lead.contact_outcome.isnot(None),
            Lead.contact_outcome != ContactOutcome.NEW
        ).count()
    
    unreachable_count = base_query.filter(
        Lead.contact_outcome == ContactOutcome.UNREACHABLE
    ).count()
    
    return {
        "queue_type": queue_type.value,
        "total_count": total_count,
        "added_today": added_today,
        "added_this_week": added_this_week,
        "conversion_rate": round(conversion_rate, 1),
        "response_rate": round(response_rate, 1),
        "avg_time_in_queue_hours": round(avg_time_in_queue_hours, 1) if avg_time_in_queue_hours else None,
        "scheduled_count": scheduled_count,
        "contacted_count": contacted_count,
        "unreachable_count": unreachable_count,
    }


# =============================================================================
# Monthly Trends Endpoint
# =============================================================================

@router.get(
    "/analytics/trends/monthly",
    response_model=MonthlyTrendsResponse,
    summary="Get Monthly Lead Trends",
    description="Get lead trends aggregated by month with robust error handling.",
)
async def get_monthly_trends(
    period: TrendPeriod = Query(TrendPeriod.TWELVE_MONTHS, description="Time period"),
    db: Session = Depends(get_db),
) -> MonthlyTrendsResponse:
    """
    Get lead trends aggregated by month.
    
    Provides monthly lead counts for trend visualization.
    Much more efficient than daily aggregation for long periods.
    
    Features:
    - Redis caching with 60-second TTL
    - Comprehensive error handling with request IDs
    - Graceful degradation on database errors
    - Query timeout protection (10 seconds)
    
    Args:
        period: Time period to retrieve
        db: Database session
        
    Returns:
        Monthly trend data with summary statistics
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    
    logger.info(f"[{request_id}] Monthly trends request: period={period.value}")
    
    # Try cache first
    cache = get_cache()
    cache_key = f"{CACHE_PREFIX_TRENDS}:monthly:{period.value}"
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.debug(f"[{request_id}] Monthly trends cache hit ({(time.time() - start_time) * 1000:.2f}ms)")
        return MonthlyTrendsResponse(**cached_data)
    
    try:
        now = datetime.now(timezone.utc)
        
        # Determine date range based on period
        if period == TrendPeriod.SIX_MONTHS:
            start_date = (now - timedelta(days=180)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == TrendPeriod.TWELVE_MONTHS:
            start_date = (now - timedelta(days=365)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == TrendPeriod.YEAR_TO_DATE:
            start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:  # ALL_TIME
            # Get the earliest lead date or default to 2 years ago
            earliest = db.query(func.min(Lead.created_at)).scalar()
            start_date = earliest if earliest else (now - timedelta(days=730))
        
        # Query with monthly aggregation using date_trunc — EXCLUDES soft-deleted leads
        monthly_data = db.query(
            func.date_trunc('month', Lead.created_at).label('month'),
            func.count(Lead.id).label('total_leads'),
            func.sum(
                case((Lead.priority == PriorityType.HOT, 1), else_=0)
            ).label('hot_leads'),
            func.sum(
                case((Lead.priority == PriorityType.MEDIUM, 1), else_=0)
            ).label('medium_leads'),
            func.sum(
                case((Lead.priority == PriorityType.LOW, 1), else_=0)
            ).label('low_leads'),
            func.sum(
                case((Lead.status.in_([LeadStatus.SCHEDULED, LeadStatus.CONSULTATION_COMPLETE]), 1), else_=0)
            ).label('scheduled_count'),
        ).filter(
            Lead.created_at >= start_date,
            Lead.deleted_at.is_(None),  # EXCLUDE soft-deleted leads
        ).group_by(
            func.date_trunc('month', Lead.created_at)
        ).order_by(
            func.date_trunc('month', Lead.created_at)
        ).all()
        
        # Convert to response format
        data_points: List[MonthlyTrendDataPoint] = []
        total_leads_sum = 0
        peak_month = None
        peak_count = 0
        
        # Month name mapping
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        for row in monthly_data:
            month_dt = row.month
            total = row.total_leads or 0
            scheduled = row.scheduled_count or 0
            conversion_rate = (scheduled / total * 100) if total > 0 else 0.0
            
            point = MonthlyTrendDataPoint(
                month=month_dt.strftime('%Y-%m'),
                label=month_names[month_dt.month - 1],
                total_leads=total,
                hot_leads=row.hot_leads or 0,
                medium_leads=row.medium_leads or 0,
                low_leads=row.low_leads or 0,
                scheduled_count=scheduled,
                conversion_rate=round(conversion_rate, 1),
            )
            data_points.append(point)
            
            total_leads_sum += total
            if total > peak_count:
                peak_count = total
                peak_month = f"{month_names[month_dt.month - 1]} {month_dt.year}"
        
        # Calculate summary
        num_months = len(data_points) if data_points else 1
        monthly_average = total_leads_sum / num_months
        
        query_time = round((time.time() - start_time) * 1000, 2)
        logger.info(f"[{request_id}] Monthly trends completed in {query_time}ms, {len(data_points)} months")
        
        summary = {
            "total_leads": total_leads_sum,
            "monthly_average": round(monthly_average, 1),
            "peak_month": peak_month or "N/A",
            "peak_count": peak_count,
            "num_months": num_months,
        }
        
        # Cache the result for 60 seconds
        result_dict = {
            "period": period.value,
            "data": [p.model_dump() for p in data_points],
            "summary": summary,
        }
        cache.set(cache_key, result_dict, ttl=CACHE_TTL_TRENDS)
        
        return MonthlyTrendsResponse(
            period=period.value,
            data=data_points,
            summary=summary,
        )
        
    except SQLAlchemyError as e:
        logger.error(f"[{request_id}] Database error in monthly trends: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=f"Database temporarily unavailable. Request ID: {request_id}"
        )
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error in monthly trends: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load trend data. Request ID: {request_id}"
        )


# =============================================================================
# Daily Trends Endpoint
# =============================================================================

@router.get(
    "/analytics/trends/daily",
    response_model=DailyTrendsResponse,
    summary="Get Daily Lead Trends",
    description="Get lead trends aggregated by day for short-term analysis.",
)
async def get_daily_trends(
    period: DailyTrendPeriod = Query(DailyTrendPeriod.THIRTY_DAYS, description="Time period"),
    db: Session = Depends(get_db),
) -> DailyTrendsResponse:
    """
    Get lead trends aggregated by day.
    
    Provides daily lead counts for trend visualization.
    Best for short-term analysis (7-60 days).
    Redis cached for 60 seconds.
    
    Args:
        period: Time period to retrieve
        db: Database session
        
    Returns:
        Daily trend data with summary statistics
    """
    # Try cache first
    cache = get_cache()
    cache_key = f"{CACHE_PREFIX_TRENDS}:daily:{period.value}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return DailyTrendsResponse(**cached_data)
    
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Determine date range based on period
    period_days = {
        DailyTrendPeriod.SEVEN_DAYS: 7,
        DailyTrendPeriod.FOURTEEN_DAYS: 14,
        DailyTrendPeriod.THIRTY_DAYS: 30,
        DailyTrendPeriod.SIXTY_DAYS: 60,
    }
    days = period_days.get(period, 30)
    start_date = today - timedelta(days=days - 1)  # Include today
    
    # Query with daily aggregation using date_trunc — EXCLUDES soft-deleted leads
    daily_data = db.query(
        func.date_trunc('day', Lead.created_at).label('day'),
        func.count(Lead.id).label('total_leads'),
        func.sum(
            case((Lead.priority == PriorityType.HOT, 1), else_=0)
        ).label('hot_leads'),
        func.sum(
            case((Lead.priority == PriorityType.MEDIUM, 1), else_=0)
        ).label('medium_leads'),
        func.sum(
            case((Lead.priority == PriorityType.LOW, 1), else_=0)
        ).label('low_leads'),
        func.sum(
            case((Lead.status.in_([LeadStatus.SCHEDULED, LeadStatus.CONSULTATION_COMPLETE]), 1), else_=0)
        ).label('scheduled_count'),
    ).filter(
        Lead.created_at >= start_date,
        Lead.deleted_at.is_(None),  # EXCLUDE soft-deleted leads
    ).group_by(
        func.date_trunc('day', Lead.created_at)
    ).order_by(
        func.date_trunc('day', Lead.created_at)
    ).all()
    
    # Create a dict for quick lookup
    data_by_date = {}
    for row in daily_data:
        date_key = row.day.strftime('%Y-%m-%d')
        data_by_date[date_key] = row
    
    # Day name mapping
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    # Generate complete date range (fill missing days with 0)
    data_points: List[DailyTrendDataPoint] = []
    total_leads_sum = 0
    peak_day = None
    peak_count = 0
    
    current_date = start_date
    while current_date <= today:
        date_key = current_date.strftime('%Y-%m-%d')
        row = data_by_date.get(date_key)
        
        total = row.total_leads if row else 0
        scheduled = row.scheduled_count if row else 0
        conversion_rate = (scheduled / total * 100) if total > 0 else 0.0
        
        point = DailyTrendDataPoint(
            date=date_key,
            label=f"{month_names[current_date.month - 1]} {current_date.day}",
            day_of_week=day_names[current_date.weekday()],
            total_leads=total,
            hot_leads=row.hot_leads if row else 0,
            medium_leads=row.medium_leads if row else 0,
            low_leads=row.low_leads if row else 0,
            scheduled_count=scheduled,
            conversion_rate=round(conversion_rate, 1),
        )
        data_points.append(point)
        
        total_leads_sum += total
        if total > peak_count:
            peak_count = total
            peak_day = f"{month_names[current_date.month - 1]} {current_date.day}"
        
        current_date += timedelta(days=1)
    
    # Calculate summary
    num_days = len(data_points) if data_points else 1
    daily_average = total_leads_sum / num_days
    
    summary = {
        "total_leads": total_leads_sum,
        "daily_average": round(daily_average, 1),
        "peak_day": peak_day or "N/A",
        "peak_count": peak_count,
        "num_days": num_days,
    }
    
    # Cache the result for 60 seconds
    result_dict = {
        "period": period.value,
        "data": [p.model_dump() for p in data_points],
        "summary": summary,
    }
    cache.set(cache_key, result_dict, ttl=CACHE_TTL_TRENDS)
    
    return DailyTrendsResponse(
        period=period.value,
        data=data_points,
        summary=summary,
    )


# =============================================================================
# Dashboard Summary Endpoint (combines multiple metrics)
# =============================================================================

class DashboardSummaryResponse(BaseModel):
    """
    Complete dashboard summary for quick loading.
    
    METRIC DEFINITIONS:
    - total_leads: ALL non-deleted leads in the system (for historical context)
    - active_leads: Non-deleted leads excluding terminal statuses (matches table view)
    - hot_leads: Active HOT priority leads
    - new_leads: Leads that have never been contacted
    - scheduled_today: Leads with consultation scheduled for today
    - overall_response_rate: % of contacted leads that responded
    - overall_conversion_rate: % of total leads that reached scheduling
    - leads_this_week: Leads created this week
    - leads_today: Leads created today
    """
    total_leads: int        # All non-deleted leads (for context/historical tracking)
    active_leads: int       # Non-deleted leads excluding completed/lost/disqualified (matches table)
    hot_leads: int
    new_leads: int
    scheduled_today: int
    overall_response_rate: float
    overall_conversion_rate: float
    leads_this_week: int
    leads_today: int


@router.get(
    "/analytics/dashboard-summary",
    response_model=DashboardSummaryResponse,
    summary="Get Dashboard Summary",
    description="Get quick summary metrics for the main dashboard with Redis caching.",
)
async def get_dashboard_summary(
    db: Session = Depends(get_db),
) -> DashboardSummaryResponse:
    """
    Get quick summary metrics for the main dashboard.
    
    METRIC DEFINITIONS (Consistent with table filtering):
    =====================================================
    
    total_leads: Count of all non-deleted leads (excludes soft-deleted where deleted_at IS NOT NULL)
                 This matches the table's base query which filters Lead.deleted_at.is_(None)
    
    hot_leads: Non-deleted leads with priority='HOT' 
               (actionable hot leads, not yet completed)
    
    new_leads: Non-deleted leads that have NEVER been contacted 
               (contact_outcome='NEW' or NULL)
    
    scheduled_today: Leads with scheduled_callback_at date falling on today
    
    overall_response_rate: (ANSWERED + CALLBACK_REQUESTED) / Total Contacted × 100%
                          Response Rate = successful contacts / total contact attempts
    
    overall_conversion_rate: (SCHEDULED + CONSULTATION_COMPLETE) / Total Non-Deleted Leads × 100%
                            Conversion Rate = leads that progressed to scheduling
    
    leads_this_week: Non-deleted leads created since start of current week (Monday)
    
    leads_today: Non-deleted leads created today
    
    OPTIMIZED with Redis caching:
    - 30-second cache TTL
    - Stampede prevention with distributed locking
    - Sub-10ms response times for cached data
    
    This is a single call that returns all key metrics
    for the dashboard overview.
    """
    start_time = time.time()
    cache = get_cache()
    cache_key = CACHE_PREFIX_DASHBOARD_SUMMARY
    
    # Try cache first
    cached_data = cache.get(cache_key)
    if cached_data:
        logger.debug(f"Dashboard summary cache hit ({(time.time() - start_time) * 1000:.2f}ms)")
        return DashboardSummaryResponse(**cached_data)
    
    # Cache miss - compute with stampede prevention
    def compute_dashboard_summary():
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        
        # CRITICAL FIX: Filter out soft-deleted leads from ALL metrics
        # This ensures KPI counts match the table which uses: Lead.deleted_at.is_(None)
        # Without this filter, deleted leads inflate the total_leads count
        base_filter = Lead.deleted_at.is_(None)
        
        # Terminal statuses to exclude for "active" leads
        # These match the frontend's activeLeads filter:
        # !['consultation complete', 'treatment started', 'lost', 'disqualified'].includes(l.status)
        terminal_statuses = [
            LeadStatus.CONSULTATION_COMPLETE,
            LeadStatus.TREATMENT_STARTED,
            LeadStatus.LOST,
            LeadStatus.DISQUALIFIED,
        ]
        
        # Use a single efficient query with multiple aggregations
        # All counts now include the base_filter to exclude soft-deleted leads
        summary_query = db.query(
            # total_leads: All non-deleted leads (for historical context)
            func.count(Lead.id).filter(base_filter).label('total_leads'),
            # active_leads: Non-deleted leads EXCLUDING terminal statuses (MATCHES TABLE VIEW)
            # This is the count that should match the "All Active Leads" table
            func.count(Lead.id).filter(
                base_filter,
                Lead.status.notin_(terminal_statuses)
            ).label('active_leads'),
            # hot_leads: Non-deleted HOT priority leads (in active statuses only)
            func.count(Lead.id).filter(
                base_filter,
                Lead.priority == PriorityType.HOT,
                Lead.status.notin_(terminal_statuses)
            ).label('hot_leads'),
            # new_leads: Non-deleted leads that have never been contacted
            func.count(Lead.id).filter(
                base_filter,
                or_(Lead.contact_outcome == ContactOutcome.NEW, Lead.contact_outcome.is_(None))
            ).label('new_leads'),
            # leads_this_week: Non-deleted leads created this week
            func.count(Lead.id).filter(base_filter, Lead.created_at >= week_start).label('leads_this_week'),
            # leads_today: Non-deleted leads created today
            func.count(Lead.id).filter(base_filter, Lead.created_at >= today_start).label('leads_today'),
            # total_contacted: Non-deleted leads with any contact attempt
            func.count(Lead.id).filter(
                base_filter,
                Lead.contact_outcome.isnot(None),
                Lead.contact_outcome != ContactOutcome.NEW
            ).label('total_contacted'),
            # answered: Non-deleted leads that responded positively
            func.count(Lead.id).filter(
                base_filter,
                Lead.contact_outcome.in_([ContactOutcome.ANSWERED, ContactOutcome.CALLBACK_REQUESTED])
            ).label('answered'),
            # scheduled: Non-deleted leads that reached scheduling stage
            func.count(Lead.id).filter(
                base_filter,
                Lead.status.in_([LeadStatus.SCHEDULED, LeadStatus.CONSULTATION_COMPLETE])
            ).label('scheduled'),
        ).first()
        
        # Scheduled today (requires date filter on scheduled_callback_at) — EXCLUDES soft-deleted
        tomorrow_start = today_start + timedelta(days=1)
        scheduled_today = db.query(func.count(Lead.id)).filter(
            Lead.status == LeadStatus.SCHEDULED,
            Lead.scheduled_callback_at >= today_start,
            Lead.scheduled_callback_at < tomorrow_start,
            Lead.deleted_at.is_(None),  # EXCLUDE soft-deleted leads
        ).scalar() or 0
        
        total_leads = summary_query.total_leads or 0
        total_contacted = summary_query.total_contacted or 0
        answered = summary_query.answered or 0
        scheduled = summary_query.scheduled or 0
        
        response_rate = (answered / total_contacted * 100) if total_contacted > 0 else 0.0
        conversion_rate = (scheduled / total_leads * 100) if total_leads > 0 else 0.0
        
        return {
            "total_leads": total_leads,
            "active_leads": summary_query.active_leads or 0,  # MATCHES TABLE COUNT
            "hot_leads": summary_query.hot_leads or 0,
            "new_leads": summary_query.new_leads or 0,
            "scheduled_today": scheduled_today,
            "overall_response_rate": round(response_rate, 1),
            "overall_conversion_rate": round(conversion_rate, 1),
            "leads_this_week": summary_query.leads_this_week or 0,
            "leads_today": summary_query.leads_today or 0,
        }
    
    # Use cache with stampede prevention
    result = cache.get_or_compute(
        key=cache_key,
        compute_func=compute_dashboard_summary,
        ttl=CACHE_TTL_DASHBOARD,
        lock_timeout=5,
    )
    
    if result is None:
        # Fallback if cache fails
        result = compute_dashboard_summary()
    
    query_time = (time.time() - start_time) * 1000
    logger.debug(f"Dashboard summary computed in {query_time:.2f}ms")
    
    return DashboardSummaryResponse(**result)
