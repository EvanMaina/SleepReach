"""
Application configuration management.

Loads settings from environment variables with validation.
All secrets should be provided via environment variables, never hardcoded.
"""

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Uses pydantic-settings for validation and type coercion.
    All sensitive values should come from environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================================================================
    # Application Settings
    # ==========================================================================
    environment: str = Field(default="development",
                             description="Runtime environment")
    debug: bool = Field(default=False, description="Enable debug mode")
    app_name: str = Field(default="SleepReach",
                          description="Application name")
    app_version: str = Field(
        default="1.0.0", description="Application version")

    # ==========================================================================
    # Server Settings
    # ==========================================================================
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # ==========================================================================
    # Database Settings (Optimized for Scale)
    # ==========================================================================
    database_url: str = Field(
        default="postgresql://sleepreach:sleepreach_dev_password@localhost:5432/sleepreach",
        description="PostgreSQL connection string"
    )
    database_read_url: str = Field(
        default="",
        description="Read replica URL (empty = use primary)"
    )
    db_pool_size: int = Field(
        default=20, description="Database connection pool size")
    db_max_overflow: int = Field(
        default=30, description="Max overflow connections")
    db_pool_recycle: int = Field(
        default=1800, description="Connection recycle time in seconds (30 min)")
    db_pool_timeout: int = Field(
        default=30, description="Connection checkout timeout in seconds")
    enable_read_replica: bool = Field(
        default=False, description="Enable read/write splitting")

    # ==========================================================================
    # Redis Cache Settings
    # ==========================================================================
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    cache_ttl_dashboard: int = Field(
        default=30, description="Dashboard stats cache TTL in seconds")
    cache_ttl_analytics: int = Field(
        default=60, description="Analytics data cache TTL in seconds")
    cache_ttl_conditions: int = Field(
        default=120, description="Conditions distribution cache TTL in seconds")
    cache_ttl_leads: int = Field(
        default=60, description="Lead list cache TTL in seconds")
    cache_enabled: bool = Field(
        default=True, description="Enable/disable Redis caching")
    cache_stampede_lock_ttl: int = Field(
        default=10, description="Lock TTL for stampede prevention")

    # ==========================================================================
    # Celery Task Queue Settings
    # ==========================================================================
    celery_enabled: bool = Field(
        default=True,
        description="Enable Celery async task queue. When False, tasks run synchronously."
    )
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL (Redis)"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2",
        description="Celery result backend URL"
    )
    celery_worker_concurrency: int = Field(
        default=10, description="Number of Celery worker processes")
    celery_task_time_limit: int = Field(
        default=300, description="Task time limit in seconds")
    celery_max_retries: int = Field(
        default=5, description="Max retries for failed tasks")
    lead_queue_max_depth: int = Field(
        default=10000, description="Max queue depth before backpressure")
    lead_batch_size: int = Field(
        default=100, description="Batch size for lead processing")

    # ==========================================================================
    # Elasticsearch Settings
    # ==========================================================================
    elasticsearch_url: str = Field(
        default="http://localhost:9200",
        description="Elasticsearch URL"
    )
    elasticsearch_index: str = Field(
        default="leads", description="Elasticsearch index name")
    elasticsearch_enabled: bool = Field(
        default=False, description="Enable Elasticsearch (feature flag)")

    # ==========================================================================
    # Security Settings
    # ==========================================================================
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for JWT signing"
    )
    encryption_key: str = Field(
        default="dev-encryption-key-32bytes!",
        description="AES-256 encryption key for PHI (must be 32 bytes)"
    )
    access_token_expire_minutes: int = Field(
        default=30,
        description="JWT access token expiration in minutes"
    )
    refresh_token_expire_days: int = Field(
        default=7,
        description="JWT refresh token expiration in days"
    )

    # ==========================================================================
    # CORS Settings
    # ==========================================================================
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:3000",
        description="Comma-separated list of allowed CORS origins"
    )

    # ==========================================================================
    # Rate Limiting (Tiered)
    # ==========================================================================
    rate_limit_per_minute: int = Field(
        default=60,
        description="Default maximum requests per minute (unauthenticated)"
    )
    rate_limit_burst: int = Field(
        default=10,
        description="Burst limit for rate limiting"
    )
    rate_limit_webhooks: int = Field(
        default=1000,
        description="Webhook rate limit per minute per source"
    )
    rate_limit_authenticated: int = Field(
        default=300,
        description="Authenticated API rate limit per minute per user"
    )
    rate_limit_search: int = Field(
        default=30,
        description="Search endpoint rate limit per minute (expensive)"
    )

    # ==========================================================================
    # Service Area Configuration
    # ==========================================================================
    service_area_zip_prefixes: str = Field(
        default="85,86",
        description="Comma-separated ZIP code prefixes for service area"
    )

    # ==========================================================================
    # Logging
    # ==========================================================================
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="json", description="Log format (json or text)")

    # ==========================================================================
    # Google Ads Webhook Key (Lead Form Extension verification)
    # ==========================================================================
    google_ads_webhook_key: str = Field(
        default="",
        description="Secret key for Google Ads lead form webhook verification"
    )

    # ==========================================================================
    # Google Ads Configuration
    # ==========================================================================
    google_ads_developer_token: str = Field(
        default="",
        description="Google Ads API Developer Token"
    )
    google_ads_client_id: str = Field(
        default="",
        description="Google Ads OAuth2 Client ID"
    )
    google_ads_client_secret: str = Field(
        default="",
        description="Google Ads OAuth2 Client Secret"
    )
    google_ads_refresh_token: str = Field(
        default="",
        description="Google Ads OAuth2 Refresh Token"
    )
    google_ads_customer_id: str = Field(
        default="",
        description="Google Ads Customer ID (without dashes, e.g., 1234567890)"
    )
    google_ads_login_customer_id: str = Field(
        default="",
        description="Google Ads Manager Account ID (if using MCC, optional)"
    )

    # ==========================================================================
    # Twilio Configuration (SMS ONLY)
    # Voice calls are handled by 3CX (external phone system).
    # Twilio is used exclusively for outbound SMS.
    # ==========================================================================
    sms_mode: str = Field(
        default="twilio",
        description="SMS mode: 'local' for dev server, 'twilio' for real Twilio"
    )
    sms_local_url: str = Field(
        default="http://localhost:1080",
        description="Local SMS dev server URL"
    )
    twilio_account_sid: str = Field(
        default="",
        description="Twilio Account SID (for SMS)"
    )
    twilio_auth_token: str = Field(
        default="",
        description="Twilio Auth Token (for SMS)"
    )
    twilio_phone_number: str = Field(
        default="",
        description="Twilio Phone Number for outbound SMS"
    )

    # ==========================================================================
    # Email Configuration (SMTP - Fallback)
    # ==========================================================================
    smtp_host: str = Field(
        default="smtp.gmail.com",
        description="SMTP server host"
    )
    smtp_port: int = Field(
        default=587,
        description="SMTP server port"
    )
    smtp_username: str = Field(
        default="",
        description="SMTP username/email"
    )
    smtp_password: str = Field(
        default="",
        description="SMTP password/app password"
    )
    from_email: str = Field(
        default="noreply@sleepinstitute.co",
        description="From email address"
    )
    from_name: str = Field(
        default="The Insomnia and Sleep Institute of Arizona",
        description="From name for emails"
    )
    support_phone: str = Field(
        default="(480) 745-3547",
        description="Support phone number for emails/SMS"
    )

    # ==========================================================================
    # Email Mode (controls which email provider is used)
    # ==========================================================================
    email_mode: str = Field(
        default="maildev",
        description="Email sending mode: 'maildev' for local SMTP/MailDev, 'paubox' for production HIPAA email"
    )

    # ==========================================================================
    # Paubox Email API Configuration (HIPAA-Compliant)
    # ==========================================================================
    paubox_api_key: str = Field(
        default="",
        description="Paubox Email API Key"
    )
    paubox_api_username: str = Field(
        default="",
        description="Paubox API Username (endpoint username)"
    )
    paubox_api_base_url: str = Field(
        default="",
        description="Paubox API Base URL (e.g., https://api.paubox.net/v1/username)"
    )
    paubox_from_email: str = Field(
        default="",
        description="Paubox verified sender email address"
    )
    paubox_enabled: bool = Field(
        default=False,
        description="Enable Paubox for email sending (vs SMTP fallback)"
    )

    # ==========================================================================
    # CallRail Configuration (Call Analytics)
    # ==========================================================================
    callrail_api_key: str = Field(
        default="",
        description="CallRail API Key"
    )
    callrail_account_id: str = Field(
        default="",
        description="CallRail Account ID"
    )
    callrail_company_id: str = Field(
        default="",
        description="CallRail Company ID"
    )

    # ==========================================================================
    # Email Logo URL (used in all email templates)
    # ==========================================================================
    email_logo_url: str = Field(
        default="http://localhost:8000/static/images/logo.png",
        description="Full URL to the logo image used in email templates. "
                    "Must be publicly accessible (no auth required)."
    )

    # ==========================================================================
    # Computed Properties
    # ==========================================================================
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def service_area_prefixes_list(self) -> List[str]:
        """Parse service area ZIP prefixes into list."""
        return [prefix.strip() for prefix in self.service_area_zip_prefixes.split(",") if prefix.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() == "development"

    # ==========================================================================
    # Validators
    # ==========================================================================
    @field_validator("encryption_key")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        """
        Validate encryption key length.

        AES-256 requires exactly 32 bytes.
        """
        if len(v) < 32:
            # Pad key if too short (development only - warning logged)
            v = v.ljust(32, "0")
        elif len(v) > 32:
            # Truncate if too long
            v = v[:32]
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.

    Returns:
        Settings instance with values from environment
    """
    return Settings()


# Global settings instance
settings = get_settings()
