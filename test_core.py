"""
End-to-End Verification Test for Family Clinic Memory Assistant
"""
import sys
import os
import json
from dotenv import load_dotenv

load_dotenv()

from fastapi.testclient import TestClient
from main import app, init_db, seed_patient_memory

import asyncio
print("Initializing DB and memory...")
init_db()
asyncio.run(seed_patient_memory())

client = TestClient(app)

print("\n--- 1. Testing GET /inventory ---")
res = client.get("/inventory")
assert res.status_code == 200, f"Inventory failed: {res.text}"
inv = res.json()["inventory"]
print(f"Inventory items ({len(inv)}): {[m['medicine_name'] for m in inv]}")

print("\n--- 2. Testing POST /doctor/visit for patient_001 (Existing Patient) ---")
res = client.post("/doctor/visit", json={
    "patient_id": "patient_001",
    "symptoms": "Feeling fatigued, fasting blood sugar is slightly high around 160 mg/dL",
    "notes": "Follow-up visit for diabetes review",
    "use_memory": True
})
assert res.status_code == 200, f"Doctor visit failed: {res.text}"
visit_data = res.json()
print("Diagnosis:", visit_data["ai_diagnosis"])
print("Prescription:", visit_data["prescription"])
print("Memory Used:", visit_data["memory_used"])
print("Is New Patient:", visit_data["is_new_patient"])
assert not visit_data["is_new_patient"], "Expected patient_001 to NOT be a new patient"
rx_id_1 = visit_data["prescription"]["prescription_id"]

import uuid
new_pid = f"patient_new_{uuid.uuid4().hex[:6]}"
print(f"\n--- 3. Testing POST /doctor/visit for {new_pid} (Brand New Patient) ---")
res = client.post("/doctor/visit", json={
    "patient_id": new_pid,
    "symptoms": "Mild headache and fever for 1 day",
    "notes": "First time clinic visit",
    "use_memory": True
})
assert res.status_code == 200, f"New patient visit failed: {res.text}"
new_patient_data = res.json()
print("Diagnosis:", new_patient_data["ai_diagnosis"])
print("Memory Used:", new_patient_data["memory_used"])
print("Is New Patient:", new_patient_data["is_new_patient"])
assert new_patient_data["is_new_patient"], f"Expected {new_pid} to be detected as a new patient"

print("\n--- 4. Testing GET /pharmacy/pending ---")
res = client.get("/pharmacy/pending")
assert res.status_code == 200, f"Pending failed: {res.text}"
pending_list = res.json()["pending"]
print(f"Pending prescriptions ({len(pending_list)}): {[p['prescription_id'] for p in pending_list]}")
assert any(p["prescription_id"] == rx_id_1 for p in pending_list), "rx_id_1 should be in pending queue"

print(f"\n--- 5. Testing POST /pharmacy/dispense for {rx_id_1} ---")
res = client.post("/pharmacy/dispense", json={"prescription_id": rx_id_1})
assert res.status_code == 200, f"Dispense failed: {res.text}"
dispense_data = res.json()
print("Dispensed Medicine:", dispense_data["dispensed_medicine"])
print("Stock Warning:", dispense_data.get("stock_warning"))
print("Patient Context from Hindsight:", dispense_data.get("patient_context")[:120] if dispense_data.get("patient_context") else "None")

print("\n--- 6. Testing GET /pharmacy/pending after dispense ---")
res = client.get("/pharmacy/pending")
pending_after = res.json()["pending"]
assert not any(p["prescription_id"] == rx_id_1 for p in pending_after), "rx_id_1 should now be fulfilled, not pending"
print(f"Remaining pending: {len(pending_after)}")

print("\n--- 7. Testing MODULE 3: GET /patient/patient_001/summary (Reflect) ---")
res = client.get("/patient/patient_001/summary")
assert res.status_code == 200, f"Summary failed: {res.text}"
summary_data = res.json()
print("Reflect Summary Preview:\n", summary_data["summary"][:300], "...")

print("\n[OK] ALL TESTS PASSED! CORE + MODULES OPERATIONAL!")
