"""
Admin / utility endpoints.
  GET  /inventory                — all authenticated roles
  GET  /patients                 — all authenticated roles
  POST /medicines/alternatives   — doctor + pharmacist; rate-limited (LLM call)
  GET  /admin/audit              — owner only, paginated
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db import get_db
from app.models import MedicineQuery
from app.services.auth import get_current_user, require_role
from app.services.inventory import get_inventory_list
from app.services.llm import groq_chat, parse_llm_json
from app.services.rate_limit import rate_limit

log = logging.getLogger("clinic.admin")
router = APIRouter(tags=["admin"])


# ── GET /inventory ────────────────────────────────────────────────────────────

@router.get("/inventory")
async def get_inventory(
    user: dict = Depends(require_role("doctor", "pharmacist", "owner")),
):
    return {"inventory": get_inventory_list()}


# ── GET /patients ─────────────────────────────────────────────────────────────

@router.get("/patients")
async def list_patients(
    user: dict = Depends(require_role("doctor", "pharmacist", "owner")),
):
    with get_db() as conn:
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


# ── POST /medicines/alternatives ─────────────────────────────────────────────

@router.post("/medicines/alternatives")
@rate_limit("20/minute")
async def medicine_alternatives(
    request: Request,
    req: MedicineQuery,
    user: dict = Depends(require_role("doctor", "pharmacist")),
):
    medicine_name = req.medicine_name.strip()
    if not medicine_name:
        raise HTTPException(400, "medicine_name is required")

    system_msg = (
        "You are a clinical pharmacology expert. "
        "List drug alternatives concisely as a JSON array only."
    )
    prompt = (
        f'The doctor is considering prescribing "{medicine_name}".\n'
        "List the top 8 therapeutic alternatives (same drug class or same indication), "
        "including the original medicine itself.\n"
        "Respond ONLY with a raw JSON array — no markdown, no prose:\n"
        '[{"name": "Medicine Name Strength", "category": "Drug Class", "indication": "What it treats"}]'
    )

    raw = groq_chat(system_msg, prompt)

    try:
        alternatives = parse_llm_json(raw)
        if not isinstance(alternatives, list):
            raise ValueError("expected a JSON array")
    except Exception:
        alternatives = [
            {"name": medicine_name, "category": "Original", "indication": "As prescribed"}
        ]

    inventory = get_inventory_list()
    inv_map   = {item["medicine_name"].lower(): item for item in inventory}

    def _find_in_inv(name: str) -> dict | None:
        name_l = name.lower()
        if name_l in inv_map:
            return inv_map[name_l]
        base = name_l.split(" ")[0]
        for key, val in inv_map.items():
            if base and base in key:
                return val
        return None

    status_order = {"in_stock": 0, "low_stock": 1, "out_of_stock": 2, "not_stocked": 3}
    result = []
    for alt in alternatives:
        name    = alt.get("name", "")
        matched = _find_in_inv(name)
        if matched:
            qty       = matched["quantity"]
            threshold = matched["reorder_threshold"]
            status    = "in_stock" if qty > threshold else ("low_stock" if qty > 0 else "out_of_stock")
            inv_name  = matched["medicine_name"]
        else:
            qty, status, inv_name = 0, "not_stocked", None

        result.append({
            "name": name,
            "category": alt.get("category", ""),
            "indication": alt.get("indication", ""),
            "status": status,
            "quantity": qty,
            "inventory_name": inv_name,
        })

    result.sort(key=lambda x: status_order.get(x["status"], 9))
    log.info("💊 ALTERNATIVES │ medicine=%s │ results=%d", medicine_name, len(result))
    return {"medicine": medicine_name, "alternatives": result}


# ── GET /admin/audit ──────────────────────────────────────────────────────────

@router.get("/admin/audit")
async def get_audit_log(
    user: dict = Depends(require_role("owner")),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=200, description="Results per page"),
):
    """
    Paginated audit log — owner only.
    Returns entries in reverse-chronological order.
    """
    offset = (page - 1) * page_size
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        rows  = conn.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }
