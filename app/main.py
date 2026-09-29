"""
FastAPI application factory.

Import the `app` object from here:
    uvicorn app.main:app --reload

The root main.py shim also re-exports it so that
    uvicorn main:app
continues to work.
"""
import logging
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routers import admin, doctor, health, patient, pharmacy
from app.services.memory import seed_patient_memory

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("clinic")


# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🔗 HINDSIGHT_BASE_URL = %s", settings.HINDSIGHT_BASE_URL)
    log.info("🔧 DEMO_MODE          = %s", settings.DEMO_MODE)
    log.info(
        "🔌 Integrations       — hindsight=%s | groq=%s | telegram=%s",
        settings.hindsight_configured,
        settings.groq_configured,
        settings.telegram_configured,
    )
    init_db()
    await seed_patient_memory()
    log.info("✅ Clinic backend ready — http://127.0.0.1:8000")
    yield


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Family Clinic Memory Assistant",
    description=(
        "FastAPI backend connecting a doctor's desk and pharmacy counter "
        "via Hindsight persistent memory."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(doctor.router)
app.include_router(pharmacy.router)
app.include_router(patient.router)
app.include_router(admin.router)

# ── Static files & page routes ────────────────────────────────────────────────
# static/ lives at the repo root, one level above this file (app/main.py)
STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"
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
