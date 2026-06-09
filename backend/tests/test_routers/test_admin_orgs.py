import pytest
import uuid
from httpx import AsyncClient


async def _make_user_and_token(client: AsyncClient) -> tuple[str, str]:
    email = f"u_{uuid.uuid4().hex[:6]}@test.com"
    resp = await client.post("/api/v1/auth/register",
                             json={"email": email, "password": "Pass1234!Secret"})
    token = resp.json()["access_token"]
    return email, token


async def _make_operator_token(client: AsyncClient, db_session) -> str:
    from app.models.user import User, UserRole
    from app.auth.password import hash_password
    from datetime import datetime, timezone
    op = User(
        id=uuid.uuid4(),
        email=f"op_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        role=UserRole.operator,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(op)
    await db_session.commit()
    login = await client.post("/api/v1/auth/login",
                              json={"email": op.email, "password": "Pass1234!Secret"})
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_patch_org_requires_operator(client: AsyncClient, db_session):
    _, user_token = await _make_user_and_token(client)
    org_r = await client.post(
        "/api/v1/organizations",
        json={"name": "TestOrg", "slug": f"testorg-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    org_id = org_r.json()["id"]
    resp = await client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"max_concurrent_tasks": 10},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_org_sets_max_concurrent_tasks(client: AsyncClient, db_session):
    op_token = await _make_operator_token(client, db_session)
    _, user_token = await _make_user_and_token(client)
    org_r = await client.post(
        "/api/v1/organizations",
        json={"name": "OrgA", "slug": f"orga-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    org_id = org_r.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"max_concurrent_tasks": 10},
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["max_concurrent_tasks"] == 10


@pytest.mark.asyncio
async def test_patch_org_sets_llm_override(client: AsyncClient, db_session):
    op_token = await _make_operator_token(client, db_session)
    _, user_token = await _make_user_and_token(client)
    org_r = await client.post(
        "/api/v1/organizations",
        json={"name": "OrgB", "slug": f"orgb-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    org_id = org_r.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"llm_provider": "groq", "llm_model": "llama-3-70b"},
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["llm_provider"] == "groq"
    assert resp.json()["llm_model"] == "llama-3-70b"


@pytest.mark.asyncio
async def test_patch_org_sets_token_budget(client: AsyncClient, db_session):
    op_token = await _make_operator_token(client, db_session)
    _, user_token = await _make_user_and_token(client)
    org_r = await client.post(
        "/api/v1/organizations",
        json={"name": "OrgC", "slug": f"orgc-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    org_id = org_r.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"token_budget_monthly": 5_000_000},
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["token_budget_monthly"] == 5_000_000


@pytest.mark.asyncio
async def test_patch_org_nonexistent_returns_404(client: AsyncClient, db_session):
    op_token = await _make_operator_token(client, db_session)
    fake_id = str(uuid.uuid4())
    resp = await client.patch(
        f"/api/v1/admin/organizations/{fake_id}",
        json={"max_concurrent_tasks": 3},
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 404
