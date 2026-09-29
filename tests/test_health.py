"""Tests for GET /health — public endpoint, no auth required."""


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_schema(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"
    assert isinstance(data["demo_mode"], bool)
    assert "integrations" in data
    for key in ("hindsight", "groq", "telegram"):
        assert key in data["integrations"]
        assert isinstance(data["integrations"][key], bool)


def test_health_demo_mode_integrations(client):
    """In DEMO_MODE with no keys, all integrations must report False."""
    data = client.get("/health").json()
    assert data["demo_mode"] is True
    assert data["integrations"]["hindsight"] is False
    assert data["integrations"]["telegram"] is False


def test_health_no_secrets_in_response(client):
    raw = client.get("/health").text
    for bad in ("api_key", "token", "secret", "password"):
        assert bad not in raw.lower(), f"Sensitive field '{bad}' found in /health response"


def test_health_requires_no_auth(client):
    """Health must work without any Authorization header."""
    resp = client.get("/health")
    assert resp.status_code == 200
