"""
Audit log service.

Every clinically significant action (approve, reject, dispense) will be
written here. The DB table is created in db.init_db; write calls are wired
in the router handlers.

Design principle: every important action must be written to an audit log
(Design Principle 5). This module owns that concern.
"""
import datetime
import logging

log = logging.getLogger("clinic.audit")


def append_audit(action: str, patient_id: str, detail: str) -> None:
    """
    Write a structured audit entry.

    Currently logs to the application logger; a persistent DB-backed
    table will be wired in the audit task (next iteration).
    """
    log.info(
        "AUDIT │ action=%-20s │ patient=%-15s │ %s",
        action,
        patient_id,
        detail,
    )
