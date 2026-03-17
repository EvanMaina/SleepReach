"""
============================================================================
UNIFIED LEAD CONFIRMATION EMAIL — SINGLE SOURCE OF TRUTH
============================================================================

This is the single source of truth for all lead confirmation emails.
Any new lead source should call send_lead_confirmation_email(lead_data).

All three lead sources (Widget, Google Ads, Jotform) use this ONE template.
DO NOT create separate confirmation email templates elsewhere.

Uses the shared email_base for consistent header/footer/logo across all emails.
============================================================================
"""

import logging
from typing import Dict, Any

from .email_base import wrap_in_email_layout, email_divider

logger = logging.getLogger(__name__)


# =============================================================================
# HTML Email Builder
# =============================================================================

def build_lead_confirmation_email(lead_data: Dict[str, Any]) -> str:
    """
    Build the unified lead confirmation email HTML.

    This is the ONLY place the lead confirmation email HTML lives.
    Final version — no conditions section, no reference number.
    Uses bullet dots instead of numbered steps.

    Args:
        lead_data: Dict with keys:
            - first_name (str): Patient's first name

    Returns:
        Fully rendered HTML string for the confirmation email.
    """
    first_name = lead_data.get("first_name", "").strip() or "there"

    # Build the body content (just the inner rows, no header/footer)
    body_html = f"""
{email_divider()}

                    <!-- Greeting -->
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <h2 style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 24px; font-weight: bold; color: #1A1A1A; line-height: 1.3;">
                                Thank You, {first_name}!
                            </h2>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                We're glad you reached out to TMS Institute of Arizona. Taking the first step toward feeling better takes courage &mdash; and we're here to make the rest easy for you.
                            </p>
                        </td>
                    </tr>

{email_divider()}

                    <!-- What Happens Next -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <h3 style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 20px; font-weight: bold; color: #1A1A1A; line-height: 1.3;">
                                What Happens Next
                            </h3>
                        </td>
                    </tr>

                    <!-- Step 1 -->
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <p style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; font-weight: bold; color: #1A1A1A; line-height: 1.4;">
                                &#8226; We Review Your Information
                            </p>
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                Our care team is reviewing your details now.
                            </p>
                        </td>
                    </tr>

                    <!-- Step 2 -->
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; font-weight: bold; color: #1A1A1A; line-height: 1.4;">
                                &#8226; A Personal Call From Us
                            </p>
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                A care coordinator will reach out within 2 hours to answer your questions.
                            </p>
                        </td>
                    </tr>

                    <!-- Step 3 -->
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; font-weight: bold; color: #1A1A1A; line-height: 1.4;">
                                &#8226; Your Consultation
                            </p>
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                We'll schedule a consultation with our TMS specialists at a time that works for you.
                            </p>
                        </td>
                    </tr>

{email_divider()}

                    <!-- Warm closing -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; font-style: italic; line-height: 1.6;">
                                We look forward to helping you on your journey to wellness.
                            </p>
                        </td>
                    </tr>

{email_divider()}

                    <!-- Contact -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <p style="margin: 0 0 8px 0; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: bold; color: #1A1A1A; line-height: 1.4;">
                                Have questions right now?
                            </p>
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                Call us at <a href="tel:4806683599" style="color: #1A1A1A; font-weight: bold; text-decoration: none;">(480) 668-3599</a> &mdash; we're happy to help.
                            </p>
                        </td>
                    </tr>
"""

    return wrap_in_email_layout(
        title="We've Received Your Request",
        body_html=body_html,
    )


# =============================================================================
# Follow-Up Email Builder
# =============================================================================

FOLLOW_UP_EMAIL_SUBJECT = "Following Up on Your TMS Therapy Inquiry"
FOLLOW_UP_EMAIL_FROM = "support@tmsinstitute.co"


