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


@pytest.mark.asyncio
async def test_schema_indexes_exist():
    """Verify key indexes are present in the migrated schema."""
    from tests.conftest import test_engine
    async with test_engine.connect() as conn:
        result = await conn.execute(text(
            """SELECT indexname FROM pg_indexes
               WHERE schemaname='public'
               AND tablename IN ('users','tasks','task_steps','audit_log','api_keys','refresh_tokens','artifacts')"""
        ))
        indexes = {row[0] for row in result}
    required_indexes = {
        "idx_users_email_lower",
        "idx_tasks_user_status",
        "idx_task_steps_task",
        "idx_audit_user_time",
        "idx_api_keys_hash",
        "idx_refresh_tokens_hash",
        "idx_artifacts_task",
    }
    missing = required_indexes - indexes
    assert not missing, f"Missing indexes: {missing}"
