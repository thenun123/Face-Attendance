"""
JWT Authentication
──────────────────
- /api/v1/auth/login   → returns access token
- /api/v1/auth/me      → returns current user info
- require_auth         → FastAPI dependency (any valid token)
- require_admin        → FastAPI dependency (role == "admin" only)

Usage in a route:
    @router.get("/employees")
    async def list_employees(current_user: AdminUser = Depends(require_auth)):
        ...

    @router.delete("/employee/{id}")
    async def delete_employee(..., current_user: AdminUser = Depends(require_admin)):
        ...
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import AdminUser, get_db

router = APIRouter()
bearer_scheme = HTTPBearer()


# ── Pydantic models ──────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    email: str


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    department: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


# ── Password helpers ─────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── Token helpers ─────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── DB helpers ───────────────────────────────────────────────────────────────

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[AdminUser]:
    result = await db.execute(select(AdminUser).where(AdminUser.email == email))
    return result.scalar_one_or_none()


async def create_admin_user(
    db: AsyncSession,
    email: str,
    password: str,
    role: str = "viewer",
    department: Optional[str] = None,
) -> AdminUser:
    """Utility — call from a setup script or seed endpoint."""
    user = AdminUser(
        email=email,
        hashed_password=hash_password(password),
        role=role,
        department=department,
    )
    db.add(user)
    await db.flush()
    return user


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """Dependency: any authenticated user."""
    payload = decode_token(credentials.credentials)
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Token missing subject claim.")

    user = await get_user_by_email(db, email)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive.")
    return user


async def require_admin(
    current_user: AdminUser = Depends(require_auth),
) -> AdminUser:
    """Dependency: admin role only."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password → returns JWT."""
    user = await get_user_by_email(db, request.email)
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled.")

    token = create_access_token({"sub": user.email, "role": user.role})
    return TokenResponse(access_token=token, role=user.role, email=user.email)


@router.get("/auth/me", response_model=UserOut)
async def me(current_user: AdminUser = Depends(require_auth)):
    """Return current authenticated user info."""
    return current_user


@router.post("/auth/setup-admin", status_code=201)
async def setup_first_admin(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
    x_setup_token: Optional[str] = Header(None),
):
    """
    One-time endpoint: create the first admin user.
    Requires SETUP_TOKEN env var to be set and matching X-Setup-Token header.
    Disabled automatically once any admin exists.
    """
    # Gate 1: SETUP_TOKEN must be configured
    if not settings.SETUP_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="Admin setup is disabled. Set SETUP_TOKEN env var to enable.",
        )

    # Gate 2: Header must match
    if x_setup_token != settings.SETUP_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing setup token.",
        )

    from sqlalchemy import func
    result = await db.execute(
        select(func.count(AdminUser.id)).where(AdminUser.role == "admin")
    )
    admin_count = result.scalar()
    if admin_count > 0:
        raise HTTPException(
            status_code=400,
            detail="Admin already exists. Use /auth/login instead.",
        )
    user = await create_admin_user(db, request.email, request.password, role="admin")
    await db.commit()
    return {"message": f"Admin '{user.email}' created successfully."}
