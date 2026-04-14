"""AI Insights API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.get("/email-draft/{lead_id}")
async def generate_ai_email(
    lead_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Generate an AI-powered personalized email for a specific lead."""
    import httpx
    from ..models.lead import Lead
    from ..services.encryption import EncryptionService
    from ..core.config import settings

    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.deleted_at.is_(None)).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    decrypted = EncryptionService.decrypt_lead_phi(lead)
    first_name = decrypted.get("first_name", "there")

    condition = lead.condition.value if lead.condition else "sleep concerns"
    outcome = lead.contact_outcome.value if lead.contact_outcome else "NEW"
    urgency = lead.urgency.value if lead.urgency else "unknown"
    has_insurance = "insured" if lead.has_insurance else "uninsured"
    treatment = lead.sleep_treatment_interest or "not specified"

    if not settings.anthropic_api_key:
        return {"subject": "Following up on your sleep consultation inquiry", "body": f"Hi {first_name},\n\nFollowing up on your inquiry with The Insomnia and Sleep Institute of Arizona.\n\nCall us at (480) 745-3547.\n\nWarmly,\nThe Insomnia and Sleep Institute of Arizona", "ai_generated": False}

    prompt = (
        f"Write a personalized follow-up EMAIL for a sleep medicine clinic lead.\n\n"
        f"Lead info:\n"
        f"- First name: {first_name}\n"
        f"- Condition: {condition}\n"
        f"- Current status: {outcome}\n"
        f"- Urgency: {urgency}\n"
        f"- Insurance: {has_insurance}\n"
        f"- Treatment interest: {treatment}\n"
        f"- Contact attempts: {lead.contact_attempts or 0}\n\n"
        f"Clinic: The Insomnia and Sleep Institute of Arizona\n"
        f"Phone: (480) 745-3547\n\n"
        f"Rules:\n"
        f"- Return JSON only with keys: subject, body\n"
        f"- Warm, professional tone — not pushy\n"
        f"- Mention their specific condition naturally\n"
        f"- If status is NO_ANSWER/UNREACHABLE, acknowledge missed contact\n"
        f"- If status is NOT_INTERESTED, be very gentle, no pressure\n"
        f"- If status is SCHEDULED/COMPLETED, focus on next steps or thank you\n"
        f"- Keep body under 150 words\n"
        f"- Sign off as 'The Insomnia and Sleep Institute of Arizona'\n"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.anthropic_model,
                    "max_tokens": 500,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            payload = response.json()
            text = payload.get("content", [{}])[0].get("text", "{}")
            # Parse JSON from Claude
            import json as _json
            # Handle markdown code blocks
            clean = text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0]
            result = _json.loads(clean)
            return {"subject": result.get("subject", ""), "body": result.get("body", ""), "ai_generated": True}
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"AI email generation failed: {e}")
        return {"subject": "Following up on your sleep consultation inquiry", "body": f"Hi {first_name},\n\nFollowing up on your inquiry with The Insomnia and Sleep Institute of Arizona about your {condition.lower().replace('_', ' ')}.\n\nWe'd love to connect and discuss next steps. Call us at (480) 745-3547 or reply to this email.\n\nWarmly,\nThe Insomnia and Sleep Institute of Arizona", "ai_generated": False}
