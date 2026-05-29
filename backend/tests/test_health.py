import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from app.main import app
from tests.conftest import test_engine


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_schema_tables_exist():
    async with test_engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ))
        tables = {row[0] for row in result}
    expected = {"users", "tasks", "task_steps", "artifacts", "organizations",
                "organization_memberships", "audit_log", "refresh_tokens", "api_keys"}
    assert expected.issubset(tables)
