"""
Face Recognition Attendance System — Main FastAPI entry point (v2)

Changes from v1:
  - Auth router registered at /api/v1
  - CORS updated to allow Vercel frontend origins
  - Removed local unknown_faces static mount (now served from ImageKit)
  - APScheduler absent job unchanged
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.api import employees, recognition, attendance
from app.core import auth as auth_module
from app.db.database import init_db, AsyncSessionLocal
from app.db.crud import mark_absent_for_today
from app.core.config import settings

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def run_absent_job():
    try:
        async with AsyncSessionLocal() as db:
            count = await mark_absent_for_today(db)
            await db.commit()
            if count > 0:
                logger.info(f"[Absent Scheduler] Marked {count} employee(s) as Absent.")
    except Exception as e:
        logger.error(f"[Absent Scheduler] Error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Only create local dir if ImageKit is not configured (dev fallback)
    if not settings.imagekit_configured:
        os.makedirs(settings.UNKNOWN_FACES_DIR, exist_ok=True)
        logger.warning(
            "ImageKit not configured — unknown face snapshots will be saved locally. "
            "Set IMAGEKIT_* env vars for production."
        )

    scheduler.add_job(
        run_absent_job,
        trigger=IntervalTrigger(minutes=30),
        id="absent_marker",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Absent scheduler started.")

    yield

    scheduler.shutdown()


app = FastAPI(
    title="Face Recognition Attendance System",
    description="AI-powered attendance tracking. Auth required — POST /api/v1/auth/login first.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ── CORS: origins from env var (comma-separated) or localhost fallback ─────────
_default_origins = ["http://localhost:3000", "http://localhost:3001"]
ALLOWED_ORIGINS = (
    [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    if settings.CORS_ORIGINS
    else _default_origins
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_module.router,      prefix="/api/v1", tags=["Auth"])
app.include_router(employees.router,        prefix="/api/v1", tags=["Employees"])
app.include_router(recognition.router,      prefix="/api/v1", tags=["Recognition"])
app.include_router(attendance.router,       prefix="/api/v1", tags=["Attendance"])


@app.get("/health", tags=["Health"])
async def health_check():
    """Used by UptimeRobot to keep Render free tier awake."""
    return {"status": "ok", "version": settings.APP_VERSION}


# ── Local fallback: serve unknown face snapshots if ImageKit not used ─────────
if not settings.imagekit_configured:
    try:
        app.mount(
            "/unknown_faces",
            StaticFiles(directory=settings.UNKNOWN_FACES_DIR),
            name="unknown_faces",
        )
    except Exception:
        pass  # Dir doesn't exist yet — that's fine

# ── Serve legacy HTML frontend (optional — will be replaced by Next.js) ──────
try:
    app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
except Exception:
    pass
