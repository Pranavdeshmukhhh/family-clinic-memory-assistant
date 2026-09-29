"""Telegram alert service."""
import logging

import httpx

from app.config import settings

log = logging.getLogger("clinic.alerts")


def send_telegram(text: str) -> None:
    """Send a Telegram message. Silently skips when not configured."""
    if not settings.telegram_configured:
        return
    try:
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = httpx.post(
            url,
            json={
                "chat_id": settings.TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            log.info("📨 Telegram alert sent")
        else:
            log.warning("⚠️  Telegram response: %s", resp.text)
    except Exception as exc:
        log.error("❌ Telegram error: %s", exc)
