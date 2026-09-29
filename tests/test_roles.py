"""
Role enforcement tests.

For every protected endpoint, verify:
  - The correct role(s) → 200
  - A forbidden role    → 403
  - No token            → 401

Role matrix (from requirements):
  doctor     : POST /doctor/visit|approve|reject
  pharmacist : POST /pharmacy/dispense
  owner      : GET /admin/audit (read-only dashboards)
  all authed : GET /pharmacy/pending, GET /inventory, GET /patients
"""
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_pending_rx(client, doctor_headers: dict, patient_id: str) -> str:
    """Create a visit and approve it; return the pending prescription_id."""
    visit = client.post("/doctor/visit", json={
        "patient_id": patient_id,
        "symptoms": "fever",
        "use_memory": False,
    }, headers=doctor_headers)
    assert visit.status_code == 200
    rx_id = visit.json()["prescription"]["prescription_id"]
    client.post("/doctor/approve",
                json={"prescription_id": rx_id},
                headers=doctor_headers)
    return rx_id


# ── /doctor/visit ─────────────────────────────────────────────────────────────

def test_doctor_can_create_visit(client, doctor_headers):
    resp = client.post("/doctor/visit", json={
        "patient_id": "role_test_p1",
        "symptoms": "headache",
        "use_memory": False,
    }, headers=doctor_headers)
    assert resp.status_code == 200


def test_pharmacist_cannot_create_visit(client, pharmacist_headers):
    resp = client.post("/doctor/visit", json={
        "patient_id": "role_test_p2",
        "symptoms": "headache",
        "use_memory": False,
    }, headers=pharmacist_headers)
    assert resp.status_code == 403


def test_owner_cannot_create_visit(client, owner_headers):
    resp = client.post("/doctor/visit", json={
        "patient_id": "role_test_p3",
        "symptoms": "headache",
        "use_memory": False,
    }, headers=owner_headers)
    assert resp.status_code == 403


def test_unauthenticated_cannot_create_visit(client):
    resp = client.post("/doctor/visit", json={
        "patient_id": "role_test_unauth",
        "symptoms": "headache",
        "use_memory": False,
    })
    assert resp.status_code == 401


# ── /doctor/approve ───────────────────────────────────────────────────────────

def test_pharmacist_cannot_approve(client, doctor_headers, pharmacist_headers):
    visit = client.post("/doctor/visit", json={
        "patient_id": "role_approve_p",
        "symptoms": "cough",
        "use_memory": False,
    }, headers=doctor_headers)
    rx_id = visit.json()["prescription"]["prescription_id"]

    resp = client.post("/doctor/approve",
                       json={"prescription_id": rx_id},
                       headers=pharmacist_headers)
    assert resp.status_code == 403


def test_owner_cannot_approve(client, doctor_headers, owner_headers):
    visit = client.post("/doctor/visit", json={
        "patient_id": "role_approve_o",
        "symptoms": "cough",
        "use_memory": False,
    }, headers=doctor_headers)
    rx_id = visit.json()["prescription"]["prescription_id"]

    resp = client.post("/doctor/approve",
                       json={"prescription_id": rx_id},
                       headers=owner_headers)
    assert resp.status_code == 403


# ── /pharmacy/dispense ────────────────────────────────────────────────────────

def test_pharmacist_can_dispense(client, doctor_headers, pharmacist_headers):
    rx_id = _create_pending_rx(client, doctor_headers, "role_disp_ph")
    resp = client.post("/pharmacy/dispense",
                       json={"prescription_id": rx_id},
                       headers=pharmacist_headers)
    assert resp.status_code == 200


def test_doctor_cannot_dispense(client, doctor_headers):
    rx_id = _create_pending_rx(client, doctor_headers, "role_disp_doc")
    resp = client.post("/pharmacy/dispense",
                       json={"prescription_id": rx_id},
                       headers=doctor_headers)
    assert resp.status_code == 403


def test_owner_cannot_dispense(client, doctor_headers, owner_headers):
    rx_id = _create_pending_rx(client, doctor_headers, "role_disp_own")
    resp = client.post("/pharmacy/dispense",
                       json={"prescription_id": rx_id},
                       headers=owner_headers)
    assert resp.status_code == 403


def test_unauthenticated_cannot_dispense(client):
    resp = client.post("/pharmacy/dispense", json={"prescription_id": "rx_any"})
    assert resp.status_code == 401


# ── /admin/audit ─────────────────────────────────────────────────────────────

def test_owner_can_view_audit(client, owner_headers):
    resp = client.get("/admin/audit", headers=owner_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)


def test_audit_contains_login_events(client, owner_headers):
    """Logins from conftest fixtures must have been recorded."""
    data = client.get("/admin/audit", headers=owner_headers).json()
    actions = [item["action"] for item in data["items"]]
    assert "login" in actions


def test_audit_pagination(client, owner_headers):
    full   = client.get("/admin/audit?page=1&page_size=5", headers=owner_headers).json()
    assert len(full["items"]) <= 5
    assert full["page"] == 1
    assert full["page_size"] == 5


def test_doctor_cannot_view_audit(client, doctor_headers):
    resp = client.get("/admin/audit", headers=doctor_headers)
    assert resp.status_code == 403


def test_pharmacist_cannot_view_audit(client, pharmacist_headers):
    resp = client.get("/admin/audit", headers=pharmacist_headers)
    assert resp.status_code == 403


def test_unauthenticated_cannot_view_audit(client):
    resp = client.get("/admin/audit")
    assert resp.status_code == 401


# ── Read-only routes accessible to all authenticated roles ────────────────────

def test_all_roles_can_view_inventory(client, doctor_headers, pharmacist_headers, owner_headers):
    for headers in (doctor_headers, pharmacist_headers, owner_headers):
        assert client.get("/inventory", headers=headers).status_code == 200


def test_all_roles_can_view_pending(client, doctor_headers, pharmacist_headers, owner_headers):
    for headers in (doctor_headers, pharmacist_headers, owner_headers):
        assert client.get("/pharmacy/pending", headers=headers).status_code == 200


def test_all_roles_can_view_patients(client, doctor_headers, pharmacist_headers, owner_headers):
    for headers in (doctor_headers, pharmacist_headers, owner_headers):
        assert client.get("/patients", headers=headers).status_code == 200


# ── Error response format — no stack traces ───────────────────────────────────

def test_403_response_has_no_stack_trace(client, pharmacist_headers):
    resp = client.post("/doctor/visit", json={
        "patient_id": "x", "symptoms": "y", "use_memory": False,
    }, headers=pharmacist_headers)
    assert resp.status_code == 403
    body = resp.text
    assert "Traceback" not in body
    assert "File " not in body


def test_401_response_has_no_stack_trace(client):
    resp = client.post("/doctor/visit", json={
        "patient_id": "x", "symptoms": "y", "use_memory": False,
    })
    assert resp.status_code == 401
    assert "Traceback" not in resp.text
