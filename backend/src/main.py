"""
NeuroReach AI Backend - FastAPI Application Entry Point

HIPAA-compliant patient intake and lead generation platform
for TMS therapy clinics.

Performance optimized with:
- Redis caching layer
- Response compression (gzip/brotli)
- Performance monitoring middleware
- Database query optimization
"""

import os
import time
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Dict, List

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .core.config import settings
from .core.database import engine, Base
from .api import health_router, leads_router, analytics_router, metrics_router, calls_router, source_analytics_router, platform_analytics_router, webhooks_router, providers_router, communications_router, auth_router, users_router, widget_router, notes_router
from .services.cache import get_cache


logger = logging.getLogger(__name__)


# =============================================================================
# Rate Limiting Middleware
# =============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis-backed sliding window algorithm.

    PRIMARY (Redis):
      Uses a sorted set (ZSET) per IP keyed as ``rl:{ip}``.
      A single pipelined command sequence atomically removes stale timestamps,
      counts the window, records the new request, and sets a TTL — all in one
      round-trip.  This works correctly across **multiple pods/replicas** (K8s,
      docker-compose scale, etc.) because state lives in the shared Redis
      instance rather than in-process memory.

    FALLBACK (in-memory):
      If Redis is unavailable (startup, transient failure, test environment),
      the middleware transparently degrades to a per-process sliding window.
      The fallback is self-healing: every request re-checks Redis availability
      via the shared ``get_cache()`` singleton, so the primary path resumes
      automatically once Redis recovers.

    Returns HTTP 429 when limit exceeded.
    """

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        # Authenticated coordinators fire 5-10 parallel requests per page load.
        # Apply a higher ceiling for Bearer-token requests so the dashboard
        # never returns 429 during normal use.
        self.authenticated_limit: int = getattr(
            settings, "rate_limit_authenticated", requests_per_minute * 5
        )
        self.window_size = 60  # seconds
        # In-memory fallback storage (used when Redis is unavailable)
        self.request_log: Dict[str, List[float]] = defaultdict(list)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, honouring X-Forwarded-For for proxied deployments."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _get_redis(self):
        """
        Return a live Redis client from the shared CacheService singleton,
        or None if Redis is not connected.

        Calling get_cache() on every request is cheap — it returns the module-
        level singleton without IO.  This approach is intentionally stateless so
        the middleware self-heals after a Redis reconnect without a process
        restart.
        """
        try:
            cache = get_cache()
            if cache.is_connected and cache._redis is not None:
                return cache._redis
        except Exception:
            pass
        return None

    # -------------------------------------------------------------------------
    # Redis sliding window (ZSET per IP)
    # -------------------------------------------------------------------------

    def _is_rate_limited_redis(self, redis_client, ip: str, is_authenticated: bool) -> bool:
        """
        Distributed sliding window via Redis sorted set.

        Pipeline (not MULTI/EXEC — pipelining is sufficient for rate limiting):
          1. ZREMRANGEBYSCORE  Remove timestamps older than the window cutoff.
          2. ZCARD             Count requests still in window *before* this one.
          3. ZADD              Record this request's timestamp as both key+score.
          4. EXPIRE            Guarantee TTL so ZSET keys never accumulate forever.

        Evaluates ``ZCARD`` result (step 2) against the limit; if already at or
        above limit the request is rejected (the ZADD still executes but that
        single over-limit entry will be evicted by the next ZREMRANGEBYSCORE).
        """
        now = time.time()
        cutoff = now - self.window_size
        limit = self.authenticated_limit if is_authenticated else self.requests_per_minute
        key = f"rl:{ip}"

        pipe = redis_client.pipeline(transaction=False)
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        pipe.zadd(key, {f"{now:.6f}": now})
        pipe.expire(key, self.window_size + 5)
        results = pipe.execute()

        # results[1] is the ZCARD *before* our ZADD — correct basis for decision
        count_before = results[1]
        return count_before >= limit

    def _get_remaining_redis(self, redis_client, ip: str, is_authenticated: bool) -> int:
        """Count how many requests remain in the current window (Redis path)."""
        limit = self.authenticated_limit if is_authenticated else self.requests_per_minute
        try:
            now = time.time()
            cutoff = now - self.window_size
            count = redis_client.zcount(f"rl:{ip}", cutoff, "+inf")
            return max(0, limit - count)
        except Exception:
            return 0

    # -------------------------------------------------------------------------
    # In-memory fallback sliding window
    # -------------------------------------------------------------------------

    def _clean_old_requests(self, ip: str, current_time: float) -> None:
        """
        Remove timestamps outside the sliding window and evict empty entries.

        Evicting depleted keys prevents the dict from growing without bound as
        unique IPs accumulate over the lifetime of the process.
        """
        cutoff = current_time - self.window_size
        self.request_log[ip] = [ts for ts in self.request_log[ip] if ts > cutoff]
        if not self.request_log[ip]:
            del self.request_log[ip]

    def _is_rate_limited_memory(self, ip: str, is_authenticated: bool) -> bool:
        """Per-process sliding window fallback."""
        now = time.time()
        self._clean_old_requests(ip, now)
        limit = self.authenticated_limit if is_authenticated else self.requests_per_minute
        if len(self.request_log[ip]) >= limit:
            return True
        self.request_log[ip].append(now)
        return False

    # -------------------------------------------------------------------------
    # Unified entry point
    # -------------------------------------------------------------------------

    def _is_rate_limited(self, ip: str, is_authenticated: bool = False) -> bool:
        """
        Route to Redis limiter (primary) or in-memory limiter (fallback).

        Any Redis exception falls through to in-memory so a Redis blip never
        results in a hard 500 for the user.
        """
        redis_client = self._get_redis()
        if redis_client is not None:
            try:
                return self._is_rate_limited_redis(redis_client, ip, is_authenticated)
            except Exception as _e:
                logger.warning("Redis rate limiter error, falling back to in-memory: %s", _e)
        return self._is_rate_limited_memory(ip, is_authenticated)

    def _get_remaining(self, ip: str, is_authenticated: bool) -> int:
        """Return remaining requests in the current window for the response header."""
        limit = self.authenticated_limit if is_authenticated else self.requests_per_minute
        redis_client = self._get_redis()
        if redis_client is not None:
            try:
                return self._get_remaining_redis(redis_client, ip, is_authenticated)
            except Exception:
                pass
        return max(0, limit - len(self.request_log.get(ip, [])))

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        # Health probes must never be rate-limited (liveness/readiness loops)
        if request.url.path in ["/health", "/health/ready", "/health/live"]:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        # Detect authenticated requests by Bearer token presence.
        # We intentionally skip JWT decoding here (too expensive per-request);
        # the actual auth validation happens inside the route handler.
        is_authenticated = bool(request.headers.get("Authorization", ""))
        effective_limit = self.authenticated_limit if is_authenticated else self.requests_per_minute

        if self._is_rate_limited(client_ip, is_authenticated=is_authenticated):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "success": False,
                    "error": "rate_limit_exceeded",
                    "message": (
                        f"Too many requests. Please try again later. "
                        f"Limit: {effective_limit} requests per minute."
                    ),
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(effective_limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        remaining = self._get_remaining(client_ip, is_authenticated)
        response.headers["X-RateLimit-Limit"] = str(effective_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response


# =============================================================================
# Performance Monitoring Middleware
# =============================================================================

class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track API response times and log slow requests.

    Logs warnings for requests exceeding 500ms.
    Adds X-Response-Time header to all responses.
    """

    SLOW_REQUEST_THRESHOLD_MS = 500

    async def dispatch(self, request: Request, call_next):
        """Process request with timing."""
        start_time = time.time()

        response = await call_next(request)

        # Calculate response time
        process_time_ms = (time.time() - start_time) * 1000

        # Add timing header
        response.headers["X-Response-Time"] = f"{process_time_ms:.2f}ms"

        # Log slow requests (>500ms)
        if process_time_ms > self.SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                f"Slow request: {request.method} {request.url.path} "
                f"took {process_time_ms:.2f}ms"
            )

        # Log all request times in debug mode
        if settings.debug:
            logger.debug(
                f"{request.method} {request.url.path} - {process_time_ms:.2f}ms"
            )

        return response


# =============================================================================
# Application Lifespan
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.

    Handles startup and shutdown events.
    Initializes cache service and performs health checks.
    """
    # Startup
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    logger.info("Environment: %s", settings.environment)

    # =========================================================================
    # PRODUCTION ENVIRONMENT VALIDATION
    # Refuse to start in production with insecure defaults or missing config.
    # In development, warn but allow startup.
    # =========================================================================
    _insecure_secrets = []
    if settings.secret_key == "dev-secret-key-change-in-production":
        _insecure_secrets.append("SECRET_KEY")
    if settings.encryption_key.rstrip("0") == "dev-encryption-key-32bytes!":
        _insecure_secrets.append("ENCRYPTION_KEY")
    if "neuroreach_dev_password" in settings.database_url:
        _insecure_secrets.append("DATABASE_URL")

    _missing_services = []
    if settings.is_production:
        if not settings.redis_url or settings.redis_url == "redis://localhost:6379/0":
            _missing_services.append("REDIS_URL (still pointing to localhost)")
        if not settings.paubox_api_key and settings.email_mode == "paubox":
            _missing_services.append("PAUBOX_API_KEY (email_mode=paubox but no key)")
        if not settings.twilio_account_sid and settings.sms_mode == "twilio":
            _missing_services.append("TWILIO_ACCOUNT_SID (sms_mode=twilio but no SID)")

    if _insecure_secrets and settings.is_production:
        logger.critical(
            "FATAL: INSECURE SECRETS DETECTED IN PRODUCTION. "
            "The following env vars still use dev defaults: %s. "
            "Set strong, unique values before deploying to production! Refusing to start.",
            ", ".join(_insecure_secrets),
        )
        import sys
        sys.exit(1)
    elif _insecure_secrets:
        logger.warning(
            "Dev-default secrets in use: %s. "
            "This is fine for development, but MUST be changed for production.",
            ", ".join(_insecure_secrets),
        )

    if _missing_services:
        logger.warning(
            "Potentially missing production services: %s. "
            "These services may not work correctly in production.",
            ", ".join(_missing_services),
        )

    # Initialize cache service
    cache = get_cache()
    if cache.is_connected:
        logger.info("Redis cache connected")
    else:
        logger.warning("Redis cache not available - operating without cache")

    # In development, we can create tables (production should use Alembic)
    if settings.is_development:
        logger.info("Development mode - tables managed by init SQL script")

    # Admin seeding is handled by the setup_fresh_admin.py script.
    # Run it after first deployment:
    #   docker exec -it neuroreach-backend python /app/scripts/setup_fresh_admin.py --email you@clinic.com
    try:
        from .core.database import SessionLocal
        from .models.user import User

        db = SessionLocal()
        try:
            user_count = db.query(User).count()
            if user_count == 0:
                logger.warning(
                    "NO USERS FOUND. Run the setup script to create the first admin: "
                    "docker exec -it neuroreach-backend python /app/scripts/setup_fresh_admin.py --email admin@clinic.com"
                )
        finally:
            db.close()
    except Exception as e:
        logger.warning("Could not check user table: %s", e)

    yield

    # Shutdown
    logger.info("Shutting down...")
    engine.dispose()


# =============================================================================
# Application Factory
# =============================================================================

def create_application() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "HIPAA-compliant patient intake and lead generation API "
            "for TMS therapy clinics. Performance optimized with Redis caching."
        ),
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        openapi_url="/openapi.json" if settings.is_development else None,
        lifespan=lifespan,
    )

    # Add GZip compression middleware (compress responses > 1KB)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Add performance monitoring middleware
    app.add_middleware(PerformanceMonitoringMiddleware)

    # Configure CORS
    # NOTE: allow_origins includes "*" to support the embeddable widget
    # being loaded on external sites (WordPress, etc.) that need to POST
    # to /api/leads/submit. Starlette's CORSMiddleware will reflect the
    # specific request Origin header when credentials are sent, keeping
    # dashboard auth secure while allowing widget submissions from any origin.
    cors_origins = settings.cors_origins_list
    allow_all = "*" in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else cors_origins,
        allow_credentials=not allow_all,  # credentials not compatible with wildcard
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-Response-Time",
        ],
    )

    # Add rate limiting middleware (60 requests per minute per IP)
    app.add_middleware(RateLimitMiddleware,
                       requests_per_minute=settings.rate_limit_per_minute)

    # Register routers
    app.include_router(health_router)
    app.include_router(leads_router)
    app.include_router(analytics_router)
    app.include_router(source_analytics_router)
    app.include_router(platform_analytics_router)
    app.include_router(metrics_router)
    app.include_router(calls_router)
    app.include_router(webhooks_router)
    app.include_router(providers_router)
    app.include_router(communications_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(widget_router)
    app.include_router(notes_router)

    return app


# =============================================================================
# Exception Handlers
# =============================================================================

app = create_application()

# =============================================================================
# Mount Static Files (for email logo, etc.)
# Serves files at /static/ -- e.g., /static/images/logo.png
# No authentication required so email clients can fetch the logo.
# Checks two locations: /app/static (Docker) and src/static (legacy).
# =============================================================================
_static_dir = Path("/app/static")
if not _static_dir.is_dir():
    _static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
    logger.info("Static files mounted at /static from %s", _static_dir)
else:
    logger.warning("Static directory not found -- /static will not be available")


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """
    Handle ValueError exceptions.

    Returns user-friendly error response without exposing internals.
    In production, returns a generic message to avoid leaking internal details.
    """
    import traceback
    logger.error(f"ValueError on {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
    logger.error(traceback.format_exc())
    # In production, never forward raw exception text to the client —
    # it may contain field values, internal paths, or other sensitive details.
    client_message = str(exc) if settings.is_development else "Invalid input. Please check your data and try again."
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": "validation_error",
            "message": client_message,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle unhandled exceptions.

    Logs error and returns generic message (never expose PHI or internals).
    """
    # Log ALL unhandled exceptions regardless of environment so production
    # 500 errors are never silently swallowed and are always traceable.
    # exc_info=True captures the full traceback without leaking it to the client.
    logger.error(
        "Unhandled exception on %s %s: %s: %s",
        request.method,
        request.url.path,
        type(exc).__name__,
        exc,
        exc_info=True,
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "internal_error",
            "message": "An unexpected error occurred. Please try again later.",
        },
    )


# =============================================================================
# Root Endpoint
# =============================================================================

@app.get("/", tags=["Root"])
async def root() -> dict:
    """
    Root endpoint returning API information.
    """
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs" if settings.is_development else "disabled",
    }


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level="debug" if settings.debug else "info",
    )