def build_follow_up_email(lead_data: Dict[str, Any]) -> str:
    """
    Build the automated follow-up email HTML.

    Reuses the shared email_base layout (same TMS logo header, footer, styling)
    with follow-up specific body content.

    Args:
        lead_data: Dict with keys:
            - first_name (str): Patient's first name

    Returns:
        Fully rendered HTML string for the follow-up email.
    """
    first_name = lead_data.get("first_name", "").strip() or "there"

    body_html = f"""
{email_divider()}

                    <!-- Greeting -->
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <h2 style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 24px; font-weight: bold; color: #1A1A1A; line-height: 1.3;">
                                Hi {first_name},
                            </h2>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                I hope this message finds you well. I wanted to follow up on your recent inquiry about TMS therapy.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                We understand that taking the first step toward treatment can feel overwhelming, and we're here to support you every step of the way.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                If you have any questions about TMS therapy or would like to schedule a consultation, please don't hesitate to reach out. You can call us at <a href="tel:4806683599" style="color: #1A1A1A; font-weight: bold; text-decoration: none;">(480) 668-3599</a>.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                We look forward to hearing from you.
                            </p>
                        </td>
                    </tr>

{email_divider()}

                    <!-- Sign-off -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <p style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                Warm regards,
                            </p>
                            <p style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; font-weight: bold; color: #1A1A1A; line-height: 1.6;">
                                TMS Institute of Arizona
                            </p>
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                <a href="tel:4806683599" style="color: #1A1A1A; font-weight: bold; text-decoration: none;">(480) 668-3599</a>
                            </p>
                        </td>
                    </tr>
"""

    return wrap_in_email_layout(
        title="Following Up on Your TMS Therapy Inquiry",
        body_html=body_html,
    )


