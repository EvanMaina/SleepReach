"""
Email service for sending transactional emails.

Provides:
- Email sending via SMTP
- HTML email templates using shared email_base design system
- Template rendering with Jinja2
- Async email sending via Celery

ALL templates use the shared email_base.py for consistent header/footer/logo.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from datetime import datetime

from jinja2 import Template

from ..core.config import settings
from .email_base import (
    wrap_in_email_layout,
    email_divider,
    get_logo_url,
    CLINIC_NAME,
    CLINIC_ADDRESS,
    CLINIC_PHONE,
    CLINIC_EMAIL,
    CLINIC_WEBSITE,
    HEADER_BG_COLOR,
)


logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending transactional emails."""

    def __init__(self):
        """Initialize email service with SMTP configuration."""
        self.smtp_host = getattr(settings, 'smtp_host', 'smtp.gmail.com')
        self.smtp_port = getattr(settings, 'smtp_port', 587)
        self.smtp_username = getattr(settings, 'smtp_username', '')
        self.smtp_password = getattr(settings, 'smtp_password', '')
        self.from_email = getattr(
            settings, 'from_email', 'noreply@neuroreach.ai')
        self.from_name = getattr(settings, 'from_name', 'TMS Institute of Arizona')

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """
        Send an email.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email body
            text_content: Plain text email body (optional)

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email

            # Add text part
            if text_content:
                text_part = MIMEText(text_content, 'plain')
                msg.attach(text_part)

            # Add HTML part
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            # Send email via SMTP
            # For Maildev, we don't need authentication
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                # Only use TLS and login if credentials are provided
                if self.smtp_username and self.smtp_password:
                    server.starttls()
                    server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render an email template using shared email_base layout.

        Templates are built dynamically using wrap_in_email_layout from email_base.
        Jinja2 is used for variable substitution within the body content.

        Args:
            template_name: Name of the template
            context: Template context variables

        Returns:
            Rendered HTML content
        """
        # Build the body using Jinja2 template strings
        body_template_str = EMAIL_BODY_TEMPLATES.get(template_name)
        if not body_template_str:
            logger.error(f"Template {template_name} not found")
            return ""

        # Get title and subtitle for this template type
        title, subtitle = EMAIL_TITLES.get(template_name, ("", None))

        # Render the body with Jinja2
        body_template = Template(body_template_str)
        rendered_body = body_template.render(**context)

        # Render the title with Jinja2 (some titles have variables)
        title_template = Template(title)
        rendered_title = title_template.render(**context)

        if subtitle:
            subtitle_template = Template(subtitle)
            rendered_subtitle = subtitle_template.render(**context)
        else:
            rendered_subtitle = None

        # Wrap in the shared layout
        return wrap_in_email_layout(
            title=rendered_title,
            body_html=rendered_body,
            subtitle=rendered_subtitle,
        )


# =============================================================================
# Template Titles (title, subtitle) for each email type
# =============================================================================

EMAIL_TITLES = {
    "lead_receipt": (
        "TMS Therapy Consultation Request Received",
        "Thank you for reaching out to our care team",
    ),
    "user_invitation": (
        "Welcome to TMS NeuroReach",
        "Your account has been created",
    ),
    "password_reset": (
        "Reset Your Password",
        "We received a request to reset your TMS NeuroReach account password",
    ),
    "access_request_admin": (
        "New Access Request — TMS NeuroReach",
        "A new user has requested access to the dashboard",
    ),
}


# =============================================================================
# Template Body Content (Jinja2 strings - inner rows only, no header/footer)
# =============================================================================

_DIVIDER = email_divider()

