"""
Database layer: async SQLAlchemy engine for Supabase (PostgreSQL).

Changes from v1 (SQLite):
  - Engine uses asyncpg instead of aiosqlite
  - Added AdminUser model for JWT auth
  - pool_pre_ping=True keeps connections alive on Supabase free tier
  - Embeddings stored as ARRAY(Float) instead of JSON Text
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, DateTime, Date, Integer,
    ForeignKey, Boolean, Text, ARRAY
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from app.core.config import settings

# pool_pre_ping reconnects if Supabase drops idle connections
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    },
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


# ── ORM Models ────────────────────────────────────────────────────────────────

class AdminUser(Base):
    """System users who can log into the dashboard."""
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="viewer")          # "admin" | "viewer"
    department = Column(String, nullable=True)       # viewers only see their dept
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EmployeeModel(Base):
    __tablename__ = "employees"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    department = Column(String, default="General")
    role = Column(String, default="employee")
    shift_start = Column(String, default="09:00")
    shift_end = Column(String, default="17:00")
    status = Column(String, default="active")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    embeddings = relationship(
        "EmbeddingModel", back_populates="employee", cascade="all, delete-orphan"
    )
    attendance_records = relationship(
        "AttendanceModel", back_populates="employee", cascade="all, delete-orphan"
    )


class EmbeddingModel(Base):
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String, ForeignKey("employees.id"), nullable=False)
    # PostgreSQL native float array — efficient storage & compatible with pgvector
    vector = Column(ARRAY(Float), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    employee = relationship("EmployeeModel", back_populates="embeddings")


class AttendanceModel(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String, ForeignKey("employees.id"), nullable=False)
    date = Column(Date, nullable=False)
    check_in_time = Column(DateTime, nullable=True)
    check_out_time = Column(DateTime, nullable=True)
    total_hours = Column(Float, nullable=True)
    status = Column(String, default="Present")
    confidence = Column(Float, nullable=True)

    employee = relationship("EmployeeModel", back_populates="attendance_records")


class UnknownFaceModel(Base):
    __tablename__ = "unknown_faces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # Stores ImageKit URL (e.g. https://ik.imagekit.io/xxx/unknown_faces/file.jpg)
    snapshot_url = Column(String, nullable=True)
    # ImageKit file ID — needed to delete the image later
    imagekit_file_id = Column(String, nullable=True)
    resolved = Column(Boolean, default=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def init_db():
    """Create all tables on startup (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
