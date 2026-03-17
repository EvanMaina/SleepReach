"""
Celery application configuration.

Configures Celery for async lead processing with:
- Redis as message broker (supports both redis:// and rediss:// TLS)
- Automatic retry with exponential backoff
- Dead letter queue for failed tasks
- Task routing for different priorities
- Monitoring via Flower
- AWS ElastiCache compatibility (TLS with self-signed certs)
"""

import logging
import ssl as _ssl
from celery import Celery
from kombu import Exchange, Queue

from ..core.config import settings


logger = logging.getLogger(__name__)


# =============================================================================
# TLS Configuration for AWS ElastiCache
# =============================================================================
# ElastiCache with transit encryption uses rediss:// URLs.
# The self-signed certificates require disabling strict cert verification.

_broker_use_ssl = None
_backend_use_ssl = None

if settings.celery_broker_url.startswith("rediss://"):
    _broker_use_ssl = {
        "ssl_cert_reqs": _ssl.CERT_NONE,
    }
    logger.info("Celery broker TLS enabled (ssl_cert_reqs=CERT_NONE for ElastiCache)")

if settings.celery_result_backend.startswith("rediss://"):
    _backend_use_ssl = {
        "ssl_cert_reqs": _ssl.CERT_NONE,
    }
    logger.info("Celery result backend TLS enabled (ssl_cert_reqs=CERT_NONE for ElastiCache)")


# =============================================================================
# Celery Application
# =============================================================================

celery_app = Celery(
    "neuroreach",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "src.tasks.lead_tasks",
    ],
)


# =============================================================================
# Celery Configuration
# =============================================================================

_conf = dict(
    # Task execution settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task time limits
    task_time_limit=settings.celery_task_time_limit,  # Hard limit (kill task)
    task_soft_time_limit=settings.celery_task_time_limit - 30,  # Soft limit (raise exception)
    
    # Worker settings
    worker_concurrency=settings.celery_worker_concurrency,
    worker_prefetch_multiplier=4,  # Prefetch 4x concurrency
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks (memory leak prevention)
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_backend_transport_options={
        "visibility_timeout": 3600,
    },
    
    # Broker settings
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    
    # Task acknowledgement
    task_acks_late=True,  # Ack after task completes (more reliable)
    task_reject_on_worker_lost=True,  # Re-queue if worker dies
    
    # Task routing
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    
    # ==========================================================================
    # CELERY BEAT SCHEDULER - Using /tmp for writable location
    # This fixes the "[Errno 13] Permission denied: 'celerybeat-schedule'" error
    # ==========================================================================
    beat_scheduler="celery.beat:PersistentScheduler",
    beat_schedule_filename="/tmp/celerybeat-schedule",  # Use /tmp for writable location
    
    # Beat schedule for periodic tasks
    beat_schedule={
        "cleanup-dead-letter-queue": {
            "task": "src.tasks.lead_tasks.process_dead_letter_queue",
            "schedule": 300.0,  # Every 5 minutes
        },
        "cache-warm-dashboard": {
            "task": "src.tasks.lead_tasks.warm_dashboard_cache",
            "schedule": 60.0,  # Every minute
        },
        "elasticsearch-sync-check": {
            "task": "src.tasks.lead_tasks.check_elasticsearch_sync",
            "schedule": 600.0,  # Every 10 minutes
        },
        "refresh-platform-analytics": {
            "task": "src.tasks.lead_tasks.refresh_platform_analytics_views",
            "schedule": 300.0,  # Every 5 minutes
        },
        "daily-lead-digest-7am-mst": {
            "task": "src.tasks.lead_tasks.send_daily_lead_digest",
            "schedule": __import__("celery.schedules", fromlist=["crontab"]).crontab(
                hour=14, minute=0,  # 14:00 UTC = 7:00 AM MST (UTC-7)
            ),
        },
        "automated-follow-ups-every-6h": {
            "task": "src.tasks.lead_tasks.send_automated_follow_ups",
            "schedule": __import__("celery.schedules", fromlist=["crontab"]).crontab(
                hour="1,7,13,19", minute=0,  # Every 6 hours: 1:00, 7:00, 13:00, 19:00 UTC
            ),
        },
        "not-interested-follow-ups-every-21d": {
            "task": "src.tasks.lead_tasks.send_not_interested_follow_ups",
            "schedule": __import__("celery.schedules", fromlist=["crontab"]).crontab(
                hour=15, minute=0,  # 15:00 UTC = 8:00 AM MST
                day_of_week="monday",  # Run every Monday — ~3 week cadence managed by last_follow_up_sent_at
            ),
        },
    },
)

