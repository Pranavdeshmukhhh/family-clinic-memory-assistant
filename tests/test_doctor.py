"""Tests for /doctor/* endpoints — authenticated as doctor_demo."""


def test_visit_returns_draft(client, doctor_headers):
    resp = client.post("/doctor/visit", json={
        "patient_id": "test_visit_001",
        "symptoms": "headache and mild fever",
        "use_memory": False,
    }, headers=doctor_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["prescription"]["status"] == "draft"
    assert data["prescription"]["patient_id"] == "test_visit_001"
    assert "ai_diagnosis" in data
    assert "warning" in data
    assert "memory_used" in data
    assert "is_new_patient" in data


def test_visit_unauthenticated_returns_401(client):
    resp = client.post("/doctor/visit", json={
        "patient_id": "test_unauth",
        "symptoms": "headache",
        "use_memory": False,
    })
    assert resp.status_code == 401


def test_visit_draft_not_visible_in_pharmacy_pending(client, doctor_headers, pharmacist_headers):
    resp = client.post("/doctor/visit", json={
        "patient_id": "test_pending_isolation",
        "symptoms": "sore throat",
        "use_memory": False,
    }, headers=doctor_headers)
    rx_id = resp.json()["prescription"]["prescription_id"]

    pending = client.get("/pharmacy/pending", headers=pharmacist_headers).json()["pending"]
    assert rx_id not in [p["prescription_id"] for p in pending]


def test_approve_moves_to_pending(client, doctor_headers, pharmacist_headers):
    visit = client.post("/doctor/visit", json={
        "patient_id": "test_approve_001",
        "symptoms": "blood sugar high",
        "use_memory": False,
    }, headers=doctor_headers)
    rx_id = visit.json()["prescription"]["prescription_id"]

    approve = client.post("/doctor/approve",
                          json={"prescription_id": rx_id},
                          headers=doctor_headers)
    assert approve.status_code == 200
    assert approve.json()["status"] == "pending"

    pending = client.get("/pharmacy/pending", headers=pharmacist_headers).json()["pending"]
    assert any(p["prescription_id"] == rx_id for p in pending)


def test_approve_doctor_can_edit_medicine(client, doctor_headers):
    visit = client.post("/doctor/visit", json={
        "patient_id": "test_edit_approve",
        "symptoms": "fever",
        "use_memory": False,
    }, headers=doctor_headers)
    rx_id = visit.json()["prescription"]["prescription_id"]

    approve = client.post("/doctor/approve", json={
        "prescription_id": rx_id,
        "medicine_name": "Paracetamol 650mg",
        "dosage": "650mg three times daily",
    }, headers=doctor_headers)
    assert approve.status_code == 200
    assert approve.json()["medicine_name"] == "Paracetamol 650mg"
    assert approve.json()["dosage"] == "650mg three times daily"


def test_approve_nonexistent_returns_404(client, doctor_headers):
    resp = client.post("/doctor/approve",
                       json={"prescription_id": "rx_ghost_000"},
                       headers=doctor_headers)
    assert resp.status_code == 404


def test_approve_twice_returns_400(client, doctor_headers):
    visit = client.post("/doctor/visit", json={
        "patient_id": "test_double_approve",
        "symptoms": "cough",
        "use_memory": False,
    }, headers=doctor_headers)
    rx_id = visit.json()["prescription"]["prescription_id"]
    client.post("/doctor/approve", json={"prescription_id": rx_id}, headers=doctor_headers)
    resp = client.post("/doctor/approve", json={"prescription_id": rx_id}, headers=doctor_headers)
    assert resp.status_code == 400


def test_reject_sets_status(client, doctor_headers):
    visit = client.post("/doctor/visit", json={
        "patient_id": "test_reject_001",
        "symptoms": "dizziness",
        "use_memory": False,
    }, headers=doctor_headers)
    rx_id = visit.json()["prescription"]["prescription_id"]

    reject = client.post("/doctor/reject",
                         json={"prescription_id": rx_id},
                         headers=doctor_headers)
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"


def test_reject_nonexistent_returns_404(client, doctor_headers):
    resp = client.post("/doctor/reject",
                       json={"prescription_id": "rx_ghost_999"},
                       headers=doctor_headers)
    assert resp.status_code == 404


def test_rejected_not_in_pharmacy_pending(client, doctor_headers, pharmacist_headers):
    visit = client.post("/doctor/visit", json={
        "patient_id": "test_reject_isolation",
        "symptoms": "headache",
        "use_memory": False,
    }, headers=doctor_headers)
    rx_id = visit.json()["prescription"]["prescription_id"]
    client.post("/doctor/reject", json={"prescription_id": rx_id}, headers=doctor_headers)

    pending = client.get("/pharmacy/pending", headers=pharmacist_headers).json()["pending"]
    assert not any(p["prescription_id"] == rx_id for p in pending)
