"""
Authentication service.

Responsibilities:
  - Password hashing/verification (bcrypt via passlib)
  - JWT creation and decoding (python-jose)
  - FastAPI dependencies: get_current_user, require_role

Design principles kept here:
  - Tokens contain only username + role (never PII).
  - Generic error messages on auth failure (401 / 403 only).
  - require_role returns a callble so FastAPI Depends picks it up cleanly.
"""
import datetime
import logging
from typing import Callable

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

log = logging.getLogger("clinic.auth")

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
_ALGORITHM = "HS256"


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(username: str, role: str) -> str:
    """Create a signed JWT valid for JWT_EXPIRE_HOURS."""
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        hours=settings.JWT_EXPIRE_HOURS
    )
    payload = {"sub": username, "role": role, "exp": expires}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT. Raises jose.JWTError on any failure."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[_ALGORITHM])


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def get_current_user(token: str = Depends(_oauth2_scheme)) -> dict:
    """
    Extract and validate the Bearer JWT from the Authorization header.
    Returns {"username": ..., "role": ...}.
    Raises 401 on missing / invalid / expired token.
    """
    try:
        payload = decode_access_token(token)
        username: str | None = payload.get("sub")
        role: str | None = payload.get("role")
        if not username or not role:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "role": role}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_role(*roles: str) -> Callable:
    """
    Return a FastAPI dependency that checks the caller's role.

    Usage:
        @router.post("/some-route")
        async def handler(user: dict = Depends(require_role("doctor"))):
            ...

    Raises:
        401  — no / invalid token
        403  — valid token but wrong role
    """
    async def _checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions for this action",
            )
        return user

    return _checker
