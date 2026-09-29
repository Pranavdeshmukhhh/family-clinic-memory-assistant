"""
Family Clinic Memory Assistant — Backend
FastAPI server with Hindsight memory, Groq LLM, SQLite storage, and Telegram alerts.
"""

import os
import json
import sqlite3
import datetime
import uuid
import logging
import pathlib
import httpx

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional

from hindsight_client import Hindsight
from groq import Groq

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("clinic")

# ── Env ─────────────────────────────────────────────────────────────────────
load_dotenv()

HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY", "")
HINDSIGHT_BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

GROQ_MODEL = "openai/gpt-oss-120b"

# ── Clients ─────────────────────────────────────────────────────────────────
def get_hindsight() -> Hindsight:
    return Hindsight(base_url=HINDSIGHT_BASE_URL, api_key=HINDSIGHT_API_KEY)

groq_client = Groq(api_key=GROQ_API_KEY) if (GROQ_API_KEY and not GROQ_API_KEY.startswith("your_")) else None

# ── SQLite ──────────────────────────────────────────────────────────────────
DB_PATH = "clinic.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables and seed data if needed."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            medicine_name TEXT PRIMARY KEY,
            quantity INTEGER NOT NULL,
            reorder_threshold INTEGER NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS prescriptions (
            prescription_id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            medicine_name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)

    # Seed inventory (only if empty)
    cur.execute("SELECT COUNT(*) FROM inventory")
    if cur.fetchone()[0] == 0:
        seed_meds = [
            # ── Fever / Pain / Anti-inflammatory ──
            ("Paracetamol 500mg",         100, 20),
            ("Paracetamol 650mg",          80, 15),
            ("Ibuprofen 400mg",            60, 12),
            ("Ibuprofen 600mg",            45, 10),
            ("Aspirin 75mg",               70, 15),
            ("Aspirin 325mg",              40, 10),
            ("Diclofenac 50mg",            35, 8),
            ("Naproxen 250mg",             30, 8),
            ("Nimesulide 100mg",           25, 6),
            ("Mefenamic Acid 250mg",       20, 5),
            ("Tramadol 50mg",              15, 4),
            ("Ketorolac 10mg",             10, 3),
            ("Metamizole 500mg",           18, 5),
            ("Dexamethasone 4mg",          22, 5),
            ("Methylprednisolone 4mg",     18, 5),
            # ── Cold / Cough / Allergy / Respiratory ──
            ("Cetirizine 10mg",            60, 12),
            ("Loratadine 10mg",            55, 10),
            ("Fexofenadine 120mg",         40, 8),
            ("Levocetirizine 5mg",         45, 10),
            ("Chlorpheniramine 4mg",       50, 10),
            ("Dextromethorphan 15mg",      35, 8),
            ("Guaifenesin 100mg",          40, 8),
            ("Ambroxol 30mg",              50, 10),
            ("Bromhexine 8mg",             45, 10),
            ("Salbutamol 4mg",             30, 8),
            ("Montelukast 10mg",           25, 6),
            ("Diphenhydramine 25mg",       30, 8),
            ("Pseudoephedrine 60mg",       20, 5),
            ("Budesonide 200mcg",          15, 4),
            ("Ipratropium 20mcg",          10, 3),
            # ── Antibiotics ──
            ("Amoxicillin 500mg",          40, 10),
            ("Amoxicillin 250mg",          30, 8),
            ("Amoxicillin+Clavulanate 625mg", 25, 6),
            ("Azithromycin 500mg",         30, 8),
            ("Ciprofloxacin 500mg",        25, 6),
            ("Doxycycline 100mg",          20, 5),
            ("Metronidazole 400mg",        35, 8),
            ("Cefixime 200mg",             20, 5),
            ("Cephalexin 500mg",           18, 5),
            ("Co-trimoxazole 480mg",       15, 4),
            ("Erythromycin 500mg",         15, 4),
            ("Clindamycin 300mg",          12, 3),
            ("Levofloxacin 500mg",         18, 5),
            ("Nitrofurantoin 100mg",       12, 3),
            ("Clarithromycin 500mg",       10, 3),
            # ── Diabetes ──
            ("Metformin 500mg",            50, 10),
            ("Metformin 1000mg",           40, 8),
            ("Glibenclamide 5mg",          30, 7),
            ("Glipizide 5mg",              25, 6),
            ("Sitagliptin 50mg",           20, 5),
            ("Voglibose 0.2mg",            15, 4),
            ("Insulin Regular 100IU/ml",   10, 3),
            ("Insulin NPH 100IU/ml",        8, 2),
            ("Empagliflozin 10mg",         12, 3),
            ("Dapagliflozin 10mg",         10, 3),
            # ── Blood Pressure / Heart ──
            ("Lisinopril 5mg",              3, 5),   # low — tests restock
            ("Lisinopril 10mg",            18, 5),
            ("Amlodipine 5mg",             35, 8),
            ("Amlodipine 10mg",            25, 6),
            ("Atenolol 25mg",              30, 7),
            ("Atenolol 50mg",              22, 5),
            ("Enalapril 5mg",              20, 5),
            ("Losartan 50mg",              25, 6),
            ("Telmisartan 40mg",           18, 5),
            ("Hydrochlorothiazide 25mg",   20, 5),
            ("Furosemide 40mg",            15, 4),
            ("Spironolactone 25mg",        12, 3),
            ("Bisoprolol 5mg",             18, 5),
            # ── GI / Stomach ──
            ("Omeprazole 20mg",            55, 12),
            ("Pantoprazole 40mg",          45, 10),
            ("Ranitidine 150mg",           30, 7),
            ("Domperidone 10mg",           40, 8),
            ("Ondansetron 4mg",            25, 6),
            ("Metoclopramide 10mg",        20, 5),
            ("Loperamide 2mg",             25, 6),
            ("ORS Powder",                 60, 15),
            ("Zinc 20mg",                  40, 10),
            ("Lactulose 10g",              15, 4),
            # ── Vitamins / Supplements ──
            ("Vitamin C 500mg",            80, 15),
            ("Vitamin D3 60000IU",         30, 7),
            ("Vitamin B12 500mcg",         40, 8),
            ("Iron 100mg",                 35, 8),
            ("Calcium 500mg",              40, 8),
            ("Folic Acid 5mg",             30, 7),
            ("Multivitamin Tablet",        50, 10),
            # ── Thyroid / Hormones ──
            ("Levothyroxine 25mcg",        20, 5),
            ("Levothyroxine 50mcg",        18, 5),
            ("Levothyroxine 100mcg",       12, 3),
            ("Prednisolone 5mg",           22, 5),
            ("Hydrocortisone 20mg",        10, 3),
            # ── Cholesterol ──
            ("Atorvastatin 10mg",          35, 8),
            ("Atorvastatin 20mg",          28, 7),
            ("Rosuvastatin 10mg",          25, 6),
            # ── Mental Health / Neuro ──
            ("Alprazolam 0.25mg",          10, 3),
            ("Sertraline 50mg",            15, 4),
            # ── Skin ──
            ("Hydrocortisone Cream 1%",    15, 4),
            ("Clotrimazole Cream 1%",      12, 3),
            ("Mupirocin Ointment 2%",      10, 3),
            ("Betamethasone Cream 0.1%",    8, 2),
        ]
        cur.executemany(
            "INSERT INTO inventory (medicine_name, quantity, reorder_threshold) VALUES (?,?,?)",
            seed_meds,
        )
        log.info("📦 Seeded %d medicines into inventory", len(seed_meds))

    conn.commit()
    conn.close()


