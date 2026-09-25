import os
import tempfile

_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
# Test-only Telegram config (must precede `from main import app`,
# since get_settings() is lru-cached at import time).
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-webhook-secret-12345")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-bot-token")
os.environ.setdefault("PROVIDER_KEY_ENCRYPTION_SECRET", "test-provider-secret-1234567890")

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def headers(client):
    client.post("/api/auth/register", json={"username": "dayuser", "password": "pass1234"})
    r = client.post(
        "/api/auth/login",
        data={"username": "dayuser", "password": "pass1234"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def auth_headers():
    """Create users directly in the DB and mint real JWTs.

    Avoids the 5/minute register and 10/minute login rate limits when a
    test module needs several distinct users (e.g. owner-scoping tests).
    Tokens are real access tokens, so the auth dependency is still exercised.
    """
    from auth import create_access_token, get_password_hash
    from database import SessionLocal
    import models

    created = set()

    def _headers(username: str):
        if username not in created:
            db = SessionLocal()
            try:
                if not db.query(models.BatAccount).filter_by(username=username).first():
                    db.add(
                        models.BatAccount(
                            username=username,
                            hashed_password=get_password_hash("pass1234"),
                        )
                    )
                    db.commit()
            finally:
                db.close()
            created.add(username)
        # Every test user gets a dummy provider config so run_turn
        # reaches the tool loop; tests then mock adapter resolution.
        # Idempotent: only creates when missing. Tests for the no-config
        # path delete this row explicitly after getting headers.
        from services import provider_config_service

        db = SessionLocal()
        try:
            user = db.query(models.BatAccount).filter_by(username=username).first()
            if user is not None and provider_config_service.get_config_row(db, user) is None:
                provider_config_service.save_config(
                    db, user, "gemini", "test-model", "test-key"
                )
        finally:
            db.close()
        token = create_access_token({"sub": username})
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Fresh slowapi budget per test.

    Webhook/notes/countdown tests share one TestClient IP, so without this
    the per-minute limits leak across tests. Rate-limit tests still pass:
    they burn 35 requests inside a single test.
    """
    from dependencies import limiter

    storage = getattr(limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        try:
            storage.reset()
        except Exception:
            pass
    yield