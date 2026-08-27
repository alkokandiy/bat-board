import json
import logging as stdlib_logging
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, ConfigDict


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

    log_level: str = "INFO"
    log_format: str = "console"

    @field_validator("secret_key", mode="before")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v == "change-me-to-a-secure-random-string-in-production" or len(v) < 16:
            raise RuntimeError(
                "SECRET_KEY must be set to a strong random value in production. "
                "Refusing to start with a missing or default key."
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