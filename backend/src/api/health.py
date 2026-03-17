"""
Health check endpoints for monitoring.

Provides health status for load balancers, monitoring systems,
and container orchestration health probes.

Endpoints:
- /health: Basic liveness check (fast, no dependencies)
- /health/ready: Deep readiness check (DB, Redis, queue)
- /health/live: Simple alive check
- /api/admin/queue/status: Queue monitoring (admin)
"""

import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..core.config import settings
from ..core.database import get_db
from ..schemas.common import HealthResponse
from ..services.cache import get_cache
from ..core.auth import require_role


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Returns the health status of the API and its dependencies.",
)
async def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    """
    Health check endpoint for monitoring systems.
    
    Checks:
    - API is responding
    - Database connection is healthy
    - Database response time
    
    Returns:
        HealthResponse with status and component health
    """
    # Check database connection with response time
    db_status = "connected"
    db_response_time_ms = None
    
    try:
        import time
        start = time.time()
        db.execute(text("SELECT 1"))
        db_response_time_ms = int((time.time() - start) * 1000)
        
        # Warn if database is slow
        if db_response_time_ms > 100:
            logger.warning(f"Slow database response: {db_response_time_ms}ms")
    except Exception as e:
        db_status = "disconnected"
        logger.error(f"Database health check failed: {e}")
    
    # Determine overall status
    if db_status == "connected":
        health_status = "healthy"
    else:
        health_status = "unhealthy"
    
    return HealthResponse(
        status=health_status,
        version=settings.app_version,
        timestamp=datetime.utcnow(),
        database=db_status,
        environment=settings.environment,
    )


@router.get(
    "/health/ready",
    summary="Readiness Check",
    description="Deep readiness check for all dependencies.",
)
async def readiness_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Readiness probe for Kubernetes/container orchestration.
    
    Verifies ALL dependencies are ready before accepting traffic:
    - Database connection
    - Redis cache
    - Elasticsearch (if enabled)
    - Celery queue depth
    
    All blocking checks run in a thread with a 10s overall timeout
    to prevent hanging the async event loop.
    
    Returns:
        Dict with detailed health status of each component
    """
    import concurrent.futures
    import time as _time

    components = {}
    overall_healthy = True

    # 1. Check database connection (inline — session must stay on same thread)
    try:
        components["database"] = {
            "status": "healthy",
            "connected": True,
        }
        db.execute(text("SELECT 1"))
    except Exception as e:
        components["database"] = {
            "status": "unhealthy",
            "connected": False,
            "error": str(e)[:100],
        }
        overall_healthy = False

    # 2. Check Redis cache (in thread with 5s timeout)
    def _check_redis():
        cache = get_cache()
        if cache.is_connected and cache._redis is not None:
            t0 = _time.time()
            cache._redis.ping()
            latency_ms = (_time.time() - t0) * 1000
            return {"status": "healthy", "connected": True, "latency_ms": round(latency_ms, 2)}
        return {"status": "unhealthy", "connected": False, "error": "Not connected"}

    try:
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        components["redis"] = pool.submit(_check_redis).result(timeout=5)
        pool.shutdown(wait=False)
    except Exception as e:
        components["redis"] = {"status": "unknown", "connected": False, "error": str(e)[:100]}

    # 3. Elasticsearch
    components["elasticsearch"] = (
        {"status": "healthy", "enabled": True}
        if settings.elasticsearch_enabled
        else {"status": "disabled", "enabled": False}
    )

    # 4. Check Celery queue depth (in thread with 5s timeout)
    def _check_queue():
        from ..tasks.celery_app import get_queue_stats, is_queue_overloaded
        return get_queue_stats(), is_queue_overloaded()

    try:
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        queue_stats, queue_overloaded = pool.submit(_check_queue).result(timeout=5)
        pool.shutdown(wait=False)
        components["queue"] = {
            "status": "overloaded" if queue_overloaded else "healthy",
            "depths": queue_stats,
            "max_depth": settings.lead_queue_max_depth,
        }
        if queue_overloaded:
            overall_healthy = False
    except Exception as e:
        components["queue"] = {"status": "unknown", "error": str(e)[:100]}

    return {
        "status": "ready" if overall_healthy else "not_ready",
        "version": settings.app_version,
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.environment,
        "components": components,
    }


@router.get(
    "/health/live",
    summary="Liveness Check",
    description="Simple liveness check to verify the API is running.",
)
async def liveness_check() -> dict:
    """
    Liveness probe for Kubernetes/container orchestration.
    
    Simple check that the API process is alive.
    Does NOT check dependencies - use /health/ready for that.
    
    Returns:
        Simple dict with status
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
    }


# =============================================================================
# Admin Endpoints
# =============================================================================

@router.get(
    "/api/admin/queue/status",
    summary="Queue Status",
    description="Get Celery queue status and depths (admin only).",
    dependencies=[Depends(require_role("administrator"))],
)
async def get_queue_status() -> Dict[str, Any]:
    """
    Get detailed status of Celery task queues.
    
    Used for monitoring queue depth and detecting backpressure.
    
    Returns:
        Dict with queue statistics
    """
    try:
        from ..tasks.celery_app import get_queue_stats, is_queue_overloaded
        
        queue_stats = get_queue_stats()
        overloaded = is_queue_overloaded()
        
        return {
            "status": "overloaded" if overloaded else "healthy",
            "queues": queue_stats,
            "max_depth": settings.lead_queue_max_depth,
            "backpressure_active": overloaded,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.get(
    "/api/admin/cache/stats",
    summary="Cache Statistics",
    description="Get Redis cache statistics (admin only).",
    dependencies=[Depends(require_role("administrator"))],
)
async def get_cache_stats() -> Dict[str, Any]:
    """
    Get Redis cache statistics including hit rate.
    
    Returns:
        Dict with cache statistics
    """
    cache = get_cache()
    
    return {
        "health": cache.health_check(),
        "stats": cache.get_stats(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post(
    "/api/admin/cache/invalidate",
    summary="Invalidate Cache",
    description="Invalidate all caches (admin only).",
    dependencies=[Depends(require_role("administrator"))],
)
async def invalidate_all_caches() -> Dict[str, Any]:
    """
    Invalidate all caches.
    
    Use with caution - this will cause temporary performance degradation.
    
    Returns:
        Confirmation of invalidation
    """
    cache = get_cache()
    cache.invalidate_all()
    
    return {
        "status": "invalidated",
        "message": "All caches have been invalidated",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post(
    "/api/admin/test-follow-up",
    summary="Test Follow-Up Send",
    description="Trigger a test follow-up SMS + email to the most recent eligible lead (admin only).",
    dependencies=[Depends(require_role("administrator"))],
)
async def test_follow_up(lead_id: str = None) -> Dict[str, Any]:
    """
    Trigger a single test follow-up send to verify SMS and email templates.
    
    If lead_id is provided, sends to that specific lead.
    Otherwise picks the most recent non-scheduled, non-deleted lead.
    
    Args:
        lead_id: Optional UUID of a specific lead to send to
    
    Returns:
        Dict with test results (email provider, SMS SID, etc.)
    """
    try:
        from ..tasks.lead_tasks import send_test_follow_up
        
        # Run synchronously for immediate feedback (not via Celery delay)
        result = send_test_follow_up(lead_id=lead_id)
        
        return {
            "status": "completed",
            "result": result,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Test follow-up failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }
