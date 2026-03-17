"""
Paubox Email Service for HIPAA-compliant email sending.

Integrates with Paubox Email API for secure, encrypted email delivery.
Provides:
- HIPAA-compliant email transmission
- Open/click tracking (if enabled in Paubox dashboard)
- Automatic fallback to SMTP if Paubox is unavailable
- Comprehensive error handling and logging
"""

import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import httpx

from ..core.config import settings


logger = logging.getLogger(__name__)


class PauboxEmailService:
    """
    Service for sending HIPAA-compliant emails via Paubox Email API.
    
    API Documentation: https://docs.paubox.com/docs/email-api/
    
    Features:
    - Secure HTTPS transmission
    - TLS encryption for email delivery
    - Optional force_secure_notification for sensitive content
    - Tracking capabilities (opens, clicks, unsubscribes)
    """
    
    def __init__(self):
        """Initialize Paubox email service with configuration."""
        self.api_key = settings.paubox_api_key
        self.api_username = settings.paubox_api_username
        self.api_base_url = settings.paubox_api_base_url
        self.from_email = settings.paubox_from_email
        self.enabled = settings.paubox_enabled
        
        # Validate configuration
        if self.enabled:
            if not all([self.api_key, self.api_username, self.api_base_url, self.from_email]):
                logger.warning(
                    "Paubox is enabled but not fully configured. "
                    "Missing: api_key=%s, api_username=%s, api_base_url=%s, from_email=%s",
                    bool(self.api_key), bool(self.api_username), 
                    bool(self.api_base_url), bool(self.from_email)
                )
                self.enabled = False
    
    @property
    def is_configured(self) -> bool:
        """Check if Paubox is properly configured."""
        return self.enabled and all([
            self.api_key,
            self.api_username,
            self.api_base_url,
            self.from_email
        ])
    
    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers with authentication."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Token token={self.api_key}"
        }
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        force_secure_notification: bool = False,
        allow_non_tls: bool = True,
    ) -> Dict[str, Any]:
        """
        Send an email via Paubox Email API.
        
        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_content: HTML email body
            text_content: Plain text email body (optional, recommended)
            reply_to: Reply-to email address (optional)
            cc: List of CC recipients (optional)
            bcc: List of BCC recipients (optional)
            force_secure_notification: If True, forces portal pickup for PHI
            allow_non_tls: If True, allows delivery even if recipient doesn't support TLS
            
        Returns:
            Dict with success status, message_id, and any error details
        """
        if not self.is_configured:
            logger.error("Paubox is not configured. Cannot send email.")
            return {
                "success": False,
                "error": "Paubox email service is not configured",
                "fallback_available": True
            }
        
        # Build recipient object
        recipients = {
            "to": [to_email]
        }
        if cc:
            recipients["cc"] = cc
        if bcc:
            recipients["bcc"] = bcc
        
        # Build content object
        content = {
            "text/html": html_content
        }
        if text_content:
            content["text/plain"] = text_content
        
        # Build the message payload
        # Paubox API format: https://docs.paubox.com/docs/email-api/send-messages
        payload = {
            "data": {
                "message": {
                    "recipients": [to_email],
                    "headers": {
                        "subject": subject,
                        "from": f"{settings.from_name} <{self.from_email}>"
                    },
                    "content": content,
                    "allow_non_tls": allow_non_tls
                }
            }
        }
        
        # Add optional headers
        if reply_to:
            payload["data"]["message"]["headers"]["reply-to"] = reply_to
        
        # Add CC/BCC if provided
        if cc:
            payload["data"]["message"]["cc"] = cc
        if bcc:
            payload["data"]["message"]["bcc"] = bcc
        
        # Force secure notification for sensitive PHI
        if force_secure_notification:
            payload["data"]["message"]["force_secure_notification"] = "true"
        
        try:
            # Send request to Paubox API
            endpoint = f"{self.api_base_url}/messages"
            
            logger.info(f"Sending email via Paubox to {to_email}, subject: {subject[:50]}...")
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    endpoint,
                    headers=self._get_headers(),
                    json=payload
                )
            
            # Parse response
            if response.status_code in [200, 201]:
                response_data = response.json()
                source_tracking_id = response_data.get("sourceTrackingId", "")
                
                logger.info(
                    f"Email sent successfully via Paubox. "
                    f"To: {to_email}, Tracking ID: {source_tracking_id}"
                )
                
                return {
                    "success": True,
                    "message_id": source_tracking_id,
                    "status": "sent",
                    "provider": "paubox",
                    "response": response_data
                }
            else:
                # Handle error response
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = json.dumps(error_json)
                except (ValueError, TypeError):
                    pass
                
                logger.error(
                    f"Paubox API error: {response.status_code} - {error_detail}"
                )
                
                return {
                    "success": False,
                    "error": f"Paubox API returned {response.status_code}",
                    "detail": error_detail,
                    "fallback_available": True
                }
                
        except httpx.TimeoutException as e:
            logger.error(f"Paubox API timeout: {e}")
            return {
                "success": False,
                "error": "Paubox API request timed out",
                "fallback_available": True
            }
        except httpx.RequestError as e:
            logger.error(f"Paubox API request error: {e}")
            return {
                "success": False,
                "error": f"Failed to connect to Paubox API: {str(e)}",
                "fallback_available": True
            }
        except Exception as e:
            logger.error(f"Unexpected error sending via Paubox: {e}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "fallback_available": True
            }
    
    def get_email_status(self, source_tracking_id: str) -> Dict[str, Any]:
        """
        Get the delivery status of a sent email.
        
        Args:
            source_tracking_id: The tracking ID returned when email was sent
            
        Returns:
            Dict with status information
        """
        if not self.is_configured:
            return {"success": False, "error": "Paubox not configured"}
        
        try:
            endpoint = f"{self.api_base_url}/message_receipt/{source_tracking_id}"
            
            with httpx.Client(timeout=30.0) as client:
                response = client.get(endpoint, headers=self._get_headers())
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "data": response.json()
                }
            else:
                return {
                    "success": False,
                    "error": f"API returned {response.status_code}",
                    "detail": response.text
                }
                
        except Exception as e:
            logger.error(f"Error fetching email status: {e}")
            return {"success": False, "error": str(e)}


