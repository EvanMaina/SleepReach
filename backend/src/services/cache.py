"""
Redis caching service for performance optimization.

Provides caching layer for dashboard statistics, analytics data,
and frequently accessed data with:
- Automatic cache invalidation
- Stampede prevention (distributed locking)
- Stale-while-revalidate pattern
- Cache warming on startup
"""

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Optional, Callable, TypeVar, Tuple
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

import redis
from redis.exceptions import RedisError
from redis.lock import Lock

from ..core.config import settings


logger = logging.getLogger(__name__)

T = TypeVar('T')

# Background executor for stale-while-revalidate
_background_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cache_refresh")


class CacheService:
    """
    Redis-based caching service with fallback to no-cache.
    
    Provides:
    - Dashboard statistics caching (30s TTL)
    - Analytics data caching (60s TTL)
    - Conditions distribution caching (120s TTL)
    - Automatic cache invalidation on data updates
    - Graceful fallback when Redis is unavailable
    """
    
    # Cache key prefixes
    PREFIX_DASHBOARD = "neuroreach:dashboard"
    PREFIX_ANALYTICS = "neuroreach:analytics"
    PREFIX_LEADS = "neuroreach:leads"
    PREFIX_CONDITIONS = "neuroreach:conditions"
    PREFIX_COHORT = "neuroreach:cohort"
    PREFIX_TREND = "neuroreach:trend"
    
    def __init__(self):
        """Initialize Redis connection."""
        self._redis: Optional[redis.Redis] = None
        self._connected = False
        self._connect()
    
    def _connect(self) -> None:
        """Establish Redis connection."""
        if not settings.cache_enabled:
            logger.info("Caching disabled by configuration")
            return
            
        try:
            # Build connection kwargs
            redis_kwargs = dict(
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )

            # Clean the Redis URL: strip any query parameters like
            # ?ssl_cert_reqs=CERT_NONE that were added for Celery but
            # confuse redis.from_url(). We handle TLS settings via kwargs.
            redis_url = settings.redis_url
            if "?" in redis_url:
                redis_url = redis_url.split("?")[0]

            # AWS ElastiCache with transit encryption uses self-signed certs.
            # When the URL scheme is rediss:// (TLS), disable strict cert
            # verification so the connection succeeds without a custom CA bundle.
            if redis_url.startswith("rediss://"):
                import ssl
                redis_kwargs["ssl_cert_reqs"] = "none"

            self._redis = redis.from_url(
                redis_url,
                **redis_kwargs,
            )
            # Test connection
            self._redis.ping()
            self._connected = True
            logger.info("Redis cache connected successfully")
        except RedisError as e:
            logger.warning(f"Redis connection failed: {e}. Operating without cache.")
            self._connected = False
    
    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        return self._connected and self._redis is not None
    
    def _ensure_connection(self) -> bool:
        """Ensure Redis connection is active, attempt reconnect if needed."""
        if not settings.cache_enabled:
            return False
            
        if self.is_connected:
            try:
                self._redis.ping()
                return True
            except RedisError:
                self._connected = False
        
        # Attempt reconnection
        self._connect()
        return self.is_connected
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/error
        """
        if not self._ensure_connection():
            return None
            
        try:
            value = self._redis.get(key)
            if value:
                return json.loads(value)
            return None
        except (RedisError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get error for {key}: {e}")
            return None
    
    def get_with_stale(self, key: str) -> Tuple[Optional[Any], bool]:
        """
        Get value from cache with stale indicator.
        
        Returns the value and whether it's stale (past soft TTL).
        Used for stale-while-revalidate pattern.
        
        Args:
            key: Cache key
            
        Returns:
            Tuple of (value, is_stale)
        """
        if not self._ensure_connection():
            return None, True
            
        try:
            # Get value and metadata
            pipe = self._redis.pipeline()
            pipe.get(key)
            pipe.ttl(key)
            value, ttl = pipe.execute()
            
            if not value:
                return None, True
            
            parsed = json.loads(value)
            
            # Check if within soft TTL (80% of remaining TTL means fresh)
            # If TTL is less than 20% of original, consider stale
            is_stale = ttl is not None and ttl < 10  # Last 10 seconds = stale
            
            return parsed, is_stale
        except (RedisError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get_with_stale error for {key}: {e}")
            return None, True
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache with optional TTL.
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connection():
            return False
            
        try:
            serialized = json.dumps(value, default=str)
            if ttl:
                self._redis.setex(key, ttl, serialized)
            else:
                self._redis.set(key, serialized)
            return True
        except (RedisError, TypeError) as e:
            logger.warning(f"Cache set error for {key}: {e}")
            return False
    
    # ==========================================================================
    # Stampede Prevention (Distributed Locking)
    # ==========================================================================
    
    def acquire_lock(self, lock_name: str, timeout: int = 10) -> Optional[Lock]:
        """
        Acquire a distributed lock for cache operations.
        
        Prevents thundering herd / cache stampede when many requests
        try to refresh expired cache simultaneously.
        
        Args:
            lock_name: Name of the lock
            timeout: Lock timeout in seconds
            
        Returns:
            Lock object if acquired, None otherwise
        """
        if not self._ensure_connection():
            return None
            
        try:
            lock = self._redis.lock(
                f"lock:{lock_name}",
                timeout=timeout,
                blocking_timeout=1,  # Wait max 1 second for lock
            )
            if lock.acquire(blocking=True):
                return lock
            return None
        except RedisError as e:
            logger.warning(f"Failed to acquire lock {lock_name}: {e}")
            return None
    
    def release_lock(self, lock: Optional[Lock]) -> None:
        """
        Release a distributed lock.
        
        Args:
            lock: Lock object to release
        """
        if lock:
            try:
                lock.release()
            except RedisError as e:
                logger.warning(f"Failed to release lock: {e}")
    
    def get_or_compute(
        self,
        key: str,
        compute_func: Callable[[], T],
        ttl: int = 60,
        lock_timeout: int = 10,
    ) -> Optional[T]:
        """
        Get from cache or compute value with stampede prevention.
        
        If cache miss, acquires lock before computing to prevent
        multiple simultaneous computations.
        
        Args:
            key: Cache key
            compute_func: Function to compute value if not cached
            ttl: Cache TTL in seconds
            lock_timeout: Lock timeout in seconds
            
        Returns:
            Cached or computed value
        """
        # Try to get from cache first
        cached = self.get(key)
        if cached is not None:
            return cached
        
        # Try to acquire lock for computation
        lock = self.acquire_lock(key, timeout=lock_timeout)
        
        if lock:
            try:
                # Double-check cache (another thread may have populated it)
                cached = self.get(key)
                if cached is not None:
                    return cached
                
                # Compute value
                value = compute_func()
                
                # Store in cache
                self.set(key, value, ttl=ttl)
                
                return value
            finally:
                self.release_lock(lock)
        else:
            # Couldn't get lock, another thread is computing
            # Wait briefly and try cache again
            time.sleep(0.5)
            return self.get(key)
    
    def get_stale_while_revalidate(
        self,
        key: str,
        compute_func: Callable[[], T],
        ttl: int = 60,
        stale_ttl: int = 300,
    ) -> Optional[T]:
        """
        Get from cache with stale-while-revalidate pattern.
        
        Returns stale data immediately while refreshing in background.
        Prevents user-visible latency from cache misses.
        
        Args:
            key: Cache key
            compute_func: Function to compute fresh value
            ttl: Fresh TTL in seconds
            stale_ttl: Extended TTL for stale data
            
        Returns:
            Cached value (possibly stale while refresh happens)
        """
        value, is_stale = self.get_with_stale(key)
        
        if value is not None:
            if is_stale:
                # Trigger background refresh
                self._refresh_in_background(key, compute_func, ttl + stale_ttl)
            return value
        
        # No cached value, compute synchronously with lock
        return self.get_or_compute(key, compute_func, ttl + stale_ttl)
    
    def _refresh_in_background(
        self,
        key: str,
        compute_func: Callable[[], Any],
        ttl: int,
    ) -> None:
        """
        Refresh cache value in background thread.
        
        Uses thread pool to avoid blocking request.
        """
        def refresh():
            lock = self.acquire_lock(f"refresh:{key}", timeout=30)
            if lock:
                try:
                    value = compute_func()
                    self.set(key, value, ttl=ttl)
                    logger.debug(f"Background cache refresh completed for {key}")
                finally:
                    self.release_lock(lock)
        
        try:
            _background_executor.submit(refresh)
        except Exception as e:
            logger.warning(f"Failed to queue background refresh: {e}")
    
    def delete(self, key: str) -> bool:
        """
        Delete value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connection():
            return False
            
        try:
            self._redis.delete(key)
            return True
        except RedisError as e:
            logger.warning(f"Cache delete error for {key}: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.
        
        Args:
            pattern: Key pattern with wildcards (e.g., "neuroreach:leads:*")
            
        Returns:
            Number of keys deleted
        """
        if not self._ensure_connection():
            return 0
            
        try:
            keys = list(self._redis.scan_iter(match=pattern))
            if keys:
                return self._redis.delete(*keys)
            return 0
        except RedisError as e:
            logger.warning(f"Cache delete pattern error for {pattern}: {e}")
            return 0

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Alias for delete_pattern for API consistency.

        Several callers (providers.py, etc.) use invalidate_pattern; this ensures
        they all resolve to the same underlying delete_pattern implementation.

        Args:
            pattern: Key pattern with wildcards (e.g., "providers:*")

        Returns:
            Number of keys deleted
        """
        return self.delete_pattern(pattern)
    
    # ==========================================================================
    # Dashboard Caching Methods
    # ==========================================================================
    
    def get_dashboard_stats(self) -> Optional[dict]:
        """Get cached dashboard statistics."""
        return self.get(f"{self.PREFIX_DASHBOARD}:stats")
    
    def set_dashboard_stats(self, stats: dict) -> bool:
        """Cache dashboard statistics."""
        return self.set(
            f"{self.PREFIX_DASHBOARD}:stats",
            stats,
            ttl=settings.cache_ttl_dashboard
        )
    
    def get_leads_trend(self, period: int = 30) -> Optional[list]:
        """Get cached leads trend data."""
        return self.get(f"{self.PREFIX_TREND}:{period}d")
    
    def set_leads_trend(self, data: list, period: int = 30) -> bool:
        """Cache leads trend data."""
        return self.set(
            f"{self.PREFIX_TREND}:{period}d",
            data,
            ttl=settings.cache_ttl_analytics
        )
    
    def get_conditions_distribution(self) -> Optional[dict]:
        """Get cached conditions distribution."""
        return self.get(f"{self.PREFIX_CONDITIONS}:distribution")
    
    def set_conditions_distribution(self, data: dict) -> bool:
        """Cache conditions distribution."""
        return self.set(
            f"{self.PREFIX_CONDITIONS}:distribution",
            data,
            ttl=settings.cache_ttl_conditions
        )
    
    def get_cohort_data(self) -> Optional[list]:
        """Get cached cohort retention data."""
        return self.get(f"{self.PREFIX_COHORT}:retention")
    
    def set_cohort_data(self, data: list) -> bool:
        """Cache cohort retention data."""
        return self.set(
            f"{self.PREFIX_COHORT}:retention",
            data,
            ttl=settings.cache_ttl_analytics
        )
    
    # ==========================================================================
    # Lead Count Caching
    # ==========================================================================
    
    def get_lead_counts(self) -> Optional[dict]:
        """Get cached lead counts by status/priority."""
        return self.get(f"{self.PREFIX_LEADS}:counts")
    
    def set_lead_counts(self, counts: dict) -> bool:
        """Cache lead counts."""
        return self.set(
            f"{self.PREFIX_LEADS}:counts",
            counts,
            ttl=settings.cache_ttl_dashboard
        )
    
    # ==========================================================================
    # Cache Invalidation
    # ==========================================================================
    
    def invalidate_dashboard(self) -> None:
        """Invalidate all dashboard-related caches."""
        patterns = [
            f"{self.PREFIX_DASHBOARD}:*",
            f"{self.PREFIX_LEADS}:counts",
            f"{self.PREFIX_TREND}:*",
        ]
        for pattern in patterns:
            self.delete_pattern(pattern)
        logger.info("Dashboard cache invalidated")
    
    def invalidate_analytics(self) -> None:
        """Invalidate all analytics caches."""
        patterns = [
            f"{self.PREFIX_ANALYTICS}:*",
            f"{self.PREFIX_CONDITIONS}:*",
            f"{self.PREFIX_COHORT}:*",
            f"{self.PREFIX_TREND}:*",
        ]
        for pattern in patterns:
            self.delete_pattern(pattern)
        logger.info("Analytics cache invalidated")
    
    def invalidate_all(self) -> None:
        """Invalidate all caches (use sparingly)."""
        self.delete_pattern("neuroreach:*")
        logger.info("All caches invalidated")
    
    def invalidate_on_lead_change(self) -> None:
        """
        Invalidate caches affected by lead changes.
        
        Called when a lead is created, updated, or deleted.
        
        CRITICAL: This must invalidate ALL cache keys that contain lead data
        to ensure immediate UI reflection of changes.
        """
        # Invalidate dashboard stats (quick refresh needed)
        self.delete(f"{self.PREFIX_DASHBOARD}:stats")
        self.delete(f"{self.PREFIX_LEADS}:counts")
        
        # CRITICAL FIX: Also invalidate metrics dashboard summary cache
        # This key is used by /api/metrics/analytics/dashboard-summary
        self.delete("neuroreach:metrics:dashboard_summary")
        
        # Invalidate queue metrics for all queue types
        self.delete_pattern("neuroreach:metrics:queue:*")
        
        # Also invalidate source-specific caches (used by source_analytics.py)
        self.delete_pattern(f"{self.PREFIX_ANALYTICS}:source:*")
        self.delete_pattern("source_analytics:*")
        self.delete_pattern("platform_trend:*")
        self.delete_pattern("hot_leads_platform:*")
        
        # Invalidate trend caches for immediate updates
        self.delete_pattern(f"{self.PREFIX_TREND}:*")
        
        # Invalidate metrics trends caches (daily/monthly trends in metrics.py)
        self.delete_pattern("neuroreach:metrics:trends:*")
        
        # CRITICAL: Invalidate conditions + TMS distribution caches
        # When a lead's tms_therapy_interest or condition is edited,
        # the analytics dashboard cards must reflect changes immediately.
        self.delete_pattern(f"{self.PREFIX_CONDITIONS}:*")
        
        # Invalidate ALL cohort retention caches (per-filter keys: months:3, year:2026, etc.)
        self.delete_pattern(f"{self.PREFIX_COHORT}:*")
        
        logger.debug("Lead change cache invalidation completed (all related caches cleared)")
    
    # ==========================================================================
    # Health & Monitoring
    # ==========================================================================
    
    def health_check(self) -> dict:
        """
        Check Redis health and return status.
        
        Returns:
            Dict with health status and metrics
        """
        if not self._ensure_connection():
            return {
                "status": "unhealthy",
                "connected": False,
                "error": "Not connected to Redis"
            }
        
        try:
            # Ping test
            latency_start = time.time()
            self._redis.ping()
            latency_ms = (time.time() - latency_start) * 1000
            
            # Get memory info
            info = self._redis.info(section="memory")
            
            return {
                "status": "healthy",
                "connected": True,
                "latency_ms": round(latency_ms, 2),
                "used_memory": info.get("used_memory_human", "unknown"),
                "max_memory": info.get("maxmemory_human", "unlimited"),
            }
        except RedisError as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e)
            }
    
    def get_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache stats
        """
        if not self._ensure_connection():
            return {"error": "Not connected"}
        
        try:
            info = self._redis.info(section="stats")
            keyspace = self._redis.info(section="keyspace")
            
            return {
                "total_connections_received": info.get("total_connections_received", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                ),
                "db_keys": keyspace,
            }
        except RedisError as e:
            return {"error": str(e)}
    
    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """Calculate cache hit rate percentage."""
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)


# Global cache service instance
_cache_service: Optional[CacheService] = None


def get_cache() -> CacheService:
    """
    Get global cache service instance.
    
    Creates instance on first call (lazy initialization).
    
    Returns:
        CacheService instance
    """
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service


def cached(
    key_func: Callable[..., str],
    ttl: int = 60,
    cache_empty: bool = False,
):
    """
    Decorator to cache function results.
    
    Args:
        key_func: Function to generate cache key from args
        ttl: Cache TTL in seconds
        cache_empty: Whether to cache empty/None results
        
    Example:
        @cached(
            key_func=lambda period: f"trend:{period}",
            ttl=60
        )
        def get_trend_data(period: int) -> list:
            return expensive_calculation(period)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            cache = get_cache()
            
            # Generate cache key
            cache_key = key_func(*args, **kwargs)
            
            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            if result is not None or cache_empty:
                cache.set(cache_key, result, ttl=ttl)
            
            return result
        return wrapper
    return decorator
