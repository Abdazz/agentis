import pytest
import uuid
from httpx import AsyncClient


def _make_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_organization(client: AsyncClient):
    email = f"u_{uuid.uuid4().hex[:8]}@test.com"
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    token = r.json()["access_token"]
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Acme Corp", "slug": f"acme-{uuid.uuid4().hex[:6]}"},
        headers=_make_headers(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Acme Corp"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_org_duplicate_slug_fails(client: AsyncClient):
    email = f"u_{uuid.uuid4().hex[:8]}@test.com"
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    token = r.json()["access_token"]
    slug = f"dup-{uuid.uuid4().hex[:6]}"
    await client.post("/api/v1/organizations", json={"name": "A", "slug": slug}, headers=_make_headers(token))
    resp = await client.post("/api/v1/organizations", json={"name": "B", "slug": slug}, headers=_make_headers(token))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_my_organizations(client: AsyncClient):
    email = f"u_{uuid.uuid4().hex[:8]}@test.com"
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    token = r.json()["access_token"]
    slug = f"org-{uuid.uuid4().hex[:6]}"
    await client.post("/api/v1/organizations", json={"name": "Org1", "slug": slug}, headers=_make_headers(token))
    resp = await client.get("/api/v1/organizations", headers=_make_headers(token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert any(o["slug"] == slug for o in resp.json())


@pytest.mark.asyncio
async def test_set_active_organization(client: AsyncClient):
    email = f"u_{uuid.uuid4().hex[:8]}@test.com"
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    token = r.json()["access_token"]
    org_r = await client.post("/api/v1/organizations", json={"name": "Active Org", "slug": f"active-{uuid.uuid4().hex[:6]}"}, headers=_make_headers(token))
    org_id = org_r.json()["id"]
    resp = await client.patch("/api/v1/organizations/active", json={"organization_id": org_id}, headers=_make_headers(token))
    assert resp.status_code == 200
    assert resp.json()["active_organization_id"] == org_id
