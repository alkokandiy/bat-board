"""Per-user LLM provider configs (BYOK). Keys encrypted at rest with Fernet.

Plain importable functions — no FastAPI request/response objects.
The raw key is decrypted ONLY at the moment of an actual LLM call.
"""

import base64
import hashlib
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

import models
from config import get_settings

SUPPORTED_PROVIDERS = ("gemini", "anthropic", "openai", "deepseek", "kimi")


def _fernet():
    from cryptography.fernet import Fernet

    secret = get_settings().provider_key_encryption_secret
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_key(raw_key: str) -> str:
    return _fernet().encrypt(raw_key.encode()).decode()


def decrypt_key(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def save_config(
    db: Session,
    current_user: models.BatAccount,
    provider: str,
    model_name: str,
    raw_api_key: str,
) -> models.BatAIProviderConfig:
    """Encrypt + upsert (one config per user). Does NOT test the key."""
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    if not model_name or not model_name.strip():
        raise ValueError("model_name is required")
    if not raw_api_key or not raw_api_key.strip():
        raise ValueError("api_key is required")

    row = (
        db.query(models.BatAIProviderConfig)
        .filter_by(owner_id=current_user.id)
        .first()
    )
    if row is None:
        row = models.BatAIProviderConfig(owner_id=current_user.id)
        db.add(row)
    row.provider = provider
    row.model_name = model_name.strip()
    row.api_key_encrypted = encrypt_key(raw_api_key.strip())
    db.commit()
    db.refresh(row)
    return row


def get_config_row(db: Session, current_user: models.BatAccount) -> Optional[models.BatAIProviderConfig]:
    return (
        db.query(models.BatAIProviderConfig)
        .filter_by(owner_id=current_user.id)
        .first()
    )


def get_decrypted_key(db: Session, current_user: models.BatAccount) -> Optional[str]:
    """Decrypt at the call moment. Never expose through API responses."""
    row = get_config_row(db, current_user)
    if row is None:
        return None
    return decrypt_key(row.api_key_encrypted)


def get_config_status(db: Session, current_user: models.BatAccount) -> Dict:
    """Status only — NEVER the key itself."""
    row = get_config_row(db, current_user)
    if row is None:
        return {"provider": None, "model_name": None, "configured": False}
    return {"provider": row.provider, "model_name": row.model_name, "configured": True}


def delete_config(db: Session, current_user: models.BatAccount) -> bool:
    row = get_config_row(db, current_user)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def build_adapter(provider: str, model_name: str, raw_api_key: str):
    """Instantiate the Batch A adapter for a provider. Raises ValueError if unknown."""
    if provider == "gemini":
        from services.llm_providers.gemini import GeminiAdapter

        return GeminiAdapter(api_key=raw_api_key, model=model_name)
    if provider == "anthropic":
        from services.llm_providers.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(api_key=raw_api_key, model=model_name)
    if provider in ("openai", "deepseek", "kimi"):
        from services.llm_providers.openai_compatible import OpenAICompatibleAdapter

        return OpenAICompatibleAdapter.for_provider(provider, api_key=raw_api_key, model=model_name)
    raise ValueError(f"Unknown provider: {provider}")


async def test_config(provider: str, model_name: str, raw_api_key: str) -> Tuple[bool, str]:
    """ONE minimal cheap call through the real adapter. Returns (ok, message)."""
    if provider not in SUPPORTED_PROVIDERS:
        return False, f"Unknown provider: {provider}. Choose one of: {', '.join(SUPPORTED_PROVIDERS)}."
    if not model_name or not model_name.strip():
        return False, "model_name is required."
    if not raw_api_key or not raw_api_key.strip():
        return False, "api_key is required."
    try:
        adapter = build_adapter(provider, model_name.strip(), raw_api_key.strip())
        resp = await adapter.generate(
            [{"role": "user", "content": "Reply with exactly: ok"}],
            [],
            "Reply with exactly: ok",
        )
        text = (resp.text or "").strip().lower()
        if text and "ok" not in text:
            return True, f"Key works (model replied: {resp.text[:120]})."
        return True, "Key works."
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:300]}"
