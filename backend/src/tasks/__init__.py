"""
Celery tasks package for async lead processing.

Provides background task infrastructure for:
- Async lead ingestion from webhooks
- Batch processing for efficiency
- Dead letter queue for failed tasks
- Elasticsearch sync
"""

from .celery_app import celery_app
from .lead_tasks import (
    process_lead_async,
    process_lead_batch,
    sync_lead_to_elasticsearch,
    reindex_all_leads,
)

__all__ = [
    "celery_app",
    "process_lead_async",
    "process_lead_batch",
    "sync_lead_to_elasticsearch",
    "reindex_all_leads",
]
