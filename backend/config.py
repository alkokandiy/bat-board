import json
import logging as stdlib_logging
from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, ValidationInfo, field_validator, ConfigDict


# Example values that appear in this repo (README/.env.example/old
# railway.toml). Long enough to pass the length check, but public, so a
# deployment that copied one would accept forged tokens.
_PLACEHOLDER_SECRETS = frozenset({
    "change-me-to-a-secure-random-string-in-production",
    "set-this-to-a-random-64-char-string-in-railway",
    "your-super-secret-key-change-in-production-min-32-chars",
    "dev-secret-key-change-in-production-min32chars",
})


def _is_placeholder(value: str, info: ValidationInfo) -> bool:
    """Placeholders are allowed only in local development (docker-compose)."""
    return value in _PLACEHOLDER_SECRETS and info.data.get("environment") != "development"


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    app_name: str = "Bat-Board API"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "production"

    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str = "sqlite:///./batboard.db"

    secret_key: str = Field(default="change-me-to-a-secure-random-string-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 30

    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Usernames allowed to use the admin endpoints (/api/admin/*), as a plain
    # comma-separated string (e.g. "alice,bob"). Kept as `str`, not List[str]:
    # pydantic-settings JSON-decodes complex env fields before validators run,
    # so a bare "alice" would crash startup. Parsed in routers/admin.py.
    # Empty (the default) means NO admins — the admin API stays inert.
    admin_usernames: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # Telegram bot (Phase 2A). Optional until Telegram features are active;
    # the webhook route fails closed with 503 when these are unset.
    telegram_bot_token: Optional[str] = None
    telegram_webhook_secret: Optional[str] = None

    # Phase F: shared secret for the briefings/reminders cron endpoint
    # (POST /api/internal/cron/tick). Unset → the endpoint fails closed (503),
    # so the feature is simply dormant until an operator configures it.
    cron_secret: Optional[str] = None

    # LLM key for Alfred Phase 2B. Unused for now.
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.1-flash-lite"

    # Free tier: a built-in provider the operator funds so NEW users get value
    # with no API key of their own. Dormant until `system_provider_key` is set —
    # until then users without their own key see the normal setup prompt.
    # BYOK remains unlimited; free-tier users are capped per day below.
    system_provider: Optional[str] = None          # gemini | anthropic | openai | deepseek | kimi
    system_model: Optional[str] = None              # model id for that provider
    system_provider_key: Optional[str] = None       # the operator-funded key
    free_tier_daily_cap: int = 15                   # messages/day on the free tier

    # Per-user provider keys (BYOK). Fail-loudly like SECRET_KEY: the app
    # refuses to boot without it, so stored keys are never unreadable.
    provider_key_encryption_secret: Optional[str] = None

    log_level: str = "INFO"
    log_format: str = "console"

    @field_validator("secret_key", mode="before")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        if _is_placeholder(v, info) or len(v) < 16:
            raise RuntimeError(
                "SECRET_KEY must be set to a strong random value in production. "
                "Refusing to start with a missing or default key."
            )
        return v

    @field_validator("provider_key_encryption_secret", mode="before")
    @classmethod
    def validate_provider_secret(cls, v, info: ValidationInfo) -> str:
        if not v or _is_placeholder(v, info) or len(v) < 16:
            raise RuntimeError(
                "PROVIDER_KEY_ENCRYPTION_SECRET must be set to a strong random "
                "value in production. Refusing to start without it — stored "
                "provider keys would be unreadable."
            )
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if v.startswith("postgres://") and "+" not in v:
            v = v.replace("postgres://", "postgresql+psycopg2://", 1)
        elif v.startswith("postgresql://") and "+" not in v:
            v = v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()