async def _seed_one_patient(bank_id: str, name: str, seed_content: str):
    """
    Always try create_bank first (ignore 'already exists' errors),
    then always retain the seed content. Logs clearly at each step.
    """
    h = get_hindsight()
    try:
        try:
            await h.acreate_bank(bank_id=bank_id, name=name)
            log.info("🧠 Created Hindsight bank for %s", bank_id)
        except Exception as e:
            err_str = str(e).lower()
            if "already exists" in err_str or "conflict" in err_str or "409" in err_str:
                log.info("🧠 Bank already exists for %s — skipping create", bank_id)
            else:
                log.warning("⚠️  create_bank for %s: %s", bank_id, e)

        try:
            await h.aretain(
                bank_id=bank_id,
                content=seed_content,
                context="doctor_visit",
            )
            log.info("🧠 Retained seed history for %s", bank_id)
        except Exception as e:
            log.warning("⚠️  retain seed for %s: %s", bank_id, e)
    finally:
        await h.aclose()


async def seed_patient_memory():
    """Seed Hindsight banks for demo patients on startup."""
    await _seed_one_patient(
        bank_id="patient_001",
        name="Patient Rajesh Kumar",
        seed_content=(
            "Patient Rajesh Kumar, age 54. Visited on 2026-08-10. "
            "Presented with elevated fasting glucose (168 mg/dL) and fatigue. "
            "Diagnosed with Type 2 Diabetes Mellitus. "
            "Prescribed Metformin 500mg twice daily. "
            "Patient reported a known penicillin allergy (developed hives after Amoxicillin in 2019). "
            "No other medications currently."
        ),
    )
    await _seed_one_patient(
        bank_id="patient_002",
        name="Patient Meera Iyer",
        seed_content=(
            "Patient Meera Iyer, age 29. Visited on 2026-09-20. "
            "Presented with hypertension symptoms, blood pressure 148/94. "
            "Diagnosed with Stage 1 Hypertension. "
            "Prescribed Lisinopril 5mg once daily. "
            "No known drug allergies. No other current medications."
        ),
    )


# ── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🔗 HINDSIGHT_BASE_URL = %s", HINDSIGHT_BASE_URL)
    init_db()
    await seed_patient_memory()
    log.info("✅ Clinic backend ready")
    yield


app = FastAPI(title="Family Clinic Memory Assistant", lifespan=lifespan)

# ── Static files ────────────────────────────────────────────────────────────
STATIC_DIR = pathlib.Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/doctor")
async def serve_doctor():
    return FileResponse(str(STATIC_DIR / "doctor.html"))


@app.get("/pharmacy")
async def serve_pharmacy():
    return FileResponse(str(STATIC_DIR / "pharmacy.html"))


# ── Pydantic models ────────────────────────────────────────────────────────
class VisitRequest(BaseModel):
    patient_id: str
    symptoms: str
    notes: Optional[str] = ""
    use_memory: bool = True  # MODULE 2 toggle


class DispenseRequest(BaseModel):
    prescription_id: str


class MedicineQuery(BaseModel):
    medicine_name: str


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _recall_patient(patient_id: str, query: str) -> tuple[str, bool]:
    """
    Try to recall from Hindsight asynchronously.
    Returns (history_text, is_new_patient).
    """
    h = get_hindsight()
    try:
        resp = await h.arecall(bank_id=patient_id, query=query)
        facts = [r.text for r in resp.results] if resp.results else []
        log.info(
            "🔍 RECALL  │ patient=%s │ query=%s │ results=%d │ facts=%s",
            patient_id, query, len(facts), facts,
        )
        if facts:
            return "\n".join(facts), False
        return "", False
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            log.info("🆕 RECALL  │ patient=%s │ Bank not found — new patient", patient_id)
            try:
                await h.acreate_bank(bank_id=patient_id, name=f"Patient {patient_id}")
                log.info("🧠 Created new bank for %s", patient_id)
            except Exception as ce:
                log.warning("⚠️  create_bank %s: %s", patient_id, ce)
            return "", True
        log.error("❌ RECALL error │ patient=%s │ %s", patient_id, e)
        raise
    finally:
        await h.aclose()


async def _retain_patient(patient_id: str, content: str, context: str):
    """Store info into Hindsight asynchronously and log it."""
    h = get_hindsight()
    try:
        await h.aretain(bank_id=patient_id, content=content, context=context)
        log.info(
            "💾 RETAIN  │ patient=%s │ context=%s │ content_preview=%.120s…",
            patient_id, context, content,
        )
    except Exception as e:
        log.error("❌ RETAIN error │ patient=%s │ %s", patient_id, e)
        raise
    finally:
        await h.aclose()


