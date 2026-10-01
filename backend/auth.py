from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, field_validator

from config import get_settings
from database import get_db
import models

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None
    # Account id ("uid" claim). Tokens are resolved by id when present so a
    # token can't outlive a rename and then authenticate whoever registers
    # the old username. Older tokens without it fall back to the username.
    user_id: Optional[int] = None


USERNAME_PATTERN = r"^[A-Za-z0-9_.\- ]+$"
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72  # bcrypt ignores everything past 72 bytes


def validate_new_password(v: str) -> str:
    if len(v) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    if len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long")
    return v


def validate_username(v: str) -> str:
    import re

    v = v.strip()
    if not 3 <= len(v) <= 32:
        raise ValueError("Username must be 3-32 characters long")
    if not re.match(USERNAME_PATTERN, v):
        raise ValueError("Username may only contain letters, digits, spaces, '.', '_' and '-'")
    return v


class UserCreate(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        return validate_username(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_new_password(v)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    points: int
    bat_level: str
    is_active: bool
    created_at: datetime


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def token_claims(user: models.BatAccount) -> dict:
    return {"sub": user.username, "uid": user.id}


def _decode(token: str, expected_type: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    username = payload.get("sub")
    if username is None:
        return None
    uid = payload.get("uid")
    return TokenData(username=username, user_id=uid if isinstance(uid, int) else None)


def decode_token(token: str) -> Optional[TokenData]:
    return _decode(token, "access")


def decode_refresh_token(token: str) -> Optional[TokenData]:
    return _decode(token, "refresh")


def get_user(db: Session, username: str) -> Optional[models.BatAccount]:
    return db.query(models.BatAccount).filter(models.BatAccount.username == username).first()


def get_user_for_token(db: Session, token_data: TokenData) -> Optional[models.BatAccount]:
    if token_data.user_id is not None:
        return db.query(models.BatAccount).filter(models.BatAccount.id == token_data.user_id).first()
    return get_user(db, token_data.username)


# Verified against when the username is unknown, so a login attempt takes
# the same bcrypt time whether or not the account exists.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt()).decode("utf-8")


def authenticate_user(db: Session, username: str, password: str) -> Optional[models.BatAccount]:
    user = get_user(db, username)
    if not user:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.BatAccount:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = decode_token(token)
    if token_data is None:
        raise credentials_exception
    user = get_user_for_token(db, token_data)
    if user is None:
        raise credentials_exception
    return user


def get_current_active_user(
    current_user: models.BatAccount = Depends(get_current_user),
) -> models.BatAccount:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return current_user