EMAIL_BODY_TEMPLATES = {

    # =========================================================================
    # LEAD RECEIPT — sent to new leads (alternative to confirmation email)
    # =========================================================================
    "lead_receipt": f"""
{_DIVIDER}

                    <!-- Greeting -->
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <h2 style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 24px; font-weight: bold; color: #1A1A1A; line-height: 1.3;">
                                Thank You, {{{{ first_name }}}}!
                            </h2>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                We've received your consultation request for TMS therapy. We understand that taking the first step toward treatment can feel overwhelming &mdash; you're not alone, and our team is here to guide you every step of the way.
                            </p>
                        </td>
                    </tr>

{_DIVIDER}

                    <!-- What Happens Next -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <h3 style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 20px; font-weight: bold; color: #1A1A1A; line-height: 1.3;">
                                What Happens Next
                            </h3>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <p style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; font-weight: bold; color: #1A1A1A;">&#8226; We Review Your Information</p>
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">Our team reviews your information and medical history.</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; font-weight: bold; color: #1A1A1A;">&#8226; A Personal Call From Us</p>
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">A care coordinator will personally reach out to you within {{{{ response_time }}}} to discuss your options.</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; font-weight: bold; color: #1A1A1A;">&#8226; Your Consultation</p>
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">We'll schedule a consultation with our TMS specialists at a time that works for you.</p>
                        </td>
                    </tr>

{_DIVIDER}

                    <!-- CTA -->
                    <tr>
                        <td align="center" style="padding: 10px 30px 0 30px;">
                            <a href="tel:+14806683599" style="display: inline-block; padding: 14px 32px; background-color: {HEADER_BG_COLOR}; color: #ffffff; text-decoration: none; border-radius: 8px; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: bold;">Call Us: (480) 668-3599</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #999999; line-height: 1.6; text-align: center;">
                                If you have any questions or need immediate assistance, please don't hesitate to contact us.
                            </p>
                        </td>
                    </tr>
""",

    # =========================================================================
    # USER INVITATION — sent when an admin creates a new coordinator account
    # =========================================================================
    "user_invitation": f"""
{_DIVIDER}

                    <!-- Greeting -->
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <h2 style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 22px; font-weight: bold; color: #1A1A1A; line-height: 1.3;">
                                Hi {{{{ first_name }}}} {{{{ last_name }}}},
                            </h2>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                An administrator has created your TMS Institute of Arizona account. You can use the credentials below to log in for the first time.
                            </p>
                        </td>
                    </tr>

{_DIVIDER}

                    <!-- Credentials Box -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #F0F4F8; border-radius: 8px;">
                                <tr>
                                    <td style="padding: 24px 28px;">
                                        <table width="100%" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #DCE4EC;">
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #6B7280; font-size: 13px;">Role</span><br>
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #1A1A1A; font-size: 15px; font-weight: bold;">{{{{ role }}}}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #DCE4EC;">
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #6B7280; font-size: 13px;">Email (Username)</span><br>
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #1A1A1A; font-size: 15px; font-weight: bold;">{{{{ email }}}}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0;">
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #6B7280; font-size: 13px;">Temporary Password</span><br>
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #1E3A5F; font-size: 18px; font-weight: bold; letter-spacing: 1px;">{{{{ temp_password }}}}</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

{_DIVIDER}

                    <!-- Log In CTA Button -->
                    <tr>
                        <td align="center" style="padding: 10px 30px 0 30px;">
                            <a href="{{{{ login_url }}}}" style="display: inline-block; padding: 16px 40px; background-color: {HEADER_BG_COLOR}; color: #ffffff; text-decoration: none; border-radius: 8px; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: bold;">Log In to Your Account</a>
                        </td>
                    </tr>

{_DIVIDER}

                    <!-- Warning Box -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #FEF3C7; border-left: 4px solid #F59E0B; border-radius: 8px;">
                                <tr>
                                    <td style="padding: 16px 20px;">
                                        <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; color: #92400E; font-size: 14px; line-height: 1.5;">
                                            <strong>Important:</strong> You will be prompted to change this temporary password on your first login. Your temporary password expires in 48 hours. Please choose a strong password that includes at least 8 characters, one uppercase letter, one lowercase letter, and one number.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #444444; line-height: 1.6;">
                                If you have any questions or trouble logging in, contact your administrator.
                            </p>
                        </td>
                    </tr>
""",

    # =========================================================================
    # PASSWORD RESET — sent when user requests a password reset
    # =========================================================================
    "password_reset": f"""
{_DIVIDER}

                    <!-- Greeting -->
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <h2 style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 22px; font-weight: bold; color: #1A1A1A; line-height: 1.3;">
                                Hi {{{{ first_name }}}},
                            </h2>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                We received a request to reset your password for your TMS NeuroReach account. Click the button below to set a new password.
                            </p>
                        </td>
                    </tr>

{_DIVIDER}

                    <!-- Reset Password CTA Button -->
                    <tr>
                        <td align="center" style="padding: 10px 30px 0 30px;">
                            <a href="{{{{ reset_url }}}}" style="display: inline-block; padding: 16px 40px; background-color: {HEADER_BG_COLOR}; color: #ffffff; text-decoration: none; border-radius: 8px; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: bold;">Reset Your Password</a>
                        </td>
                    </tr>

{_DIVIDER}

                    <!-- Expiry Notice -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #F0F7F7; border-left: 4px solid {HEADER_BG_COLOR}; border-radius: 8px;">
                                <tr>
                                    <td style="padding: 16px 20px;">
                                        <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; color: #1A1A1A; font-size: 14px; line-height: 1.5;">
                                            <strong>This link will expire in 1 hour.</strong> After that, you'll need to request a new reset link.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

{_DIVIDER}

                    <!-- Security Notice -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #999999; line-height: 1.6;">
                                If you didn't request this password reset, you can safely ignore this email. Your password will remain unchanged.
                            </p>
                        </td>
                    </tr>

                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 13px; color: #BBBBBB; line-height: 1.5;">
                                For security reasons, this link can only be used once. If you need to reset your password again, please submit a new request from the login page.
                            </p>
                        </td>
                    </tr>
""",

    # =========================================================================
    # ACCESS REQUEST ADMIN — sent to admin when someone requests dashboard access
    # =========================================================================
    "access_request_admin": f"""
{_DIVIDER}

                    <!-- Intro -->
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                A new user has requested access to the TMS NeuroReach dashboard. Please review their details below.
                            </p>
                        </td>
                    </tr>

{_DIVIDER}

                    <!-- Request Details Box -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #F0F4F8; border-radius: 8px;">
                                <tr>
                                    <td style="padding: 24px 28px;">
                                        <table width="100%" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #DCE4EC;">
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #6B7280; font-size: 13px;">Full Name</span><br>
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #1A1A1A; font-size: 15px; font-weight: bold;">{{{{ full_name }}}}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; border-bottom: 1px solid #DCE4EC;">
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #6B7280; font-size: 13px;">Email Address</span><br>
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #1A1A1A; font-size: 15px; font-weight: bold;">{{{{ requester_email }}}}</span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0;">
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #6B7280; font-size: 13px;">Role / Reason for Access</span><br>
                                                    <span style="font-family: Arial, Helvetica, sans-serif; color: #1A1A1A; font-size: 15px;">{{{{ reason }}}}</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

{_DIVIDER}

                    <!-- Action Note -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #F0F7F7; border-left: 4px solid {HEADER_BG_COLOR}; border-radius: 8px;">
                                <tr>
                                    <td style="padding: 16px 20px;">
                                        <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; color: #1A1A1A; font-size: 14px; line-height: 1.5;">
                                            <strong>To grant access:</strong> Log into the admin panel and create their account from the Settings &rarr; User Management section.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
""",
}


# Create global instance
email_service = EmailService()
