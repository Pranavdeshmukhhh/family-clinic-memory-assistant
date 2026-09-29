"""Tests for /pharmacy/* and /inventory endpoints."""


def _create_approved_rx(client, doctor_headers: dict, patient_id: str, symptoms: str) -> str:
    """Helper: create a visit and approve it; return the prescription_id."""
    visit = client.post("/doctor/visit", json={
        "patient_id": patient_id,
        "symptoms": symptoms,
        "use_memory": False,
    }, headers=doctor_headers)
    assert visit.status_code == 200, f"Visit failed: {visit.text}"
    rx_id = visit.json()["prescription"]["prescription_id"]
    approve = client.post("/doctor/approve",
                          json={"prescription_id": rx_id},
                          headers=doctor_headers)
    assert approve.status_code == 200, f"Approve failed: {approve.text}"
    return rx_id


def test_pending_returns_list(client, pharmacist_headers):
    resp = client.get("/pharmacy/pending", headers=pharmacist_headers)
    assert resp.status_code == 200
    assert "pending" in resp.json()
    assert isinstance(resp.json()["pending"], list)


def test_pending_unauthenticated_returns_401(client):
    resp = client.get("/pharmacy/pending")
    assert resp.status_code == 401


def test_dispense_decrements_stock(client, doctor_headers, pharmacist_headers):
    rx_id = _create_approved_rx(client, doctor_headers, "test_dispense_stock", "fever")

    inv_before = {
        m["medicine_name"]: m["quantity"]
        for m in client.get("/inventory", headers=pharmacist_headers).json()["inventory"]
    }

    resp = client.post("/pharmacy/dispense",
                       json={"prescription_id": rx_id},
                       headers=pharmacist_headers)
    assert resp.status_code == 200
    dispensed = resp.json()["dispensed_medicine"]

    inv_after = {
        m["medicine_name"]: m["quantity"]
        for m in client.get("/inventory", headers=pharmacist_headers).json()["inventory"]
    }

    assert inv_after[dispensed] == inv_before[dispensed] - 1


def test_dispense_removes_from_pending(client, doctor_headers, pharmacist_headers):
    rx_id = _create_approved_rx(client, doctor_headers, "test_dispense_pending", "headache")
    client.post("/pharmacy/dispense",
                json={"prescription_id": rx_id},
                headers=pharmacist_headers)

    pending = client.get("/pharmacy/pending", headers=pharmacist_headers).json()["pending"]
    assert not any(p["prescription_id"] == rx_id for p in pending)


def test_dispense_nonexistent_returns_404(client, pharmacist_headers):
    resp = client.post("/pharmacy/dispense",
                       json={"prescription_id": "rx_no_such"},
                       headers=pharmacist_headers)
    assert resp.status_code == 404


def test_dispense_unauthenticated_returns_401(client):
    resp = client.post("/pharmacy/dispense", json={"prescription_id": "rx_any"})
    assert resp.status_code == 401


def test_dispense_response_schema(client, doctor_headers, pharmacist_headers):
    rx_id = _create_approved_rx(client, doctor_headers, "test_dispense_schema", "body ache")
    data = client.post("/pharmacy/dispense",
                       json={"prescription_id": rx_id},
                       headers=pharmacist_headers).json()
    for field in ("prescription_id", "dispensed_medicine", "original_medicine", "dosage"):
        assert field in data, f"Missing field: {field}"


def test_inventory_has_90_plus_medicines(client, doctor_headers):
    resp = client.get("/inventory", headers=doctor_headers)
    assert resp.status_code == 200
    inv = resp.json()["inventory"]
    assert len(inv) >= 90, f"Expected 90+ medicines, got {len(inv)}"


def test_inventory_metformin_in_stock(client, pharmacist_headers):
    inv = {m["medicine_name"]: m
           for m in client.get("/inventory", headers=pharmacist_headers).json()["inventory"]}
    assert "Metformin 500mg" in inv
    assert inv["Metformin 500mg"]["quantity"] > 0


def test_inventory_amoxicillin_500_out_of_stock(client, pharmacist_headers):
    """Amoxicillin 500mg is seeded at qty=0 to trigger the substitution demo."""
    inv = {m["medicine_name"]: m
           for m in client.get("/inventory", headers=pharmacist_headers).json()["inventory"]}
    assert "Amoxicillin 500mg" in inv
    assert inv["Amoxicillin 500mg"]["quantity"] == 0


def test_inventory_unauthenticated_returns_401(client):
    resp = client.get("/inventory")
    assert resp.status_code == 401
