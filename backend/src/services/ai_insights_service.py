"""
AI Insights service for organization-wide conversion intelligence.

Builds a deterministic analytics snapshot from SleepReach lead/provider data,
then optionally asks Claude to enrich that snapshot with strategic commentary
and sharper messaging recommendations. Results are cached for one hour.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.lead import ContactOutcome, Lead, LeadStatus
from ..models.provider import ReferringProvider
from ..models.user import User, UserRole, UserStatus
from .cache import get_cache
from .encryption import EncryptionService


logger = logging.getLogger(__name__)

CACHE_KEY = "sleepreach:ai_insights:organization:v3"
UTC = timezone.utc

CONDITION_LABELS = {
    "INSOMNIA": "Insomnia",
    "SLEEP_APNEA": "Sleep Apnea",
    "RESTLESS_LEG": "Restless Legs",
    "NARCOLEPSY": "Narcolepsy",
    "WALKING_DREAMS": "Walking / Acting Out Dreams",
    "OTHER": "Other",
}

TREATMENT_LABELS = {
    "cpap_bipap": "CPAP Therapy",
    "inspire": "Inspire Therapy",
    "therapy_cbt": "CBT-I Therapy",
    "sleep_study": "Sleep Study / Testing",
    "medication": "Medication Review",
    "not_sure": "Not sure — I'd like to learn more",
    "CPAP_BIPAP": "CPAP Therapy",
    "MEDICATION": "Medication Review",
    "SLEEP_STUDY": "Sleep Study / Testing",
    "THERAPY_CBT": "CBT-I Therapy",
    "NONE": "No prior treatment",
    "OTHER": "Other treatment",
}

COMPLETED_STATUSES = {
    LeadStatus.CONSULTATION_COMPLETE,
    LeadStatus.TREATMENT_STARTED,
}
SCHEDULED_OR_BETTER = COMPLETED_STATUSES | {LeadStatus.SCHEDULED}
OPEN_STATUSES = {
    LeadStatus.NEW,
    LeadStatus.CONTACTED,
    LeadStatus.SCHEDULED,
}
POSITIVE_OUTCOMES = {
    ContactOutcome.ANSWERED,
    ContactOutcome.CALLBACK_REQUESTED,
    ContactOutcome.SCHEDULED,
    ContactOutcome.COMPLETED,
}


@dataclass
class PriorityCandidate:
    lead_id: str
    lead_number: str
    queue_hint: str
    priority_score: int
    condition: str
    priority: str
    status: str
    contact_outcome: str
    urgency: str
    insurance_status: str
    days_waiting: int
    stale_days: int
    recommended_action: str
    reason: str
    script: str
    treatment_interest: str
    preferred_contact_method: str
    lead_name: str = ""
    first_name: str = "there"


class AIInsightsService:
    def __init__(self, db: Session):
        self.db = db
        self.cache = get_cache()

    async def get_insights(self, force_refresh: bool = False) -> dict[str, Any]:
        cached = None if force_refresh else self.cache.get(CACHE_KEY)
        if cached:
            cached["cached"] = True
            return cached

        insights = await self._build_insights()
        self.cache.set(CACHE_KEY, insights, ttl=settings.ai_insights_cache_ttl)
        insights["cached"] = False
        return insights

    async def _build_insights(self) -> dict[str, Any]:
        snapshot = self._build_snapshot()
        narrative = await self._build_narrative(snapshot)
        snapshot = self._merge_act_now(snapshot, narrative)
        snapshot = self._merge_provider_recommendations(snapshot, narrative)

        summary = snapshot["summary"]
        summary["headline"] = narrative.get("headline_summary") or summary["headline"]
        summary["detail"] = narrative.get("summary_detail") or summary["detail"]

        snapshot["pipeline"]["commentary"] = (
            narrative.get("pipeline_commentary") or snapshot["pipeline"]["commentary"]
        )
        snapshot["communication"]["commentary"] = (
            narrative.get("communication_commentary") or snapshot["communication"]["commentary"]
        )
        snapshot["provider_intelligence"]["commentary"] = (
            narrative.get("provider_commentary") or snapshot["provider_intelligence"]["commentary"]
        )
        snapshot["trends"]["commentary"] = (
            narrative.get("trend_commentary") or snapshot["trends"]["commentary"]
        )

        if narrative.get("forecast_summary"):
            snapshot["trends"]["forecast"]["summary"] = narrative["forecast_summary"]

        llm_templates = narrative.get("communication_templates") or []
        if llm_templates:
            snapshot["communication"]["templates"] = llm_templates

        provider_recommendations = narrative.get("provider_recommendations") or []
        if provider_recommendations:
            snapshot["provider_intelligence"]["recommendations"] = provider_recommendations

        # Geographic and coordinator commentary from Claude
        if narrative.get("geographic_commentary"):
            snapshot["geographic"]["commentary"] = narrative["geographic_commentary"]
        if narrative.get("coordinator_commentary"):
            snapshot["operational"]["commentary"] = narrative["coordinator_commentary"]

        snapshot["llm_enabled"] = bool(settings.anthropic_api_key)
        return snapshot

    def _build_snapshot(self) -> dict[str, Any]:
        leads = (
            self.db.query(Lead)
            .filter(Lead.deleted_at.is_(None))
            .all()
        )
        providers = self.db.query(ReferringProvider).all()
        users = (
            self.db.query(User)
            .filter(User.status == UserStatus.ACTIVE)
            .all()
        )

        now = datetime.now(UTC)
        total_leads = len(leads)
        insufficient_data = total_leads < 5

        scheduled_or_better = [lead for lead in leads if lead.status in SCHEDULED_OR_BETTER]
        completed = [lead for lead in leads if lead.status in COMPLETED_STATUSES]
        open_leads = [lead for lead in leads if lead.status in OPEN_STATUSES]
        insured_open = [lead for lead in open_leads if lead.has_insurance]

        fresh_candidates = [self._build_priority_candidate(lead, now) for lead in open_leads]
        fresh_candidates = [item for item in fresh_candidates if item is not None]
        fresh_candidates.sort(key=lambda item: item.priority_score, reverse=True)
        top_candidates = fresh_candidates[:10]

        lead_lookup = {str(lead.id): lead for lead in leads}
        self._hydrate_candidate_names(top_candidates, lead_lookup)

        funnel = self._build_funnel(leads, now)
        stage_counts = {row["key"]: row["count"] for row in funnel["stages"]}

        first_contact_hours: list[float] = []
        schedule_lags: list[float] = []
        stale_followups = 0
        stale_new = 0
        insured_stale = 0
        callback_due = 0

        for lead in leads:
            created_at = self._ensure_utc(lead.created_at)
            first_touch = self._ensure_utc(lead.contacted_at or lead.last_contact_attempt)
            if created_at and first_touch and first_touch >= created_at:
                first_contact_hours.append((first_touch - created_at).total_seconds() / 3600)

            if created_at and lead.status in SCHEDULED_OR_BETTER:
                scheduled_at = self._ensure_utc(lead.scheduled_callback_at or lead.converted_at or lead.updated_at)
                if scheduled_at and scheduled_at >= created_at:
                    schedule_lags.append((scheduled_at - created_at).total_seconds() / 86400)

            last_touch = self._ensure_utc(lead.last_updated_at or lead.updated_at or lead.created_at)
            stale_days = int((now - last_touch).total_seconds() // 86400) if last_touch else 0
            stage = self._derive_stage_key(lead)
            if stage == "contacted" and stale_days >= 7:
                stale_followups += 1
            if stage == "new" and stale_days >= 2:
                stale_new += 1
            if lead.has_insurance and lead.status in OPEN_STATUSES and stale_days >= 3:
                insured_stale += 1
            callback_at = self._ensure_utc(lead.scheduled_callback_at)
            if callback_at and now <= callback_at <= (now + timedelta(hours=24)):
                callback_due += 1

        response_rows, best_response_window = self._build_timing_rows(leads)
        method_rows, best_contact_method = self._build_method_rows(leads)
        weekly_series = self._build_weekly_series(leads, now)
        monthly_series = self._build_monthly_series(leads, now)
        conversion_by_source = self._build_conversion_rows(leads, "source")
        conversion_by_condition = self._build_conversion_rows(leads, "condition")
        conversion_by_insurance = self._build_conversion_rows(leads, "insurance")
        provider_rankings = self._build_provider_rankings(providers)
        coordinator_performance = self._build_coordinator_performance(leads, users)
        geographic_analysis = self._build_geographic_analysis(leads)

        avg_first_contact_hours = round(sum(first_contact_hours) / len(first_contact_hours), 1) if first_contact_hours else None
        avg_schedule_days = round(sum(schedule_lags) / len(schedule_lags), 1) if schedule_lags else None

        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month_end = current_month_start - timedelta(seconds=1)
        prev_month_start = prev_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        current_month_leads = [lead for lead in leads if self._ensure_utc(lead.created_at) and self._ensure_utc(lead.created_at) >= current_month_start]
        previous_month_leads = [
            lead for lead in leads
            if self._ensure_utc(lead.created_at)
            and prev_month_start <= self._ensure_utc(lead.created_at) < current_month_start
        ]

        current_conversion_rate = round((len([lead for lead in current_month_leads if lead.status in SCHEDULED_OR_BETTER]) / len(current_month_leads)) * 100, 1) if current_month_leads else 0.0
        previous_conversion_rate = round((len([lead for lead in previous_month_leads if lead.status in SCHEDULED_OR_BETTER]) / len(previous_month_leads)) * 100, 1) if previous_month_leads else 0.0
        trend_delta = round(current_conversion_rate - previous_conversion_rate, 1)
        answered_not_scheduled = len(
            [
                lead
                for lead in leads
                if lead.contact_outcome in {ContactOutcome.ANSWERED, ContactOutcome.CALLBACK_REQUESTED}
                and lead.status not in SCHEDULED_OR_BETTER
            ]
        )

        health_score = self._compute_health_score(
            total_leads=total_leads,
            scheduled_count=len(scheduled_or_better),
            completed_count=len(completed),
            stale_followups=stale_followups,
            insured_stale=insured_stale,
            avg_first_contact_hours=avg_first_contact_hours,
        )


        health_state = (
            "healthy" if health_score >= 71 else
            "needs_attention" if health_score >= 41 else
            "critical"
        )

        top_source = conversion_by_source[0]["label"] if conversion_by_source else "Widget"
        top_condition = conversion_by_condition[0]["label"] if conversion_by_condition else "Insomnia"
        top_insurer = conversion_by_insurance[0]["label"] if conversion_by_insurance else "Insured"
        top_provider = provider_rankings[0]["name"] if provider_rankings else "Referral partners"
        summary_detail = (
            f"{insured_stale} insured leads have been idle for 3+ days, "
            f"{answered_not_scheduled} engaged leads still need scheduling, and "
            f"average first contact time is {avg_first_contact_hours if avg_first_contact_hours is not None else 'not enough data'} hours."
        )

        snapshot = {
            "generated_at": now.isoformat(),
            "cache_ttl_seconds": settings.ai_insights_cache_ttl,
            "insufficient_data": insufficient_data,
            "summary": {
                "health_score": health_score,
                "health_state": health_state,
                "trend_delta": trend_delta,
                "headline": self._build_headline(health_score, insured_stale, callback_due, answered_not_scheduled),
                "detail": summary_detail,
                "metrics": {
                    "active_leads": total_leads,
                    "insured_open_leads": len(insured_open),
                    "avg_first_contact_hours": avg_first_contact_hours,
                    "best_source": top_source,
                    "best_condition": top_condition,
                    "best_insurer": top_insurer,
                    "best_provider": top_provider,
                },
            },
            "act_now": [candidate.__dict__ for candidate in top_candidates],
            "pipeline": {
                "stages": funnel["stages"],
                "alerts": [
                    {"label": "Stale Follow-up", "count": stale_followups, "detail": "Leads in follow-up with no activity for 7+ days"},
                    {"label": "Untouched New Leads", "count": stale_new, "detail": "New leads waiting 48+ hours without meaningful activity"},
                    {"label": "Callbacks Due", "count": callback_due, "detail": "Callbacks scheduled within the next 24 hours"},
                ],
                "avg_first_contact_hours": avg_first_contact_hours,
                "avg_schedule_days": avg_schedule_days,
                "commentary": (
                    f"The biggest active queue is {self._largest_queue_label(stage_counts)}. "
                    f"Contacted-to-scheduled drop-off is {funnel['contacted_to_scheduled_dropoff']}%, "
                    f"with {answered_not_scheduled} leads already engaged but not yet booked."
                ),
                "conversion_drivers": {
                    "source": conversion_by_source,
                    "condition": conversion_by_condition,
                    "insurance": conversion_by_insurance,
                },
            },
            "communication": {
                "best_time_of_day": best_response_window,
                "best_contact_method": best_contact_method,
                "timing_rows": response_rows,
                "method_rows": method_rows,
                "templates": self._default_templates(),
                "commentary": (
                    f"The strongest response window is {best_response_window}. "
                    f"{best_contact_method} is the most successful preferred contact channel in the current pipeline."
                ),
            },
            "provider_intelligence": {
                "providers": provider_rankings,
                "commentary": (
                    "Strengthen relationships with providers who pair strong conversion rates with repeat referral volume."
                ),
                "recommendations": [],
            },
            "trends": {
                "weekly": weekly_series,
                "monthly": monthly_series,
                "forecast": self._default_forecast(weekly_series, current_month_leads, current_conversion_rate),
                "commentary": (
                    f"This month is tracking at {current_conversion_rate}% scheduled-or-better conversion versus {previous_conversion_rate}% last month."
                ),
            },
            "operational": {
                "team_performance": coordinator_performance,
                "queue_health": {
                    "new": stage_counts.get("new", 0),
                    "contacted": stage_counts.get("contacted", 0),
                    "scheduled": stage_counts.get("scheduled", 0),
                    "completed": stage_counts.get("completed", 0),
                },
            },
            "geographic": geographic_analysis,
        }
        return snapshot

    def _build_headline(
        self,
        health_score: int,
        insured_stale: int,
        callback_due: int,
        answered_not_scheduled: int,
    ) -> str:
        if insured_stale:
            return (
                f"Pipeline health is {health_score}/100. {insured_stale} insured leads are cooling off and need same-day outreach."
            )
        if callback_due:
            return (
                f"Pipeline health is {health_score}/100. You have {callback_due} callbacks due in the next 24 hours."
            )
        if answered_not_scheduled:
            return (
                f"Pipeline health is {health_score}/100. {answered_not_scheduled} leads already engaged live and should be pushed toward scheduling now."
            )
        return f"Pipeline health is {health_score}/100. Focus on same-day first contact to improve scheduling velocity."

    async def _build_narrative(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not settings.anthropic_api_key:
            return self._fallback_narrative(snapshot)

        try:
            return await self._generate_claude_narrative(snapshot)
        except Exception as exc:  # pragma: no cover - network fallback
            logger.warning("Anthropic insight generation failed: %s", exc, exc_info=True)
            return self._fallback_narrative(snapshot)

    async def _generate_claude_narrative(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        sanitized = {
            "summary": snapshot["summary"],
            "pipeline": {
                "stages": snapshot["pipeline"]["stages"],
                "alerts": snapshot["pipeline"]["alerts"],
                "avg_first_contact_hours": snapshot["pipeline"]["avg_first_contact_hours"],
                "avg_schedule_days": snapshot["pipeline"]["avg_schedule_days"],
                "conversion_drivers": {
                    "source": snapshot["pipeline"]["conversion_drivers"]["source"][:6],
                    "condition": snapshot["pipeline"]["conversion_drivers"]["condition"][:6],
                    "insurance": snapshot["pipeline"]["conversion_drivers"]["insurance"][:6],
                },
            },
            "provider_intelligence": {
                "providers": snapshot["provider_intelligence"]["providers"][:8],
            },
            "communication": {
                "best_time_of_day": snapshot["communication"]["best_time_of_day"],
                "best_contact_method": snapshot["communication"]["best_contact_method"],
                "timing_rows": snapshot["communication"]["timing_rows"],
                "method_rows": snapshot["communication"]["method_rows"],
            },
            "trends": {
                "weekly": snapshot["trends"]["weekly"],
                "monthly": snapshot["trends"]["monthly"],
                "forecast": snapshot["trends"]["forecast"],
            },
            "act_now_candidates": [
                {
                    "lead_id": item["lead_id"],
                    "lead_number": item["lead_number"],
                    "queue_hint": item["queue_hint"],
                    "lead_name": item.get("lead_name"),
                    "condition": item["condition"],
                    "priority": item["priority"],
                    "status": item["status"],
                    "contact_outcome": item["contact_outcome"],
                    "urgency": item["urgency"],
                    "insurance_status": item["insurance_status"],
                    "treatment_interest": item["treatment_interest"],
                    "preferred_contact_method": item["preferred_contact_method"],
                    "days_waiting": item["days_waiting"],
                    "stale_days": item["stale_days"],
                    "recommended_action": item["recommended_action"],
                    "reason": item["reason"],
                }
                for item in snapshot["act_now"][:10]
            ],
            "geographic": snapshot.get("geographic", {}),
            "operational": snapshot.get("operational", {}),
        }

        system_prompt = (
            "You are an AI conversion strategist for The Insomnia and Sleep Institute of Arizona, "
            "a sleep medicine clinic treating insomnia, sleep apnea, restless legs syndrome, narcolepsy, and other sleep disorders. "
            "Common treatments include CPAP therapy, Inspire therapy, CBT-I, and sleep studies. "
            "The lead lifecycle is NEW -> CONTACTED -> SCHEDULED -> COMPLETED, where completed means the consultation occurred. "
            "Insurance, urgency, referral source strength, and response speed all matter. "
            "You also analyze geographic lead patterns (which zip codes and areas generate the most leads and best conversion), "
            "and coordinator performance (which coordinators have the highest completion/conversion rates). "
            "Return JSON only. Be specific, operationally useful, and grounded in the provided metrics. "
            "Do not invent data, do not mention revenue, and make every recommendation concrete enough for clinic leadership and coordinators to act on today."
        )
        user_prompt = (
            "Analyze this de-identified clinic pipeline snapshot and produce JSON with keys: "
            "headline_summary, summary_detail, pipeline_commentary, communication_commentary, "
            "provider_commentary, trend_commentary, forecast_summary, "
            "geographic_commentary, coordinator_commentary, "
            "act_now_overrides, communication_templates, provider_recommendations. "
            "geographic_commentary should analyze which zip codes/areas produce the most leads and best conversions — "
            "suggest where the clinic should focus marketing or consider expansion. "
            "coordinator_commentary should assess team performance — who is converting best, "
            "who may need support, and concrete coaching recommendations. "
            "act_now_overrides should be an array of up to 5 objects with lead_id, recommended_action, reason, script. "
            "Each act_now override must mention the lead's actual condition or contact state from the data. "
            "communication_templates should be an array of 4 objects with id, title, body for sleep-medicine outreach that a coordinator would genuinely use. "
            "provider_recommendations should be arrays of short, concrete relationship-building suggestions.\n\n"
            f"{json.dumps(sanitized, default=str)}"
        )

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.anthropic_model,
                    "max_tokens": 2500,
                    "temperature": 0.2,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
            response.raise_for_status()
            payload = response.json()

        text_parts = []
        for block in payload.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                text_parts.append(block["text"])
        return self._parse_llm_json("\n".join(text_parts))

    def _fallback_narrative(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        top_source = snapshot["pipeline"]["conversion_drivers"]["source"][0]["label"] if snapshot["pipeline"]["conversion_drivers"]["source"] else "Widget"
        top_provider = snapshot["provider_intelligence"]["providers"][0]["name"] if snapshot["provider_intelligence"]["providers"] else "your best provider partners"
        return {
            "headline_summary": snapshot["summary"]["headline"],
            "summary_detail": snapshot["summary"]["detail"],
            "pipeline_commentary": snapshot["pipeline"]["commentary"],
            "communication_commentary": snapshot["communication"]["commentary"],
            "provider_commentary": (
                f"{top_provider} appears to be a strong referral relationship. "
                "Reinforce high-volume, high-converting partners with faster feedback loops."
            ),
            "trend_commentary": snapshot["trends"]["commentary"],
            "forecast_summary": snapshot["trends"]["forecast"]["summary"],
            "act_now_overrides": [],
            "communication_templates": self._default_templates(),
            "provider_recommendations": [
                f"Review your {top_source} lead source weekly so the strongest pipeline stays warm.",
            ],
        }

    def _parse_llm_json(self, text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end + 1])
        return {}

    def _merge_act_now(self, snapshot: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        overrides = narrative.get("act_now_overrides") or []
        if not overrides:
            return snapshot

        override_map = {item.get("lead_id"): item for item in overrides if item.get("lead_id")}
        merged = []
        for action in snapshot["act_now"]:
            override = override_map.get(action["lead_id"])
            if override:
                action["recommended_action"] = override.get("recommended_action") or action["recommended_action"]
                action["reason"] = override.get("reason") or action["reason"]
                action["script"] = override.get("script") or action["script"]
            merged.append(action)
        snapshot["act_now"] = merged
        return snapshot

    def _merge_provider_recommendations(self, snapshot: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        recommendations = narrative.get("provider_recommendations") or []
        if recommendations:
            snapshot["provider_intelligence"]["recommendations"] = recommendations
            return snapshot

        providers = snapshot["provider_intelligence"]["providers"][:3]
        generated = []
        for provider in providers:
            generated.append(
                f"{provider['name']} is converting at {provider['conversion_rate']}% across {provider['referrals']} referrals. "
                "Keep that relationship warm with regular referral follow-up."
            )
        snapshot["provider_intelligence"]["recommendations"] = generated
        return snapshot

    def _hydrate_candidate_names(
        self,
        candidates: list[PriorityCandidate],
        lead_lookup: dict[str, Lead],
    ) -> None:
        if not candidates:
            return

        def decrypt_candidate(candidate: PriorityCandidate) -> tuple[str, str, str]:
            lead = lead_lookup.get(candidate.lead_id)
            if not lead:
                return candidate.lead_id, candidate.lead_number, "there"

            decrypted = EncryptionService.decrypt_lead_phi(lead)
            first_name = (decrypted.get("first_name") or "").strip()
            last_name = (decrypted.get("last_name") or "").strip()
            display = " ".join(part for part in [first_name, last_name] if part).strip()
            return candidate.lead_id, display or candidate.lead_number, first_name or "there"

        with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as executor:
            for lead_id, display_name, first_name in executor.map(decrypt_candidate, candidates):
                for candidate in candidates:
                    if candidate.lead_id == lead_id:
                        candidate.lead_name = display_name
                        candidate.first_name = first_name
                        candidate.script = candidate.script.replace("{first_name}", first_name)
                        break

    def _condition_values(self, lead: Lead) -> list[str]:
        values: list[str] = []
        for item in lead.conditions or []:
            if not item:
                continue
            if str(item).upper() == "OTHER":
                if lead.other_condition_text:
                    values.append(lead.other_condition_text.strip())
                elif lead.condition_other:
                    values.append(lead.condition_other.strip())
                else:
                    values.append("Other")
            else:
                values.append(self._normalize_condition(str(item)))

        if not values and lead.condition:
            if str(lead.condition.value if hasattr(lead.condition, "value") else lead.condition).upper() == "OTHER":
                values.append((lead.other_condition_text or lead.condition_other or "Other").strip())
            else:
                values.append(self._normalize_condition(str(lead.condition.value if hasattr(lead.condition, "value") else lead.condition)))
        return values

    def _normalize_condition(self, value: str | None) -> str:
        if not value:
            return "Not specified"
        normalized = str(value).upper().strip()
        return CONDITION_LABELS.get(normalized, value.replace("_", " ").title())

    def _normalize_treatment_interest(self, value: str | None) -> str:
        if not value:
            return "General consultation"
        raw = str(value).strip()
        return TREATMENT_LABELS.get(raw, TREATMENT_LABELS.get(raw.upper(), raw.replace("_", " ").title()))

    def _safe_label(self, value: Any) -> str:
        if value is None:
            return "Unknown"
        if hasattr(value, "value"):
            value = value.value
        return str(value).replace("_", " ").title()

    def _ensure_utc(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _derive_stage_key(self, lead: Lead) -> str:
        if lead.status in COMPLETED_STATUSES:
            return "completed"
        if lead.status == LeadStatus.SCHEDULED:
            return "scheduled"
        if lead.contact_outcome == ContactOutcome.CALLBACK_REQUESTED:
            return "callback"
        if lead.status == LeadStatus.CONTACTED or lead.contact_outcome in {
            ContactOutcome.ANSWERED,
            ContactOutcome.NO_ANSWER,
            ContactOutcome.UNREACHABLE,
            ContactOutcome.NOT_INTERESTED,
        }:
            return "contacted"
        return "new"

    def _derive_queue_hint(self, lead: Lead) -> str:
        if lead.status in COMPLETED_STATUSES:
            return "completed"
        if lead.status == LeadStatus.SCHEDULED:
            return "scheduled"
        if lead.contact_outcome == ContactOutcome.CALLBACK_REQUESTED:
            return "callback"
        if lead.contact_outcome == ContactOutcome.NO_ANSWER:
            return "follow_up"
        if lead.contact_outcome == ContactOutcome.UNREACHABLE:
            return "unreachable"
        if lead.contact_outcome == ContactOutcome.NOT_INTERESTED:
            return "not_interested"
        if lead.priority and self._safe_label(lead.priority).lower() == "hot":
            return "hot"
        return "new"

    def _build_priority_candidate(self, lead: Lead, now: datetime) -> PriorityCandidate | None:
        if lead.status not in OPEN_STATUSES or lead.contact_outcome == ContactOutcome.NOT_INTERESTED:
            return None

        created_at = self._ensure_utc(lead.created_at)
        last_touch = self._ensure_utc(lead.last_updated_at or lead.updated_at or lead.created_at)
        days_waiting = int((now - created_at).total_seconds() // 86400) if created_at else 0
        stale_days = int((now - last_touch).total_seconds() // 86400) if last_touch else 0

        priority = self._safe_label(lead.priority)
        urgency = self._safe_label(lead.urgency)
        outcome = self._safe_label(lead.contact_outcome)
        status = self._safe_label(lead.status)
        insurance_status = lead.insurance_provider.strip() if lead.has_insurance and lead.insurance_provider else ("Insured" if lead.has_insurance else "Uninsured")
        condition = ", ".join(self._condition_values(lead))
        treatment_interest = self._normalize_treatment_interest(lead.sleep_treatment_interest)
        preferred_contact_method = self._safe_label(
            lead.preferred_contact_method or lead.contact_method or "Phone"
        )

        score = 0
        score += {"Hot": 45, "Medium": 28, "Low": 14}.get(priority, 12)
        score += {"Asap": 18, "Within 30 Days": 12, "Exploring": 6}.get(urgency, 0)
        score += 14 if lead.has_insurance else 0
        score += 8 if lead.is_referral else 0
        score += min(days_waiting, 10) * 2
        score += min(stale_days, 8) * 2
        score += {
            "Answered": 18,
            "Callback Requested": 18,
            "No Answer": 10,
            "New": 12,
            "Unreachable": 4,
            "Scheduled": 8,
        }.get(outcome, 0)

        if lead.status == LeadStatus.SCHEDULED:
            action = "Confirm attendance and remove any scheduling friction"
            reason = (
                f"This lead is already scheduled for care around {condition.lower()}, so the "
                "highest-value move is protecting show rate."
            )
            script = (
                "Hi {first_name}, this is SleepReach checking in before your upcoming sleep "
                f"consultation for {condition.lower()}. If anything about timing, paperwork, or "
                "insurance needs attention, reply here and we will help right away."
            )
        elif lead.contact_outcome == ContactOutcome.ANSWERED:
            action = "Move this lead from interest to a booked consultation"
            reason = (
                f"This lead already engaged live, has {insurance_status.lower()}, and is still "
                "close enough to the conversation for scheduling to feel natural today."
            )
            script = (
                "Hi {first_name}, this is SleepReach following up on our conversation about "
                f"{condition.lower()}. Since you are interested in {treatment_interest.lower()}, "
                "the best next step is to reserve a consultation slot while we still have "
                "availability this week."
            )
        elif lead.contact_outcome == ContactOutcome.NO_ANSWER:
            action = "Retry by phone, then send a concise SMS"
            reason = (
                f"This lead has not connected yet, but they are still active and looking for help "
                f"with {condition.lower()}. Consistent follow-up is still worth it here."
            )
            script = (
                "Hi {first_name}, this is SleepReach. I am following up on your request for help "
                f"with {condition.lower()}. We can quickly review your symptoms, insurance, and the "
                "best next step for a sleep consultation by phone or text."
            )
        elif lead.contact_outcome == ContactOutcome.CALLBACK_REQUESTED:
            action = "Honor the promised callback window"
            reason = (
                f"They already asked for a callback, and fast follow-through is one of the "
                f"strongest trust signals for someone seeking help with {condition.lower()}."
            )
            script = (
                "Hi {first_name}, this is SleepReach calling back as promised about your "
                f"{condition.lower()} concerns. I can help you review {treatment_interest.lower()} "
                "options and get a consultation time on the calendar."
            )
        elif lead.is_referral:
            action = "Reference the referring provider and offer immediate scheduling"
            reason = (
                "Referral leads tend to convert well when the clinic acknowledges the provider "
                "connection and moves straight into scheduling."
            )
            script = (
                "Hi {first_name}, this is SleepReach. We received your referral and would love to "
                f"help you with {condition.lower()}. I can walk you through insurance, testing, "
                "and available consultation times today."
            )
        else:
            action = "Make first contact today"
            reason = (
                f"This lead is still early in the funnel and faster first-touch speed improves "
                f"scheduling rates for patients dealing with {condition.lower()}."
            )
            script = (
                "Hi {first_name}, this is SleepReach. I am reaching out about your interest in "
                f"care for {condition.lower()}. We can help you understand treatment paths like "
                f"{treatment_interest.lower()} and guide you to the right next step."
            )

        return PriorityCandidate(
            lead_id=str(lead.id),
            lead_number=lead.lead_number,
            queue_hint=self._derive_queue_hint(lead),
            priority_score=score,
            condition=condition,
            priority=priority,
            status=status,
            contact_outcome=outcome,
            urgency=urgency,
            insurance_status=insurance_status,
            days_waiting=days_waiting,
            stale_days=stale_days,
            recommended_action=action,
            reason=reason,
            script=script,
            treatment_interest=treatment_interest,
            preferred_contact_method=preferred_contact_method,
        )

    def _compute_health_score(
        self,
        *,
        total_leads: int,
        scheduled_count: int,
        completed_count: int,
        stale_followups: int,
        insured_stale: int,
        avg_first_contact_hours: float | None,
    ) -> int:
        if total_leads == 0:
            return 0

        scheduled_rate = scheduled_count / total_leads
        completed_rate = completed_count / total_leads
        stale_ratio = stale_followups / total_leads
        insured_stale_ratio = insured_stale / total_leads
        response_bonus = 0.0
        if avg_first_contact_hours is not None:
            response_bonus = max(0.0, 1.0 - min(avg_first_contact_hours, 72) / 72)

        score = (
            28 * scheduled_rate
            + 24 * completed_rate
            + 18 * response_bonus
            + 18 * (1 - stale_ratio)
            + 12 * (1 - insured_stale_ratio)
        )
        return max(0, min(100, round(score)))

    def _build_funnel(self, leads: list[Lead], now: datetime) -> dict[str, Any]:
        buckets = {"new": [], "contacted": [], "scheduled": [], "completed": []}

        for lead in leads:
            stage = self._derive_stage_key(lead)
            if stage == "callback":
                stage = "contacted"
            if stage in buckets:
                buckets[stage].append(lead)

        stages = []
        previous_count = None
        total = len(leads) or 1

        for key, label in (
            ("new", "New"),
            ("contacted", "Contacted"),
            ("scheduled", "Scheduled"),
            ("completed", "Completed"),
        ):
            stage_leads = buckets[key]
            avg_days = []
            for lead in stage_leads:
                created_at = self._ensure_utc(lead.created_at)
                if not created_at:
                    continue
                if key == "new":
                    avg_days.append((now - created_at).total_seconds() / 86400)
                elif key == "contacted":
                    touch = self._ensure_utc(lead.contacted_at or lead.last_contact_attempt or lead.updated_at)
                    if touch:
                        avg_days.append((touch - created_at).total_seconds() / 86400)
                elif key == "scheduled":
                    scheduled_at = self._ensure_utc(lead.scheduled_callback_at or lead.updated_at)
                    if scheduled_at:
                        avg_days.append((scheduled_at - created_at).total_seconds() / 86400)
                else:
                    converted_at = self._ensure_utc(lead.converted_at or lead.updated_at)
                    if converted_at:
                        avg_days.append((converted_at - created_at).total_seconds() / 86400)

            count = len(stage_leads)
            dropoff = None
            if previous_count is not None and previous_count > 0:
                dropoff = round((1 - (count / previous_count)) * 100, 1)
            previous_count = count

            stages.append(
                {
                    "key": key,
                    "label": label,
                    "count": count,
                    "percentage_of_total": round((count / total) * 100, 1),
                    "dropoff_from_previous": dropoff,
                    "avg_days": round(sum(avg_days) / len(avg_days), 1) if avg_days else 0.0,
                }
            )

        contacted_to_scheduled_dropoff = stages[2]["dropoff_from_previous"] if len(stages) > 2 else 0.0
        return {
            "stages": stages,
            "contacted_to_scheduled_dropoff": contacted_to_scheduled_dropoff or 0.0,
        }

    def _build_conversion_rows(self, leads: list[Lead], dimension: str) -> list[dict[str, Any]]:
        buckets: defaultdict[str, list[Lead]] = defaultdict(list)
        for lead in leads:
            if dimension == "source":
                key = self._safe_label(lead.source)
                buckets[key].append(lead)
                continue

            if dimension == "condition":
                labels = self._condition_values(lead) or ["Not specified"]
                for label in labels:
                    buckets[label].append(lead)
                continue

            key = lead.insurance_provider.strip() if lead.has_insurance and lead.insurance_provider else ("Uninsured" if not lead.has_insurance else "Insured")
            buckets[key].append(lead)

        rows = []
        for key, items in buckets.items():
            total = len(items)
            converted = len([lead for lead in items if lead.status in SCHEDULED_OR_BETTER])
            completed = len([lead for lead in items if lead.status in COMPLETED_STATUSES])
            rows.append(
                {
                    "label": key,
                    "count": total,
                    "converted": converted,
                    "completed": completed,
                    "conversion_rate": round((converted / total) * 100, 1) if total else 0.0,
                }
            )
        rows.sort(key=lambda item: (-item["conversion_rate"], -item["count"], item["label"]))
        return rows[:10]

    def _build_provider_rankings(self, providers: list[ReferringProvider]) -> list[dict[str, Any]]:
        rows = []
        for provider in providers:
            referrals = provider.total_referrals or 0
            rows.append(
                {
                    "id": str(provider.id),
                    "name": provider.name,
                    "specialty": provider.specialty or "Other",
                    "status": provider.status.value if hasattr(provider.status, "value") else str(provider.status),
                    "referrals": referrals,
                    "converted": provider.converted_referrals or 0,
                    "conversion_rate": round(provider.conversion_rate or 0.0, 1),
                    "last_referral_at": provider.last_referral_at.isoformat() if provider.last_referral_at else None,
                    "practice_name": provider.practice_name,
                }
            )
        rows.sort(key=lambda item: (-item["conversion_rate"], -item["referrals"], item["name"]))
        return rows[:10]

    def _build_coordinator_performance(self, leads: list[Lead], users: list[User]) -> list[dict[str, Any]]:
        user_lookup = {
            str(user.id): {
                "name": f"{user.first_name} {user.last_name}".strip(),
                "role": user.role.value if isinstance(user.role, UserRole) else str(user.role),
            }
            for user in users
        }
        performance: defaultdict[str, dict[str, Any]] = defaultdict(lambda: {"assigned": 0, "scheduled": 0, "completed": 0})
        for lead in leads:
            if not lead.assigned_to:
                continue
            key = str(lead.assigned_to)
            performance[key]["assigned"] += 1
            if lead.status in SCHEDULED_OR_BETTER:
                performance[key]["scheduled"] += 1
            if lead.status in COMPLETED_STATUSES:
                performance[key]["completed"] += 1

        rows = []
        for user_id, metrics in performance.items():
            user = user_lookup.get(user_id)
            if not user:
                continue
            assigned = metrics["assigned"]
            rows.append(
                {
                    "user_id": user_id,
                    "name": user["name"],
                    "role": user["role"],
                    "assigned": assigned,
                    "scheduled": metrics["scheduled"],
                    "completed": metrics["completed"],
                    "scheduled_rate": round((metrics["scheduled"] / assigned) * 100, 1) if assigned else 0.0,
                    "completion_rate": round((metrics["completed"] / assigned) * 100, 1) if assigned else 0.0,
                }
            )
        rows.sort(key=lambda item: (-item["completion_rate"], -item["scheduled_rate"], -item["assigned"]))
        return rows[:8]

    # Arizona zip code → city mapping for geographic resolution
    AZ_ZIP_CITY: dict[str, str] = {
        "85001": "Phoenix", "85002": "Phoenix", "85003": "Phoenix", "85004": "Phoenix",
        "85006": "Phoenix", "85007": "Phoenix", "85008": "Phoenix", "85009": "Phoenix",
        "85011": "Phoenix", "85012": "Phoenix", "85013": "Phoenix", "85014": "Phoenix",
        "85015": "Phoenix", "85016": "Phoenix", "85017": "Phoenix", "85018": "Phoenix",
        "85019": "Phoenix", "85020": "Phoenix", "85021": "Phoenix", "85022": "Phoenix",
        "85023": "Phoenix", "85024": "Phoenix", "85027": "Phoenix", "85028": "Phoenix",
        "85029": "Phoenix", "85031": "Phoenix", "85032": "Phoenix", "85033": "Phoenix",
        "85034": "Phoenix", "85035": "Phoenix", "85037": "Phoenix", "85040": "Phoenix",
        "85041": "Phoenix", "85042": "Phoenix", "85043": "Phoenix", "85044": "Phoenix",
        "85045": "Phoenix", "85048": "Phoenix", "85050": "Phoenix", "85051": "Phoenix",
        "85053": "Phoenix", "85054": "Phoenix",
        "85201": "Mesa", "85202": "Mesa", "85203": "Mesa", "85204": "Mesa",
        "85205": "Mesa", "85206": "Mesa", "85207": "Mesa", "85208": "Mesa",
        "85209": "Mesa", "85210": "Mesa", "85212": "Mesa", "85213": "Mesa",
        "85215": "Mesa", "85233": "Gilbert", "85234": "Gilbert", "85295": "Gilbert",
        "85296": "Gilbert", "85297": "Gilbert", "85298": "Gilbert",
        "85225": "Chandler", "85224": "Chandler", "85226": "Chandler",
        "85248": "Chandler", "85249": "Chandler", "85286": "Chandler",
        "85250": "Scottsdale", "85251": "Scottsdale", "85252": "Scottsdale",
        "85253": "Scottsdale", "85254": "Scottsdale", "85255": "Scottsdale",
        "85256": "Scottsdale", "85257": "Scottsdale", "85258": "Scottsdale",
        "85259": "Scottsdale", "85260": "Scottsdale", "85262": "Scottsdale",
        "85266": "Scottsdale", "85267": "Scottsdale",
        "85281": "Tempe", "85282": "Tempe", "85283": "Tempe", "85284": "Tempe",
        "85301": "Glendale", "85302": "Glendale", "85303": "Glendale",
        "85304": "Glendale", "85305": "Glendale", "85306": "Glendale",
        "85307": "Goodyear", "85338": "Goodyear", "85340": "Litchfield Park",
        "85308": "Glendale", "85310": "Glendale",
        "85345": "Peoria", "85381": "Peoria", "85382": "Peoria", "85383": "Peoria",
        "85374": "Surprise", "85375": "Surprise", "85378": "Surprise",
        "85142": "Queen Creek", "85143": "San Tan Valley",
        "85118": "Gold Canyon", "85120": "Apache Junction",
        "85122": "Casa Grande", "85128": "Coolidge",
        "85268": "Fountain Hills", "85331": "Cave Creek", "85377": "Carefree",
        "86301": "Prescott", "86303": "Prescott", "86305": "Prescott Valley",
        "86401": "Kingman", "85701": "Tucson", "85710": "Tucson", "85718": "Tucson",
        "85392": "Avondale", "85323": "Buckeye", "85326": "Buckeye",
        "86001": "Flagstaff", "86004": "Flagstaff",
    }

    def _build_geographic_analysis(self, leads: list[Lead]) -> dict[str, Any]:
        """Analyze lead distribution by resolved city name and recorded location."""
        from collections import Counter
        city_counts: Counter[str] = Counter()
        city_conversion: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "converted": 0})
        location_counts: Counter[str] = Counter()

        for lead in leads:
            zc = (lead.zip_code or "").strip()
            if zc:
                city = self.AZ_ZIP_CITY.get(zc, f"Zip {zc}")
                city_counts[city] += 1
                city_conversion[city]["total"] += 1
                if lead.status in SCHEDULED_OR_BETTER:
                    city_conversion[city]["converted"] += 1
            loc = getattr(lead, "lead_location", None)
            if loc and loc.strip():
                location_counts[loc.strip()] += 1

        top_cities = [
            {"city": c, "count": n, "converted": city_conversion[c]["converted"],
             "rate": round((city_conversion[c]["converted"] / city_conversion[c]["total"]) * 100, 1)}
            for c, n in city_counts.most_common(10)
        ]
        top_locations = [{"location": loc, "count": c} for loc, c in location_counts.most_common(10)]

        return {
            "top_cities": top_cities,
            "top_locations": top_locations,
            "total_unique_cities": len(city_counts),
            "total_with_location": sum(location_counts.values()),
        }

    def _build_weekly_series(self, leads: list[Lead], now: datetime) -> list[dict[str, Any]]:
        rows = []
        for offset in range(7, -1, -1):
            week_start = (now - timedelta(days=now.weekday())) - timedelta(weeks=offset)
            week_end = week_start + timedelta(days=7)
            week_leads = [lead for lead in leads if self._ensure_utc(lead.created_at) and week_start <= self._ensure_utc(lead.created_at) < week_end]
            scheduled = [lead for lead in week_leads if lead.status in SCHEDULED_OR_BETTER]
            rows.append(
                {
                    "label": week_start.strftime("%b %d"),
                    "leads": len(week_leads),
                    "scheduled": len(scheduled),
                    "conversion_rate": round((len(scheduled) / len(week_leads)) * 100, 1) if week_leads else 0.0,
                }
            )
        return rows

    def _build_monthly_series(self, leads: list[Lead], now: datetime) -> list[dict[str, Any]]:
        rows = []
        current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_starts = []
        cursor = current
        for _ in range(6):
            month_starts.append(cursor)
            cursor = (cursor - timedelta(days=1)).replace(day=1)
        month_starts.reverse()

        for month_start in month_starts:
            next_month = (month_start + timedelta(days=32)).replace(day=1)
            month_leads = [lead for lead in leads if self._ensure_utc(lead.created_at) and month_start <= self._ensure_utc(lead.created_at) < next_month]
            completed = [lead for lead in month_leads if lead.status in COMPLETED_STATUSES]
            rows.append(
                {
                    "label": month_start.strftime("%b"),
                    "leads": len(month_leads),
                    "completed": len(completed),
                    "conversion_rate": round((len(completed) / len(month_leads)) * 100, 1) if month_leads else 0.0,
                }
            )
        return rows

    def _hour_bucket(self, dt: datetime | None) -> str:
        if not dt:
            return "Unknown"
        hour = dt.hour
        if 6 <= hour < 11:
            return "Morning"
        if 11 <= hour < 15:
            return "Midday"
        if 15 <= hour < 19:
            return "Afternoon"
        return "Evening"

    def _best_contact_bucket(self, rows: list[dict[str, Any]]) -> str:
        meaningful = [row for row in rows if row["attempts"] > 0]
        if not meaningful:
            return "Midday"
        best = max(meaningful, key=lambda item: (item["positive_rate"], item["attempts"]))
        return best["label"]

    def _build_timing_rows(self, leads: list[Lead]) -> tuple[list[dict[str, Any]], str]:
        buckets: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"attempts": 0, "positive": 0})
        for lead in leads:
            attempt_time = self._ensure_utc(lead.last_contact_attempt or lead.contacted_at)
            if not attempt_time:
                continue
            bucket = self._hour_bucket(attempt_time)
            buckets[bucket]["attempts"] += 1
            if lead.contact_outcome in POSITIVE_OUTCOMES:
                buckets[bucket]["positive"] += 1

        rows = []
        for label in ["Morning", "Midday", "Afternoon", "Evening"]:
            attempts = buckets[label]["attempts"]
            positive = buckets[label]["positive"]
            rows.append(
                {
                    "label": label,
                    "attempts": attempts,
                    "positive": positive,
                    "positive_rate": round((positive / attempts) * 100, 1) if attempts else 0.0,
                }
            )
        return rows, self._best_contact_bucket(rows)

    def _best_contact_method(self, rows: list[dict[str, Any]]) -> str:
        meaningful = [row for row in rows if row["count"] > 0]
        if not meaningful:
            return "Phone"
        best = max(meaningful, key=lambda item: (item["success_rate"], item["count"]))
        return best["label"]

    def _build_method_rows(self, leads: list[Lead]) -> tuple[list[dict[str, Any]], str]:
        buckets: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "positive": 0})
        for lead in leads:
            label = self._safe_label(lead.preferred_contact_method or lead.contact_method or "Phone")
            buckets[label]["count"] += 1
            if lead.contact_outcome in POSITIVE_OUTCOMES:
                buckets[label]["positive"] += 1

        labels = ["Phone", "Sms", "Email", "Video Call", "Any"]
        rows = []
        for label in labels:
            count = buckets[label]["count"]
            positive = buckets[label]["positive"]
            rows.append(
                {
                    "label": "SMS" if label == "Sms" else label,
                    "count": count,
                    "positive": positive,
                    "success_rate": round((positive / count) * 100, 1) if count else 0.0,
                }
            )
        return rows, self._best_contact_method(rows)

    def _default_templates(self) -> list[dict[str, str]]:
        return [
            {
                "id": "first_contact",
                "title": "First Contact Script",
                "body": "Hi, this is SleepReach with The Insomnia and Sleep Institute of Arizona. We received your request for help with your sleep concerns and can walk you through consultation options, insurance review, and the right next step today.",
            },
            {
                "id": "follow_up_no_answer",
                "title": "Follow-up After No Answer",
                "body": "Hi, this is SleepReach. I tried to reach you about your sleep consultation request. If now is not a good time, reply here and we can coordinate the best time to talk about insomnia, sleep apnea, testing, or treatment options.",
            },
            {
                "id": "re_engagement",
                "title": "Re-engagement for Cooling Leads",
                "body": "Hi, this is SleepReach checking back in. We still have your information on file and can help you explore sleep studies, CPAP support, Inspire therapy, or CBT-I when you are ready.",
            },
            {
                "id": "scheduling_confirmation",
                "title": "Scheduling Confirmation",
                "body": "Hi, this is SleepReach confirming your upcoming sleep consultation. If you need to adjust the time, reply here and we will help you stay on track.",
            },
        ]

    def _default_forecast(
        self,
        weekly_series: list[dict[str, Any]],
        current_month_leads: list[Lead],
        current_conversion_rate: float,
    ) -> dict[str, Any]:
        recent_weeks = weekly_series[-4:] if weekly_series else []
        avg_weekly_leads = round(sum(item["leads"] for item in recent_weeks) / len(recent_weeks), 1) if recent_weeks else 0.0
        projected_monthly_leads = round(avg_weekly_leads * 4.3)
        projected_scheduled = round(projected_monthly_leads * (current_conversion_rate / 100))
        return {
            "projected_monthly_leads": projected_monthly_leads,
            "projected_scheduled": projected_scheduled,
            "summary": (
                f"Based on recent pacing, you are on track for about {projected_monthly_leads} leads and "
                f"{projected_scheduled} scheduled consultations this month."
            ),
            "current_month_leads": len(current_month_leads),
            "current_conversion_rate": current_conversion_rate,
        }

    def _largest_queue_label(self, stage_counts: dict[str, int]) -> str:
        if not stage_counts:
            return "the active pipeline"
        label_map = {
            "new": "New",
            "contacted": "Contacted",
            "scheduled": "Scheduled",
            "completed": "Completed",
        }
        key = max(stage_counts, key=stage_counts.get)
        return label_map.get(key, key.title())


def get_ai_insights_service(db: Session) -> AIInsightsService:
    return AIInsightsService(db)
