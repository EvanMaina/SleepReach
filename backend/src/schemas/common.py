"""Common Pydantic schemas shared across API endpoints."""

from datetime import datetime
from typing import Any, List, Optional

from fastapi import Query
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime
    database: str
    environment: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    message: str


class SuccessResponse(BaseModel):
    success: bool = True
    message: str


# =============================================================================
# Pagination
# =============================================================================


class PaginationParams:
    """
    Reusable FastAPI dependency for pagination query parameters.

    Usage::

        @router.get("/items")
        async def list_items(pagination: PaginationParams = Depends()):
            ...
    """

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""

    items: List[Any] = Field(default_factory=list, description="Page of results")
    total: int = Field(..., description="Total number of items matching the query")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether a next page exists")
    has_previous: bool = Field(..., description="Whether a previous page exists")
