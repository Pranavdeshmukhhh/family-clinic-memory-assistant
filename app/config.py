"""
Application configuration via pydantic-settings.

Fail-closed behaviour:
  - HINDSIGHT_API_KEY is required at startup.
  - JWT_SECRET must not be the default value.
  - Both checks are skipped when DEMO_MODE=true.
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

    # ── Authentication ────────────────────────────────────────────────────────
    # Change this to a random 32+ byte hex string in production.
    JWT_SECRET: str = "change-me-in-production"
    JWT_EXPIRE_HOURS: int = 24

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins.
    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    # ── Rate limiting ─────────────────────────────────────────────────────────
    # Set to false in tests / DEMO_MODE to avoid spurious 429s.
    RATELIMIT_ENABLED: bool = True

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

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ── Startup validation ────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _fail_closed(self) -> "Settings":
        if self.DEMO_MODE:
            return self  # skip all required-key checks in demo / test mode

        errors: list[str] = []

        if not self.HINDSIGHT_API_KEY:
            errors.append(
                "  • HINDSIGHT_API_KEY is not set.\n"
                "    Set it in your .env file, or run in demo mode:\n"
                "      DEMO_MODE=true uvicorn app.main:app"
            )

        if self.JWT_SECRET == "change-me-in-production":
            errors.append(
                "  • JWT_SECRET is still the default value.\n"
                "    Generate a secure random secret:\n"
                "      python -c \"import secrets; print(secrets.token_hex(32))\"\n"
                "    and set JWT_SECRET=<value> in your .env file."
            )

        if errors:
            raise ValueError("\n\n❌  Production startup checks failed:\n\n" + "\n\n".join(errors))

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()


# Convenience alias — import `settings` directly in modules.
settings: Settings = get_settings()
