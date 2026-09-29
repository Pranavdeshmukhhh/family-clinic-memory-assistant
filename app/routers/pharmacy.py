"""
Pharmacy endpoints.
  GET  /pharmacy/pending  — doctor + pharmacist + owner (read)
  POST /pharmacy/dispense — pharmacist only

Every dispense (normal, substitution, or refill attempt) is audited.
"""
import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db
from app.models import DispenseRequest
from app.services.audit import append_audit
from app.services.auth import require_role
from app.services.inventory import check_restock, get_in_stock_medicines
from app.services.llm import groq_chat, parse_llm_json
from app.services.memory import recall_patient, retain_patient

log = logging.getLogger("clinic.pharmacy")
router = APIRouter(prefix="/pharmacy", tags=["pharmacy"])


@router.get("/pending")
async def pharmacy_pending(
    user: dict = Depends(require_role("doctor", "pharmacist", "owner")),
):
    """Return only doctor-approved prescriptions waiting for dispensing."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM prescriptions WHERE status = 'pending' ORDER BY created_at DESC"
        ).fetchall()
    return {"pending": [dict(r) for r in rows]}


@router.post("/dispense")
async def pharmacy_dispense(
    req: DispenseRequest,
    user: dict = Depends(require_role("pharmacist")),
):
    # ── Phase 1: Read prescription + inventory ───────────────────────────────
    with get_db() as conn:
        rx = conn.execute(
            "SELECT * FROM prescriptions WHERE prescription_id = ?",
            (req.prescription_id,),
        ).fetchone()

        if not rx:
            raise HTTPException(404, "Prescription not found")

        rx_data       = dict(rx)
        patient_id    = rx_data["patient_id"]
        medicine_name = rx_data["medicine_name"]
        dosage        = rx_data["dosage"]

        if rx["status"] == "fulfilled":
            append_audit(
                actor=user["username"], role=user["role"],
                action="refill_attempted",
                entity="prescription", entity_id=req.prescription_id,
                details={"patient_id": patient_id, "medicine": medicine_name},
            )
            return {
                "message": "Already dispensed",
                "prescription_id": req.prescription_id,
            }

        if rx["status"] != "pending":
            raise HTTPException(
                400, f"Cannot dispense a prescription with status '{rx['status']}'"
            )

        inv = conn.execute(
            "SELECT * FROM inventory WHERE medicine_name = ?", (medicine_name,)
        ).fetchone()
        inv_data = dict(inv) if inv else None

    dispensed_medicine = medicine_name
    substitution       = None
    stock_warning      = None

    if inv_data and inv_data["quantity"] > 0:
        # ── Phase 2a: In stock — dispense ────────────────────────────────────
        new_qty = inv_data["quantity"] - 1
        with get_db() as conn:
            conn.execute(
                "UPDATE inventory SET quantity = ? WHERE medicine_name = ?",
                (new_qty, medicine_name),
            )
            conn.execute(
                "UPDATE prescriptions SET status = 'fulfilled' WHERE prescription_id = ?",
                (req.prescription_id,),
            )
            conn.commit()

        log.info("💊 DISPENSED │ %s │ patient=%s │ remaining=%d", medicine_name, patient_id, new_qty)
        check_restock(medicine_name)

        if new_qty <= inv_data["reorder_threshold"]:
            stock_warning = (
                f"⚠️ Low stock: {medicine_name} — {new_qty} remaining "
                f"(threshold: {inv_data['reorder_threshold']})"
            )

        append_audit(
            actor=user["username"], role=user["role"],
            action="prescription_dispensed",
            entity="prescription", entity_id=req.prescription_id,
            details={
                "patient_id": patient_id,
                "medicine": medicine_name,
                "remaining_stock": new_qty,
            },
        )
    else:
        # ── Phase 2b: Out of stock — LLM substitution ─────────────────────────
        in_stock = get_in_stock_medicines()
        alt_prompt = (
            f"The prescribed medicine '{medicine_name}' is out of stock. "
            f"In-stock medicines: {', '.join(in_stock)}. "
            f"Suggest the best alternative from the in-stock list in the same "
            f"drug class or for the same condition. "
            f'Respond in JSON: {{"alternative": "...", "reason": "..."}}'
        )
        alt_response = groq_chat(
            "You are a pharmacist AI. Suggest a safe drug substitution from available stock.",
            alt_prompt,
        )

        try:
            alt_result = parse_llm_json(alt_response)
        except Exception:
            alt_result = {"alternative": "No suitable alternative found", "reason": alt_response}

        substitution     = alt_result
        alternative_name = alt_result.get("alternative", "")

        if alternative_name:
            with get_db() as conn:
                alt_inv = conn.execute(
                    "SELECT * FROM inventory WHERE medicine_name = ?", (alternative_name,)
                ).fetchone()
                alt_inv_data = dict(alt_inv) if alt_inv else None

            if alt_inv_data and alt_inv_data["quantity"] > 0:
                new_qty = alt_inv_data["quantity"] - 1
                with get_db() as conn:
                    conn.execute(
                        "UPDATE inventory SET quantity = ? WHERE medicine_name = ?",
                        (new_qty, alternative_name),
                    )
                    conn.execute(
                        "UPDATE prescriptions SET status = 'fulfilled' WHERE prescription_id = ?",
                        (req.prescription_id,),
                    )
                    conn.commit()
                dispensed_medicine = alternative_name
                log.info(
                    "💊 DISPENSED (sub) │ %s → %s │ patient=%s",
                    medicine_name, alternative_name, patient_id,
                )
                check_restock(alternative_name)

        append_audit(
            actor=user["username"], role=user["role"],
            action="substitution_dispensed",
            entity="prescription", entity_id=req.prescription_id,
            details={
                "patient_id": patient_id,
                "original_medicine": medicine_name,
                "dispensed_medicine": dispensed_medicine,
                "reason": alt_result.get("reason", ""),
            },
        )

    # ── Phase 3: Recall patient context for pharmacist ───────────────────────
    patient_context = ""
    try:
        history_text, _ = await recall_patient(patient_id, "latest prescription and history")
        patient_context = history_text
    except Exception:
        pass

    # ── Phase 4: Retain dispensing event ────────────────────────────────────
    retain_text = (
        f"Pharmacy dispensed on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}. "
        f"Original prescription: {medicine_name} {dosage}. "
    )
    retain_text += (
        f"Out of stock — substituted with {substitution.get('alternative', 'N/A')}. "
        f"Reason: {substitution.get('reason', 'N/A')}."
        if substitution
        else "Dispensed as prescribed."
    )
    try:
        await retain_patient(patient_id, retain_text, "pharmacy_dispense")
    except Exception as exc:
        log.error("❌ Retain after dispense failed: %s", exc)

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