# Create global instance
paubox_email_service = PauboxEmailService()


def send_email_via_paubox(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    lead_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to send email with provider controlled by EMAIL_MODE.
    
    EMAIL_MODE controls behavior:
    - "maildev" (default for local dev): Always use SMTP -> MailDev. Never touches Paubox.
    - "paubox" (production): Use Paubox API, fall back to SMTP on failure.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML email body
        text_content: Plain text email body (optional)
        lead_id: Optional lead ID for logging
        
    Returns:
        Dict with success status and details
    """
    email_mode = getattr(settings, "email_mode", "maildev").lower().strip()

    # =========================================================================
    # MAILDEV MODE: Go straight to SMTP (MailDev container), skip Paubox
    # =========================================================================
    if email_mode == "maildev":
        logger.info(f"EMAIL_MODE=maildev — sending via SMTP/MailDev to {to_email}")
        try:
            from .email_service import email_service

            smtp_result = email_service.send_email(
                to_email=to_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )

            if smtp_result:
                logger.info(f"Email sent via MailDev SMTP to {to_email}")
            else:
                logger.error(f"MailDev SMTP send failed for {to_email}")

            return {
                "success": smtp_result,
                "provider": "maildev",
                "message": "Email sent via MailDev" if smtp_result else "MailDev SMTP send failed",
            }

        except Exception as e:
            logger.error(f"MailDev SMTP error: {e}")
            return {"success": False, "error": f"MailDev SMTP failed: {str(e)}"}

    # =========================================================================
    # PAUBOX MODE: Try Paubox first, fall back to SMTP on failure
    # =========================================================================
    if paubox_email_service.is_configured:
        result = paubox_email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )
        
        if result.get("success"):
            return result
        
        # If Paubox failed but fallback is available, try SMTP
        if result.get("fallback_available"):
            logger.warning("Paubox failed, falling back to SMTP")
    else:
        logger.info("Paubox not configured, using SMTP directly")
    
    # Fallback to SMTP
    try:
        from .email_service import email_service
        
        smtp_result = email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )
        
        return {
            "success": smtp_result,
            "provider": "smtp",
            "message": "Email sent via SMTP fallback" if smtp_result else "SMTP send failed"
        }
        
    except Exception as e:
        logger.error(f"SMTP fallback also failed: {e}")
        return {
            "success": False,
            "error": f"Both Paubox and SMTP failed: {str(e)}"
        }
