"""
Unified email template sending helpers for SleepReach.

This module is used by:
- widget / lead submission auto-response
- scheduled follow-up tasks
- any other patient-facing automated email flow

Template copy comes from communication_templates.py so the coordinator UI,
settings editor, and automated sends stay aligned.
"""

from __future__ import annotations

import html
import logging
from typing import Any, Dict

from ..core.database import SessionLocal
from .communication_templates import (
    get_template_by_id,
    get_template_context,
    render_personalized_text,
)
from .email_base import wrap_in_email_layout

logger = logging.getLogger(__name__)


def _load_email_template(template_id: str) -> Dict[str, Any] | None:
    db = SessionLocal()
    try:
        return get_template_by_id(db, template_id, "email")
    finally:
        db.close()


def _render_template_copy(template_id: str, first_name: str) -> tuple[str, str]:
    template = _load_email_template(template_id)
    if not template:
        raise ValueError(f"Email template '{template_id}' not found")

    context = get_template_context(first_name)
    subject = render_personalized_text(template["subject"], context)
    body = render_personalized_text(template["body"], context)
    return subject, body


def _text_body_to_html_rows(body: str) -> str:
    blocks: list[str] = []
    for raw_block in body.split("\n\n"):
        lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
        if not lines:
            continue

        if all(line.startswith("- ") for line in lines):
            items = "".join(
                f'<li style="margin: 0 0 10px 0;">{html.escape(line[2:])}</li>'
                for line in lines
            )
            blocks.append(
                f"""                    <tr>
                        <td style="padding: 0 30px 18px 30px;">
                            <ul style="margin: 0; padding-left: 20px; font-family: Arial, Helvetica, sans-serif; color: #444444; font-size: 15px; line-height: 1.7;">
                                {items}
                            </ul>
                        </td>
                    </tr>"""
            )
            continue

        paragraph_html = "<br>".join(html.escape(line) for line in lines)
        blocks.append(
            f"""                    <tr>
                        <td style="padding: 0 30px 18px 30px;">
                            <p style="margin: 0; font-family: Arial, Helvetica, sans-serif; color: #444444; font-size: 15px; line-height: 1.7;">
                                {paragraph_html}
                            </p>
                        </td>
                    </tr>"""
        )

    return "\n".join(blocks)


def _build_email_html(subject: str, body: str) -> str:
    return wrap_in_email_layout(
        title=subject,
        body_html=f"""
                    <tr>
                        <td style="padding: 28px 0 10px 0;"></td>
                    </tr>
{_text_body_to_html_rows(body)}
""",
    )


def _send_email(template_id: str, lead_data: Dict[str, Any]) -> Dict[str, Any]:
    email = lead_data.get("email", "")
    first_name = lead_data.get("first_name", "") or "there"
    lead_id = lead_data.get("lead_id")
    lead_number = lead_data.get("lead_number", "unknown")

    if not email:
        logger.warning("Cannot send %s email - no email address for lead %s", template_id, lead_number)
        return {"success": False, "error": "No email address provided"}

    subject, body = _render_template_copy(template_id, first_name)
    html_content = _build_email_html(subject, body)

    try:
        from .paubox_email_service import send_email_via_paubox

        result = send_email_via_paubox(
            to_email=email,
            subject=subject,
            html_content=html_content,
            text_content=body,
            lead_id=lead_id,
        )

        if result.get("success"):
            logger.info(
                "%s email sent to %s for lead %s via %s",
                template_id,
                email,
                lead_number,
                result.get("provider", "unknown"),
            )
        else:
            logger.error(
                "Failed to send %s email for lead %s: %s",
                template_id,
                lead_number,
                result.get("error", "unknown error"),
            )

        return result
    except Exception as exc:
        logger.error("Exception sending %s email for lead %s: %s", template_id, lead_number, exc)
        return {"success": False, "error": str(exc)}


def build_lead_confirmation_email(lead_data: Dict[str, Any]) -> str:
    subject, body = _render_template_copy("lead_receipt", lead_data.get("first_name", "there"))
    return _build_email_html(subject, body)


def build_follow_up_email(lead_data: Dict[str, Any]) -> str:
    subject, body = _render_template_copy("follow_up", lead_data.get("first_name", "there"))
    return _build_email_html(subject, body)


def build_not_interested_follow_up_email(lead_data: Dict[str, Any]) -> str:
    subject, body = _render_template_copy("final_outreach", lead_data.get("first_name", "there"))
    return _build_email_html(subject, body)


def send_lead_confirmation_email(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    return _send_email("lead_receipt", lead_data)


def send_follow_up_email(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    return _send_email("follow_up", lead_data)


def send_not_interested_follow_up_email(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    return _send_email("final_outreach", lead_data)
