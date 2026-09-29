"""
Inventory queries and restock alerting (MODULE 4).
"""
import datetime
import logging
import pathlib

from app.db import get_db
from app.services.alerts import send_telegram

log = logging.getLogger("clinic.inventory")


def get_inventory_list() -> list[dict]:
    """Return the full inventory as a list of dicts."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM inventory").fetchall()
    return [dict(r) for r in rows]


def get_in_stock_medicines() -> list[str]:
    """Return medicine names that have quantity > 0."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT medicine_name FROM inventory WHERE quantity > 0"
        ).fetchall()
    return [r["medicine_name"] for r in rows]


def check_restock(medicine_name: str) -> None:
    """
    If the medicine has dropped below its reorder threshold:
      - Append one line to stores/requirements.txt (deduped).
      - Send a Telegram alert.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT quantity, reorder_threshold FROM inventory WHERE medicine_name = ?",
            (medicine_name,),
        ).fetchone()

    if not row or row["quantity"] >= row["reorder_threshold"]:
        return

    qty = row["quantity"]
    threshold = row["reorder_threshold"]
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    alert_line = f"{now} — {medicine_name} — qty: {qty} (below threshold {threshold})"

    stores_dir = pathlib.Path("stores")
    stores_dir.mkdir(exist_ok=True)
    req_file = stores_dir / "requirements.txt"

    # Deduplicate — only write if medicine is not already flagged
    if req_file.exists() and medicine_name in req_file.read_text():
        return

    with open(req_file, "a") as f:
        f.write(alert_line + "\n")
    log.warning("📋 RESTOCK FILE │ %s", alert_line)

    send_telegram(
        f"⚠️ *Low Stock Alert*\n\n"
        f"💊 *{medicine_name}*\n"
        f"📉 Current qty: {qty}\n"
        f"🔻 Threshold: {threshold}\n"
        f"🕐 {now}"
    )
