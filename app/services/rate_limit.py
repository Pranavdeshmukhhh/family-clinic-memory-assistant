"""
Rate limiting singleton.

Import `limiter` in app/main.py to attach it to app.state.
Use `rate_limit("N/period")` as a route decorator:

    @router.post("/login")
    @rate_limit("10/minute")
    async def login(request: Request, ...):
        ...

The decorator is a no-op when RATELIMIT_ENABLED=false (tests / DEMO_MODE).
The route MUST declare `request: Request` so slowapi can extract the client IP.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Single limiter instance — shared between all routers via import.
# Uses in-memory storage (sufficient for single-process deployments).
limiter: Limiter = Limiter(key_func=get_remote_address)


def rate_limit(limit_string: str):
    """
    Conditional rate-limit decorator.

    Evaluated at module-import time, so env vars set before the first
    import (e.g., in conftest.py) are correctly respected.
    """
    from app.config import settings  # late import to honour test env setup

    if settings.RATELIMIT_ENABLED:
        return limiter.limit(limit_string)
    return lambda f: f  # identity — no-op in demo / test mode
