"""
Platform Analytics Service.

High-performance analytics service for platform performance metrics.
Uses materialized views and Redis caching for sub-200ms response times.
Designed to handle 10M+ leads with zero lag.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.database import get_db
from .cache import get_cache, CacheService


logger = logging.getLogger(__name__)


# Cache TTLs
CACHE_TTL_PLATFORM_SUMMARY = 300  # 5 minutes
CACHE_TTL_PLATFORM_TRENDS = 300  # 5 minutes
CACHE_TTL_PLATFORM_ACTIVITY = 60  # 1 minute
CACHE_TTL_PLATFORM_INSIGHTS = 300  # 5 minutes


class PlatformAnalyticsService:
    """
    Service for retrieving platform performance analytics.
    
    Leverages PostgreSQL materialized views for pre-aggregated data
    and Redis caching for minimal latency. Designed for:
    - Sub-200ms API response times
    - Support for millions of leads
    - Real-time dashboard updates
    """
    
    # Cache key prefixes
    PREFIX = "neuroreach:platform"
    
    def __init__(self, db: Session, cache: Optional[CacheService] = None):
        """
        Initialize service with database session and cache.
        
        Args:
            db: SQLAlchemy database session
            cache: Optional cache service (uses global if not provided)
        """
        self.db = db
        self.cache = cache or get_cache()
    
    # =========================================================================
    # Platform Summary Analytics
    # =========================================================================
    
    def get_platform_summary(self, period: str = "30d") -> Dict[str, Any]:
        """
        Get comprehensive platform analytics summary.
        
        Returns aggregated metrics for all platforms including:
        - Total leads per platform
        - Conversion rates
        - Quality distribution
        - Growth metrics
        
        Args:
            period: Time period (7d, 30d, 90d, all)
            
        Returns:
            Platform analytics summary dictionary
        """
        cache_key = f"{self.PREFIX}:summary:{period}"
        
        # Try cache first
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Get data from materialized views
        platforms = self._get_platform_stats()
        status_distribution = self._get_status_distribution()
        priority_distribution = self._get_priority_distribution()
        daily_trends = self._get_daily_trends(self._period_to_days(period))
        growth_metrics = self._get_growth_metrics()
        
        # Build response
        response = self._build_summary_response(
            platforms=platforms,
            status_distribution=status_distribution,
            priority_distribution=priority_distribution,
            daily_trends=daily_trends,
            growth_metrics=growth_metrics,
            period=period
        )
        
        # Cache result
        self.cache.set(cache_key, response, ttl=CACHE_TTL_PLATFORM_SUMMARY)
        
        return response
    
    def _get_platform_stats(self) -> List[Dict[str, Any]]:
        """Get platform stats from materialized view."""
        try:
            result = self.db.execute(text("""
                SELECT 
                    source,
                    total_leads,
                    converted_leads,
                    conversion_rate,
                    hot_leads,
                    medium_leads,
                    low_leads,
                    contacted_leads,
                    contact_rate,
                    avg_quality_score,
                    avg_days_to_convert,
                    avg_hours_to_contact,
                    last_lead_at,
                    first_lead_at,
                    refreshed_at
                FROM mv_platform_analytics
                ORDER BY total_leads DESC
            """))
            
            rows = result.fetchall()
            return [self._row_to_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching platform stats: {e}")
            return []
    
    def _get_status_distribution(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get status distribution by platform."""
        try:
            result = self.db.execute(text("""
                SELECT source, status, count, percentage
                FROM mv_platform_status_distribution
                ORDER BY source, 
                    CASE status
                        WHEN 'NEW' THEN 1
                        WHEN 'CONTACTED' THEN 2
                        WHEN 'SCHEDULED' THEN 3
                        WHEN 'CONSULTATION_COMPLETE' THEN 4
                        WHEN 'TREATMENT_STARTED' THEN 5
                        WHEN 'LOST' THEN 6
                        WHEN 'DISQUALIFIED' THEN 7
                        ELSE 8
                    END
            """))
            
            rows = result.fetchall()
            distribution = {}
            for row in rows:
                source = row[0]
                if source not in distribution:
                    distribution[source] = []
                distribution[source].append({
                    "status": row[1],
                    "count": int(row[2]),
                    "percentage": float(row[3]) if row[3] else 0
                })
            return distribution
        except Exception as e:
            logger.error(f"Error fetching status distribution: {e}")
            return {}
    
    def _get_priority_distribution(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get priority distribution by platform."""
        try:
            result = self.db.execute(text("""
                SELECT source, priority, count, percentage
                FROM mv_platform_priority_distribution
                ORDER BY source,
                    CASE priority
                        WHEN 'HOT' THEN 1
                        WHEN 'MEDIUM' THEN 2
                        WHEN 'LOW' THEN 3
                        WHEN 'DISQUALIFIED' THEN 4
                        ELSE 5
                    END
            """))
            
            rows = result.fetchall()
            distribution = {}
            for row in rows:
                source = row[0]
                if source not in distribution:
                    distribution[source] = []
                distribution[source].append({
                    "priority": row[1],
                    "count": int(row[2]),
                    "percentage": float(row[3]) if row[3] else 0
                })
            return distribution
        except Exception as e:
            logger.error(f"Error fetching priority distribution: {e}")
            return {}
    
    def _get_daily_trends(self, days: int = 30) -> Dict[str, List[Dict[str, Any]]]:
        """Get daily trends by platform."""
        try:
            result = self.db.execute(text("""
                SELECT 
                    source, 
                    lead_date, 
                    total_leads, 
                    converted_leads, 
                    hot_leads,
                    contacted_leads
                FROM mv_platform_daily_stats
                WHERE lead_date >= CURRENT_DATE - :days
                ORDER BY lead_date ASC, source
            """), {"days": days})
            
            rows = result.fetchall()
            trends = {}
            for row in rows:
                source = row[0]
                if source not in trends:
                    trends[source] = []
                trends[source].append({
                    "date": row[1].isoformat() if row[1] else None,
                    "total_leads": int(row[2]),
                    "converted_leads": int(row[3]),
                    "hot_leads": int(row[4]),
                    "contacted_leads": int(row[5])
                })
            return trends
        except Exception as e:
            logger.error(f"Error fetching daily trends: {e}")
            return {}
    
    def _get_growth_metrics(self, weeks: int = 8) -> Dict[str, List[Dict[str, Any]]]:
        """Get week-over-week growth metrics."""
        try:
            result = self.db.execute(text("""
                WITH weekly_with_lag AS (
                    SELECT 
                        source,
                        week_start,
                        total_leads,
                        conversion_rate,
                        LAG(total_leads) OVER (PARTITION BY source ORDER BY week_start) as prev_week
                    FROM mv_platform_weekly_stats
                    WHERE week_start >= CURRENT_DATE - :days
                )
                SELECT 
                    source,
                    week_start,
                    total_leads,
                    COALESCE(prev_week, 0) as prev_week_leads,
                    ROUND(
                        (total_leads - COALESCE(prev_week, 0))::DECIMAL / 
                        NULLIF(COALESCE(prev_week, 0), 0) * 100,
                        2
                    ) as wow_growth,
                    conversion_rate
                FROM weekly_with_lag
                ORDER BY week_start DESC, source
            """), {"days": weeks * 7})
            
            rows = result.fetchall()
            growth = {}
            for row in rows:
                source = row[0]
                if source not in growth:
                    growth[source] = []
                growth[source].append({
                    "week_start": row[1].isoformat() if row[1] else None,
                    "total_leads": int(row[2]),
                    "prev_week_leads": int(row[3]),
                    "wow_growth": float(row[4]) if row[4] else 0,
                    "conversion_rate": float(row[5]) if row[5] else 0
                })
            return growth
        except Exception as e:
            logger.error(f"Error fetching growth metrics: {e}")
            return {}
    
    def _build_summary_response(
        self,
        platforms: List[Dict],
        status_distribution: Dict,
        priority_distribution: Dict,
        daily_trends: Dict,
        growth_metrics: Dict,
        period: str
    ) -> Dict[str, Any]:
        """Build the summary response structure."""
        
        # Get platform configurations
        platform_configs = self._get_platform_configs()
        
        # Calculate totals
        totals = self._calculate_totals(platforms)
        
        # Build platform details
        platform_details = []
        for platform in platforms:
            source = platform.get("source", "unknown")
            config = platform_configs.get(source, {})
            
            platform_details.append({
                "id": source,
                "displayName": config.get("display_name", source.title()),
                "icon": config.get("icon", "link"),
                "color": config.get("color", "#6B7280"),
                "status": config.get("status", "unknown"),
                "metrics": {
                    "totalLeads": platform.get("total_leads", 0),
                    "convertedLeads": platform.get("converted_leads", 0),
                    "conversionRate": platform.get("conversion_rate", 0),
                    "hotLeads": platform.get("hot_leads", 0),
                    "mediumLeads": platform.get("medium_leads", 0),
                    "lowLeads": platform.get("low_leads", 0),
                    "contactedLeads": platform.get("contacted_leads", 0),
                    "contactRate": platform.get("contact_rate", 0),
                    "qualityScore": platform.get("avg_quality_score", 0),
                    "avgDaysToConvert": platform.get("avg_days_to_convert"),
                    "avgHoursToContact": platform.get("avg_hours_to_contact"),
                    "lastLeadAt": platform.get("last_lead_at"),
                    "firstLeadAt": platform.get("first_lead_at"),
                },
                "statusDistribution": status_distribution.get(source, []),
                "priorityDistribution": priority_distribution.get(source, []),
                "dailyTrend": daily_trends.get(source, []),
                "growthMetrics": growth_metrics.get(source, []),
            })
        
        # Generate insights
        insights = self._generate_insights(platforms, growth_metrics)
        
        return {
            "platforms": platform_details,
            "totals": totals,
            "insights": insights,
            "period": {
                "value": period,
                "days": self._period_to_days(period),
                "label": self._period_to_label(period)
            },
            "refreshedAt": platforms[0].get("refreshed_at") if platforms else datetime.utcnow().isoformat()
        }
    
    def _get_platform_configs(self) -> Dict[str, Dict]:
        """Get platform configurations from database."""
        try:
            result = self.db.execute(text("""
                SELECT id, display_name, icon, color, status
                FROM platforms
            """))
            
            configs = {}
            for row in result.fetchall():
                configs[row[0]] = {
                    "display_name": row[1],
                    "icon": row[2],
                    "color": row[3],
                    "status": row[4]
                }
            return configs
        except Exception as e:
            logger.warning(f"Error fetching platform configs: {e}")
            # Return defaults
            return {
                "widget": {"display_name": "Website Widget", "icon": "widget", "color": "#6366F1", "status": "active"},
                "jotform": {"display_name": "JotForm", "icon": "clipboard-list", "color": "#F59E0B", "status": "pending_integration"},
                "google_ads": {"display_name": "Google Ads", "icon": "megaphone", "color": "#EF4444", "status": "pending_integration"},
                "manual": {"display_name": "Manual Entry", "icon": "pencil", "color": "#10B981", "status": "active"},
                "api": {"display_name": "API", "icon": "code", "color": "#8B5CF6", "status": "active"},
                "import": {"display_name": "Import", "icon": "upload", "color": "#06B6D4", "status": "active"},
            }
    
    def _calculate_totals(self, platforms: List[Dict]) -> Dict[str, Any]:
        """Calculate total metrics across all platforms."""
        totals = {
            "totalLeads": 0,
            "convertedLeads": 0,
            "hotLeads": 0,
            "mediumLeads": 0,
            "lowLeads": 0,
            "contactedLeads": 0,
        }
        
        for platform in platforms:
            totals["totalLeads"] += platform.get("total_leads", 0) or 0
            totals["convertedLeads"] += platform.get("converted_leads", 0) or 0
            totals["hotLeads"] += platform.get("hot_leads", 0) or 0
            totals["mediumLeads"] += platform.get("medium_leads", 0) or 0
            totals["lowLeads"] += platform.get("low_leads", 0) or 0
            totals["contactedLeads"] += platform.get("contacted_leads", 0) or 0
        
        # Calculate rates
        if totals["totalLeads"] > 0:
            totals["conversionRate"] = round(
                totals["convertedLeads"] * 100 / totals["totalLeads"], 2
            )
            totals["contactRate"] = round(
                totals["contactedLeads"] * 100 / totals["totalLeads"], 2
            )
        else:
            totals["conversionRate"] = 0
            totals["contactRate"] = 0
        
        return totals
    
    def _generate_insights(
        self, 
        platforms: List[Dict], 
        growth_metrics: Dict
    ) -> List[Dict[str, Any]]:
        """Generate AI-like insights from platform data."""
        insights = []
        
        if not platforms:
            return insights
        
        # Best converter
        active_platforms = [p for p in platforms if (p.get("total_leads") or 0) >= 10]
        if active_platforms:
            best_converter = max(
                active_platforms, 
                key=lambda p: p.get("conversion_rate") or 0
            )
            if best_converter.get("conversion_rate", 0) > 0:
                insights.append({
                    "type": "best_converter",
                    "platform": best_converter.get("source"),
                    "title": "Top Converter",
                    "description": f"{best_converter.get('source', '').title()} has the highest conversion rate at {best_converter.get('conversion_rate')}%",
                    "metricValue": best_converter.get("conversion_rate"),
                    "trend": "positive",
                    "priority": "high"
                })
        
        # Fastest growing
        if growth_metrics:
            latest_growth = {}
            for source, weeks in growth_metrics.items():
                if weeks:
                    latest_growth[source] = weeks[0].get("wow_growth", 0) or 0
            
            if latest_growth:
                fastest = max(latest_growth.items(), key=lambda x: x[1])
                if fastest[1] > 0:
                    insights.append({
                        "type": "fastest_growing",
                        "platform": fastest[0],
                        "title": "Fastest Growth",
                        "description": f"{fastest[0].title()} grew {fastest[1]}% this week",
                        "metricValue": fastest[1],
                        "trend": "positive" if fastest[1] > 0 else "negative",
                        "priority": "high"
                    })
        
        # Highest quality
        if active_platforms:
            highest_quality = max(
                active_platforms,
                key=lambda p: p.get("avg_quality_score") or 0
            )
            if highest_quality.get("avg_quality_score", 0) > 0:
                insights.append({
                    "type": "highest_quality",
                    "platform": highest_quality.get("source"),
                    "title": "Best Quality Leads",
                    "description": f"{highest_quality.get('source', '').title()} delivers the highest quality score ({highest_quality.get('avg_quality_score')})",
                    "metricValue": highest_quality.get("avg_quality_score"),
                    "trend": "positive",
                    "priority": "medium"
                })
        
        # Needs attention
        low_converters = [
            p for p in active_platforms 
            if (p.get("conversion_rate") or 0) < 10 and (p.get("conversion_rate") or 0) > 0
        ]
        if low_converters:
            worst = min(low_converters, key=lambda p: p.get("conversion_rate") or 0)
            insights.append({
                "type": "needs_attention",
                "platform": worst.get("source"),
                "title": "Needs Attention",
                "description": f"{worst.get('source', '').title()} has low conversion rate ({worst.get('conversion_rate')}%) - consider optimizing",
                "metricValue": worst.get("conversion_rate"),
                "trend": "negative",
                "priority": "high"
            })
        
        return insights
    
    # =========================================================================
    # Platform Activity Feed
    # =========================================================================
    
    def get_recent_activity(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
        platform: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get recent lead activity with cursor-based pagination.
        
        Uses cursor pagination for consistent performance with large datasets.
        
        Args:
            limit: Number of activities to return
            cursor: Pagination cursor
            platform: Filter by platform (optional)
            
        Returns:
            Activity feed with pagination info
        """
        cache_key = f"{self.PREFIX}:activity:{platform or 'all'}:{cursor or 'first'}:{limit}"
        
        # Try cache for non-cursor requests
        if not cursor:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        
        # Build query
        params = {"limit": limit + 1}  # Fetch one extra to check if there's more
        
        cursor_condition = ""
        if cursor:
            timestamp, lead_id = self._decode_cursor(cursor)
            cursor_condition = "AND (created_at, id) < (:cursor_ts, :cursor_id::uuid)"
            params["cursor_ts"] = timestamp
            params["cursor_id"] = lead_id
        
        platform_condition = ""
        if platform and platform != "all":
            platform_condition = "AND source = :platform"
            params["platform"] = platform
        
        # EXCLUDE soft-deleted leads — deleted_at IS NULL guard is mandatory
        query = f"""
            SELECT 
                id,
                lead_number,
                source,
                status,
                priority,
                condition,
                created_at,
                updated_at,
                contact_outcome
            FROM leads
            WHERE deleted_at IS NULL {cursor_condition} {platform_condition}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
        """
        
        try:
            result = self.db.execute(text(query), params)
            rows = result.fetchall()
            
            has_more = len(rows) > limit
            activities = rows[:limit]
            
            activity_list = []
            for row in activities:
                activity_list.append({
                    "id": str(row[0]),
                    "leadNumber": row[1],
                    "platform": row[2],
                    "status": row[3],
                    "priority": row[4],
                    "condition": row[5],
                    "createdAt": row[6].isoformat() if row[6] else None,
                    "updatedAt": row[7].isoformat() if row[7] else None,
                    "contactOutcome": row[8],
                })
            
            next_cursor = None
            if has_more and activity_list:
                last = activities[-1]
                next_cursor = self._encode_cursor(last[6], str(last[0]))
            
            response = {
                "activities": activity_list,
                "hasMore": has_more,
                "nextCursor": next_cursor,
                "platform": platform or "all"
            }
            
            # Cache first page only
            if not cursor:
                self.cache.set(cache_key, response, ttl=CACHE_TTL_PLATFORM_ACTIVITY)
            
            return response
            
        except Exception as e:
            logger.error(f"Error fetching activity feed: {e}")
            return {
                "activities": [],
                "hasMore": False,
                "nextCursor": None,
                "platform": platform or "all"
            }
    
    # =========================================================================
    # Materialized View Refresh
    # =========================================================================
    
    def refresh_materialized_views(self) -> Dict[str, Any]:
        """
        Refresh all platform analytics materialized views.
        
        Should be called via Celery task every 5 minutes.
        
        Returns:
            Refresh status and timing information
        """
        try:
            result = self.db.execute(text("SELECT * FROM refresh_platform_analytics_views()"))
            
            refresh_results = []
            for row in result.fetchall():
                refresh_results.append({
                    "view_name": row[0],
                    "duration_ms": row[1],
                    "status": row[2]
                })
            
            self.db.commit()
            
            # Invalidate caches
            self._invalidate_platform_caches()
            
            return {
                "success": True,
                "refreshed_at": datetime.utcnow().isoformat(),
                "views": refresh_results
            }
        except Exception as e:
            logger.error(f"Error refreshing materialized views: {e}")
            self.db.rollback()
            return {
                "success": False,
                "error": str(e),
                "refreshed_at": datetime.utcnow().isoformat()
            }
    
    def _invalidate_platform_caches(self) -> None:
        """Invalidate all platform-related caches."""
        patterns = [
            f"{self.PREFIX}:summary:*",
            f"{self.PREFIX}:trends:*",
            f"{self.PREFIX}:activity:*",
            f"{self.PREFIX}:insights:*",
        ]
        for pattern in patterns:
            self.cache.delete_pattern(pattern)
        logger.info("Platform analytics caches invalidated")
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert SQLAlchemy row to dictionary."""
        return {
            "source": row[0],
            "total_leads": int(row[1]) if row[1] else 0,
            "converted_leads": int(row[2]) if row[2] else 0,
            "conversion_rate": float(row[3]) if row[3] else 0,
            "hot_leads": int(row[4]) if row[4] else 0,
            "medium_leads": int(row[5]) if row[5] else 0,
            "low_leads": int(row[6]) if row[6] else 0,
            "contacted_leads": int(row[7]) if row[7] else 0,
            "contact_rate": float(row[8]) if row[8] else 0,
            "avg_quality_score": float(row[9]) if row[9] else None,
            "avg_days_to_convert": float(row[10]) if row[10] else None,
            "avg_hours_to_contact": float(row[11]) if row[11] else None,
            "last_lead_at": row[12].isoformat() if row[12] else None,
            "first_lead_at": row[13].isoformat() if row[13] else None,
            "refreshed_at": row[14].isoformat() if row[14] else None,
        }
    
    def _period_to_days(self, period: str) -> int:
        """Convert period string to days."""
        mapping = {
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "all": 3650,  # ~10 years
        }
        return mapping.get(period, 30)
    
    def _period_to_label(self, period: str) -> str:
        """Convert period string to display label."""
        mapping = {
            "7d": "Last 7 Days",
            "30d": "Last 30 Days",
            "90d": "Last 90 Days",
            "all": "All Time",
        }
        return mapping.get(period, "Last 30 Days")
    
    def _encode_cursor(self, timestamp: datetime, lead_id: str) -> str:
        """Encode cursor for pagination."""
        import base64
        cursor_str = f"{timestamp.isoformat()}:{lead_id}"
        return base64.b64encode(cursor_str.encode()).decode()
    
    def _decode_cursor(self, cursor: str) -> Tuple[str, str]:
        """Decode cursor for pagination."""
        import base64
        try:
            decoded = base64.b64decode(cursor.encode()).decode()
            parts = decoded.split(":", 1)
            return parts[0], parts[1]
        except Exception:
            raise ValueError("Invalid cursor")


# =============================================================================
# Service Factory
# =============================================================================

def get_platform_analytics_service(db: Session) -> PlatformAnalyticsService:
    """
    Factory function to create PlatformAnalyticsService instance.
    
    Args:
        db: SQLAlchemy database session
        
    Returns:
        PlatformAnalyticsService instance
    """
    return PlatformAnalyticsService(db)
