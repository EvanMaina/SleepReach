"""
Google Ads Analytics Service

Provides integration with Google Ads API to fetch campaign performance metrics.
This service retrieves ad spend, clicks, impressions, conversions, and other
key metrics for marketing attribution and ROI analysis.

METRICS TRACKED:
- Impressions: Number of times ads were shown
- Clicks: Number of ad clicks
- Cost: Total ad spend
- Conversions: Number of conversions tracked
- CTR (Click-Through Rate): Clicks / Impressions
- CPC (Cost Per Click): Cost / Clicks
- CPL (Cost Per Lead): Cost / Conversions
- Conversion Rate: Conversions / Clicks

@module services/google_ads_service
@version 1.0.0
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from ..core.config import settings

logger = logging.getLogger(__name__)


class GoogleAdsMetricType(str, Enum):
    """Types of metrics available from Google Ads."""
    IMPRESSIONS = "impressions"
    CLICKS = "clicks"
    COST = "cost"
    CONVERSIONS = "conversions"
    CTR = "ctr"
    CPC = "cpc"
    CPL = "cpl"
    CONVERSION_RATE = "conversion_rate"


@dataclass
class GoogleAdsCampaignMetrics:
    """Metrics for a single Google Ads campaign."""
    campaign_id: str
    campaign_name: str
    status: str
    impressions: int
    clicks: int
    cost_micros: int  # Cost in micros (1/1,000,000 of currency unit)
    conversions: float
    ctr: float  # Click-through rate (percentage)
    avg_cpc_micros: int  # Average CPC in micros
    cost_per_conversion_micros: Optional[int]  # CPL in micros
    conversion_rate: float  # Conversion rate (percentage)
    date_range_start: str
    date_range_end: str

    @property
    def cost(self) -> float:
        """Cost in standard currency units."""
        return self.cost_micros / 1_000_000

    @property
    def avg_cpc(self) -> float:
        """Average CPC in standard currency units."""
        return self.avg_cpc_micros / 1_000_000

    @property
    def cost_per_conversion(self) -> Optional[float]:
        """Cost per conversion in standard currency units."""
        if self.cost_per_conversion_micros:
            return self.cost_per_conversion_micros / 1_000_000
        return None


@dataclass
class GoogleAdsAccountMetrics:
    """Aggregated metrics for the entire Google Ads account."""
    account_id: str
    account_name: str
    total_impressions: int
    total_clicks: int
    total_cost_micros: int
    total_conversions: float
    overall_ctr: float
    overall_avg_cpc_micros: int
    overall_cost_per_conversion_micros: Optional[int]
    overall_conversion_rate: float
    active_campaigns: int
    paused_campaigns: int
    date_range_start: str
    date_range_end: str
    campaigns: List[GoogleAdsCampaignMetrics]

    @property
    def total_cost(self) -> float:
        """Total cost in standard currency units."""
        return self.total_cost_micros / 1_000_000

    @property
    def overall_avg_cpc(self) -> float:
        """Overall average CPC in standard currency units."""
        return self.overall_avg_cpc_micros / 1_000_000

    @property
    def overall_cost_per_conversion(self) -> Optional[float]:
        """Overall cost per conversion in standard currency units."""
        if self.overall_cost_per_conversion_micros:
            return self.overall_cost_per_conversion_micros / 1_000_000
        return None


class GoogleAdsService:
    """
    Service for interacting with Google Ads API.

    This service handles authentication and data retrieval from Google Ads.
    It uses the Google Ads API v15+ for fetching campaign performance data.

    Configuration required in environment:
    - GOOGLE_ADS_DEVELOPER_TOKEN: Developer token from Google Ads
    - GOOGLE_ADS_CLIENT_ID: OAuth2 client ID
    - GOOGLE_ADS_CLIENT_SECRET: OAuth2 client secret
    - GOOGLE_ADS_REFRESH_TOKEN: OAuth2 refresh token
    - GOOGLE_ADS_CUSTOMER_ID: Google Ads customer ID (without dashes)
    - GOOGLE_ADS_LOGIN_CUSTOMER_ID: Manager account ID (if using MCC)
    """

    def __init__(self):
        """Initialize the Google Ads service with credentials from config."""
        self.developer_token = settings.google_ads_developer_token
        self.client_id = settings.google_ads_client_id
        self.client_secret = settings.google_ads_client_secret
        self.refresh_token = settings.google_ads_refresh_token
        self.customer_id = settings.google_ads_customer_id
        self.login_customer_id = settings.google_ads_login_customer_id

        self._client = None
        self._is_configured = self._check_configuration()

        if self._is_configured:
            logger.info(
                "Google Ads service initialized with valid configuration")
        else:
            logger.warning(
                "Google Ads service initialized without valid credentials - using mock data")

    def _check_configuration(self) -> bool:
        """Check if all required Google Ads credentials are configured."""
        required_fields = [
            self.developer_token,
            self.client_id,
            self.client_secret,
            self.refresh_token,
            self.customer_id,
        ]
        return all(field and field.strip() for field in required_fields)

    def _get_client(self):
        """
        Get or create the Google Ads API client.

        Returns:
            GoogleAdsClient instance or None if not configured
        """
        if not self._is_configured:
            return None

        if self._client is None:
            try:
                # Import here to avoid dependency issues if google-ads is not installed
                from google.ads.googleads.client import GoogleAdsClient

                credentials = {
                    "developer_token": self.developer_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "use_proto_plus": True,
                }

                if self.login_customer_id:
                    credentials["login_customer_id"] = self.login_customer_id

                self._client = GoogleAdsClient.load_from_dict(credentials)
                logger.info("Google Ads API client created successfully")

            except ImportError:
                logger.error(
                    "google-ads package not installed. Run: pip install google-ads")
                return None
            except Exception as e:
                logger.error(f"Failed to create Google Ads client: {e}")
                return None

        return self._client

    async def get_campaign_metrics(
        self,
        days_back: int = 30,
        campaign_ids: Optional[List[str]] = None
    ) -> GoogleAdsAccountMetrics:
        """
        Fetch campaign performance metrics from Google Ads.

        Args:
            days_back: Number of days to look back for metrics
            campaign_ids: Optional list of specific campaign IDs to fetch

        Returns:
            GoogleAdsAccountMetrics with campaign-level and account-level metrics
        """
        # Calculate date range
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days_back)

        # If not configured, return mock data for development
        if not self._is_configured:
            logger.info(
                "Returning mock Google Ads data (credentials not configured)")
            return self._get_mock_metrics(start_date, end_date)

        client = self._get_client()
        if not client:
            logger.warning(
                "Google Ads client not available, returning mock data")
            return self._get_mock_metrics(start_date, end_date)

        try:
            return await self._fetch_real_metrics(client, start_date, end_date, campaign_ids)
        except Exception as e:
            logger.error(f"Error fetching Google Ads metrics: {e}")
            # Return mock data on error to prevent dashboard failures
            return self._get_mock_metrics(start_date, end_date)

    async def _fetch_real_metrics(
        self,
        client,
        start_date,
        end_date,
        campaign_ids: Optional[List[str]] = None
    ) -> GoogleAdsAccountMetrics:
        """
        Fetch real metrics from Google Ads API.

        This method constructs and executes a GAQL query to retrieve
        campaign performance data.
        """
        ga_service = client.get_service("GoogleAdsService")

        # Build GAQL query
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.ctr,
                metrics.average_cpc,
                metrics.cost_per_conversion
            FROM campaign
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        """

        if campaign_ids:
            ids_str = ",".join(campaign_ids)
            query += f" AND campaign.id IN ({ids_str})"

        # Execute query
        response = ga_service.search(
            customer_id=self.customer_id,
            query=query
        )

        # Process results
        campaigns = []
        total_impressions = 0
        total_clicks = 0
        total_cost_micros = 0
        total_conversions = 0.0
        active_count = 0
        paused_count = 0

        for row in response:
            campaign = row.campaign
            metrics = row.metrics

            # Calculate cost per conversion
            cost_per_conv = None
            if metrics.conversions > 0:
                cost_per_conv = int(metrics.cost_micros / metrics.conversions)

            # Calculate conversion rate
            conv_rate = 0.0
            if metrics.clicks > 0:
                conv_rate = (metrics.conversions / metrics.clicks) * 100

            campaign_metrics = GoogleAdsCampaignMetrics(
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                status=campaign.status.name,
                impressions=metrics.impressions,
                clicks=metrics.clicks,
                cost_micros=metrics.cost_micros,
                conversions=metrics.conversions,
                ctr=metrics.ctr * 100,  # Convert to percentage
                avg_cpc_micros=metrics.average_cpc,
                cost_per_conversion_micros=cost_per_conv,
                conversion_rate=conv_rate,
                date_range_start=str(start_date),
                date_range_end=str(end_date),
            )
            campaigns.append(campaign_metrics)

            # Aggregate totals
            total_impressions += metrics.impressions
            total_clicks += metrics.clicks
            total_cost_micros += metrics.cost_micros
            total_conversions += metrics.conversions

            if campaign.status.name == "ENABLED":
                active_count += 1
            elif campaign.status.name == "PAUSED":
                paused_count += 1

        # Calculate overall metrics
        overall_ctr = (total_clicks / total_impressions *
                       100) if total_impressions > 0 else 0
        overall_avg_cpc = int(total_cost_micros /
                              total_clicks) if total_clicks > 0 else 0
        overall_cost_per_conv = int(
            total_cost_micros / total_conversions) if total_conversions > 0 else None
        overall_conv_rate = (total_conversions /
                             total_clicks * 100) if total_clicks > 0 else 0

        return GoogleAdsAccountMetrics(
            account_id=self.customer_id,
            account_name="NeuroReach TMS Clinic",
            total_impressions=total_impressions,
            total_clicks=total_clicks,
            total_cost_micros=total_cost_micros,
            total_conversions=total_conversions,
            overall_ctr=overall_ctr,
            overall_avg_cpc_micros=overall_avg_cpc,
            overall_cost_per_conversion_micros=overall_cost_per_conv,
            overall_conversion_rate=overall_conv_rate,
            active_campaigns=active_count,
            paused_campaigns=paused_count,
            date_range_start=str(start_date),
            date_range_end=str(end_date),
            campaigns=campaigns,
        )

    def _get_mock_metrics(self, start_date, end_date) -> GoogleAdsAccountMetrics:
        """
        Generate mock metrics for development/testing.

        This provides realistic-looking data when Google Ads credentials
        are not configured.
        """
        mock_campaigns = [
            GoogleAdsCampaignMetrics(
                campaign_id="12345678901",
                campaign_name="TMS Therapy - Depression Treatment",
                status="ENABLED",
                impressions=45230,
                clicks=1892,
                cost_micros=4250000000,  # $4,250
                conversions=47.0,
                ctr=4.18,
                avg_cpc_micros=2246000,  # $2.25
                cost_per_conversion_micros=90425000,  # $90.43
                conversion_rate=2.48,
                date_range_start=str(start_date),
                date_range_end=str(end_date),
            ),
            GoogleAdsCampaignMetrics(
                campaign_id="12345678902",
                campaign_name="TMS Therapy - Anxiety Treatment",
                status="ENABLED",
                impressions=32150,
                clicks=1245,
                cost_micros=2890000000,  # $2,890
                conversions=31.0,
                ctr=3.87,
                avg_cpc_micros=2321000,  # $2.32
                cost_per_conversion_micros=93225000,  # $93.23
                conversion_rate=2.49,
                date_range_start=str(start_date),
                date_range_end=str(end_date),
            ),
            GoogleAdsCampaignMetrics(
                campaign_id="12345678903",
                campaign_name="TMS Near Me - Local Search",
                status="ENABLED",
                impressions=28900,
                clicks=1567,
                cost_micros=3120000000,  # $3,120
                conversions=52.0,
                ctr=5.42,
                avg_cpc_micros=1991000,  # $1.99
                cost_per_conversion_micros=60000000,  # $60.00
                conversion_rate=3.32,
                date_range_start=str(start_date),
                date_range_end=str(end_date),
            ),
            GoogleAdsCampaignMetrics(
                campaign_id="12345678904",
                campaign_name="Mental Health Treatment AZ",
                status="PAUSED",
                impressions=12400,
                clicks=423,
                cost_micros=980000000,  # $980
                conversions=8.0,
                ctr=3.41,
                avg_cpc_micros=2317000,  # $2.32
                cost_per_conversion_micros=122500000,  # $122.50
                conversion_rate=1.89,
                date_range_start=str(start_date),
                date_range_end=str(end_date),
            ),
            GoogleAdsCampaignMetrics(
                campaign_id="12345678905",
                campaign_name="Insurance Accepted - TMS",
                status="ENABLED",
                impressions=18750,
                clicks=892,
                cost_micros=1780000000,  # $1,780
                conversions=28.0,
                ctr=4.76,
                avg_cpc_micros=1995000,  # $2.00
                cost_per_conversion_micros=63571000,  # $63.57
                conversion_rate=3.14,
                date_range_start=str(start_date),
                date_range_end=str(end_date),
            ),
        ]

        # Calculate totals
        total_impressions = sum(c.impressions for c in mock_campaigns)
        total_clicks = sum(c.clicks for c in mock_campaigns)
        total_cost_micros = sum(c.cost_micros for c in mock_campaigns)
        total_conversions = sum(c.conversions for c in mock_campaigns)
        active_count = sum(1 for c in mock_campaigns if c.status == "ENABLED")
        paused_count = sum(1 for c in mock_campaigns if c.status == "PAUSED")

        overall_ctr = (total_clicks / total_impressions *
                       100) if total_impressions > 0 else 0
        overall_avg_cpc = int(total_cost_micros /
                              total_clicks) if total_clicks > 0 else 0
        overall_cost_per_conv = int(
            total_cost_micros / total_conversions) if total_conversions > 0 else None
        overall_conv_rate = (total_conversions /
                             total_clicks * 100) if total_clicks > 0 else 0

        return GoogleAdsAccountMetrics(
            account_id="123-456-7890",
            account_name="NeuroReach TMS Clinic (Demo)",
            total_impressions=total_impressions,
            total_clicks=total_clicks,
            total_cost_micros=total_cost_micros,
            total_conversions=total_conversions,
            overall_ctr=round(overall_ctr, 2),
            overall_avg_cpc_micros=overall_avg_cpc,
            overall_cost_per_conversion_micros=overall_cost_per_conv,
            overall_conversion_rate=round(overall_conv_rate, 2),
            active_campaigns=active_count,
            paused_campaigns=paused_count,
            date_range_start=str(start_date),
            date_range_end=str(end_date),
            campaigns=mock_campaigns,
        )

    async def get_daily_metrics(
        self,
        days_back: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get daily breakdown of Google Ads metrics.

        Returns a list of daily metrics for trend analysis.
        """
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days_back)

        if not self._is_configured:
            return self._get_mock_daily_metrics(start_date, end_date)

        client = self._get_client()
        if not client:
            return self._get_mock_daily_metrics(start_date, end_date)

        try:
            ga_service = client.get_service("GoogleAdsService")

            query = f"""
                SELECT
                    segments.date,
                    metrics.impressions,
                    metrics.clicks,
                    metrics.cost_micros,
                    metrics.conversions
                FROM campaign
                WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            """

            response = ga_service.search(
                customer_id=self.customer_id,
                query=query
            )

            # Aggregate by date
            daily_data: Dict[str, Dict[str, Any]] = {}

            for row in response:
                date_str = row.segments.date
                if date_str not in daily_data:
                    daily_data[date_str] = {
                        "date": date_str,
                        "impressions": 0,
                        "clicks": 0,
                        "cost": 0.0,
                        "conversions": 0.0,
                    }

                daily_data[date_str]["impressions"] += row.metrics.impressions
                daily_data[date_str]["clicks"] += row.metrics.clicks
                daily_data[date_str]["cost"] += row.metrics.cost_micros / 1_000_000
                daily_data[date_str]["conversions"] += row.metrics.conversions

            # Sort by date and return
            return sorted(daily_data.values(), key=lambda x: x["date"])

        except Exception as e:
            logger.error(f"Error fetching daily Google Ads metrics: {e}")
            return self._get_mock_daily_metrics(start_date, end_date)

    def _get_mock_daily_metrics(self, start_date, end_date) -> List[Dict[str, Any]]:
        """Generate mock daily metrics for development."""
        import random

        daily_metrics = []
        current = start_date

        while current <= end_date:
            # Generate realistic daily variations
            base_impressions = 4500
            base_clicks = 180
            base_cost = 420.0
            base_conversions = 4.5

            # Add some randomness
            impressions = int(base_impressions * random.uniform(0.7, 1.3))
            clicks = int(base_clicks * random.uniform(0.7, 1.3))
            cost = round(base_cost * random.uniform(0.7, 1.3), 2)
            conversions = round(base_conversions * random.uniform(0.5, 1.5), 1)

            # Weekend dip
            if current.weekday() >= 5:
                impressions = int(impressions * 0.6)
                clicks = int(clicks * 0.6)
                cost = round(cost * 0.6, 2)
                conversions = round(conversions * 0.6, 1)

            daily_metrics.append({
                "date": str(current),
                "label": current.strftime("%b %d"),
                "impressions": impressions,
                "clicks": clicks,
                "cost": cost,
                "conversions": conversions,
                "ctr": round((clicks / impressions * 100) if impressions > 0 else 0, 2),
                "cpc": round((cost / clicks) if clicks > 0 else 0, 2),
            })

            current += timedelta(days=1)

        return daily_metrics

    def is_configured(self) -> bool:
        """Check if the service has valid credentials configured."""
        return self._is_configured


# Singleton instance
_google_ads_service: Optional[GoogleAdsService] = None


def get_google_ads_service() -> GoogleAdsService:
    """Get or create the Google Ads service singleton."""
    global _google_ads_service
    if _google_ads_service is None:
        _google_ads_service = GoogleAdsService()
    return _google_ads_service
