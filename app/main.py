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

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db import init_db, seed_demo_users
from app.routers import admin, auth, doctor, health, patient, pharmacy
from app.services.memory import seed_patient_memory
from app.services.rate_limit import limiter

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
    log.info("⚡ RATELIMIT_ENABLED  = %s", settings.RATELIMIT_ENABLED)
    log.info(
        "🔌 Integrations       — hindsight=%s | groq=%s | telegram=%s",
        settings.hindsight_configured,
        settings.groq_configured,
        settings.telegram_configured,
    )
    init_db()
    seed_demo_users()          # no-op unless DEMO_MODE=true
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
    version="0.3.0",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate limiting ─────────────────────────────────────────────────────────────
app.state.limiter = limiter


# ── Exception handlers — generic messages, never stack traces ─────────────────

@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down and try again."},
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request data", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log with traceback, but return a generic 500 to the client."""
    log.error(
        "Unhandled %s on %s %s",
        type(exc).__name__, request.method, request.url.path,
        exc_info=True,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(doctor.router)
app.include_router(pharmacy.router)
app.include_router(patient.router)
app.include_router(admin.router)

# ── Static files & page routes ────────────────────────────────────────────────
STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/doctor-page")
async def serve_doctor():
    return FileResponse(str(STATIC_DIR / "doctor.html"))


@app.get("/pharmacy-page")
async def serve_pharmacy():
    return FileResponse(str(STATIC_DIR / "pharmacy.html"))
