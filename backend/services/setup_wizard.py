"""Guided /setkey wizard (Telegram). No FastAPI imports.

Owns the `setup_wizard` pending-action rows: multi-step collection of
(key, provider, model) across separate webhook calls, then funnels into
the exact same test_config → save path as the one-shot /setkey.

The raw key is Fernet-encrypted the instant it arrives — action_args
never holds plaintext. Rows expire via the established PENDING_TTL.
"""

import json
import structlog
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

import models
from config import get_settings
from services import provider_config_service, telegram_service
from services.alfred_agent import PENDING_TTL
from services.llm_providers.capabilities import RECOMMENDED_MODELS

logger = structlog.get_logger()

WIZARD_TYPE = "setup_wizard"

STAGE_KEY = "awaiting_key"
STAGE_PROVIDER = "awaiting_provider"
STAGE_MODEL = "awaiting_model"
STAGE_MODEL_TEXT = "awaiting_model_text"

PROVIDERS = ("gemini", "anthropic", "openai", "deepseek", "kimi")


def _utcnow():
    return datetime.now(timezone.utc)


def _get_row(db: Session, user: models.BatAccount) -> Optional[models.BatPendingAlfredAction]:
    row = (
        db.query(models.BatPendingAlfredAction)
        .filter(
            models.BatPendingAlfredAction.owner_id == user.id,
            models.BatPendingAlfredAction.action_type == WIZARD_TYPE,
        )
        .first()
    )
    if row is None:
        return None
    expires = row.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is not None and expires <= _utcnow():
        db.delete(row)
        db.commit()
        return None
    return row