def send_follow_up_email(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build and send the automated follow-up email.

    Args:
        lead_data: Dict with keys:
            - first_name (str): Patient's first name
            - email (str): Patient's email address
            - lead_id (str, optional): For logging

    Returns:
        Dict with:
            - success (bool)
            - provider (str): "paubox" or "smtp"
            - error (str, optional): Error message if failed
    """
    email = lead_data.get("email", "")
    first_name = lead_data.get("first_name", "")
    lead_id = lead_data.get("lead_id", "unknown")

    if not email:
        logger.warning(
            f"Cannot send follow-up email — no email address for lead {lead_id}"
        )
        return {"success": False, "error": "No email address provided"}

    # Build the HTML
    html_content = build_follow_up_email(lead_data)

    # Build plain-text fallback
    text_content = f"""Hi {first_name or 'there'},

I hope this message finds you well. I wanted to follow up on your recent inquiry about TMS therapy.

We understand that taking the first step toward treatment can feel overwhelming, and we're here to support you every step of the way.

If you have any questions about TMS therapy or would like to schedule a consultation, please don't hesitate to reach out. You can call us at (480) 668-3599.

We look forward to hearing from you.

Warm regards,
TMS Institute of Arizona
(480) 668-3599

---
TMS Institute of Arizona
5150 N 16th St, Suite A-114, Phoenix, AZ 85016
(480) 668-3599 | support@tmsinstitute.co | tmsinstitute.co

This email contains protected health information (PHI). Your privacy is protected under HIPAA.
© 2026 TMS Institute of Arizona. All rights reserved."""

    try:
        from .paubox_email_service import send_email_via_paubox

        result = send_email_via_paubox(
            to_email=email,
            subject=FOLLOW_UP_EMAIL_SUBJECT,
            html_content=html_content,
            text_content=text_content,
            lead_id=lead_data.get("lead_id"),
        )

        if result.get("success"):
            logger.info(
                f"Follow-up email sent to {email[:3]}***@{email.split('@')[-1] if '@' in email else '***'} "
                f"via {result.get('provider', 'unknown')} for lead {lead_id}"
            )
        else:
            logger.error(
                f"Failed to send follow-up email for lead {lead_id}: "
                f"{result.get('error', 'unknown error')}"
            )

        return result

    except Exception as e:
        logger.error(f"Exception sending follow-up email for {lead_id}: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# Not Interested Follow-Up Email Builder (Softer Tone — 3-Week Cadence)
# =============================================================================

NOT_INTERESTED_FOLLOW_UP_EMAIL_SUBJECT = "Checking In — TMS Institute of Arizona"
NOT_INTERESTED_FOLLOW_UP_EMAIL_FROM = "support@tmsinstitute.co"


def build_not_interested_follow_up_email(lead_data: Dict[str, Any]) -> str:
    """
    Build the softer "not interested" follow-up email HTML.

    Used for leads who declined initially — sent every 3 weeks.
    Tone is warm, no-pressure, and inviting without being pushy.

    Args:
        lead_data: Dict with keys:
            - first_name (str): Patient's first name

    Returns:
        Fully rendered HTML string for the not-interested follow-up email.
    """
    first_name = lead_data.get("first_name", "").strip() or "there"

    body_html = f"""
{email_divider()}

                    <!-- Greeting -->
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <h2 style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 24px; font-weight: bold; color: #1A1A1A; line-height: 1.3;">
                                Hi {first_name},
                            </h2>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                We just wanted to check in and see how you're doing. We completely understand that TMS therapy may not have felt right for you at the time &mdash; and that's perfectly okay.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                If anything has changed, or if you simply have questions about how TMS works, we're always here to help &mdash; no pressure at all.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 16px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                You can reach us anytime at <a href="tel:4806683599" style="color: #1A1A1A; font-weight: bold; text-decoration: none;">(480) 668-3599</a>. We'd love to hear from you whenever you're ready.
                            </p>
                        </td>
                    </tr>

{email_divider()}

                    <!-- Sign-off -->
                    <tr>
                        <td style="padding: 0 30px;">
                            <p style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                Wishing you well,
                            </p>
                            <p style="margin: 0 0 4px 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; font-weight: bold; color: #1A1A1A; line-height: 1.6;">
                                TMS Institute of Arizona
                            </p>
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 15px; color: #444444; line-height: 1.6;">
                                <a href="tel:4806683599" style="color: #1A1A1A; font-weight: bold; text-decoration: none;">(480) 668-3599</a>
                            </p>
                        </td>
                    </tr>
"""

    return wrap_in_email_layout(
        title="Checking In — TMS Institute of Arizona",
        body_html=body_html,
    )


def send_not_interested_follow_up_email(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build and send the softer not-interested follow-up email.

    Args:
        lead_data: Dict with keys:
            - first_name (str): Patient's first name
            - email (str): Patient's email address
            - lead_id (str, optional): For logging

    Returns:
        Dict with:
            - success (bool)
            - provider (str): "paubox" or "smtp"
            - error (str, optional): Error message if failed
    """
    email = lead_data.get("email", "")
    first_name = lead_data.get("first_name", "")
    lead_id = lead_data.get("lead_id", "unknown")

    if not email:
        logger.warning(
            f"Cannot send not-interested follow-up email — no email address for lead {lead_id}"
        )
        return {"success": False, "error": "No email address provided"}

    # Build the HTML
    html_content = build_not_interested_follow_up_email(lead_data)

    # Build plain-text fallback
    text_content = f"""Hi {first_name or 'there'},

We just wanted to check in and see how you're doing. We completely understand that TMS therapy may not have felt right for you at the time — and that's perfectly okay.

If anything has changed, or if you simply have questions about how TMS works, we're always here to help — no pressure at all.

You can reach us anytime at (480) 668-3599. We'd love to hear from you whenever you're ready.

Wishing you well,
TMS Institute of Arizona
(480) 668-3599

---
TMS Institute of Arizona
5150 N 16th St, Suite A-114, Phoenix, AZ 85016
(480) 668-3599 | support@tmsinstitute.co | tmsinstitute.co

This email contains protected health information (PHI). Your privacy is protected under HIPAA.
© 2026 TMS Institute of Arizona. All rights reserved."""

    try:
        from .paubox_email_service import send_email_via_paubox

        result = send_email_via_paubox(
            to_email=email,
            subject=NOT_INTERESTED_FOLLOW_UP_EMAIL_SUBJECT,
            html_content=html_content,
            text_content=text_content,
            lead_id=lead_data.get("lead_id"),
        )

        if result.get("success"):
            logger.info(
                f"Not-interested follow-up email sent to {email[:3]}***@{email.split('@')[-1] if '@' in email else '***'} "
                f"via {result.get('provider', 'unknown')} for lead {lead_id}"
            )
        else:
            logger.error(
                f"Failed to send not-interested follow-up email for lead {lead_id}: "
                f"{result.get('error', 'unknown error')}"
            )

        return result

    except Exception as e:
        logger.error(f"Exception sending not-interested follow-up email for {lead_id}: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# Unified Sending Function (Lead Confirmation)
# =============================================================================

EMAIL_SUBJECT = "We've Received Your Request \u2014 TMS Institute of Arizona"
EMAIL_FROM = "support@tmsinstitute.co"


def send_lead_confirmation_email(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build and send the unified lead confirmation email.

    This is the ONE function all lead sources call to send the patient-facing
    confirmation email. It builds the HTML from the master template, sends
    via Paubox (with SMTP fallback), and handles errors gracefully.

    Args:
        lead_data: Dict with keys:
            - first_name (str): Patient's first name
            - email (str): Patient's email address
            - lead_number (str, optional): For logging only
            - conditions (list[str], optional): Ignored (kept for caller compat)
            - other_condition_text (str, optional): Ignored (kept for caller compat)

    Returns:
        Dict with:
            - success (bool)
            - provider (str): "paubox" or "smtp"
            - error (str, optional): Error message if failed
    """
    email = lead_data.get("email", "")
    first_name = lead_data.get("first_name", "")
    lead_number = lead_data.get("lead_number", "unknown")

    if not email:
        logger.warning(
            f"Cannot send confirmation email — no email address for lead {lead_number}"
        )
        return {"success": False, "error": "No email address provided"}

    # Build the HTML
    html_content = build_lead_confirmation_email(lead_data)

    # Build plain-text fallback (no conditions, no reference number)
    text_content = f"""Thank You, {first_name or 'there'}!

We're glad you reached out to TMS Institute of Arizona. Taking the first step toward feeling better takes courage - and we're here to make the rest easy for you.

What Happens Next:
* We Review Your Information - Our care team is reviewing your details now.
* A Personal Call From Us - A care coordinator will reach out within 2 hours to answer your questions.
* Your Consultation - We'll schedule a consultation with our TMS specialists at a time that works for you.

We look forward to helping you on your journey to wellness.

Have questions right now?
Call us at (480) 668-3599 - we're happy to help.

---
TMS Institute of Arizona
5150 N 16th St, Suite A-114, Phoenix, AZ 85016
(480) 668-3599 | support@tmsinstitute.co | tmsinstitute.co

This email contains protected health information (PHI). Your privacy is protected under HIPAA.
© 2026 TMS Institute of Arizona. All rights reserved."""

    try:
        from .paubox_email_service import send_email_via_paubox

        result = send_email_via_paubox(
            to_email=email,
            subject=EMAIL_SUBJECT,
            html_content=html_content,
            text_content=text_content,
            lead_id=lead_data.get("lead_id"),
        )

        if result.get("success"):
            logger.info(
                f"Lead confirmation email sent to {email[:3]}***@{email.split('@')[-1] if '@' in email else '***'} "
                f"via {result.get('provider', 'unknown')} for lead {lead_number}"
            )
        else:
            logger.error(
                f"Failed to send lead confirmation email for lead {lead_number}: "
                f"{result.get('error', 'unknown error')}"
            )

        return result

    except Exception as e:
        logger.error(f"Exception sending lead confirmation email for {lead_number}: {e}")
        return {"success": False, "error": str(e)}
