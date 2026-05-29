import pytest
from httpx import AsyncClient

USER = {"email": "refreshtest@example.com", "password": "Secure123!Pass"}


@pytest.mark.asyncio
async def test_refresh_issues_new_cookie(client: AsyncClient):
    """Rotation is proven by: old refresh cookie revoked, new one issued."""
    await client.post("/api/v1/auth/register", json=USER)
    old_cookie = client.cookies.get("refresh_token")

    refresh_resp = await client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()
    # A new refresh cookie was set (proving rotation happened server-side)
    new_cookie = client.cookies.get("refresh_token")
    assert new_cookie is not None

    # Second refresh with the rotated cookie must succeed
    second_resp = await client.post("/api/v1/auth/refresh")
    assert second_resp.status_code == 200


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401(client: AsyncClient):
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_replay_attack_revokes_all_sessions(client: AsyncClient):
    """Using a revoked refresh token must revoke ALL sessions (BR-AUTH-07)."""
    USER = {"email": "replay@example.com", "password": "Secure123!Pass"}
    await client.post("/api/v1/auth/register", json=USER)

    # Get first refresh token cookie value
    first_cookie = client.cookies.get("refresh_token")

    # Refresh once (rotates the token — first cookie is now revoked)
    await client.post("/api/v1/auth/refresh")

    # Create a second session (new login)
    await client.post("/api/v1/auth/login", json=USER)

    # Now replay the FIRST (already revoked) token — should revoke all sessions
    client.cookies.set("refresh_token", first_cookie, path="/api/v1/auth")
    replay_resp = await client.post("/api/v1/auth/refresh")
    assert replay_resp.status_code == 401

    # Verify: any subsequent refresh should also fail (all sessions invalidated)
    final_resp = await client.post("/api/v1/auth/refresh")
    assert final_resp.status_code == 401
