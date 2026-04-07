"""
Jotform API helpers for recovering authoritative submission data.

Some HIPAA-configured Jotform webhooks may mask PHI fields as "***" unless
"Send PHI to Webhooks" is enabled. When that happens, we can recover the real
submission payload via the Jotform submissions API if an API key is configured.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


FALLBACK_JOTFORM_API_BASES = (
    "https://hipaa-api.jotform.com",
    "https://api.jotform.com",
)


def _candidate_base_urls() -> list[str]:
    candidates: list[str] = []
    configured = (settings.jotform_api_base_url or "").strip().rstrip("/")
    if configured:
        candidates.append(configured)
    for base in FALLBACK_JOTFORM_API_BASES:
        normalized = base.rstrip("/")
        if normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _normalize_checkbox_answer(answer: Any) -> Any:
    if isinstance(answer, list):
        return [str(item).strip() for item in answer if str(item).strip()]
    if isinstance(answer, str):
        text = answer.strip()
        if not text:
            return ""
        if "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]
        return text
    return answer


def _answer_name_fallback(qid: str) -> str | None:
    return {
        "5": "q5_q5_checkbox3",
        "6": "q6_q6_checkbox4",
        "7": "q7_q7_textbox5",
        "8": "q8_q8_radio6",
        "9": "q9_q9_radio7",
        "10": "q10_q10_checkbox8",
        "11": "q11_q11_radio9",
        "12": "q12_q12_radio10",
        "13": "q13_q13_textbox11",
        "14": "q14_q14_textbox12",
        "15": "q15_q15_email13",
        "16": "q16_q16_textbox14",
        "19": "q19_q19_email17",
        "20": "q20_q20_phone18",
        "21": "q21_q21_datetime19",
        "22": "q22_q22_radio20",
        "23": "q23_q23_checkbox21",
        "24": "q24_q24_radio22",
        "25": "q25_q25_textbox23",
        "26": "q26_q26_textbox24",
        "30": "q30_fullName",
    }.get(qid)


def submission_content_to_form_data(content: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert Jotform API submission content.answers payload into the same shape
    that our canonical intake mapper already understands.
    """
    result: Dict[str, Any] = {}
    answers = content.get("answers") or {}

    submission_id = content.get("id") or content.get("submissionID") or content.get("submissionId")
    if submission_id:
        result["submissionID"] = str(submission_id)

    form_id = content.get("form_id") or content.get("formID")
    if form_id:
        result["formID"] = str(form_id)

    for raw_qid, answer_obj in answers.items():
        if not isinstance(answer_obj, dict):
            continue

        qid = str(answer_obj.get("qid") or raw_qid)
        name = str(answer_obj.get("name") or _answer_name_fallback(qid) or "").strip()
        answer = answer_obj.get("answer")

        if answer in (None, "", []):
            continue

        if qid in {"5", "6", "10", "23"}:
            answer = _normalize_checkbox_answer(answer)

        if not name:
            continue

        result[name] = answer

        if isinstance(answer, list):
            result[f"{name}[]"] = answer
        elif isinstance(answer, dict):
            for key, value in answer.items():
                result[f"{name}[{key}]"] = value

    return result


async def fetch_submission_form_data(submission_id: str) -> Dict[str, Any]:
    """
    Fetch a Jotform submission and convert it to our canonical form-data shape.

    Returns an empty dict when the API key is not configured or the submission
    cannot be retrieved.
    """
    api_key = (settings.jotform_api_key or "").strip()
    if not api_key:
        logger.info("Jotform API key not configured; cannot recover masked submission %s", submission_id)
        return {}

    headers = {"APIKEY": api_key}
    params = {"apiKey": api_key}

    async with httpx.AsyncClient(timeout=20.0) as client:
        for base_url in _candidate_base_urls():
            url = f"{base_url}/submission/{submission_id}"
            try:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
                content = payload.get("content") or {}
                if not content:
                    continue
                logger.info("Recovered authoritative Jotform submission %s from %s", submission_id, base_url)
                return submission_content_to_form_data(content)
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Jotform submission fetch failed for %s via %s: %s",
                    submission_id,
                    base_url,
                    exc.response.status_code,
                )
            except Exception as exc:
                logger.warning(
                    "Jotform submission fetch error for %s via %s: %s",
                    submission_id,
                    base_url,
                    exc,
                )

    return {}
