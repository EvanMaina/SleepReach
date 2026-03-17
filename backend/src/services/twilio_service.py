"""
Twilio Voice Service — DEPRECATED

Voice calls are handled by 3CX (external phone system).
This file is kept as a stub to prevent import errors.

Service architecture:
- 3CX: All phone calls (inbound + outbound)
- Twilio: SMS only (see sms_service.py)
- Paubox: Email only (see email_service.py / paubox_email_service.py)
- CallRail: Call tracking and analytics only (see api/callrail.py)
"""


class TwilioService:
    """Deprecated. Voice calls are handled by 3CX."""

    @property
    def is_configured(self) -> bool:
        return False


_twilio_service = None


def get_twilio_service() -> TwilioService:
    global _twilio_service
    if _twilio_service is None:
        _twilio_service = TwilioService()
    return _twilio_service
