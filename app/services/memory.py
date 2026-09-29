"""
Hindsight memory service — recall, retain, reflect, and startup seeding.

In DEMO_MODE (no Hindsight API key) all calls are graceful no-ops that
return empty results. This lets the full approval/dispense workflow run
in demos and tests without any external dependencies.
"""
import logging

from hindsight_client import Hindsight

from app.config import settings
from app.db import is_seed_key_done, mark_seed_key_done

log = logging.getLogger("clinic.memory")


def _get_hindsight() -> Hindsight:
    return Hindsight(
        base_url=settings.HINDSIGHT_BASE_URL,
        api_key=settings.HINDSIGHT_API_KEY,
    )


async def recall_patient(patient_id: str, query: str) -> tuple[str, bool]:
    """
    Recall relevant memories for a patient from Hindsight.
    Returns (history_text, is_new_patient).
    In DEMO_MODE returns ("", False) without making any API call.
    """
    if not settings.hindsight_configured:
        log.info("🔍 RECALL  │ DEMO_MODE — Hindsight not configured, returning empty")
        return "", False

    h = _get_hindsight()
    try:
        resp = await h.arecall(bank_id=patient_id, query=query)
        facts = [r.text for r in resp.results] if resp.results else []
        log.info(
            "🔍 RECALL  │ patient=%s │ query=%s │ results=%d │ facts=%s",
            patient_id, query, len(facts), facts,
        )
        return ("\n".join(facts), False) if facts else ("", False)
    except Exception as exc:
        if "404" in str(exc) or "not found" in str(exc).lower():
            log.info("🆕 RECALL  │ patient=%s │ Bank not found — new patient", patient_id)
            try:
                await h.acreate_bank(bank_id=patient_id, name=f"Patient {patient_id}")
                log.info("🧠 Created new bank for %s", patient_id)
            except Exception as ce:
                log.warning(
                    "⚠️  create_bank %s error (type=%s)", patient_id, type(ce).__name__
                )
            return "", True
        log.error("❌ RECALL error │ patient=%s │ type=%s", patient_id, type(exc).__name__)
        raise
    finally:
        await h.aclose()


async def retain_patient(patient_id: str, content: str, context: str) -> None:
    """
    Store information into Hindsight for a patient.
    No-op in DEMO_MODE.
    """
    if not settings.hindsight_configured:
        log.info(
            "💾 RETAIN  │ DEMO_MODE — skipped │ patient=%s │ context=%s",
            patient_id, context,
        )
        return

    h = _get_hindsight()
    try:
        await h.aretain(bank_id=patient_id, content=content, context=context)
        log.info(
            "💾 RETAIN  │ patient=%s │ context=%s │ content_preview=%.120s…",
            patient_id, context, content,
        )
    except Exception as exc:
        log.error("❌ RETAIN error │ patient=%s │ type=%s", patient_id, type(exc).__name__)
        raise
    finally:
        await h.aclose()


async def _seed_one_patient(
    bank_id: str,
    name: str,
    seed_items: list[tuple[str, str]],
) -> None:
    """
    Idempotent bank seeding:
      - Creates the Hindsight bank once (ignores "already exists").
      - Retains each (label, content) pair exactly once, guarded by a
        SQLite marker so restarts are safe.
    No-op in DEMO_MODE.
    """
    if not settings.hindsight_configured:
        log.info("🧠 DEMO_MODE — seed skipped for %s", bank_id)
        return

    h = _get_hindsight()
    try:
        # Create bank (idempotent)
        try:
            await h.acreate_bank(bank_id=bank_id, name=name)
            log.info("🧠 Bank created for %s", bank_id)
        except Exception as exc:
            err = str(exc).lower()
            if "already exists" in err or "conflict" in err or "409" in err:
                log.info("🧠 Bank already existed for %s — skipping create", bank_id)
            else:
                log.warning(
                    "⚠️  create_bank for %s raised unexpected error (type=%s)",
                    bank_id, type(exc).__name__,
                )

        # Retain each memory block exactly once
        for label, content in seed_items:
            seed_key = f"{bank_id}:{label}"
            if is_seed_key_done(seed_key):
                log.info("🧠 Seed skipped  %s:%s — already retained", bank_id, label)
            else:
                try:
                    await h.aretain(bank_id=bank_id, content=content, context="doctor_visit")
                    mark_seed_key_done(seed_key)
                    log.info("🧠 Seed retained %s:%s", bank_id, label)
                except Exception as exc:
                    log.warning(
                        "⚠️  retain seed %s:%s raised error (type=%s)",
                        bank_id, label, type(exc).__name__,
                    )
    finally:
        await h.aclose()


async def seed_patient_memory() -> None:
    """Seed Hindsight banks for demo patients on startup (idempotent)."""
    # patient_001 — Rajesh Kumar, 54, Type 2 Diabetes, penicillin allergy
    await _seed_one_patient(
        bank_id="patient_001",
        name="Patient Rajesh Kumar",
        seed_items=[
            (
                "visit_2026_08_10",
                "Patient Rajesh Kumar, age 54. Visited 2026-08-10. "
                "Elevated fasting glucose 168 mg/dL and fatigue. "
                "Diagnosed Type 2 Diabetes Mellitus. "
                "Prescribed Metformin 500mg twice daily. "
                "Known penicillin allergy (hives after Amoxicillin in 2019). "
                "No other medications.",
            ),
            (
                "followup_2026_09_01",
                "Follow-up 2026-09-01. Fasting glucose improved to 142 mg/dL on Metformin. "
                "Mild throat discomfort, no fever. Continue monitoring.",
            ),
        ],
    )

    # patient_002 — Meera Iyer, 29, Stage 1 Hypertension
    await _seed_one_patient(
        bank_id="patient_002",
        name="Patient Meera Iyer",
        seed_items=[
            (
                "visit_2026_09_20",
                "Patient Meera Iyer, age 29. Visited 2026-09-20. BP 148/94. "
                "Diagnosed Stage 1 Hypertension. "
                "Prescribed Lisinopril 5mg once daily. "
                "No known drug allergies.",
            ),
        ],
    )

    # patient_003 — intentionally no history (new-patient demo)
    await _seed_one_patient(
        bank_id="patient_003",
        name="Patient Demo New",
        seed_items=[],
    )
    log.info("🧠 patient_003 bank ready — no prior history (new-patient demo)")
