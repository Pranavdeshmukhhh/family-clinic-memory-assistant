"""
Application configuration via pydantic-settings.

Fail-closed behaviour:
  - HINDSIGHT_API_KEY is required at startup.
  - If it is missing, the app refuses to start — unless DEMO_MODE=true.
  - GROQ_API_KEY is optional (built-in rule engine is the fallback).
  - Telegram keys are optional (alerts are silently skipped when absent).

Never log the values of any secret fields.
"""
import logging
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("clinic.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Runtime mode ─────────────────────────────────────────────────────────
    # Set DEMO_MODE=true to run without any external API keys (events are
    # no-ops, memory returns empty results, Groq falls back to rule engine).
    DEMO_MODE: bool = False

    # ── Hindsight (required unless DEMO_MODE=true) ────────────────────────────
    HINDSIGHT_API_KEY: str = ""
    HINDSIGHT_BASE_URL: str = "https://api.hindsight.vectorize.io"

    # ── Groq (optional — built-in clinical rule engine used when absent) ──────
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    # ── Telegram (optional) ──────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # ── Database ─────────────────────────────────────────────────────────────
    DB_PATH: str = "clinic.db"

    # ── Derived convenience flags (booleans, never expose secrets) ────────────
    @property
    def hindsight_configured(self) -> bool:
        return bool(self.HINDSIGHT_API_KEY)

    @property
    def groq_configured(self) -> bool:
        return bool(self.GROQ_API_KEY) and not self.GROQ_API_KEY.startswith("your_")

    @property
    def telegram_configured(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN) and bool(self.TELEGRAM_CHAT_ID)

    # ── Startup validation ────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _fail_closed(self) -> "Settings":
        """Refuse to start without a Hindsight key unless DEMO_MODE is on."""
        if not self.DEMO_MODE and not self.HINDSIGHT_API_KEY:
            raise ValueError(
                "\n\n"
                "  ❌  HINDSIGHT_API_KEY is not set.\n"
                "  Set it in your .env file, or run in demo mode:\n\n"
                "      DEMO_MODE=true uvicorn app.main:app\n\n"
                "  In demo mode Hindsight calls are no-ops; all other\n"
                "  features (rule engine, inventory, approval gate) work.\n"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()


# Convenience alias — import `settings` directly in modules.
settings: Settings = get_settings()
