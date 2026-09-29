"""Tests for /doctor/* endpoints — run entirely in DEMO_MODE (no API keys)."""
import pytest


def test_visit_returns_draft(client):
    resp = client.post("/doctor/visit", json={
        "patient_id": "test_visit_001",
        "symptoms": "headache and mild fever",
        "use_memory": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["prescription"]["status"] == "draft"
    assert data["prescription"]["patient_id"] == "test_visit_001"
    assert "ai_diagnosis" in data
    assert "warning" in data
    assert "memory_used" in data
    assert "is_new_patient" in data


def test_visit_draft_not_visible_in_pharmacy_pending(client):
    resp = client.post("/doctor/visit", json={
        "patient_id": "test_pending_isolation",
        "symptoms": "sore throat",
        "use_memory": False,
    })
    rx_id = resp.json()["prescription"]["prescription_id"]

    pending = client.get("/pharmacy/pending").json()["pending"]
    rx_ids = [p["prescription_id"] for p in pending]
    assert rx_id not in rx_ids, "Draft prescription must not appear in pharmacy pending"


def test_approve_moves_to_pending(client):
    visit = client.post("/doctor/visit", json={
        "patient_id": "test_approve_001",
        "symptoms": "blood sugar high",
        "use_memory": False,
    })
    rx_id = visit.json()["prescription"]["prescription_id"]

    approve = client.post("/doctor/approve", json={"prescription_id": rx_id})
    assert approve.status_code == 200
    assert approve.json()["status"] == "pending"

    # Must now appear in pharmacy pending
    pending = client.get("/pharmacy/pending").json()["pending"]
    assert any(p["prescription_id"] == rx_id for p in pending)


def test_approve_doctor_can_edit_medicine(client):
    visit = client.post("/doctor/visit", json={
        "patient_id": "test_edit_approve",
        "symptoms": "fever",
        "use_memory": False,
    })
    rx_id = visit.json()["prescription"]["prescription_id"]

    approve = client.post("/doctor/approve", json={
        "prescription_id": rx_id,
        "medicine_name": "Paracetamol 650mg",
        "dosage": "650mg three times daily",
    })
    assert approve.status_code == 200
    assert approve.json()["medicine_name"] == "Paracetamol 650mg"
    assert approve.json()["dosage"] == "650mg three times daily"


def test_approve_nonexistent_returns_404(client):
    resp = client.post("/doctor/approve", json={"prescription_id": "rx_ghost_000"})
    assert resp.status_code == 404


def test_approve_twice_returns_400(client):
    visit = client.post("/doctor/visit", json={
        "patient_id": "test_double_approve",
        "symptoms": "cough",
        "use_memory": False,
    })
    rx_id = visit.json()["prescription"]["prescription_id"]
    client.post("/doctor/approve", json={"prescription_id": rx_id})
    resp = client.post("/doctor/approve", json={"prescription_id": rx_id})
    assert resp.status_code == 400


def test_reject_sets_status(client):
    visit = client.post("/doctor/visit", json={
        "patient_id": "test_reject_001",
        "symptoms": "dizziness",
        "use_memory": False,
    })
    rx_id = visit.json()["prescription"]["prescription_id"]

    reject = client.post("/doctor/reject", json={"prescription_id": rx_id})
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"


def test_reject_nonexistent_returns_404(client):
    resp = client.post("/doctor/reject", json={"prescription_id": "rx_ghost_999"})
    assert resp.status_code == 404


def test_rejected_not_in_pharmacy_pending(client):
    visit = client.post("/doctor/visit", json={
        "patient_id": "test_reject_isolation",
        "symptoms": "headache",
        "use_memory": False,
    })
    rx_id = visit.json()["prescription"]["prescription_id"]
    client.post("/doctor/reject", json={"prescription_id": rx_id})

    pending = client.get("/pharmacy/pending").json()["pending"]
    assert not any(p["prescription_id"] == rx_id for p in pending)
