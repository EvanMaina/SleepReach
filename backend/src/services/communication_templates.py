"""
Communication template registry for coordinator email/SMS and widget auto-response.

Stores default SleepReach templates and merges admin overrides persisted in
clinic_settings. This gives the frontend, auto-response flow, and manual
communications one shared source of truth.
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any, Dict, Iterable

from sqlalchemy.orm import Session

from ..models.user import ClinicSettings

logger = logging.getLogger(__name__)

TEMPLATE_STORAGE_KEY = "communication_templates"

CLINIC_NAME = "The Insomnia and Sleep Institute of Arizona"
CLINIC_PHONE = "(480) 745-3547"
CLINIC_EMAIL = "info@sleeplessinarizona.com"
CLINIC_WEBSITE = "sleeplessinarizona.com"
CLINIC_ADDRESS = "8330 E Hartford Drive, Suite 100, Scottsdale, Arizona 85255"


def _email_template(
    template_id: str,
    label: str,
    description: str,
    subject: str,
    body: str,
    *,
    editable: bool = True,
) -> Dict[str, Any]:
    return {
        "id": template_id,
        "label": label,
        "description": description,
        "subject": subject,
        "body": body,
        "editable": editable,
    }


def _sms_template(
    template_id: str,
    label: str,
    description: str,
    message: str,
    *,
    editable: bool = True,
) -> Dict[str, Any]:
    return {
        "id": template_id,
        "label": label,
        "description": description,
        "message": message,
        "editable": editable,
    }


DEFAULT_EMAIL_TEMPLATES = [
    _email_template(
        "follow_up",
        "Follow-up",
        "General follow-up after a sleep consultation inquiry.",
        "Following up on your sleep consultation inquiry",
        """Hi {{first_name}},

I'm following up on your recent inquiry with The Insomnia and Sleep Institute of Arizona. Our team works with patients dealing with insomnia, sleep apnea, restless legs syndrome, narcolepsy, and other sleep concerns, and we'd be glad to answer any questions you may have.

If you'd like to take the next step, we can help schedule your sleep consultation and review treatment options such as sleep testing, CPAP therapy, Inspire therapy, and CBT-I.

You can reply to this email or call us directly at {{clinic_phone}}.

Warmly,
The Insomnia and Sleep Institute of Arizona""",
    ),
    _email_template(
        "appointment_confirmation",
        "Appointment Confirmation",
        "Confirmation for a scheduled sleep consultation.",
        "Your sleep consultation is confirmed",
        """Hi {{first_name}},

Your appointment with The Insomnia and Sleep Institute of Arizona has been scheduled.

If you have any questions before your visit or need to make a change, please reply to this email or call us at {{clinic_phone}}.

We look forward to meeting with you and helping you move toward better sleep.

Warmly,
The Insomnia and Sleep Institute of Arizona""",
    ),
    _email_template(
        "appointment_reminder",
        "Appointment Reminder",
        "Reminder for an upcoming sleep consultation.",
        "Reminder: your upcoming sleep consultation",
        """Hi {{first_name}},

This is a friendly reminder about your upcoming appointment with The Insomnia and Sleep Institute of Arizona.

If you need to confirm, reschedule, or have any last-minute questions, please reply to this email or call {{clinic_phone}}.

We're looking forward to seeing you.

Warmly,
The Insomnia and Sleep Institute of Arizona""",
    ),
    _email_template(
        "missed_call",
        "Missed Call Follow-up",
        "Follow-up after the clinic tried to reach the patient.",
        "We tried reaching you about your sleep consultation inquiry",
        """Hi {{first_name}},

We recently tried reaching you regarding your inquiry with The Insomnia and Sleep Institute of Arizona.

We'd still be happy to connect and answer any questions you may have about your sleep concerns, evaluation options, or possible treatments.

Please reply to this email or call us at {{clinic_phone}} when it's convenient for you.

Warmly,
The Insomnia and Sleep Institute of Arizona""",
    ),
    _email_template(
        "thank_you",
        "Thank You",
        "Thank-you email after a consultation or conversation.",
        "Thank you for choosing The Insomnia and Sleep Institute of Arizona",
        """Hi {{first_name}},

Thank you for taking the time to speak with our team at The Insomnia and Sleep Institute of Arizona.

It's a privilege to support you as you work toward more restful sleep and better overall health. If any questions come up after your consultation, please reply to this email or call us at {{clinic_phone}}.

Warmly,
The Insomnia and Sleep Institute of Arizona""",
    ),
    _email_template(
        "day3_educational",
        "Day 3 — Educational",
        "Educational email about sleep health, sent ~3 days after inquiry.",
        "Understanding your sleep — what to expect from a consultation",
        """Hi {{first_name}},

Many of our patients tell us they waited years before seeking help for their sleep concerns — and wish they'd done it sooner.

Here's what a consultation at our clinic typically looks like:
• A brief review of your sleep history and symptoms
• Discussion of diagnostic options like a sleep study, if appropriate
• A clear outline of treatment paths, including CPAP therapy, Inspire therapy, CBT-I, and other options tailored to your situation

