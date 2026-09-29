"""
Patient summary — doctor + owner only.
  GET /patient/{patient_id}/summary  — Hindsight reflect
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from hindsight_client import Hindsight

from app.config import settings
from app.services.auth import require_role

log = logging.getLogger("clinic.patient")
router = APIRouter(prefix="/patient", tags=["patient"])


@router.get("/{patient_id}/summary")
async def patient_summary(
    patient_id: str,
    user: dict = Depends(require_role("doctor", "owner")),
):
    if not settings.hindsight_configured:
        return {
            "patient_id": patient_id,
            "summary": (
                "Memory not configured (DEMO_MODE). No prior history available."
            ),
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
        return {"patient_id": patient_id, "summary": summary}
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
        }
    finally:
        await h.aclose()
