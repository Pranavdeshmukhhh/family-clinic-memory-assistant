"""
Patient summary endpoint:
  GET /patient/{patient_id}/summary — Hindsight reflect on patient history
"""
import logging

from fastapi import APIRouter, HTTPException
from hindsight_client import Hindsight

from app.config import settings

log = logging.getLogger("clinic.patient")
router = APIRouter(prefix="/patient", tags=["patient"])


@router.get("/{patient_id}/summary")
async def patient_summary(patient_id: str):
    if not settings.hindsight_configured:
        return {
            "patient_id": patient_id,
            "summary": (
                "Memory not configured (DEMO_MODE). "
                "No prior history available."
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
            "🪞 REFLECT │ patient=%s │ summary_preview=%.120s…", patient_id, summary
        )
        return {"patient_id": patient_id, "summary": summary}
    except Exception as exc:
        if "404" in str(exc) or "not found" in str(exc).lower():
            raise HTTPException(404, f"No memory bank found for patient {patient_id}")
        log.error("❌ Reflect error │ %s", exc)
        raise HTTPException(500, str(exc))
    finally:
        await h.aclose()
