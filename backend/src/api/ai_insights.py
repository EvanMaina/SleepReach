"""AI Insights API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.auth import get_current_user
from ..core.database import get_db
from ..services.ai_insights_service import get_ai_insights_service


router = APIRouter(
    prefix="/api/ai-insights",
    tags=["AI Insights"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
async def get_ai_insights(
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    service = get_ai_insights_service(db)
    return await service.get_insights(force_refresh=force_refresh)
