"""
SMS service for sending transactional text messages via Twilio.

Provides:
- SMS sending via Twilio or local dev server
- SMS templates
- Template rendering
- Async SMS sending via Celery
"""

import logging
from typing import Optional, Dict, Any
import requests

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from ..core.config import settings


logger = logging.getLogger(__name__)


class SMSService:
    """Service for sending transactional SMS messages."""

    def __init__(self):
        """Initialize SMS service with Twilio configuration."""
        self.account_sid = settings.twilio_account_sid
        self.auth_token = settings.twilio_auth_token
        self.from_number = settings.twilio_phone_number
        self.sms_mode = settings.sms_mode.lower()
        self.local_url = settings.sms_local_url

        # Initialize Twilio client if in Twilio mode
        if self.sms_mode == "twilio":
            if self.account_sid and self.auth_token:
                self.client = Client(self.account_sid, self.auth_token)
            else:
                self.client = None
                logger.warning(
                    "Twilio credentials not configured - SMS service disabled")
        else:
            self.client = None
            logger.info(f"🔧 SMS service initialized in LOCAL mode - routing to dev server at {self.local_url}")

    def send_sms(
        self,
        to_number: str,
        message: str,
    ) -> Dict[str, Any]:
        """
        Send an SMS message via Twilio or local dev server.

        Args:
            to_number: Recipient phone number (E.164 format)
            message: SMS message content

        Returns:
            Dict with success status, message SID, and error details
        """
        try:
            # Validate phone number format
            if not to_number.startswith('+'):
                to_number = f'+1{to_number}'  # Assume US number

            logger.info(f"📤 Sending SMS via {self.sms_mode.upper()} mode to {to_number}")
            
            # LOCAL MODE: Send to local dev server
            if self.sms_mode == "local":
                logger.info(f"🔄 Routing SMS to local dev server: {self.local_url}")
                return self._send_to_local_server(to_number, message)
            
            # TWILIO MODE: Send via Twilio API
            if not self.client:
                logger.warning(
                    f"Twilio not configured - SMS not sent: {to_number}")
                return {
                    "success": False,
                    "error": "Twilio not configured",
                    "to": to_number,
                    "message": "SMS not sent (Twilio credentials missing)",
                }

            # Send SMS via Twilio
            message_obj = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number
            )

            logger.info(
                f"SMS sent via Twilio to {to_number} (SID: {message_obj.sid})")
            
            return {
                "success": True,
                "message_sid": message_obj.sid,
                "status": message_obj.status,
                "to": message_obj.to,
                "from": message_obj.from_,
                "message": f"SMS sent successfully (SID: {message_obj.sid})",
            }

        except TwilioRestException as e:
            logger.error(f"Twilio error sending SMS to {to_number}: {e.msg} (Code: {e.code})")
            return {
                "success": False,
                "error": e.msg,
                "error_code": e.code,
                "to": to_number,
                "message": f"Twilio error: {e.msg}",
            }

        except Exception as e:
            logger.error(f"Failed to send SMS to {to_number}: {e}")
            return {
                "success": False,
                "error": str(e),
                "to": to_number,
                "message": f"Failed to send SMS: {str(e)}",
            }
    
    def _send_to_local_server(self, to_number: str, message: str) -> Dict[str, Any]:
        """
        Send SMS to local dev server for testing.
        
        Args:
            to_number: Recipient phone number
            message: SMS message content
            
        Returns:
            Dict with success status and message SID
        """
        try:
            # Construct Twilio-compatible API URL
            url = f"{self.local_url}/2010-04-01/Accounts/{self.account_sid or 'local'}/Messages.json"
            
            # Send as form data (Twilio format)
            response = requests.post(
                url,
                data={
                    'To': to_number,
                    'From': self.from_number or '+15555555555',
                    'Body': message
                },
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                logger.info(f"SMS captured by local server: {to_number} (SID: {result.get('sid')})")
                return {
                    "success": True,
                    "message_sid": result.get('sid', 'LOCAL_NO_SID'),
                    "status": "queued",
                    "to": to_number,
                    "from": self.from_number or '+15555555555',
                    "message": f"SMS captured by local server (SID: {result.get('sid')})",
                }
            else:
                logger.error(f"Local SMS server error: {response.status_code}")
                return {
                    "success": False,
                    "error": f"Local server returned {response.status_code}",
                    "to": to_number,
                    "message": "Failed to send to local SMS server",
                }
                
        except requests.exceptions.ConnectionError:
            logger.error(f"Cannot connect to local SMS server at {self.local_url}")
            return {
                "success": False,
                "error": "Local SMS server not running",
                "to": to_number,
                "message": f"Local SMS server not running at {self.local_url}. Start it with: python scripts/sms_dev_server.py",
            }
        except Exception as e:
            logger.error(f"Error sending to local SMS server: {e}")
            return {
                "success": False,
                "error": str(e),
                "to": to_number,
                "message": f"Failed to send to local SMS server: {str(e)}",
            }

    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render an SMS template.

        Args:
            template_name: Name of the template
            context: Template context variables

        Returns:
            Rendered SMS content
        """
        template_content = SMS_TEMPLATES.get(template_name, "")
        if not template_content:
            logger.error(f"SMS template {template_name} not found")
            return ""

        # Simple string formatting for SMS templates
        try:
            return template_content.format(**context)
        except KeyError as e:
            logger.error(f"Missing template variable: {e}")
            return template_content


# =============================================================================
# SMS Templates
# =============================================================================

SMS_TEMPLATES = {
    "lead_receipt": """Hi {first_name}! Thank you for your interest in TMS therapy. We've received your consultation request (Ref: {lead_number}). A care coordinator will personally reach out to you within {response_time}. Questions? Call us at {phone_number} - TMS Institute of Arizona""",

    "follow_up": """Hi {first_name}, this is TMS Institute of Arizona following up on your inquiry. We'd love to answer any questions about TMS therapy. Call us at (480) 668-3599""",

    "not_interested_follow_up": """Hi {first_name}, it's TMS Institute of Arizona. We just wanted to check in — if anything has changed or you have questions about TMS therapy, we're here for you. No pressure at all. Call us anytime at (480) 668-3599""",

}


# Create global instance
sms_service = SMSService()
