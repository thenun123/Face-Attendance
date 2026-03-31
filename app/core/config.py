"""
Application configuration — loaded from environment variables.
Supports Supabase (PostgreSQL), ImageKit, and JWT auth.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # ── App ──────────────────────────────────────────────
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    TIMEZONE: str = "Asia/Karachi"

    # ── Database (Supabase PostgreSQL) ───────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/attendance"

    # ── JWT Auth ─────────────────────────────────────────
    JWT_SECRET: str = "change-this-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480          # 8 hours

    # ── ImageKit ─────────────────────────────────────────
    IMAGEKIT_PUBLIC_KEY: str = ""
    IMAGEKIT_PRIVATE_KEY: str = ""
    IMAGEKIT_URL_ENDPOINT: str = ""
    IMAGEKIT_UPLOAD_FOLDER: str = "/face_attendance/unknown_faces"

    # ── Model ────────────────────────────────────────────
    MODEL_NAME: str = "vggface2"
    EMBEDDING_DIM: int = 512

    # ── Recognition ──────────────────────────────────────
    RECOGNITION_THRESHOLD: float = 0.65
    CONFIRM_FRAMES: int = 3

    # ── Attendance Rules ─────────────────────────────────
    ANTI_SPAM_MINUTES: int = 5
    DEFAULT_SHIFT_START: str = "09:00"
    DEFAULT_SHIFT_END: str = "17:00"
    LATE_GRACE_MINUTES: int = 10
    HALF_DAY_HOUR: int = 11

    # ── Legacy local path (fallback if ImageKit not configured) ──
    UNKNOWN_FACES_DIR: str = "unknown_faces"

    # ── Security ─────────────────────────────────────────
    SETUP_TOKEN: str = ""                              # required to call /auth/setup-admin
    CORS_ORIGINS: str = ""                             # comma-separated, e.g. "http://localhost:3000,https://your-app.vercel.app"

    CAMERA_INDEX: int = 0

    @property
    def imagekit_configured(self) -> bool:
        """True if all three ImageKit credentials are set."""
        return bool(
            self.IMAGEKIT_PUBLIC_KEY
            and self.IMAGEKIT_PRIVATE_KEY
            and self.IMAGEKIT_URL_ENDPOINT
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
