"""
Doctor endpoints — require role 'doctor'.
  POST /doctor/visit    — recall history, LLM diagnosis, save draft
  POST /doctor/approve  — draft → pending; retain to Hindsight
  POST /doctor/reject   — draft → rejected; retain to Hindsight

/doctor/visit is also rate-limited (LLM call).
Every state change is written to audit_log.
"""
import datetime
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db
from app.models import ApproveRequest, RejectRequest, VisitRequest
from app.services.audit import append_audit
from app.services.auth import require_role
from app.services.llm import groq_chat, parse_llm_json
from app.services.memory import recall_patient, retain_patient
from app.services.rate_limit import rate_limit

log = logging.getLogger("clinic.doctor")
router = APIRouter(prefix="/doctor", tags=["doctor"])


# ── POST /doctor/visit ───────────────────────────────────────────────────────

@router.post("/visit")
@rate_limit("30/minute")
async def doctor_visit(
    request: Request,
    req: VisitRequest,
    user: dict = Depends(require_role("doctor")),
):
    patient_id = req.patient_id.strip()
    symptoms = req.symptoms.strip()
    notes = (req.notes or "").strip()

    # ── Step 1: Recall patient history ──────────────────────────────────────
    history_text = ""
    is_new_patient = False
    memory_used = "Memory disabled (use_memory=false)"

    if req.use_memory:
        history_text, is_new_patient = await recall_patient(patient_id, symptoms)
        if is_new_patient:
            memory_used = "No prior history — first visit (new patient bank created)"
        elif not history_text:
            memory_used = "Bank exists but no relevant memories found for this query"
        else:
            memory_used = history_text

    # ── Step 1b: Recall allergies & current medications ──────────────────────
    allergy_info = ""
    if req.use_memory:
        try:
            allergy_text, _ = await recall_patient(
                patient_id,
                "allergies, drug allergies, current medications, adverse reactions",
            )
            allergy_info = allergy_text
        except Exception:
            pass

    # ── Step 2: Build LLM prompt (patient_id is never sent to LLM) ──────────
    history_block = (
        f"PATIENT HISTORY:\n{history_text}"
        if history_text
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

    raw_response = groq_chat(system_prompt, user_prompt)

    try:
        ai_result = parse_llm_json(raw_response)
    except Exception:
        ai_result = {
            "diagnosis": raw_response,
            "medicine_name": "Unknown",
            "dosage": "See notes",
            "instructions": "",
            "reasoning": raw_response,
            "warning": None,
        }

    # ── Step 3: Save as DRAFT — not visible to pharmacy until approved ────────
    rx_id = f"rx_{uuid.uuid4().hex[:8]}"
    medicine_name = ai_result.get("medicine_name", "Unknown")
    dosage = ai_result.get("dosage", "As directed")

    with get_db() as conn:
        conn.execute(
            "INSERT INTO prescriptions"
            " (prescription_id, patient_id, medicine_name, dosage, notes, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'draft', ?)",
            (
                rx_id, patient_id, medicine_name, dosage,
                ai_result.get("instructions", ""),
                datetime.datetime.now().isoformat(),
            ),
        )
        conn.commit()

    # ── Step 4: Retain visit notes to Hindsight ──────────────────────────────
    if req.use_memory:
        visit_content = (
            f"Visit on {datetime.datetime.now().strftime('%Y-%m-%d')}. "
            f"Symptoms: {symptoms}. "
            f"{'Doctor notes: ' + notes + '. ' if notes else ''}"
            f"AI suggested diagnosis: {ai_result.get('diagnosis', 'N/A')}. "
            f"Awaiting doctor approval before prescription is finalised."
        )
        await retain_patient(patient_id, visit_content, "doctor_visit")

    # ── Step 5: Audit ─────────────────────────────────────────────────────────
    append_audit(
        actor=user["username"],
        role=user["role"],
        action="visit_created",
        entity="prescription",
        entity_id=rx_id,
        details={
            "patient_id": patient_id,
            "medicine": medicine_name,
            "has_warning": bool(ai_result.get("warning")),
        },
    )

    return {
        "prescription": {
            "prescription_id": rx_id,
            "patient_id": patient_id,
            "medicine_name": medicine_name,
            "dosage": dosage,
            "notes": ai_result.get("instructions", ""),
            "status": "draft",
        },
        "ai_diagnosis": ai_result.get("diagnosis", ""),
        "ai_reasoning": ai_result.get("reasoning", ""),
        "warning": ai_result.get("warning"),
        "memory_used": memory_used,
        "is_new_patient": is_new_patient,
        "use_memory": req.use_memory,
    }


# ── POST /doctor/approve ─────────────────────────────────────────────────────

@router.post("/approve")
async def doctor_approve(
    req: ApproveRequest,
    user: dict = Depends(require_role("doctor")),
):
    with get_db() as conn:
        rx = conn.execute(
            "SELECT * FROM prescriptions WHERE prescription_id = ?",
            (req.prescription_id,),
        ).fetchone()

        if not rx:
            raise HTTPException(404, "Prescription not found")
        if rx["status"] != "draft":
            raise HTTPException(
                400, f"Cannot approve a prescription with status '{rx['status']}'"
            )

        final_medicine = (req.medicine_name or "").strip() or rx["medicine_name"]
        final_dosage   = (req.dosage or "").strip() or rx["dosage"]
        patient_id     = rx["patient_id"]
        original_med   = rx["medicine_name"]

        conn.execute(
            "UPDATE prescriptions SET status='pending', medicine_name=?, dosage=?"
            " WHERE prescription_id=?",
            (final_medicine, final_dosage, req.prescription_id),
        )
        conn.commit()

    # Detect override: doctor changed what the AI suggested
    action = (
        "prescription_override"
        if final_medicine != original_med or final_dosage != rx["dosage"]
        else "prescription_approved"
    )

    log.info(
        "✅ %s │ rx=%s │ patient=%s │ medicine=%s",
        action.upper(), req.prescription_id, patient_id, final_medicine,
    )

    append_audit(
        actor=user["username"],
        role=user["role"],
        action=action,
        entity="prescription",
        entity_id=req.prescription_id,
        details={
            "patient_id": patient_id,
            "medicine": final_medicine,
            "dosage": final_dosage,
            "original_medicine": original_med,
        },
    )

    try:
        await retain_patient(
            patient_id,
            f"Dr {user['username']} approved prescription: {final_medicine} {final_dosage}. "
            f"Sent to pharmacy on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}.",
            "doctor_approved",
        )
    except Exception:
        pass

    return {
        "prescription_id": req.prescription_id,
        "patient_id": patient_id,
        "medicine_name": final_medicine,
        "dosage": final_dosage,
        "status": "pending",
        "message": "Prescription approved and sent to pharmacy.",
    }


# ── POST /doctor/reject ──────────────────────────────────────────────────────

@router.post("/reject")
async def doctor_reject(
    req: RejectRequest,
    user: dict = Depends(require_role("doctor")),
):
    with get_db() as conn:
        rx = conn.execute(
            "SELECT * FROM prescriptions WHERE prescription_id = ?",
            (req.prescription_id,),
        ).fetchone()

        if not rx:
            raise HTTPException(404, "Prescription not found")
        if rx["status"] != "draft":
            raise HTTPException(
                400, f"Cannot reject a prescription with status '{rx['status']}'"
            )

        patient_id    = rx["patient_id"]
        medicine_name = rx["medicine_name"]

        conn.execute(
            "UPDATE prescriptions SET status='rejected' WHERE prescription_id=?",
            (req.prescription_id,),
        )
        conn.commit()

    log.info(
        "🚫 REJECTED │ rx=%s │ patient=%s │ medicine=%s",
        req.prescription_id, patient_id, medicine_name,
    )

    append_audit(
        actor=user["username"],
        role=user["role"],
        action="prescription_rejected",
        entity="prescription",
        entity_id=req.prescription_id,
        details={"patient_id": patient_id, "medicine": medicine_name},
    )

    try:
        await retain_patient(
            patient_id,
            f"Suggestion rejected by Dr {user['username']}: {medicine_name}. "
            f"Rejected on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}.",
            "doctor_rejected",
        )
    except Exception:
        pass

    return {
        "prescription_id": req.prescription_id,
        "patient_id": patient_id,
        "medicine_name": medicine_name,
        "status": "rejected",
        "message": "Prescription rejected.",
    }
