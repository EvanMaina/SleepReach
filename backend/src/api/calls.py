"""
Calls API — DEPRECATED (Twilio Voice removed)

Voice calls are handled by 3CX (external phone system).
The frontend uses tel: links which the 3CX Chrome extension intercepts.

This module is kept as a stub to prevent import errors.
CallRail handles call analytics (see callrail.py).

Service architecture:
- 3CX: All phone calls (inbound + outbound)
- Twilio: SMS only
- Paubox: Email only
- CallRail: Call tracking and analytics only
"""

from fastapi import APIRouter

router = APIRouter(prefix="/calls", tags=["Voice Calls (Deprecated)"])


@router.get("/config")
async def get_call_config():
    """
    Call configuration status.

    Voice calls are handled by 3CX (external phone system).
    The coordinator dashboard uses tel: links which the 3CX Chrome
    extension intercepts to initiate calls.
    """
    return {
        "configured": True,
        "provider": "3CX",
        "message": "Voice calls are handled by 3CX. The dashboard uses tel: links for click-to-call."
    }
