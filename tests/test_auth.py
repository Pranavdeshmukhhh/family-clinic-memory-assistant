"""Tests for POST /auth/login."""


def test_login_doctor(client):
    resp = client.post("/auth/login",
                       json={"username": "doctor_demo", "password": "demo1234"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 20


def test_login_pharmacist(client):
    resp = client.post("/auth/login",
                       json={"username": "pharmacist_demo", "password": "demo1234"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_owner(client):
    resp = client.post("/auth/login",
                       json={"username": "owner_demo", "password": "demo1234"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client):
    resp = client.post("/auth/login",
                       json={"username": "doctor_demo", "password": "wrongpassword"})
    assert resp.status_code == 401
    # Generic message — no hint about whether username or password was wrong
    assert "detail" in resp.json()


def test_login_unknown_user(client):
    resp = client.post("/auth/login",
                       json={"username": "nobody_at_all", "password": "demo1234"})
    assert resp.status_code == 401


def test_login_response_contains_no_sensitive_fields(client):
    data = client.post("/auth/login",
                       json={"username": "doctor_demo", "password": "demo1234"}).json()
    for bad in ("password", "password_hash", "secret", "key"):
        assert bad not in data, f"Sensitive field '{bad}' should not be in login response"


def test_login_token_is_usable(client):
    """Token from /auth/login must be accepted by a protected endpoint."""
    login = client.post("/auth/login",
                        json={"username": "doctor_demo", "password": "demo1234"})
    token = login.json()["access_token"]

    resp = client.post("/doctor/visit", json={
        "patient_id": "test_token_usable",
        "symptoms": "cough",
        "use_memory": False,
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_bad_token_returns_401(client):
    resp = client.post("/doctor/visit", json={
        "patient_id": "x",
        "symptoms": "y",
        "use_memory": False,
    }, headers={"Authorization": "Bearer this.is.not.a.valid.jwt"})
    assert resp.status_code == 401


def test_missing_auth_header_returns_401(client):
    resp = client.post("/doctor/visit", json={
        "patient_id": "x",
        "symptoms": "y",
        "use_memory": False,
    })
    assert resp.status_code == 401
