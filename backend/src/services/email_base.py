"""
============================================================================
SHARED EMAIL BASE — Consistent Design System for ALL Email Templates
============================================================================

Single source of truth for email layout: header, footer, logo, fonts.
ALL email templates import from here to guarantee visual consistency.

Design system:
- Teal header (#3D6B6B) with white logo, title, and subtitle
- White body with 30px horizontal padding
- Consistent footer with clinic info, HIPAA notice, copyright
- Arial/Helvetica font stack
- Consistent divider style
============================================================================
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================================
# Clinic Constants
# =============================================================================
CLINIC_NAME = "TMS Institute of Arizona"
CLINIC_ADDRESS = "5150 N 16th St, Suite A-114, Phoenix, AZ 85016"
CLINIC_PHONE = "(480) 668-3599"
CLINIC_EMAIL = "support@tmsinstitute.co"
CLINIC_WEBSITE = "tmsinstitute.co"
HEADER_BG_COLOR = "#3D6B6B"
FOOTER_BG_COLOR = "#3D6B6B"
HIPAA_BG_COLOR = "#2F5C5C"


def get_logo_url() -> str:
    """
    Get the logo URL for ALL emails.

    Reads EMAIL_LOGO_URL from settings. If the setting is unavailable
    for any reason, returns a safe empty string so that emails still
    render with alt text instead of crashing.

    ALL email templates MUST use this function for the logo.
    """
    try:
        from ..core.config import settings
        url = getattr(settings, "email_logo_url", "")
        if url:
            return url
    except Exception:
        pass
    return ""


def email_header(title: str, subtitle: Optional[str] = None) -> str:
    """
    Build the standard teal email header with logo, title, and optional subtitle.
    
    Args:
        title: Large white bold text below the logo (e.g., "We've Received Your Request")
        subtitle: Smaller white text below title (defaults to clinic name)
    
    Returns:
        HTML string for the header rows
    """
    if subtitle is None:
        subtitle = CLINIC_NAME
    
    logo_url = get_logo_url()
    
    return f"""                    <!-- ============================================ -->
                    <!-- HEADER: Teal background with logo + title  -->
                    <!-- ============================================ -->
                    <tr>
                        <td align="center" style="background-color: {HEADER_BG_COLOR}; padding: 24px 30px 12px 30px; font-size: 0; line-height: 0;">
                            <img src="{logo_url}"
                                 alt="{CLINIC_NAME}"
                                 width="180" height="47"
                                 style="width: 180px; height: auto; border: 0; display: block; margin: 0 auto;" />
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="background-color: {HEADER_BG_COLOR}; padding: 8px 30px 6px 30px;">
                            <h1 style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 22px; font-weight: bold; color: #FFFFFF; line-height: 1.3;">
                                {title}
                            </h1>
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="background-color: {HEADER_BG_COLOR}; padding: 0 30px 24px 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 14px; color: #FFFFFF; opacity: 0.9; line-height: 1.4;">
                                {subtitle}
                            </p>
                        </td>
                    </tr>"""


def email_divider() -> str:
    """Standard horizontal divider."""
    return """                    <tr>
                        <td style="padding: 20px 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr><td style="border-top: 1px solid #EEEEEE; font-size: 0; line-height: 0;" height="1">&nbsp;</td></tr>
                            </table>
                        </td>
                    </tr>"""


def email_footer() -> str:
    """
    Build the standard email footer with clinic info, HIPAA notice, copyright.
    
    Returns:
        HTML string for the footer rows
    """
    return f"""                    <!-- ============================================ -->
                    <!-- FOOTER                                     -->
                    <!-- ============================================ -->

                    <!-- Divider -->
                    <tr>
                        <td style="padding: 20px 30px 0 30px;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr><td style="border-top: 1px solid #EEEEEE; font-size: 0; line-height: 0;" height="1">&nbsp;</td></tr>
                            </table>
                        </td>
                    </tr>

                    <tr>
                        <td align="center" style="padding: 24px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 12px; font-weight: bold; color: #999999; line-height: 1.4;">
                                {CLINIC_NAME}
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="padding: 6px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #999999; line-height: 1.4;">
                                {CLINIC_ADDRESS}
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="padding: 6px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #999999; line-height: 1.4;">
                                <a href="tel:4806683599" style="color: #999999; text-decoration: none;">{CLINIC_PHONE}</a>
                                &nbsp;|&nbsp;
                                <a href="mailto:{CLINIC_EMAIL}" style="color: #999999; text-decoration: none;">{CLINIC_EMAIL}</a>
                                &nbsp;|&nbsp;
                                <a href="https://{CLINIC_WEBSITE}" style="color: #999999; text-decoration: none;">{CLINIC_WEBSITE}</a>
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="padding: 14px 30px 0 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #999999; line-height: 1.4;">
                                This email contains protected health information (PHI). Your privacy is protected under HIPAA.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="padding: 6px 30px 24px 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #999999; line-height: 1.4;">
                                &copy; 2026 {CLINIC_NAME}. All rights reserved.
                            </p>
                        </td>
                    </tr>"""


def wrap_in_email_layout(title: str, body_html: str, subtitle: Optional[str] = None) -> str:
    """
    Wrap body content in the full email layout (header + body + footer).
    
    This is the master wrapper that ALL email templates should use.
    
    Args:
        title: Header title text (shown in teal bar below logo)
        body_html: Inner HTML for the body section (table rows)
        subtitle: Optional subtitle (defaults to clinic name)
    
    Returns:
        Complete HTML email string
    """
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>{title} &mdash; {CLINIC_NAME}</title>
    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
</head>
<body style="margin: 0; padding: 0; background-color: #F5F5F7; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #F5F5F7;">
        <tr>
            <td align="center" style="padding: 30px 20px;">
                <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; width: 100%; background-color: #FFFFFF; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">

{email_header(title, subtitle)}

                    <!-- ============================================ -->
                    <!-- BODY                                         -->
                    <!-- ============================================ -->

{body_html}

{email_footer()}

                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
