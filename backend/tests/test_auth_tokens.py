"""JWT token tests for the PyJWT migration (no network, real ciphers only).

Covers: jose->PyJWT interop (the 24h/30d post-deploy window), reverse
interop (rollback safety), expiry on both token types, tampered
signatures, forged-key rejection (CVE-2026-85394 shape), the
library-enforced explicit-algorithms discipline, and a full refresh
round-trip through the real endpoints.
"""

from datetime import timedelta

import jwt as pyjwt_lib
import pytest

import auth
from auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    decode_token,
)

JOSE = pytest.importorskip("jose.jwt")


def _flip_mid_signature(token: str) -> str:
    header, payload, sig = token.split(".")
    mid = len(sig) // 2
    return header + "." + payload + "." + sig[:mid] + ("A" if sig[mid] != "A" else "B") + sig[mid + 1:]


def test_interop_jose_encoded_decodes_under_pyjwt():
    """Tokens issued by the OLD code validate under the NEW code path."""
    from config import get_settings

    settings = get_settings()
    old = JOSE.encode(
        {"sub": "interop", "type": "access"},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    got = decode_token(old)
    assert got is not None and got.username == "interop"


def test_reverse_interop_pyjwt_encoded_decodes_under_jose():
    """Rollback safety: new-era tokens still read under the old library."""
    from config import get_settings

    settings = get_settings()
    new = create_access_token({"sub": "rollback"})
    got = JOSE.decode(new, settings.secret_key, algorithms=[settings.algorithm])
    assert got["sub"] == "rollback" and got["type"] == "access"


def test_expired_access_and_refresh_rejected():
    old_access = create_access_token({"sub": "exp"}, expires_delta=timedelta(minutes=-1))
    old_refresh = create_refresh_token({"sub": "exp"}, expires_delta=timedelta(minutes=-1))
    assert decode_token(old_access) is None
    assert decode_refresh_token(old_refresh) is None
    # And the wrong-type gate still holds on live tokens.
    fresh_refresh = create_refresh_token({"sub": "exp"})
    assert decode_token(fresh_refresh) is None
    assert decode_refresh_token(create_access_token({"sub": "exp"})) is None


def test_tampered_signature_rejected():
    good = create_access_token({"sub": "tamper"})
    assert decode_token(_flip_mid_signature(good)) is None


def test_forged_wrong_key_rejected():
    """CVE-2026-85394 shape: attacker-signed material must not verify."""
    from config import get_settings

    settings = get_settings()
    forged = pyjwt_lib.encode(
        {"sub": "admin", "type": "access"}, "attacker-controlled-bytes", algorithm="HS256"
    )
    assert decode_token(forged) is None
    with pytest.raises(pyjwt_lib.InvalidSignatureError):
        pyjwt_lib.decode(forged, settings.secret_key, algorithms=["HS256"])


def test_decode_without_explicit_algorithms_raises():
    """The algorithms discipline is library-enforced, not just convention."""
    from config import get_settings

    token = create_access_token({"sub": "noalg"})
    with pytest.raises(pyjwt_lib.PyJWTError):
        pyjwt_lib.decode(token, get_settings().secret_key)


def test_full_refresh_round_trip(client):
    client.post("/api/auth/register", json={"username": "jwt_roundtrip", "password": "pass1234"})
    r = client.post("/api/auth/login", data={"username": "jwt_roundtrip", "password": "pass1234"})
    assert r.status_code == 200, r.text
    pair = r.json()
    assert decode_token(pair["access_token"]).username == "jwt_roundtrip"

    r = client.post("/api/auth/refresh", json=pair["refresh_token"])
    assert r.status_code == 200, r.text
    rotated = r.json()
    assert decode_token(rotated["access_token"]).username == "jwt_roundtrip"
    assert decode_refresh_token(rotated["refresh_token"]).username == "jwt_roundtrip"

    r = client.post("/api/auth/refresh", json="not-a-token")
    assert r.status_code in (400, 401, 422)
