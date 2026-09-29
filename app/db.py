"""
SQLite connection management and schema initialisation.

All callers must use `get_db()` as a context manager:

    with get_db() as conn:
        rows = conn.execute("SELECT ...").fetchall()

The connection is always closed on exit, even if an exception is raised.
"""
import datetime
import logging
import sqlite3
from contextlib import contextmanager
from typing import Generator

from app.config import settings

log = logging.getLogger("clinic.db")


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite connection; guaranteed to close on exit."""
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ── Inventory seed data ──────────────────────────────────────────────────────
CORE_MEDS: list[tuple[str, int, int]] = [
    # ── Key demo medicines with specified realistic quantities ──
    ("Metformin 500mg",      40, 15),   # Rajesh's ongoing medication
    ("Lisinopril 5mg",        6,  5),   # Meera's medication — near threshold
    ("Amlodipine 5mg",       25, 10),
    ("Azithromycin 500mg",   18,  8),
    ("Amoxicillin 500mg",     0, 10),   # intentionally out of stock
    ("Paracetamol 500mg",    60, 20),
    ("Atorvastatin 10mg",    12,  6),
    ("Omeprazole 20mg",      30, 10),
    # ── Fever / Pain / Anti-inflammatory ──
    ("Paracetamol 650mg",    35, 12),
    ("Ibuprofen 400mg",      48, 12),
    ("Ibuprofen 600mg",      22, 10),
    ("Aspirin 75mg",         55, 15),
    ("Aspirin 325mg",        28,  8),
    ("Diclofenac 50mg",      20,  7),
    ("Naproxen 250mg",       14,  6),
    ("Nimesulide 100mg",     17,  5),
    ("Mefenamic Acid 250mg", 11,  4),
    ("Tramadol 50mg",        10,  4),
    ("Ketorolac 10mg",        7,  3),
    ("Metamizole 500mg",     13,  5),
    ("Dexamethasone 4mg",    16,  5),
    ("Methylprednisolone 4mg", 9, 4),
    # ── Cold / Cough / Allergy / Respiratory ──
    ("Cetirizine 10mg",      45, 12),
    ("Loratadine 10mg",      38, 10),
    ("Fexofenadine 120mg",   21,  7),
    ("Levocetirizine 5mg",   33,  9),
    ("Chlorpheniramine 4mg", 40, 10),
    ("Dextromethorphan 15mg",24,  7),
    ("Guaifenesin 100mg",    31,  8),
    ("Ambroxol 30mg",        42, 10),
    ("Bromhexine 8mg",       36,  9),
    ("Salbutamol 4mg",       19,  7),
    ("Montelukast 10mg",     16,  6),
    ("Diphenhydramine 25mg", 22,  7),
    ("Pseudoephedrine 60mg", 11,  5),
    ("Budesonide 200mcg",     8,  4),
    ("Ipratropium 20mcg",     5,  3),
    # ── Antibiotics ──
    ("Amoxicillin 250mg",    22,  8),
    ("Amoxicillin+Clavulanate 625mg", 14, 6),
    ("Ciprofloxacin 500mg",  17,  6),
    ("Doxycycline 100mg",    13,  5),
    ("Metronidazole 400mg",  26,  8),
    ("Cefixime 200mg",       11,  5),
    ("Cephalexin 500mg",     10,  5),
    ("Co-trimoxazole 480mg",  8,  4),
    ("Erythromycin 500mg",    9,  4),
    ("Clindamycin 300mg",     7,  3),
    ("Levofloxacin 500mg",   12,  5),
    ("Nitrofurantoin 100mg",  6,  3),
    ("Clarithromycin 500mg",  5,  3),
    # ── Diabetes ──
    ("Metformin 1000mg",     28,  8),
    ("Glibenclamide 5mg",    19,  7),
    ("Glipizide 5mg",        15,  6),
    ("Sitagliptin 50mg",     11,  5),
    ("Voglibose 0.2mg",       8,  4),
    ("Insulin Regular 100IU/ml", 7, 3),
    ("Insulin NPH 100IU/ml",  5,  2),
    ("Empagliflozin 10mg",    9,  3),
    ("Dapagliflozin 10mg",    6,  3),
    # ── Blood Pressure / Heart ──
    ("Lisinopril 10mg",      15,  5),
    ("Amlodipine 10mg",      18,  6),
    ("Atenolol 25mg",        24,  7),
    ("Atenolol 50mg",        14,  5),
    ("Enalapril 5mg",        12,  5),
    ("Losartan 50mg",        18,  6),
    ("Telmisartan 40mg",     11,  5),
    ("Hydrochlorothiazide 25mg", 14, 5),
    ("Furosemide 40mg",       9,  4),
    ("Spironolactone 25mg",   7,  3),
    ("Bisoprolol 5mg",       13,  5),
    # ── GI / Stomach ──
    ("Pantoprazole 40mg",    32, 10),
    ("Ranitidine 150mg",     20,  7),
    ("Domperidone 10mg",     27,  8),
    ("Ondansetron 4mg",      16,  6),
    ("Metoclopramide 10mg",  13,  5),
    ("Loperamide 2mg",       18,  6),
    ("ORS Powder",           50, 15),
    ("Zinc 20mg",            30, 10),
    ("Lactulose 10g",         9,  4),
    # ── Vitamins / Supplements ──
    ("Vitamin C 500mg",      65, 15),
    ("Vitamin D3 60000IU",   22,  7),
    ("Vitamin B12 500mcg",   29,  8),
    ("Iron 100mg",           24,  8),
    ("Calcium 500mg",        28,  8),
    ("Folic Acid 5mg",       20,  7),
    ("Multivitamin Tablet",  38, 10),
    # ── Thyroid / Hormones ──
    ("Levothyroxine 25mcg",  13,  5),
    ("Levothyroxine 50mcg",  11,  5),
    ("Levothyroxine 100mcg",  7,  3),
    ("Prednisolone 5mg",     16,  5),
    ("Hydrocortisone 20mg",   6,  3),
    # ── Cholesterol ──
    ("Atorvastatin 20mg",    19,  7),
    ("Rosuvastatin 10mg",    16,  6),
    # ── Mental Health / Neuro ──
    ("Alprazolam 0.25mg",     6,  3),
    ("Sertraline 50mg",       9,  4),
    # ── Skin ──
    ("Hydrocortisone Cream 1%",  10, 4),
    ("Clotrimazole Cream 1%",     8, 3),
    ("Mupirocin Ointment 2%",     6, 3),
    ("Betamethasone Cream 0.1%",  5, 2),
]


def init_db() -> None:
    """Create all tables and upsert inventory seed data. Safe to call multiple times."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS inventory (
                medicine_name      TEXT PRIMARY KEY,
                quantity           INTEGER NOT NULL,
                reorder_threshold  INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS prescriptions (
                prescription_id  TEXT PRIMARY KEY,
                patient_id       TEXT NOT NULL,
                medicine_name    TEXT NOT NULL,
                dosage           TEXT NOT NULL,
                notes            TEXT,
                status           TEXT NOT NULL DEFAULT 'pending',
                created_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seeded_patients (
                patient_id   TEXT PRIMARY KEY,
                seeded_at    TEXT NOT NULL
            );
        """)
        conn.executemany(
            "INSERT OR REPLACE INTO inventory"
            " (medicine_name, quantity, reorder_threshold) VALUES (?,?,?)",
            CORE_MEDS,
        )
        conn.commit()
    log.info("📦 DB initialised — %d medicines in inventory", len(CORE_MEDS))


# ── Per-retain idempotency helpers ───────────────────────────────────────────

def is_seed_key_done(seed_key: str) -> bool:
    """Return True if this seed retain has already been completed."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM seeded_patients WHERE patient_id = ?", (seed_key,)
        ).fetchone()
    return row is not None


def mark_seed_key_done(seed_key: str) -> None:
    """Record that this seed retain is complete so it is never repeated."""
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seeded_patients (patient_id, seeded_at) VALUES (?, ?)",
            (seed_key, datetime.datetime.now().isoformat()),
        )
        conn.commit()
