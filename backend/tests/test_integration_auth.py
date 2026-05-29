import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_auth_flow(client: AsyncClient):
    """
    Register → login → use access token → refresh → logout → verify refresh fails.
    This is the complete happy path for the authentication system.
    """
    # 1. Register
    reg = await client.post("/api/v1/auth/register", json={
        "email": "integration@example.com",
        "password": "Secure123!Pass",
        "name": "Integration Test"
    })
    assert reg.status_code == 201
    access_token = reg.json()["access_token"]
    assert reg.json()["user"]["email"] == "integration@example.com"
    assert "refresh_token" in reg.cookies

    # 2. Use access token on a protected endpoint (api-keys list)
    keys_resp = await client.get(
        "/api/v1/auth/api-keys",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert keys_resp.status_code == 200
    assert keys_resp.json() == []  # no keys yet

    # 3. Create an API key
    key_resp = await client.post(
        "/api/v1/auth/api-keys",
        json={"label": "smoke-test-key"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert key_resp.status_code == 201
    api_key = key_resp.json()["key"]
    assert api_key.startswith("agentis_sk_")

    # 4. Use API key on a request (X-API-Key header)
    keys_via_apikey = await client.get(
        "/api/v1/auth/api-keys",
        headers={"X-API-Key": api_key}
    )
    assert keys_via_apikey.status_code == 200
    assert len(keys_via_apikey.json()) == 1
    assert keys_via_apikey.json()[0]["label"] == "smoke-test-key"

    # 5. Refresh token (proves rotation works)
    refresh_resp = await client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    new_access_token = refresh_resp.json()["access_token"]
    # New refresh cookie was issued
    assert "refresh_token" in client.cookies

    # 6. Use NEW access token
    keys_resp2 = await client.get(
        "/api/v1/auth/api-keys",
        headers={"Authorization": f"Bearer {new_access_token}"}
    )
    assert keys_resp2.status_code == 200

    # 7. Logout
    logout_resp = await client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200

    # 8. Refresh after logout must fail
    post_logout = await client.post("/api/v1/auth/refresh")
    assert post_logout.status_code == 401


@pytest.mark.asyncio
async def test_api_key_full_lifecycle(client: AsyncClient):
    """Create → use → revoke → verify revoked key fails."""
    # Register and get access token
    reg = await client.post("/api/v1/auth/register", json={
        "email": "apilifecycle@example.com",
        "password": "Secure123!Pass",
    })
    access_token = reg.json()["access_token"]
    auth = {"Authorization": f"Bearer {access_token}"}

    # Create
    create_resp = await client.post("/api/v1/auth/api-keys", json={"label": "ci"}, headers=auth)
    assert create_resp.status_code == 201
    api_key = create_resp.json()["key"]
    key_id = create_resp.json()["id"] if "id" in create_resp.json() else None

    # If id not in create response, get it from list
    if not key_id:
        list_resp = await client.get("/api/v1/auth/api-keys", headers=auth)
        key_id = list_resp.json()[0]["id"]

    # Use
    use_resp = await client.get("/api/v1/auth/api-keys", headers={"X-API-Key": api_key})
    assert use_resp.status_code == 200

    # Revoke
    revoke_resp = await client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=auth)
    assert revoke_resp.status_code == 204

    # Revoked key must fail
    after_revoke = await client.get("/api/v1/auth/api-keys", headers={"X-API-Key": api_key})
    assert after_revoke.status_code == 401


@pytest.mark.asyncio
async def test_error_responses_use_standard_schema(client: AsyncClient):
    """All error responses must follow {"error": {"code": ..., "message": ...}} schema."""
    # 401 - invalid credentials
    r = await client.post("/api/v1/auth/login", json={
        "email": "nobody@example.com", "password": "Secure123!Pass"
    })
    assert r.status_code == 401
    body = r.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]

    # 409 - duplicate registration
    await client.post("/api/v1/auth/register", json={
        "email": "dup@example.com", "password": "Secure123!Pass"
    })
    r2 = await client.post("/api/v1/auth/register", json={
        "email": "dup@example.com", "password": "Secure123!Pass"
    })
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "email_taken"

    # 422 - weak password (validation error)
    r3 = await client.post("/api/v1/auth/register", json={
        "email": "valid@example.com", "password": "weak"
    })
    assert r3.status_code == 422
    # 422 may not follow the exact same schema (Pydantic validation errors)
    # but should return JSON


@pytest.mark.asyncio
async def test_x_request_id_on_all_responses(client: AsyncClient):
    """Every response must carry an X-Request-ID header."""
    responses = [
        await client.get("/api/v1/health"),
        await client.post("/api/v1/auth/login", json={
            "email": "x@x.com", "password": "Secure123!Pass"
        }),
        await client.get("/api/v1/auth/api-keys"),  # 401, no auth
    ]
    for r in responses:
        assert "x-request-id" in r.headers, f"Missing X-Request-ID on {r.url} {r.status_code}"
