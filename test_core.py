"""
Core integration tests — hackathon verification.

Tests:
1. Allergy rule catches amoxicillin for penicillin-allergic patient
2. Dispensing stock decrement works
3. Failed LLM returns fallback, not 500
4. Visit → approve → pending → dispense full flow
5. Patient summary returns safe fallback in demo mode
"""
import os
# Force demo mode before any imports
os.environ["DEMO_MODE"] = "true"
os.environ["HINDSIGHT_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["RATELIMIT_ENABLED"] = "false"

import tempfile
_fd, _db = tempfile.mkstemp(suffix=".db", prefix="clinic_core_test_")
os.close(_fd)
os.environ["DB_PATH"] = _db

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.safety import check_prescription, has_blocking_findings


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def doctor_token(client):
    resp = client.post("/auth/login", json={"username": "doctor_demo", "password": "demo1234"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def pharmacist_token(client):
    resp = client.post("/auth/login", json={"username": "pharmacist_demo", "password": "demo1234"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Test 1: Allergy rule catches amoxicillin for penicillin-allergic patient ──

def test_allergy_rule_blocks_amoxicillin_for_penicillin_allergy():
    """Deterministic safety checker catches amoxicillin when patient has penicillin allergy."""
    findings = check_prescription(
        patient_allergies=["penicillin"],
        current_meds=[],
        proposed_items=["Amoxicillin 500mg"],
    )
    assert len(findings) > 0, "Should produce at least one finding"
    allergy_findings = [f for f in findings if f.type == "allergy"]
    assert len(allergy_findings) > 0, "Should have an allergy finding"
    assert allergy_findings[0].severity == "contraindicated"
    assert has_blocking_findings(findings), "Allergy finding should be blocking"


# ── Test 2: Full visit → approve → pending → dispense flow ───────────────────

def test_full_visit_approve_dispense_flow(client, doctor_token, pharmacist_token):
    """End-to-end: visit creates draft, approve moves to pending, dispense decrements stock."""
    # Create visit
    resp = client.post(
        "/doctor/visit",
        json={"patient_id": "test_p1", "symptoms": "mild headache", "use_memory": True},
        headers=auth(doctor_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    rx_id = data["prescription"]["prescription_id"]

    # Draft should NOT be in pending
    resp = client.get("/pharmacy/pending", headers=auth(pharmacist_token))
    pending_ids = [p["prescription_id"] for p in resp.json()["pending"]]
    assert rx_id not in pending_ids, "Draft must not appear in pharmacy pending"

    # Approve
    resp = client.post(
        "/doctor/approve",
        json={"prescription_id": rx_id},
        headers=auth(doctor_token),
    )
    assert resp.status_code == 200

    # Now should be in pending
    resp = client.get("/pharmacy/pending", headers=auth(pharmacist_token))
    pending_ids = [p["prescription_id"] for p in resp.json()["pending"]]
    assert rx_id in pending_ids, "Approved prescription must appear in pharmacy pending"

    # Get initial stock for the medicine
    resp = client.get("/inventory", headers=auth(pharmacist_token))
    inv = {m["medicine_name"]: m["quantity"] for m in resp.json()["inventory"]}
    medicine = data["prescription"]["medicine_name"]
    initial_stock = inv.get(medicine, 0)

    # Dispense
    resp = client.post(
        "/pharmacy/dispense",
        json={"prescription_id": rx_id},
        headers=auth(pharmacist_token),
    )
    assert resp.status_code == 200

    # Stock should have decremented (if it was in stock)
    if initial_stock > 0:
        resp = client.get("/inventory", headers=auth(pharmacist_token))
        inv_after = {m["medicine_name"]: m["quantity"] for m in resp.json()["inventory"]}
        assert inv_after.get(medicine, 0) == initial_stock - 1, "Stock should decrement by 1"


# ── Test 3: Dispensing stock decrement is correct ────────────────────────────

def test_stock_decrement_on_dispense(client, doctor_token, pharmacist_token):
    """Verify that dispensing reduces stock by exactly 1."""
    # Create and approve a prescription
    resp = client.post(
        "/doctor/visit",
        json={"patient_id": "test_stock", "symptoms": "fever", "use_memory": False},
        headers=auth(doctor_token),
    )
    rx_id = resp.json()["prescription"]["prescription_id"]
    medicine = resp.json()["prescription"]["medicine_name"]

    client.post(
        "/doctor/approve",
        json={"prescription_id": rx_id},
        headers=auth(doctor_token),
    )

    # Check stock before
    resp = client.get("/inventory", headers=auth(pharmacist_token))
    before = {m["medicine_name"]: m["quantity"] for m in resp.json()["inventory"]}
    stock_before = before.get(medicine, 0)

    # Dispense
    client.post(
        "/pharmacy/dispense",
        json={"prescription_id": rx_id},
        headers=auth(pharmacist_token),
    )

    # Check stock after
    resp = client.get("/inventory", headers=auth(pharmacist_token))
    after = {m["medicine_name"]: m["quantity"] for m in resp.json()["inventory"]}
    stock_after = after.get(medicine, 0)

    if stock_before > 0:
        assert stock_after == stock_before - 1, f"Expected {stock_before - 1}, got {stock_after}"


# ── Test 4: LLM fallback returns valid response, not 500 ────────────────────

def test_llm_fallback_no_500(client, doctor_token):
    """In DEMO_MODE (no Groq key), visit should succeed with fallback rule engine, never 500."""
    resp = client.post(
        "/doctor/visit",
        json={"patient_id": "test_fallback", "symptoms": "cough and sore throat", "use_memory": True},
        headers=auth(doctor_token),
    )
    assert resp.status_code == 200, f"Should not return 500; got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "prescription" in data
    assert data["prescription"]["medicine_name"], "Fallback should still produce a medicine name"


# ── Test 5: Patient summary returns fallback in demo mode ────────────────────

def test_patient_summary_demo_fallback(client, doctor_token):
    """In DEMO_MODE, /patient/{id}/summary should return a safe message, not crash."""
    resp = client.get("/patient/test_p1/summary", headers=auth(doctor_token))
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "patient_id" in data