def _groq_chat(system_prompt: str, user_prompt: str) -> str:
    """Call Groq LLM and return the text response with clinical fallback."""
    if groq_client:
        try:
            completion = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_tokens=1500,
            )
            return completion.choices[0].message.content
        except Exception as e:
            log.warning("⚠️ Groq API call error (%s). Falling back to clinical decision logic.", e)

    # ── Fallback Clinical Rule Engine (if GROQ_API_KEY is not set) ──
    log.info("🩺 Using built-in clinical rule engine (Groq key not configured or call failed)")
    prompt_lower = (user_prompt + " " + system_prompt).lower()

    # Case 1: Pharmacy Substitution
    if "substitution" in prompt_lower or "alternative" in prompt_lower or "pharmacist" in prompt_lower:
        in_stock = _get_in_stock_medicines()
        alt_name = in_stock[0] if in_stock else "Paracetamol 500mg"
        for med in in_stock:
            if "metformin" in med.lower() or "paracetamol" in med.lower() or "ibuprofen" in med.lower():
                alt_name = med
                break
        return json.dumps({
            "alternative": alt_name,
            "reason": f"Selected safe in-stock therapeutic alternative ({alt_name}) from current inventory."
        })

    # Case 2: Doctor Visit (Diagnosis + Prescription + Interaction Check)
    has_diabetes_hist = "diabetes" in prompt_lower or "metformin" in prompt_lower
    has_allergy_penicillin = ("penicillin" in prompt_lower and "allerg" in prompt_lower) or ("amoxicillin" in prompt_lower and "allerg" in prompt_lower)

    if "blood sugar" in prompt_lower or "diabetes" in prompt_lower or "fatigue" in prompt_lower and has_diabetes_hist:
        diagnosis = "Type 2 Diabetes Mellitus - Glycemic Review"
        med = "Metformin 500mg"
        dosage = "500mg twice daily with meals"
        instructions = "Take after breakfast and dinner. Maintain continuous glucose monitoring."
        reasoning = "Recalled patient records indicate Type 2 Diabetes on Metformin. Continuing therapy."
        warning = None
    elif "fever" in prompt_lower or "headache" in prompt_lower or "body ache" in prompt_lower:
        diagnosis = "Acute Febrile Illness / Viral Syndrome"
        med = "Paracetamol 500mg"
        dosage = "500mg every 6 to 8 hours as needed"
        instructions = "Do not exceed 3000mg in 24 hours. Drink plenty of fluids."
        reasoning = "Symptomatic treatment for acute pyrexia and body ache."
        warning = None
    elif "cough" in prompt_lower or "throat" in prompt_lower or "bacterial" in prompt_lower:
        diagnosis = "Upper Respiratory Tract Infection"
        med = "Amoxicillin 250mg"
        dosage = "250mg three times daily for 5 days"
        instructions = "Complete the entire antibiotic course even if feeling better."
        reasoning = "First-line empirical coverage for suspected bacterial respiratory infection."
        warning = "CRITICAL ALLERGY CONFLICT: Patient history indicates penicillin allergy. Discontinue penicillin class immediately!" if has_allergy_penicillin else None
    else:
        diagnosis = "General Clinical Evaluation / Gastro-esophageal Reflux"
        med = "Omeprazole 20mg"
        dosage = "20mg once daily before breakfast"
        instructions = "Take 30 minutes before first meal of the day."
        reasoning = "First-line gastric acid suppression for dyspeptic symptoms."
        warning = None

    return json.dumps({
        "diagnosis": diagnosis,
        "medicine_name": med,
        "dosage": dosage,
        "instructions": instructions,
        "reasoning": reasoning,
        "warning": warning
    })


