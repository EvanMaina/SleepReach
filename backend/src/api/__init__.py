"""API route controllers for SleepReach."""

from .health import router as health_router
from .leads import router as leads_router
from .analytics import router as analytics_router
from .metrics import router as metrics_router
from .calls import router as calls_router
from .source_analytics import router as source_analytics_router
from .platform_analytics import router as platform_analytics_router
from .webhooks import router as webhooks_router
from .providers import router as providers_router
from .communications import router as communications_router
from .auth import router as auth_router
from .users import router as users_router
from .widget import router as widget_router
from .notes import router as notes_router

__all__ = [
    "health_router", "leads_router", "analytics_router", "metrics_router",
    "calls_router", "source_analytics_router", "platform_analytics_router",
    "webhooks_router", "providers_router", "communications_router",
    "auth_router", "users_router", "widget_router", "notes_router",
]