There's no obligation, and our goal is simply to help you understand what's affecting your sleep and what your options are.

If you'd like to schedule a consultation, reply to this email or call us at {{clinic_phone}}.

Wishing you restful nights,
The Insomnia and Sleep Institute of Arizona""",
    ),
    _email_template(
        "day7_value",
        "Day 7 — Why Patients Choose Us",
        "Social proof and value email, sent ~7 days after inquiry.",
        "Why patients trust The Insomnia and Sleep Institute of Arizona",
        """Hi {{first_name}},

We wanted to share a bit about why patients choose our clinic for their sleep health:

• Led by Dr. Patel, a board-certified sleep medicine specialist
• Comprehensive approach — from diagnosis through treatment and follow-up
• Experience with a wide range of conditions, including insomnia, sleep apnea, restless legs, and narcolepsy
• Multiple treatment options so you're never locked into a single path

If sleep is affecting your energy, focus, or overall health, we're here to help you take the next step — at your pace.

Call us at {{clinic_phone}} or reply to this email to schedule your consultation.

Warmly,
The Insomnia and Sleep Institute of Arizona""",
    ),
    _email_template(
        "day14_reengage",
        "Day 14 — Re-engagement",
        "Gentle re-engagement for leads who haven't responded in ~2 weeks.",
        "Still thinking about your sleep health?",
        """Hi {{first_name}},

We know that deciding to address sleep concerns is a personal decision, and there's no rush.

We just wanted to let you know that our team is still here if you have questions or would like to explore your options. Whether it's a quick phone call or scheduling a consultation, we're happy to help in whatever way feels right for you.

If now isn't the right time, that's completely okay. You can always reach us at {{clinic_phone}} when you're ready.

Take care,
The Insomnia and Sleep Institute of Arizona""",
    ),
    _email_template(
        "final_outreach",
        "Final Outreach",
        "Last gentle re-engagement attempt (~30+ days).",
        "One last note about your sleep consultation inquiry",
        """Hi {{first_name}},

I wanted to send one final note in case you still wanted to speak with our team about your sleep concerns.

If this is still something you'd like help with, we'd be glad to talk through next steps and help you decide whether a consultation would be useful for you.

You can reply to this email or call us at {{clinic_phone}} whenever you're ready.

Warmly,
The Insomnia and Sleep Institute of Arizona""",
    ),
    _email_template(
        "custom",
        "Custom Email",
        "Blank email for a coordinator to write from scratch.",
        "",
        "",
    ),
    _email_template(
        "lead_receipt",
        "Widget Auto-Response",
        "Automatic confirmation sent immediately after widget submission.",
        "We received your information, {{first_name}} - here's what happens next",
        """Hi {{first_name}},

Thank you for reaching out to The Insomnia and Sleep Institute of Arizona. We received your information and our team is reviewing it now.

Here's what happens next:
- A care coordinator will review your submission and reach out to you shortly.
- We'll talk through your symptoms, questions, and whether a consultation or sleep testing would be the right next step.
- If appropriate, we can help you explore treatment options such as CPAP therapy, Inspire therapy, CBT-I, and other sleep-medicine solutions.

Dr. Patel and our sleep medicine team are here to help you find a clear path toward better sleep.

If you'd like to speak with us right away, call {{clinic_phone}}.

