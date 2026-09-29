"""
pytest configuration and shared fixtures.

Sets DEMO_MODE=true and uses a temp SQLite database so tests run without
any real API keys and without touching clinic.db.

These env vars MUST be set before any app module is imported — conftest.py
is always executed first by pytest.
"""
import atexit
import os
import tempfile

# ── Force demo mode so Hindsight / Groq are never called ─────────────────────
os.environ["DEMO_MODE"] = "true"
os.environ["HINDSIGHT_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""

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
    The app lifespan (init_db + seed) runs once on first use.
    """
    from app.main import app

    with TestClient(app) as c:
        yield c
