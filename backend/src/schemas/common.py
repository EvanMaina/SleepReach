"""
Common Pydantic schemas shared across the application.

Contains health check, error, and pagination schemas.
"""

from datetime import datetime
from typing import Optional, Generic, TypeVar, List, Any

from pydantic import BaseModel, Field


# =============================================================================
# Generic Type for Paginated Responses
# =============================================================================

T = TypeVar("T")


# =============================================================================
# Health Check Schemas
# =============================================================================

class HealthResponse(BaseModel):
    """
    Health check response schema.
    
    Used by monitoring systems to verify service health.
    """
    
    status: str = Field(
        ...,
        description="Overall health status (healthy, degraded, unhealthy)"
    )
    version: str = Field(
        ...,
        description="Application version"
    )
    timestamp: datetime = Field(
        ...,
        description="Current server timestamp"
    )
    database: str = Field(
        ...,
        description="Database connection status"
    )
    environment: str = Field(
        ...,
        description="Runtime environment (development, production)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "timestamp": "2024-01-15T10:30:00Z",
                "database": "connected",
                "environment": "development"
            }
        }
    }


# =============================================================================
# Error Schemas
# =============================================================================

class ErrorDetail(BaseModel):
    """
    Detail for a single validation error.
    """
    
    field: Optional[str] = Field(
        default=None,
        description="Field that caused the error"
    )
    message: str = Field(
        ...,
        description="Error message"
    )
    code: Optional[str] = Field(
        default=None,
        description="Error code for programmatic handling"
    )


class ErrorResponse(BaseModel):
    """
    Standard error response schema.
    
    Used for consistent error formatting across all endpoints.
    Never includes PHI or sensitive information in error details.
    """
    
    success: bool = Field(
        default=False,
        description="Always false for errors"
    )
    error: str = Field(
        ...,
        description="Error type or category"
    )
    message: str = Field(
        ...,
        description="Human-readable error message"
    )
    details: Optional[List[ErrorDetail]] = Field(
        default=None,
        description="Additional error details (for validation errors)"
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Request ID for support/debugging"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": False,
                "error": "validation_error",
                "message": "Invalid input data",
                "details": [
                    {
                        "field": "email",
                        "message": "Invalid email format",
                        "code": "invalid_email"
                    }
                ],
                "request_id": "req_abc123"
            }
        }
    }


# =============================================================================
# Pagination Schemas
# =============================================================================

class PaginationParams(BaseModel):
    """
    Pagination parameters for list endpoints.
    """
    
    page: int = Field(
        default=1,
        ge=1,
        description="Page number (1-indexed)"
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page (max 100)"
    )
    sort_by: Optional[str] = Field(
        default="created_at",
        description="Field to sort by"
    )
    sort_order: str = Field(
        default="desc",
        pattern="^(asc|desc)$",
        description="Sort order (asc or desc)"
    )

    @property
    def offset(self) -> int:
        """Calculate offset for database query."""
        return (self.page - 1) * self.page_size
    
    @property
    def limit(self) -> int:
        """Return limit for database query."""
        return self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response wrapper.
    
    Wraps any list of items with pagination metadata.
    """
    
    items: List[Any] = Field(
        ...,
        description="List of items for current page"
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of items across all pages"
    )
    page: int = Field(
        ...,
        ge=1,
        description="Current page number"
    )
    page_size: int = Field(
        ...,
        ge=1,
        description="Number of items per page"
    )
    total_pages: int = Field(
        ...,
        ge=0,
        description="Total number of pages"
    )
    has_next: bool = Field(
        ...,
        description="Whether there is a next page"
    )
    has_previous: bool = Field(
        ...,
        description="Whether there is a previous page"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [],
                "total": 100,
                "page": 1,
                "page_size": 20,
                "total_pages": 5,
                "has_next": True,
                "has_previous": False
            }
        }
    }


# =============================================================================
# Success Response Schema
# =============================================================================

class SuccessResponse(BaseModel):
    """
    Generic success response for operations without specific return data.
    """
    
    success: bool = Field(
        default=True,
        description="Operation success status"
    )
    message: str = Field(
        ...,
        description="Success message"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "message": "Operation completed successfully"
            }
        }
    }