Warmly,
The Insomnia and Sleep Institute of Arizona""",
    ),
]


DEFAULT_SMS_TEMPLATES = [
    _sms_template(
        "follow_up",
        "Follow-up SMS",
        "Short follow-up about the patient's sleep consultation inquiry.",
        "Hi {{first_name}}, this is The Insomnia and Sleep Institute of Arizona following up on your sleep consultation inquiry. Reply here or call {{clinic_phone}} if you'd like to connect.",
    ),
    _sms_template(
        "appointment_reminder",
        "Appointment Reminder SMS",
        "Reminder for an upcoming appointment.",
        "Hi {{first_name}}, this is a reminder from The Insomnia and Sleep Institute of Arizona about your upcoming appointment. Questions or need to reschedule? Call {{clinic_phone}}.",
    ),
    _sms_template(
        "missed_call",
        "Missed Call SMS",
        "Follow-up after a missed call attempt.",
        "Hi {{first_name}}, we tried reaching you from The Insomnia and Sleep Institute of Arizona about your sleep inquiry. Call {{clinic_phone}} or reply here when you're available.",
    ),
    _sms_template(
        "day3_educational",
        "Day 3 Educational SMS",
        "Educational follow-up about the consultation process.",
        "Hi {{first_name}}, just a quick note from The Insomnia and Sleep Institute. A sleep consultation is a simple first step — no obligation. We're here when you're ready. Call {{clinic_phone}}.",
    ),
    _sms_template(
        "day7_value",
        "Day 7 Value SMS",
        "Social proof follow-up.",
        "Hi {{first_name}}, many patients tell us they wish they'd addressed their sleep concerns sooner. If you'd like to chat with our team, call {{clinic_phone}} or reply here.",
    ),
    _sms_template(
        "day14_reengage",
        "Day 14 Re-engagement SMS",
        "Gentle check-in for unresponsive leads.",
        "Hi {{first_name}}, we haven't heard from you and want you to know our team is still here for you. No rush. Call {{clinic_phone}} whenever you're ready.",
    ),
    _sms_template(
        "not_interested_follow_up",
        "Not Interested Re-engagement SMS",
        "Softer outreach for leads who declined.",
        "Hi {{first_name}}, just checking in from The Insomnia and Sleep Institute. If your sleep situation changes, we're here to help. No pressure. Call {{clinic_phone}} anytime.",
    ),
    _sms_template(
        "custom",
        "Custom SMS",
        "Blank SMS for a coordinator to write from scratch.",
        "",
    ),
    _sms_template(
        "lead_receipt",
        "Widget Auto-Response SMS",
        "Automatic SMS confirmation after widget submission.",
        "Hi {{first_name}}, thanks for contacting The Insomnia and Sleep Institute of Arizona. We received your information and a care coordinator will reach out soon. Questions? Call {{clinic_phone}}.",
    ),
]


def _template_list_to_map(templates: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {template["id"]: deepcopy(template) for template in templates}


def get_default_template_payload() -> Dict[str, list[Dict[str, Any]]]:
    return {
        "email_templates": deepcopy(DEFAULT_EMAIL_TEMPLATES),
        "sms_templates": deepcopy(DEFAULT_SMS_TEMPLATES),
    }


def _read_overrides(db: Session) -> Dict[str, Any]:
    row = db.query(ClinicSettings).filter(ClinicSettings.key == TEMPLATE_STORAGE_KEY).first()
    if not row or not row.value:
        return {}

    try:
        parsed = json.loads(row.value)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError as exc:
        logger.warning("Invalid communication template JSON in clinic_settings: %s", exc)

    return {}


def get_template_payload(db: Session) -> Dict[str, list[Dict[str, Any]]]:
    payload = get_default_template_payload()
    overrides = _read_overrides(db)

    email_map = _template_list_to_map(payload["email_templates"])
    for item in overrides.get("email_templates", []):
        template_id = item.get("id")
        if template_id in email_map:
            email_map[template_id]["subject"] = item.get("subject", email_map[template_id]["subject"])
            email_map[template_id]["body"] = item.get("body", email_map[template_id]["body"])

    sms_map = _template_list_to_map(payload["sms_templates"])
    for item in overrides.get("sms_templates", []):
        template_id = item.get("id")
        if template_id in sms_map:
            sms_map[template_id]["message"] = item.get("message", sms_map[template_id]["message"])

    return {
        "email_templates": [email_map[template["id"]] for template in DEFAULT_EMAIL_TEMPLATES],
        "sms_templates": [sms_map[template["id"]] for template in DEFAULT_SMS_TEMPLATES],
    }


def save_template_payload(db: Session, payload: Dict[str, Any]) -> Dict[str, list[Dict[str, Any]]]:
    defaults = get_default_template_payload()
    allowed_email_ids = {template["id"] for template in defaults["email_templates"]}
    allowed_sms_ids = {template["id"] for template in defaults["sms_templates"]}

    clean_payload = {
        "email_templates": [],
        "sms_templates": [],
    }

    for item in payload.get("email_templates", []):
        template_id = item.get("id")
        if template_id in allowed_email_ids:
            clean_payload["email_templates"].append(
                {
                    "id": template_id,
                    "subject": item.get("subject", ""),
                    "body": item.get("body", ""),
                }
            )

    for item in payload.get("sms_templates", []):
        template_id = item.get("id")
        if template_id in allowed_sms_ids:
            clean_payload["sms_templates"].append(
                {
                    "id": template_id,
                    "message": item.get("message", ""),
                }
            )

    row = db.query(ClinicSettings).filter(ClinicSettings.key == TEMPLATE_STORAGE_KEY).first()
    serialized = json.dumps(clean_payload)
    if row:
        row.value = serialized
    else:
        db.add(ClinicSettings(key=TEMPLATE_STORAGE_KEY, value=serialized))
    db.commit()
    return get_template_payload(db)


def render_personalized_text(template: str, context: Dict[str, Any]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value or ""))
    return rendered


def get_template_context(first_name: str | None = None) -> Dict[str, str]:
    return {
        "first_name": (first_name or "there").strip() or "there",
        "clinic_name": CLINIC_NAME,
        "clinic_phone": CLINIC_PHONE,
        "clinic_email": CLINIC_EMAIL,
        "clinic_website": CLINIC_WEBSITE,
        "clinic_address": CLINIC_ADDRESS,
    }


def get_template_by_id(
    db: Session,
    template_id: str,
    kind: str,
) -> Dict[str, Any] | None:
    payload = get_template_payload(db)
    key = "email_templates" if kind == "email" else "sms_templates"
    for template in payload[key]:
        if template["id"] == template_id:
            return template
    return None