def _save_row(db: Session, user: models.BatAccount, stage: str,
              key_encrypted: Optional[str] = None,
              provider: Optional[str] = None) -> models.BatPendingAlfredAction:
    db.query(models.BatPendingAlfredAction).filter(
        models.BatPendingAlfredAction.owner_id == user.id,
        models.BatPendingAlfredAction.action_type == WIZARD_TYPE,
    ).delete()
    args = {"wizard": "setkey", "stage": stage}
    if key_encrypted is not None:
        args["key_encrypted"] = key_encrypted
    if provider is not None:
        args["provider"] = provider
    row = models.BatPendingAlfredAction(
        owner_id=user.id,
        action_type=WIZARD_TYPE,
        action_args=json.dumps(args),
        confirmation_message="",
        expires_at=_utcnow() + PENDING_TTL,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _clear_row(db: Session, row: models.BatPendingAlfredAction) -> None:
    db.delete(row)
    db.commit()


def _send(chat_id: str, text: str) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        return
    telegram_service.send_telegram_message(settings.telegram_bot_token, chat_id, text)


def _send_keyboard(chat_id: str, text: str, keyboard) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        return
    telegram_service.send_telegram_message(
        settings.telegram_bot_token, chat_id, text,
        reply_markup={"inline_keyboard": keyboard},
    )


def _scrub(chat_id: str, message_id) -> None:
    """Best-effort deleteMessage. Never raises — logged only."""
    try:
        if message_id is None:
            return
        settings = get_settings()
        if not settings.telegram_bot_token:
            return
        telegram_service.delete_telegram_message(settings.telegram_bot_token, chat_id, message_id)
    except Exception as exc:
        logger.warning("wizard_message_delete_failed", error=str(exc))


def _provider_keyboard():
    return [[{"text": p, "callback_data": f"wprov:{p}"}] for p in PROVIDERS]


def _model_keyboard(provider: str):
    rec = RECOMMENDED_MODELS.get(provider, "")
    return [
        [{"text": f"{rec} (recommended)", "callback_data": f"wmodel:{rec}"}],
        [{"text": "Other — I'll type one", "callback_data": "wmodel:other"}],
    ]


def start(db: Session, user: models.BatAccount, chat_id: str) -> None:
    """Begin (or restart) the wizard. Caller clears other pendings first."""
    _save_row(db, user, STAGE_KEY)
    _send(chat_id, "Paste your API key. It will be encrypted immediately and your message deleted.")


async def handle_text(db: Session, user: models.BatAccount, chat_id: str,
                      text: str, message_id) -> bool:
    """Route a plain-text message into the wizard. True = consumed."""
    row = _get_row(db, user)
    if row is None:
        return False
    try:
        args = json.loads(row.action_args or "{}")
    except (json.JSONDecodeError, TypeError):
        args = {}
    stage = args.get("stage")

    if stage == STAGE_KEY:
        raw = (text or "").strip()
        if not raw:
            _send(chat_id, "That came through empty — paste your API key.")
            return True
        key_encrypted = provider_config_service.encrypt_key(raw)
        _scrub(chat_id, message_id)
        provider = provider_config_service.detect_provider_from_key(raw)
        if provider is not None:
            _save_row(db, user, STAGE_MODEL, key_encrypted=key_encrypted, provider=provider)
            _send_keyboard(chat_id, f"Key secured. Provider detected: {provider}. Choose a model:",
                           _model_keyboard(provider))
        else:
            _save_row(db, user, STAGE_PROVIDER, key_encrypted=key_encrypted)
            _send_keyboard(chat_id, "Key secured. Which provider is it for?", _provider_keyboard())
        return True

    if stage == STAGE_PROVIDER:
        choice = (text or "").strip().lower()
        if choice in PROVIDERS:
            args["provider"] = choice
            _save_row(db, user, STAGE_MODEL,
                      key_encrypted=args.get("key_encrypted"), provider=choice)
            _send_keyboard(chat_id, f"Provider: {choice}. Choose a model:", _model_keyboard(choice))
        else:
            _send_keyboard(chat_id, "Tap your provider below.", _provider_keyboard())
        return True

    if stage == STAGE_MODEL:
        # Free text at the model step = custom model name.
        model = (text or "").strip()
        if not model:
            _send_keyboard(chat_id, "Send a model name, or tap below.",
                           _model_keyboard(args.get("provider", "")))
            return True
        await _finalize(db, user, chat_id, row, args.get("provider"),
                        model[:128], args.get("key_encrypted"))
        return True

    if stage == STAGE_MODEL_TEXT:
        model = (text or "").strip()
        if not model:
            _send(chat_id, "Send the model name (e.g. gpt-5.6).")
            return True
        await _finalize(db, user, chat_id, row, args.get("provider"),
                        model[:128], args.get("key_encrypted"))
        return True

    return False


async def handle_callback(db: Session, user: models.BatAccount, callback: dict) -> bool:
    """Route wizard inline-keyboard taps. True = consumed."""
    data = (callback.get("data") or "")
    if not (data.startswith("wprov:") or data.startswith("wmodel:")):
        return False

    settings = get_settings()
    cb_id = callback.get("id")
    chat = ((callback.get("message") or {}).get("chat") or {})
    chat_id = str(chat.get("id", "")) if chat.get("id") is not None else ""

    def _answer(text=""):
        try:
            if settings.telegram_bot_token and cb_id:
                telegram_service.answer_callback_query(settings.telegram_bot_token, cb_id, text)
        except Exception:
            pass

    row = _get_row(db, user)
    if row is None:
        _answer("Expired — send /setkey to start over.")
        return True
    try:
        args = json.loads(row.action_args or "{}")
    except (json.JSONDecodeError, TypeError):
        args = {}
    stage = args.get("stage")

    if data.startswith("wprov:"):
        provider = data.split(":", 1)[1]
        if stage != STAGE_PROVIDER or provider not in PROVIDERS:
            _answer("Expired — send /setkey to start over.")
            return True
        _answer()
        _save_row(db, user, STAGE_MODEL,
                  key_encrypted=args.get("key_encrypted"), provider=provider)
        _send_keyboard(chat_id, f"Provider: {provider}. Choose a model:", _model_keyboard(provider))
        return True

    # wmodel:
    choice = data.split(":", 1)[1]
    if stage != STAGE_MODEL or not args.get("provider"):
        _answer("Expired — send /setkey to start over.")
        return True
    _answer()
    if choice == "other":
        _save_row(db, user, STAGE_MODEL_TEXT,
                  key_encrypted=args.get("key_encrypted"), provider=args.get("provider"))
        _send(chat_id, "Send the model name.")
        return True
    await _finalize(db, user, chat_id, row, args.get("provider"),
                    choice[:128], args.get("key_encrypted"))
    return True


async def _finalize(db: Session, user: models.BatAccount, chat_id: str,
                    row: models.BatPendingAlfredAction,
                    provider: Optional[str], model: Optional[str],
                    key_encrypted: Optional[str]) -> None:
    """Same test_config → save path as one-shot /setkey. No new save logic."""
    if not provider or provider not in PROVIDERS or not model or not key_encrypted:
        _clear_row(db, row)
        _send(chat_id, "Something went stale — send /setkey to start over.")
        return
    try:
        raw_key = provider_config_service.decrypt_key(key_encrypted)
    except Exception:
        _clear_row(db, row)
        _send(chat_id, "The stored key unreadable — send /setkey to start over.")
        return

    ok, msg = await provider_config_service.test_config(provider, model, raw_key)
    if ok:
        try:
            provider_config_service.save_config(db, user, provider, model, raw_key)
        except ValueError as exc:
            _save_row(db, user, STAGE_MODEL, key_encrypted=key_encrypted, provider=provider)
            _send_keyboard(chat_id, f"Not saved: {exc}", _model_keyboard(provider))
            return
        _clear_row(db, row)
        _send(chat_id, f"Provider key saved: {provider} / {model}. Alfred is at your service.")
    else:
        # Keep the wizard at the model step so only that answer needs redoing.
        _save_row(db, user, STAGE_MODEL, key_encrypted=key_encrypted, provider=provider)
        _send_keyboard(chat_id, f"Key test failed — not saved. {msg}", _model_keyboard(provider))
