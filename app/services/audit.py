"""
Audit log service — DB-backed, never raises.

Every clinically significant action (login, visit, approval, dispense,
substitution, override, refill) calls append_audit(). Failures are logged
but never propagate to the caller.

Table schema (created in db.init_db):
    audit_log(id, timestamp, actor, role, action, entity, entity_id, details_json)
"""
import datetime
import json
import logging

log = logging.getLogger("clinic.audit")


def append_audit(
    actor: str,
    role: str,
    action: str,
    entity: str | None = None,
    entity_id: str | None = None,
    details: dict | None = None,
) -> None:
    """
    Write one row to audit_log. Silently drops the write on any error
    so the caller's response is never blocked by audit failures.

    Args:
        actor      : username of the authenticated caller (or 'system' / 'unknown')
        role       : role of the caller
        action     : machine-readable event name  (e.g. 'login', 'visit_created')
        entity     : top-level entity type        (e.g. 'prescription', 'user')
        entity_id  : primary-key value of entity  (e.g. rx_id, patient_id)
        details    : free-form dict serialised to JSON
    """
    try:
        # Local import to avoid a circular-import at module load time.
        from app.db import get_db

        with get_db() as conn:
            conn.execute(
                "INSERT INTO audit_log"
                " (timestamp, actor, role, action, entity, entity_id, details_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.datetime.now().isoformat(),
                    actor,
                    role,
                    action,
                    entity,
                    entity_id,
                    json.dumps(details) if details else None,
                ),
            )
            conn.commit()
        log.info(
            "AUDIT │ %-25s │ actor=%-15s │ role=%-12s │ %s:%s",
            action, actor, role, entity or "", entity_id or "",
        )
    except Exception as exc:
        # Audit failure must NEVER block the main request.
        log.error("❌ Audit write failed: %s", exc)
