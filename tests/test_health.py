"""
Smoke tests — Phase 2 CI baseline.
These tests run against a real FastAPI app with a SQLite test database.
No ML inference is triggered (no face images submitted).
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Patch database to use SQLite for CI before importing app
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_ci.db")
os.environ.setdefault("JWT_SECRET", "test-secret-ci")
os.environ.setdefault("SETUP_TOKEN", "test-setup-token")

from app.main import app


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.mark.anyio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.anyio
async def test_docs_available(client):
    r = await client.get("/docs")
    assert r.status_code == 200


@pytest.mark.anyio
async def test_unauthenticated_employees_returns_401(client):
    r = await client.get("/api/v1/employees")
    assert r.status_code == 401


@pytest.mark.anyio
async def test_unauthenticated_recognize_returns_401(client):
    r = await client.post("/api/v1/recognize", data={})
    assert r.status_code == 401


@pytest.mark.anyio
async def test_login_wrong_credentials(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.com", "password": "wrong"},
    )
    assert r.status_code == 401


@pytest.mark.anyio
async def test_setup_admin_bad_token(client):
    r = await client.post(
        "/api/v1/auth/setup-admin",
        json={"email": "admin@test.com", "password": "pass123"},
        headers={"X-Setup-Token": "wrong-token"},
    )
    assert r.status_code == 403


@pytest.mark.anyio
async def test_full_admin_flow(client):
    """Create admin → login → get /me → list employees."""
    # 1. Create first admin
    r = await client.post(
        "/api/v1/auth/setup-admin",
        json={"email": "admin@ci.com", "password": "Str0ngPass!"},
        headers={"X-Setup-Token": "test-setup-token"},
    )
    assert r.status_code == 201

    # 2. Login
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ci.com", "password": "Str0ngPass!"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. /me
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "admin@ci.com"

    # 4. List employees (empty)
    r = await client.get("/api/v1/employees", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # 5. Attendance stats
    r = await client.get("/api/v1/attendance/stats", headers=headers)
    assert r.status_code == 200
    assert "total_employees" in r.json()
