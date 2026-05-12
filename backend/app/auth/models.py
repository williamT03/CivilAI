"""Token helpers and auth-domain constants."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta

import jwt
from fastapi import HTTPException, status

try:
    from backend.app.security import require_production_secret
except ImportError:  # pragma: no cover
    from app.security import require_production_secret

from .schemas import TokenPayload, UserResponse

JWT_SECRET_KEY = require_production_secret(
    "JWT_SECRET_KEY", os.getenv("JWT_SECRET_KEY")
) or secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
REFRESH_TOKEN_EXPIRE_DAYS = 30


def create_access_token(user: UserResponse) -> str:
    """Create a JWT access token."""

    now = datetime.utcnow()
    payload = {
        "sub": f"{user.id}:{user.username}",
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "type": "access",
        "is_admin": user.is_admin,
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user: UserResponse) -> str:
    """Create a JWT refresh token."""

    token = secrets.token_urlsafe(32)

    now = datetime.utcnow()
    payload = {
        "sub": f"{user.id}:{user.username}",
        "exp": int((now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).timestamp()),
        "type": "refresh",
    }

    token_with_payload = f"{token}.{jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)}"

    return token_with_payload


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token."""

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def extract_user_id(token_payload: TokenPayload) -> int:
    """Extract user ID from token payload."""

    sub = token_payload.sub
    return int(sub.split(":")[0])
