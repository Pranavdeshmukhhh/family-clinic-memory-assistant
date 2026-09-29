"""
pytest configuration and shared fixtures.

Sets DEMO_MODE=true, disables rate limiting, and uses a temp SQLite
database so tests run without any real API keys and without touching
the development clinic.db.

These env vars MUST be set before any app module is imported — conftest.py
is always executed first by pytest.
"""
import atexit
import os
import tempfile

# ── Force demo mode — no Hindsight / Groq calls ───────────────────────────────
os.environ["DEMO_MODE"]          = "true"
os.environ["HINDSIGHT_API_KEY"]  = ""
os.environ["GROQ_API_KEY"]       = ""
os.environ["RATELIMIT_ENABLED"]  = "false"   # prevent spurious 429s in tests

# ── Isolated temp database for the test session ───────────────────────────────
_fd, _db_path = tempfile.mkstemp(suffix=".db", prefix="clinic_test_")
os.close(_fd)
os.environ["DB_PATH"] = _db_path
atexit.register(os.unlink, _db_path)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client() -> TestClient:
    """
    A single TestClient for the whole test session.
    The app lifespan (init_db + seed_demo_users) runs once on first use.
    """
    from app.main import app

    with TestClient(app) as c:
        yield c


# ── Auth fixtures — log in once per session and cache the header ──────────────

@pytest.fixture(scope="session")
def doctor_headers(client: TestClient) -> dict:
    resp = client.post(
        "/auth/login", json={"username": "doctor_demo", "password": "demo1234"}
    )
    assert resp.status_code == 200, f"Doctor login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="session")
def pharmacist_headers(client: TestClient) -> dict:
    resp = client.post(
        "/auth/login", json={"username": "pharmacist_demo", "password": "demo1234"}
    )
    assert resp.status_code == 200, f"Pharmacist login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="session")
def owner_headers(client: TestClient) -> dict:
    resp = client.post(
        "/auth/login", json={"username": "owner_demo", "password": "demo1234"}
    )
    assert resp.status_code == 200, f"Owner login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
