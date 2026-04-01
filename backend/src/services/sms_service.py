"""
SMS service for sending transactional text messages via Twilio or local SMSDev.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import requests
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from ..core.config import settings

logger = logging.getLogger(__name__)


SMS_TEMPLATES = {
    "lead_receipt": "Hi {first_name}, thanks for contacting The Insomnia and Sleep Institute of Arizona. We received your information and a care coordinator will reach out within {response_time}. Questions? Call {phone_number}.",
    "follow_up": "Hi {first_name}, this is The Insomnia and Sleep Institute of Arizona following up on your sleep consultation inquiry. Reply here or call (480) 745-3547 if you'd like to connect.",
    "appointment_reminder": "Hi {first_name}, this is a reminder from The Insomnia and Sleep Institute of Arizona about your upcoming appointment. Need to reschedule? Call (480) 745-3547.",
    "missed_call": "Hi {first_name}, we tried reaching you from The Insomnia and Sleep Institute of Arizona about your sleep inquiry. Call (480) 745-3547 or reply here when you're available.",
    "not_interested_follow_up": "Hi {first_name}, it's The Insomnia and Sleep Institute of Arizona. We're checking in one last time in case you'd still like help with your sleep concerns. Call us anytime at (480) 745-3547.",
}


class SMSService:
    """Service for sending SMS messages via Twilio or the local dev server."""

    def __init__(self) -> None:
        self.account_sid = settings.twilio_account_sid
        self.auth_token = settings.twilio_auth_token
        self.from_number = settings.twilio_phone_number
        self.sms_mode = settings.sms_mode.lower()
        self.local_url = settings.sms_local_url

        if self.sms_mode == "twilio" and self.account_sid and self.auth_token:
            self.client = Client(self.account_sid, self.auth_token)
        else:
            self.client = None

    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        template_content = SMS_TEMPLATES.get(template_name, "")
        if not template_content:
            logger.error("SMS template %s not found", template_name)
            return ""

        try:
            return template_content.format(**context)
        except KeyError as exc:
            logger.error("Missing SMS template variable: %s", exc)
            return template_content

    def send_sms(self, to_number: str, message: str) -> Dict[str, Any]:
        try:
            if not to_number.startswith("+"):
                to_number = f"+1{to_number}"

            if self.sms_mode == "local":
                return self._send_to_local_server(to_number, message)

            if not self.client:
                return {
                    "success": False,
                    "error": "Twilio not configured",
                    "to": to_number,
                    "message": "SMS not sent (Twilio credentials missing)",
                }

            message_obj = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number,
            )
            return {
                "success": True,
                "message_sid": message_obj.sid,
                "status": message_obj.status,
                "to": message_obj.to,
                "from": message_obj.from_,
                "message": f"SMS sent successfully (SID: {message_obj.sid})",
            }
        except TwilioRestException as exc:
            logger.error("Twilio error sending SMS to %s: %s", to_number, exc.msg)
            return {
                "success": False,
                "error": exc.msg,
                "error_code": exc.code,
                "to": to_number,
                "message": f"Twilio error: {exc.msg}",
            }
        except Exception as exc:
            logger.error("Failed to send SMS to %s: %s", to_number, exc)
            return {
                "success": False,
                "error": str(exc),
                "to": to_number,
                "message": f"Failed to send SMS: {str(exc)}",
            }

    def _send_to_local_server(self, to_number: str, message: str) -> Dict[str, Any]:
        try:
            url = f"{self.local_url}/2010-04-01/Accounts/{self.account_sid or 'local'}/Messages.json"
            response = requests.post(
                url,
                data={
                    "To": to_number,
                    "From": self.from_number or "+15555555555",
                    "Body": message,
                },
                timeout=5,
            )

            if response.status_code not in (200, 201):
                return {
                    "success": False,
                    "error": f"Local server returned {response.status_code}",
                    "to": to_number,
                    "message": "Failed to send to local SMS server",
                }

            result = response.json()
            return {
                "success": True,
                "message_sid": result.get("sid", "LOCAL_NO_SID"),
                "status": "queued",
                "to": to_number,
                "from": self.from_number or "+15555555555",
                "message": f"SMS captured by local server (SID: {result.get('sid')})",
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "error": "Local SMS server not running",
                "to": to_number,
                "message": f"Local SMS server not running at {self.local_url}",
            }
        except Exception as exc:
            logger.error("Error sending to local SMS server: %s", exc)
            return {
                "success": False,
                "error": str(exc),
                "to": to_number,
                "message": f"Failed to send to local SMS server: {str(exc)}",
            }


sms_service = SMSService()