# Add TLS settings only if needed (broker and/or backend)
if _broker_use_ssl:
    _conf["broker_use_ssl"] = _broker_use_ssl
if _backend_use_ssl:
    _conf["redis_backend_use_ssl"] = _backend_use_ssl

celery_app.conf.update(**_conf)


# =============================================================================
# Queue Configuration
# =============================================================================

# Define exchanges
default_exchange = Exchange("default", type="direct")
lead_exchange = Exchange("leads", type="direct")
dlq_exchange = Exchange("dlq", type="direct")

# Define queues with priorities
celery_app.conf.task_queues = (
    # Default queue for general tasks
    Queue(
        "default",
        default_exchange,
        routing_key="default",
    ),
    # High priority queue for lead ingestion
    Queue(
        "leads.high",
        lead_exchange,
        routing_key="leads.high",
        queue_arguments={"x-max-priority": 10},
    ),
    # Normal priority queue for lead processing
    Queue(
        "leads.normal",
        lead_exchange,
        routing_key="leads.normal",
        queue_arguments={"x-max-priority": 5},
    ),
    # Low priority queue for batch operations
    Queue(
        "leads.batch",
        lead_exchange,
        routing_key="leads.batch",
        queue_arguments={"x-max-priority": 1},
    ),
    # Dead letter queue for failed tasks
    Queue(
        "dlq",
        dlq_exchange,
        routing_key="dlq",
    ),
    # Elasticsearch sync queue
    Queue(
        "elasticsearch",
        default_exchange,
        routing_key="elasticsearch",
    ),
)


# Task routing
celery_app.conf.task_routes = {
    "src.tasks.lead_tasks.process_lead_async": {
        "queue": "leads.high",
        "routing_key": "leads.high",
    },
    "src.tasks.lead_tasks.process_lead_batch": {
        "queue": "leads.batch",
        "routing_key": "leads.batch",
    },
    "src.tasks.lead_tasks.sync_lead_to_elasticsearch": {
        "queue": "elasticsearch",
        "routing_key": "elasticsearch",
    },
    "src.tasks.lead_tasks.reindex_all_leads": {
        "queue": "elasticsearch",
        "routing_key": "elasticsearch",
    },
    "src.tasks.lead_tasks.move_to_dead_letter": {
        "queue": "dlq",
        "routing_key": "dlq",
    },
}


# =============================================================================
# Task Error Handling
# =============================================================================

@celery_app.task(bind=True, max_retries=settings.celery_max_retries)
def retry_with_backoff(self, exc, task_id, args, kwargs, einfo):
    """
    Generic retry handler with exponential backoff.
    
    Retry intervals: 1s, 2s, 4s, 8s, 16s (geometric progression)
    """
    retry_count = self.request.retries
    countdown = 2 ** retry_count  # Exponential backoff
    
    logger.warning(
        f"Task {task_id} failed, retrying in {countdown}s. "
        f"Attempt {retry_count + 1}/{settings.celery_max_retries}. "
        f"Error: {exc}"
    )
    
    raise self.retry(exc=exc, countdown=countdown)


# =============================================================================
# Queue Monitoring
# =============================================================================

def get_queue_depth(queue_name: str = "leads.high") -> int:
    """
    Get current depth of a Celery queue.
    
    Used for backpressure handling.
    
    Args:
        queue_name: Name of queue to check
        
    Returns:
        Number of messages in queue
    """
    try:
        with celery_app.pool.acquire(block=True, timeout=3) as conn:
            return conn.default_channel.client.llen(queue_name)
    except Exception as e:
        logger.error(f"Failed to get queue depth: {e}")
        return 0


def is_queue_overloaded() -> bool:
    """
    Check if lead queue is overloaded (backpressure check).
    
    Returns True if queue depth exceeds configured maximum.
    Used to return 503 when system is overloaded.
    """
    depth = get_queue_depth("leads.high")
    return depth > settings.lead_queue_max_depth


def get_queue_stats() -> dict:
    """
    Get statistics for all queues.
    
    Returns:
        Dict with queue names and their depths
    """
    queues = ["default", "leads.high", "leads.normal", "leads.batch", "dlq", "elasticsearch"]
    stats = {}
    
    for queue in queues:
        stats[queue] = get_queue_depth(queue)
    
    return stats


# =============================================================================
# Startup Events
# =============================================================================

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Configure periodic tasks on worker startup."""
    logger.info("Celery worker configured with periodic tasks")


@celery_app.task
def health_check():
    """
    Simple health check task for monitoring.
    
    Returns:
        Dict with worker status
    """
    return {
        "status": "healthy",
        "worker": True,
    }
