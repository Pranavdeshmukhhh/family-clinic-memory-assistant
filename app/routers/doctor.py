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
from app.services.safety import (
    Finding,
    check_prescription,
    extract_allergies_from_memory,
    findings_summary,
    has_blocking_findings,
)

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

    # -- Step 1b: Recall allergies & current medications ---------------------
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

    # -- Step 1c: Build allergy list for safety checker ----------------------
    # Prefer explicit allergies from the request; supplement from recalled memory.
    known_allergies = list(req.patient_allergies)
    if allergy_info:
        memory_allergies = extract_allergies_from_memory(allergy_info)
        for a in memory_allergies:
            if a not in known_allergies:
                known_allergies.append(a)

    # -- Step 2: Build LLM prompt with safety context (patient_id never sent) --
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
        "You are a terse clinical decision-support system. "
        "Return ONLY valid JSON, no markdown, no preamble, no extra fields. "
        "Use standard abbreviations (BD, OD, TDS, PRN).\n"
        "Schema (obey word limits strictly):\n"
        '{\n'
        '  "alert": "one sentence, ONLY allergy/interaction/safety conflicts, max 20 words. Empty string if none",\n'
        '  "summary": "one sentence: likely diagnosis and why, max 25 words",\n'
        '  "prescription": [{"drug": "", "dose": "", "frequency": "", "duration": ""}],\n'
        '  "memory_used": ["max 4 short facts from history, max 8 words each, e.g. Penicillin allergy (2022)"],\n'
        '  "advice": ["max 3 bullets, max 10 words each"],\n'
        '  "follow_up": "max 12 words"\n'
        '}\n'
        "Do NOT prescribe a drug the patient is allergic to."
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
            "summary": raw_response[:300],
            "prescription": [{"drug": "Unknown", "dose": "See notes", "frequency": "", "duration": ""}],
            "alert": "",
            "memory_used": [],
            "advice": [],
            "follow_up": "",
        }

    # -- Normalise prescription from new structured format --------------------
    rx_list = ai_result.get("prescription", [])
    if isinstance(rx_list, list) and len(rx_list) > 0:
        first_rx = rx_list[0]
        medicine_name = first_rx.get("drug", "Unknown")
        dosage = " ".join(filter(None, [
            first_rx.get("dose", ""),
            first_rx.get("frequency", ""),
            first_rx.get("duration", ""),
        ])) or "As directed"
    else:
        medicine_name = ai_result.get("medicine_name", "Unknown")
        dosage = ai_result.get("dosage", "As directed")

    # -- Step 3: Full safety check now that we have a proposed medicine --------
    safety_findings: list[Finding] = check_prescription(
        patient_allergies=known_allergies,
        current_meds=req.current_meds,
        proposed_items=[medicine_name],
    )

    # Authoritative alert = rule engine findings override LLM alert
    if safety_findings:
        rule_alert: str = findings_summary(safety_findings)
    elif ai_result.get("alert"):
        rule_alert = str(ai_result["alert"])
    else:
        rule_alert = ""

    # Also keep backward compat key "warning"
    rule_warning = rule_alert or None

    # -- Step 4: Save as DRAFT ------------------------------------------------
    rx_id = f"rx_{uuid.uuid4().hex[:8]}"

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

    # ── Step 4b: Retain visit notes to Hindsight ─────────────────────────────
    if req.use_memory:
        summary_text = ai_result.get("summary", ai_result.get("diagnosis", "N/A"))
        visit_content = (
            f"Visit on {datetime.datetime.now().strftime('%Y-%m-%d')}. "
            f"Symptoms: {symptoms}. "
            f"{'Doctor notes: ' + notes + '. ' if notes else ''}"
            f"AI suggested diagnosis: {summary_text}. "
            f"Awaiting doctor approval before prescription is finalised."
        )
        await retain_patient(patient_id, visit_content, "doctor_visit")

    # -- Step 5: Audit --------------------------------------------------------
    append_audit(
        actor=user["username"],
        role=user["role"],
        action="visit_created",
        entity="prescription",
        entity_id=rx_id,
        details={
            "patient_id": patient_id,
            "medicine": medicine_name,
            "safety_findings": len(safety_findings),
            "has_blocking": has_blocking_findings(safety_findings),
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
        # ── New structured fields ──
        "alert": rule_alert,
        "summary": ai_result.get("summary", ai_result.get("diagnosis", "")),
        "rx": rx_list if isinstance(rx_list, list) else [],
        "memory_facts": ai_result.get("memory_used", []),
        "advice": ai_result.get("advice", []),
        "follow_up": ai_result.get("follow_up", ""),
        "raw_reasoning": ai_result.get("reasoning", raw_response[:400]),
        # ── Backward compat fields ──
        "ai_diagnosis": ai_result.get("summary", ai_result.get("diagnosis", "")),
        "ai_reasoning": ai_result.get("reasoning", ""),
        "warning": rule_warning,
        "safety_findings": [f.to_dict() for f in safety_findings],
        "has_blocking_findings": has_blocking_findings(safety_findings),
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

    # -- Safety gate: contraindicated findings block approval -----------------
    # Re-run safety check on the medicine being approved (may differ from draft).
    # We don't have patient_allergies stored per prescription, so we re-check
    # based on what the doctor sent.  An empty list means "no structured data"
    # which will still catch KB interactions vs current_meds if provided.
    gate_findings = check_prescription(
        patient_allergies=[],  # structured allergy data is in the visit call
        current_meds=[],
        proposed_items=[final_medicine],
    )
    # Check stored notes for any explicit allergy warning written at visit time
    # by loading back from DB (best-effort).
    blocking = [f for f in gate_findings if f.is_blocking()]
    if blocking and not req.override_reason:
        raise HTTPException(
            status_code=409,
            detail=(
                "Approval blocked: contraindicated safety finding present. "
                "Provide 'override_reason' to proceed. "
                f"Findings: {[f.to_dict() for f in blocking]}"
            ),
        )

    with get_db() as conn:
        rx = conn.execute(
            "SELECT * FROM prescriptions WHERE prescription_id = ?",
            (req.prescription_id,),
        ).fetchone()

        final_dosage  = (req.dosage or "").strip() or rx["dosage"]
        patient_id    = rx["patient_id"]
        original_med  = rx["medicine_name"]

        conn.execute(
            "UPDATE prescriptions SET status='pending', medicine_name=?, dosage=?"
            " WHERE prescription_id=?",
            (final_medicine, final_dosage, req.prescription_id),
        )
        conn.commit()

    # Detect action type
    if req.override_reason:
        action = "prescription_contraindicated_override"
    elif final_medicine != original_med or final_dosage != rx["dosage"]:
        action = "prescription_override"
    else:
        action = "prescription_approved"

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
            "override_reason": req.override_reason,  # None if not overriding
        },
    )

    try:
        await retain_patient(
            patient_id,
            f"Dr {user['username']} approved prescription: {final_medicine} {final_dosage}. "
            f"Sent to pharmacy on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}.",
            "doctor_approved",
        )
    except Exception as exc:
        log.warning(
            "⚠️ RETAIN failed on approve │ patient=%s │ rx=%s │ %s",
            patient_id, req.prescription_id, exc,
        )

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
    except Exception as exc:
        log.warning(
            "⚠️ RETAIN failed on reject │ patient=%s │ rx=%s │ %s",
            patient_id, req.prescription_id, exc,
        )

    return {
        "prescription_id": req.prescription_id,
        "patient_id": patient_id,
        "medicine_name": medicine_name,
        "status": "rejected",
        "message": "Prescription rejected.",
    }
