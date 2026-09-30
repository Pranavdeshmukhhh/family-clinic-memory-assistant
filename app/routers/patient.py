"""
Patient summary — doctor + owner only.
  GET /patient/{patient_id}/summary  — Hindsight reflect
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from hindsight_client import Hindsight

from app.config import settings
from app.services.auth import require_role
from app.services.llm import groq_chat, parse_llm_json

log = logging.getLogger("clinic.patient")
router = APIRouter(prefix="/patient", tags=["patient"])


def _condense_summary(raw_text: str) -> dict:
    """Ask Groq to condense a verbose reflect() output into structured JSON."""
    condense_prompt = (
        "Condense this patient summary into ONLY valid JSON, no markdown:\\n"
        '{\\n'
        '  "headline": "max 20 words, one-line patient risk overview",\\n'
        '  "risks": ["max 4 bullets, max 12 words each"],\\n'
        '  "trends": ["max 3 bullets, max 12 words each"]\\n'
        '}\\n'
        "Be terse. Use clinical abbreviations."
    )
    try:
        condensed_raw = groq_chat(condense_prompt, raw_text[:2000])
        result = parse_llm_json(condensed_raw)
        # Ensure expected keys exist
        return {
            "headline": result.get("headline", raw_text[:200]),
            "risks": result.get("risks", []),
            "trends": result.get("trends", []),
            "full_text": raw_text,
        }
    except Exception:
        return {
            "headline": raw_text[:200],
            "risks": [],
            "trends": [],
            "full_text": raw_text,
        }


@router.get("/{patient_id}/summary")
async def patient_summary(
    patient_id: str,
    user: dict = Depends(require_role("doctor", "owner")),
):
    if not settings.hindsight_configured:
        return {
            "patient_id": patient_id,
            "summary": "Memory not configured (DEMO_MODE). No prior history available.",
            "structured": {
                "headline": "No memory configured — demo mode active.",
                "risks": [],
                "trends": [],
                "full_text": "",
            },
        }

    h = Hindsight(
        base_url=settings.HINDSIGHT_BASE_URL,
        api_key=settings.HINDSIGHT_API_KEY,
    )
    try:
        resp = await h.areflect(
            bank_id=patient_id,
            query="Summarize this patient's risk factors and recurring patterns across visits",
        )
        summary = resp.text if hasattr(resp, "text") else str(resp)
        log.info(
            "🪞 REFLECT │ patient=%s │ actor=%s │ preview=%.80s…",
            patient_id, user["username"], summary,
        )
        structured = _condense_summary(summary)
        return {
            "patient_id": patient_id,
            "summary": summary,
            "structured": structured,
        }
    except Exception as exc:
        if "404" in str(exc) or "not found" in str(exc).lower():
            raise HTTPException(404, f"No memory bank found for patient {patient_id}")
        log.error("❌ Reflect error │ %s", exc)
        return {
            "patient_id": patient_id,
            "summary": (
                "AI summary temporarily unavailable. Please review the patient's "
                "visit history manually. (Hindsight service error)"
            ),
            "structured": {
                "headline": "Summary unavailable — Hindsight service error.",
                "risks": [],
                "trends": [],
                "full_text": "",
            },
        }
    finally:
        await h.aclose()

