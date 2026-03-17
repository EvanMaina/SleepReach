"""
Pydantic validation schemas for NeuroReach AI.

Contains request/response DTOs with validation rules.
These schemas enforce data integrity at API boundaries.
"""

from .lead import (
    LeadCreate,
    LeadResponse,
    LeadListResponse,
    LeadSubmitResponse,
    UTMParams,
)
from .common import (
    HealthResponse,
    ErrorResponse,
    PaginationParams,
    PaginatedResponse,
)

__all__ = [
    # Lead schemas
    "LeadCreate",
    "LeadResponse",
    "LeadListResponse",
    "LeadSubmitResponse",
    "UTMParams",
    # Common schemas
    "HealthResponse",
    "ErrorResponse",
    "PaginationParams",
    "PaginatedResponse",
]
