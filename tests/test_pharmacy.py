"""Tests for /pharmacy/* and /inventory endpoints."""


def _create_approved_rx(client, patient_id: str, symptoms: str) -> str:
    """Helper: create a visit and approve it; return the prescription_id."""
    visit = client.post("/doctor/visit", json={
        "patient_id": patient_id,
        "symptoms": symptoms,
        "use_memory": False,
    })
    rx_id = visit.json()["prescription"]["prescription_id"]
    client.post("/doctor/approve", json={"prescription_id": rx_id})
    return rx_id


def test_pending_returns_list(client):
    resp = client.get("/pharmacy/pending")
    assert resp.status_code == 200
    assert "pending" in resp.json()
    assert isinstance(resp.json()["pending"], list)


def test_dispense_decrements_stock(client):
    rx_id = _create_approved_rx(client, "test_dispense_stock", "fever")

    # Record stock before
    inv_before = {
        m["medicine_name"]: m["quantity"]
        for m in client.get("/inventory").json()["inventory"]
    }

    resp = client.post("/pharmacy/dispense", json={"prescription_id": rx_id})
    assert resp.status_code == 200
    data = resp.json()
    dispensed = data["dispensed_medicine"]

    inv_after = {
        m["medicine_name"]: m["quantity"]
        for m in client.get("/inventory").json()["inventory"]
    }

    assert inv_after[dispensed] == inv_before[dispensed] - 1


def test_dispense_removes_from_pending(client):
    rx_id = _create_approved_rx(client, "test_dispense_pending", "headache")
    client.post("/pharmacy/dispense", json={"prescription_id": rx_id})

    pending = client.get("/pharmacy/pending").json()["pending"]
    assert not any(p["prescription_id"] == rx_id for p in pending)


def test_dispense_nonexistent_returns_404(client):
    resp = client.post("/pharmacy/dispense", json={"prescription_id": "rx_no_such"})
    assert resp.status_code == 404


def test_dispense_response_schema(client):
    rx_id = _create_approved_rx(client, "test_dispense_schema", "body ache")
    data = client.post("/pharmacy/dispense", json={"prescription_id": rx_id}).json()
    for field in ("prescription_id", "dispensed_medicine", "original_medicine", "dosage"):
        assert field in data, f"Missing field: {field}"


def test_inventory_has_100_plus_medicines(client):
    resp = client.get("/inventory")
    assert resp.status_code == 200
    inv = resp.json()["inventory"]
    assert len(inv) >= 90, f"Expected 90+ medicines, got {len(inv)}"


def test_inventory_metformin_in_stock(client):
    inv = {m["medicine_name"]: m for m in client.get("/inventory").json()["inventory"]}
    assert "Metformin 500mg" in inv
    assert inv["Metformin 500mg"]["quantity"] > 0


def test_inventory_amoxicillin_500_out_of_stock(client):
    """Amoxicillin 500mg is seeded at qty=0 to trigger the substitution demo."""
    inv = {m["medicine_name"]: m for m in client.get("/inventory").json()["inventory"]}
    assert "Amoxicillin 500mg" in inv
    assert inv["Amoxicillin 500mg"]["quantity"] == 0
