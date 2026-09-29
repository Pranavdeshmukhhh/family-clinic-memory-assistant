"""POST /auth/login — issue a signed JWT on valid credentials."""
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db import get_db
from app.services.audit import append_audit
from app.services.auth import create_access_token, verify_password
from app.services.rate_limit import rate_limit

log = logging.getLogger("clinic.auth_router")
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
@rate_limit("10/minute")
async def login(request: Request, body: LoginRequest):
    """
    Authenticate with username + password; return a Bearer JWT.

    Rate limit: 10 requests per minute per IP.
    Error messages are generic (401) to prevent username enumeration.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT username, password_hash, role FROM users WHERE username = ?",
            (body.username,),
        ).fetchone()

    # Use a pre-hashed sentinel so bcrypt is always called (timing-safe).
    # The sentinel is the hash of the literal string "sentinel" — bcrypt 5.x
    # rejects passwords longer than 72 bytes, so we must NOT use a long dummy.
    _DUMMY_HASH = "$2b$12$KIXtWm6PpqiTPe8EcOH2BudXdTCTDYWJXLJKfnJLpIgYLGWRjRDRm"

    candidate_hash = row["password_hash"] if row else _DUMMY_HASH

    if not row or not verify_password(body.password, candidate_hash):

        append_audit(
            actor=body.username,
            role="unknown",
            action="login_failed",
            entity="user",
            entity_id=body.username,
            details={"ip": request.client.host if request.client else "unknown"},
        )
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(username=row["username"], role=row["role"])

    append_audit(
        actor=row["username"],
        role=row["role"],
        action="login",
        entity="user",
        entity_id=row["username"],
        details={"ip": request.client.host if request.client else "unknown"},
    )
    log.info("🔐 LOGIN │ user=%s │ role=%s", row["username"], row["role"])
    return {"access_token": token, "token_type": "bearer"}
