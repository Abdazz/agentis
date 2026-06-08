import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, UserRole
from app.auth.jwt import create_access_token
import uuid


@pytest.mark.asyncio
async def test_admin_stats_requires_admin(client: AsyncClient):
    """Regular user should get 403 on admin endpoints."""
    # Register + login as normal user
    email = f"user_{uuid.uuid4().hex[:8]}@test.com"
    resp = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    resp = await client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_stats_returns_data_for_admin(client: AsyncClient, db_session: AsyncSession):
    """Admin user gets usage stats."""
    email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    resp = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    assert resp.status_code == 201
    # Promote to admin directly in DB
    await db_session.execute(update(User).where(User.email == email).values(role=UserRole.admin))
    await db_session.commit()
    # Get fresh token for admin
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    token = create_access_token(user_id=str(user.id), role="admin")
    resp = await client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks_today" in data
    assert "active_users" in data
    assert "tokens_this_month" in data


@pytest.mark.asyncio
async def test_admin_users_list_paginated(client: AsyncClient, db_session: AsyncSession):
    """GET /admin/users returns paginated user list."""
    email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    resp = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    assert resp.status_code == 201
    await db_session.execute(update(User).where(User.email == email).values(role=UserRole.admin))
    await db_session.commit()
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    token = create_access_token(user_id=str(user.id), role="admin")
    resp = await client.get("/api/v1/admin/users?limit=10&offset=0", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_admin_audit_log_returns_list(client: AsyncClient, db_session: AsyncSession):
    """GET /admin/audit returns audit event list."""
    email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    resp = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    assert resp.status_code == 201
    await db_session.execute(update(User).where(User.email == email).values(role=UserRole.admin))
    await db_session.commit()
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    token = create_access_token(user_id=str(user.id), role="admin")
    resp = await client.get("/api/v1/admin/audit?limit=20", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json().get("items"), list)
