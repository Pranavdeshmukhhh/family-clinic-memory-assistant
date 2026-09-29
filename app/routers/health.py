"""GET /health — integration status (booleans only, never secrets)."""
import logging

from fastapi import APIRouter

from app.config import settings

log = logging.getLogger("clinic.health")
router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """
    Return application status and which integrations are configured.
    Responds with booleans only — never exposes API keys or tokens.
    """
    return {
        "status": "ok",
        "demo_mode": settings.DEMO_MODE,
        "integrations": {
            "hindsight": settings.hindsight_configured,
            "groq": settings.groq_configured,
            "telegram": settings.telegram_configured,
        },
    }