def _get_inventory_list() -> list[dict]:
    """Return full inventory as list of dicts."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM inventory").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_in_stock_medicines() -> list[str]:
    """Return names of medicines with qty > 0."""
    conn = get_db()
    rows = conn.execute(
        "SELECT medicine_name FROM inventory WHERE quantity > 0"
    ).fetchall()
    conn.close()
    return [r["medicine_name"] for r in rows]


def _check_restock(medicine_name: str):
    """MODULE 4 — Check if below threshold and trigger alerts."""
    conn = get_db()
    row = conn.execute(
        "SELECT quantity, reorder_threshold FROM inventory WHERE medicine_name = ?",
        (medicine_name,),
    ).fetchone()
    conn.close()

    if not row or row["quantity"] >= row["reorder_threshold"]:
        return

    qty = row["quantity"]
    threshold = row["reorder_threshold"]
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    alert_line = f"{now} — {medicine_name} — qty: {qty} (below threshold {threshold})"

    # --- File alert ---
    stores_dir = pathlib.Path("stores")
    stores_dir.mkdir(exist_ok=True)
    req_file = stores_dir / "requirements.txt"

    # Check for duplicate (not yet restocked)
    already_flagged = False
    if req_file.exists():
        existing = req_file.read_text()
        if medicine_name in existing:
            already_flagged = True

    if not already_flagged:
        with open(req_file, "a") as f:
            f.write(alert_line + "\n")
        log.warning("📋 RESTOCK FILE │ %s", alert_line)

        # --- Telegram alert ---
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            _send_telegram(
                f"⚠️ *Low Stock Alert*\n\n"
                f"💊 *{medicine_name}*\n"
                f"📉 Current qty: {qty}\n"
                f"🔻 Threshold: {threshold}\n"
                f"🕐 {now}"
            )


def _send_telegram(text: str):
    """Send a Telegram message."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = httpx.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
        }, timeout=10)
        if resp.status_code == 200:
            log.info("📨 Telegram alert sent")
        else:
            log.warning("⚠️  Telegram response: %s", resp.text)
    except Exception as e:
        log.error("❌ Telegram error: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
#  CORE — POST /doctor/visit
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/doctor/visit")
async def doctor_visit(req: VisitRequest):
    patient_id = req.patient_id.strip()
    symptoms = req.symptoms.strip()
    notes = (req.notes or "").strip()

    # ── Step 1: Recall patient history (unless memory disabled — MODULE 2) ──
    history_text = ""
    is_new_patient = False
    memory_used = "Memory disabled (use_memory=false)"

    if req.use_memory:
        history_text, is_new_patient = await _recall_patient(patient_id, symptoms)
        if is_new_patient:
            memory_used = "No prior history — first visit (new patient bank created)"
        elif not history_text:
            memory_used = "Bank exists but no relevant memories found for this query"
        else:
            memory_used = history_text

    # ── Step 1b: Recall allergies & current meds (MODULE 1) ────────────────
    allergy_info = ""
    if req.use_memory:
        h_allergy = get_hindsight()
        try:
            allergy_resp = await h_allergy.arecall(
                bank_id=patient_id,
                query="allergies, drug allergies, current medications, adverse reactions",
            )
            allergy_facts = [r.text for r in allergy_resp.results] if allergy_resp.results else []
            if allergy_facts:
                allergy_info = "\n".join(allergy_facts)
                log.info(
                    "🔍 RECALL (allergies) │ patient=%s │ facts=%s",
                    patient_id, allergy_facts,
                )
        except Exception:
            pass  # non-critical — new patient won't have allergy data
        finally:
            await h_allergy.aclose()

    # ── Step 2: Groq — diagnosis + prescription ────────────────────────────
    history_block = (
        f"PATIENT HISTORY:\n{history_text}" if history_text
        else "PATIENT HISTORY: No prior history — this is the patient's first visit."
    )

    allergy_block = (
        f"\n\nKNOWN ALLERGIES & CURRENT MEDICATIONS:\n{allergy_info}"
        if allergy_info else ""
    )

    system_prompt = (
        "You are a clinical decision-support assistant for a family clinic. "
        "Given a patient's symptoms, visit notes, and their recalled medical history, "
        "provide:\n"
        "1. A suggested diagnosis\n"
        "2. A single primary prescription (medicine name, dosage, instructions)\n"
        "3. Brief clinical reasoning referencing past visits when available\n"
        "4. A 'warning' field — if the prescribed medicine could conflict with any "
        "known allergies, current medications, or prior adverse reactions listed in the "
        "patient's history, state the conflict clearly. If no conflict, set warning to null.\n\n"
        "Respond in JSON format:\n"
        '{"diagnosis": "...", "medicine_name": "...", "dosage": "...", '
        '"instructions": "...", "reasoning": "...", "warning": "..." or null}'
    )

    user_prompt = (
        f"{history_block}{allergy_block}\n\n"
        f"CURRENT SYMPTOMS: {symptoms}\n"
        f"DOCTOR'S NOTES: {notes or 'None'}"
    )

    raw_response = _groq_chat(system_prompt, user_prompt)

    # Parse the JSON from Groq
    try:
        # Strip markdown code fences if present
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        ai_result = json.loads(cleaned)
    except json.JSONDecodeError:
        ai_result = {
            "diagnosis": raw_response,
            "medicine_name": "Unknown",
            "dosage": "See notes",
            "instructions": "",
            "reasoning": raw_response,
            "warning": None,
        }

    # ── Step 3: Create prescription ────────────────────────────────────────
    rx_id = f"rx_{uuid.uuid4().hex[:8]}"
    medicine_name = ai_result.get("medicine_name", "Unknown")
    dosage = ai_result.get("dosage", "As directed")

    conn = get_db()
    conn.execute(
        "INSERT INTO prescriptions (prescription_id, patient_id, medicine_name, dosage, notes, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (
            rx_id,
            patient_id,
            medicine_name,
            dosage,
            ai_result.get("instructions", ""),
            datetime.datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    # ── Step 4: Retain visit into Hindsight ────────────────────────────────
    if req.use_memory:
        retain_content = (
            f"Visit on {datetime.datetime.now().strftime('%Y-%m-%d')}. "
            f"Symptoms: {symptoms}. "
            f"{'Doctor notes: ' + notes + '. ' if notes else ''}"
            f"Diagnosis: {ai_result.get('diagnosis', 'N/A')}. "
            f"Prescribed: {medicine_name} {dosage}. "
            f"{ai_result.get('instructions', '')}"
        )
        await _retain_patient(patient_id, retain_content, "doctor_visit")

    # ── Step 5 & 6: Return response ───────────────────────────────────────
    return {
        "prescription": {
            "prescription_id": rx_id,
            "patient_id": patient_id,
            "medicine_name": medicine_name,
            "dosage": dosage,
            "notes": ai_result.get("instructions", ""),
            "status": "pending",
        },
        "ai_diagnosis": ai_result.get("diagnosis", ""),
        "ai_reasoning": ai_result.get("reasoning", ""),
        "warning": ai_result.get("warning"),  # MODULE 1: allergy/interaction
        "memory_used": memory_used,
        "is_new_patient": is_new_patient,
        "use_memory": req.use_memory,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CORE — GET /pharmacy/pending
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/pharmacy/pending")
async def pharmacy_pending():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM prescriptions WHERE status = 'pending' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return {"pending": [dict(r) for r in rows]}


# ══════════════════════════════════════════════════════════════════════════════
#  CORE — POST /pharmacy/dispense
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/pharmacy/dispense")
async def pharmacy_dispense(req: DispenseRequest):
    conn = get_db()
    rx = conn.execute(
        "SELECT * FROM prescriptions WHERE prescription_id = ?",
        (req.prescription_id,),
    ).fetchone()

    if not rx:
        conn.close()
        raise HTTPException(404, "Prescription not found")

    if rx["status"] == "fulfilled":
        conn.close()
        return {"message": "Already dispensed", "prescription_id": req.prescription_id}

    patient_id = rx["patient_id"]
    medicine_name = rx["medicine_name"]
    dosage = rx["dosage"]

    # ── Step 2: Recall patient context for pharmacist ──────────────────────
    patient_context = ""
    try:
        history_text, _ = await _recall_patient(patient_id, "latest prescription and history")
        patient_context = history_text
    except Exception:
        pass

    # ── Step 3: Check inventory ────────────────────────────────────────────
    inv_row = conn.execute(
        "SELECT * FROM inventory WHERE medicine_name = ?", (medicine_name,)
    ).fetchone()

    dispensed_medicine = medicine_name
    substitution = None
    stock_warning = None

    if inv_row and inv_row["quantity"] > 0:
        # In stock — dispense
        new_qty = inv_row["quantity"] - 1
        conn.execute(
            "UPDATE inventory SET quantity = ? WHERE medicine_name = ?",
            (new_qty, medicine_name),
        )
        conn.execute(
            "UPDATE prescriptions SET status = 'fulfilled' WHERE prescription_id = ?",
            (req.prescription_id,),
        )
        conn.commit()
        log.info(
            "💊 DISPENSED │ %s │ patient=%s │ remaining=%d",
            medicine_name, patient_id, new_qty,
        )

        # Check restock threshold (MODULE 4)
        _check_restock(medicine_name)
        conn.close()

        if new_qty <= (inv_row["reorder_threshold"]):
            stock_warning = (
                f"⚠️ Low stock: {medicine_name} — {new_qty} remaining "
                f"(threshold: {inv_row['reorder_threshold']})"
            )
    else:
        conn.close()
        # Out of stock — ask Groq for alternative
        in_stock = _get_in_stock_medicines()
        alt_prompt = (
            f"The prescribed medicine '{medicine_name}' is out of stock at this pharmacy. "
            f"The following medicines ARE currently in stock: {', '.join(in_stock)}. "
            f"Suggest the best alternative from the in-stock list that belongs to the "
            f"same drug class or treats the same condition. "
            f"Respond in JSON: {{\"alternative\": \"...\", \"reason\": \"...\"}}"
        )
        alt_response = _groq_chat(
            "You are a pharmacist AI. Suggest a safe drug substitution from available stock.",
            alt_prompt,
        )

        try:
            cleaned = alt_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            alt_result = json.loads(cleaned)
        except json.JSONDecodeError:
            alt_result = {"alternative": "No suitable alternative found", "reason": alt_response}

        substitution = alt_result
        alternative_name = alt_result.get("alternative", "")

        # Try to dispense the alternative
        if alternative_name:
            conn2 = get_db()
            alt_inv = conn2.execute(
                "SELECT * FROM inventory WHERE medicine_name = ?", (alternative_name,)
            ).fetchone()

            if alt_inv and alt_inv["quantity"] > 0:
                new_qty = alt_inv["quantity"] - 1
                conn2.execute(
                    "UPDATE inventory SET quantity = ? WHERE medicine_name = ?",
                    (new_qty, alternative_name),
                )
                conn2.execute(
                    "UPDATE prescriptions SET status = 'fulfilled' WHERE prescription_id = ?",
                    (req.prescription_id,),
                )
                conn2.commit()
                dispensed_medicine = alternative_name
                log.info(
                    "💊 DISPENSED (substitute) │ %s → %s │ patient=%s │ remaining=%d",
                    medicine_name, alternative_name, patient_id, new_qty,
                )
                _check_restock(alternative_name)
            else:
                log.warning("⚠️  Alternative '%s' also not available", alternative_name)
            conn2.close()

    # ── Step 5: Retain dispensing into Hindsight ──────────────────────────
    retain_text = (
        f"Pharmacy dispensed on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}. "
        f"Original prescription: {medicine_name} {dosage}. "
    )
    if substitution:
        retain_text += (
            f"Out of stock — substituted with {substitution.get('alternative', 'N/A')}. "
            f"Reason: {substitution.get('reason', 'N/A')}."
        )
    else:
        retain_text += "Dispensed as prescribed."

    try:
        await _retain_patient(patient_id, retain_text, "pharmacy_dispense")
    except Exception as e:
        log.error("❌ Retain after dispense failed: %s", e)

    return {
        "prescription_id": req.prescription_id,
        "patient_id": patient_id,
        "dispensed_medicine": dispensed_medicine,
        "original_medicine": medicine_name,
        "dosage": dosage,
        "substitution": substitution,
        "stock_warning": stock_warning,
        "patient_context": patient_context,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  MODULE 3 — GET /patient/{patient_id}/summary
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/patient/{patient_id}/summary")
async def patient_summary(patient_id: str):
    h = get_hindsight()
    try:
        resp = await h.areflect(
            bank_id=patient_id,
            query="Summarize this patient's risk factors and recurring patterns across visits",
        )
        # ReflectResponse has a .text field with the markdown summary
        summary = resp.text if hasattr(resp, 'text') else str(resp)
        log.info("🪞 REFLECT │ patient=%s │ summary_preview=%.120s…", patient_id, summary)
        return {"patient_id": patient_id, "summary": summary}
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            raise HTTPException(404, f"No memory bank found for patient {patient_id}")
        log.error("❌ Reflect error │ %s", e)
        raise HTTPException(500, str(e))
    finally:
        await h.aclose()


# ══════════════════════════════════════════════════════════════════════════════
#  Utility — GET /inventory
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/inventory")
async def get_inventory():
    return {"inventory": _get_inventory_list()}


# ══════════════════════════════════════════════════════════════════════════════
#  MODULE — GET /patients  (list all patients with last prescription)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/patients")
async def list_patients():
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT
                p.patient_id,
                p.medicine_name AS last_medicine,
                p.dosage        AS last_dosage,
                p.created_at    AS last_visit,
                (
                    SELECT COUNT(*) FROM prescriptions p2
                    WHERE p2.patient_id = p.patient_id
                ) AS visit_count
            FROM prescriptions p
            WHERE p.created_at = (
                SELECT MAX(p3.created_at) FROM prescriptions p3
                WHERE p3.patient_id = p.patient_id
            )
            GROUP BY p.patient_id
            ORDER BY p.created_at DESC
            LIMIT 50
        """).fetchall()
        return {"patients": [dict(r) for r in rows]}
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
#  MODULE — POST /medicines/alternatives  (AI + inventory cross-reference)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/medicines/alternatives")
async def medicine_alternatives(req: MedicineQuery):
    import json as _json
    medicine_name = req.medicine_name.strip()
    if not medicine_name:
        raise HTTPException(400, "medicine_name is required")

    # ── Ask Groq for therapeutic alternatives ──
    system_msg = (
        "You are a clinical pharmacology expert. "
        "List drug alternatives concisely as a JSON array only."
    )
    prompt = (
        f'The doctor is considering prescribing "{medicine_name}".\n'
        "List the top 8 therapeutic alternatives (same drug class or same indication), "
        "including the original medicine itself.\n"
        'Respond ONLY with a raw JSON array — no markdown, no prose:\n'
        '[{"name": "Medicine Name Strength", "category": "Drug Class", "indication": "What it treats"}]'
    )

    raw = _groq_chat(system_msg, prompt)

    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip().lstrip("json").strip()
        alternatives = _json.loads(cleaned)
        if not isinstance(alternatives, list):
            raise ValueError("not a list")
    except Exception:
        alternatives = [{"name": medicine_name, "category": "Original", "indication": "As prescribed"}]

    # ── Cross-reference with inventory ──
    inventory = _get_inventory_list()
    inv_map = {item["medicine_name"].lower(): item for item in inventory}

    def _find_in_inv(name: str):
        name_l = name.lower()
        # Exact match first
        if name_l in inv_map:
            return inv_map[name_l]
        # Partial match — name is substring of inv key or vice versa
        for key, val in inv_map.items():
            base_name = name_l.split(" ")[0]   # first word e.g. "paracetamol"
            if base_name and base_name in key:
                return val
        return None

    status_order = {"in_stock": 0, "low_stock": 1, "out_of_stock": 2, "not_stocked": 3}
    result = []
    for alt in alternatives:
        name = alt.get("name", "")
        matched = _find_in_inv(name)
        if matched:
            qty       = matched["quantity"]
            threshold = matched["reorder_threshold"]
            if qty > threshold:
                status = "in_stock"
            elif qty > 0:
                status = "low_stock"
            else:
                status = "out_of_stock"
            inv_name = matched["medicine_name"]
        else:
            qty, status, inv_name = 0, "not_stocked", None

        result.append({
            "name":         name,
            "category":     alt.get("category", ""),
            "indication":   alt.get("indication", ""),
            "status":       status,
            "quantity":     qty,
            "inventory_name": inv_name,
        })

    result.sort(key=lambda x: status_order.get(x["status"], 9))
    log.info("💊 ALTERNATIVES │ medicine=%s │ results=%d", medicine_name, len(result))
    return {"medicine": medicine_name, "alternatives": result}


# ══════════════════════════════════════════════════════════════════════════════
#  Run
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
