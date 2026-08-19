import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.scheduled_task import ScheduledTask
from app.auth.password import hash_password
from app.auth.jwt import create_access_token


async def _auth_user():
    async with AsyncSessionLocal() as db:
        u = User(email=f"schedrt-{uuid.uuid4()}@t.com", password_hash=hash_password("x"), language="en")
        db.add(u)
        await db.commit()
        await db.refresh(u)
        token = create_access_token(str(u.id), u.role.value)
        return u, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_scheduled_tasks_requires_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/scheduled-tasks")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_scheduled_task_computes_next_run():
    user, headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/scheduled-tasks", headers=headers,
            json={"name": "Weekly digest", "goal_template": "Summarize this week's news",
                  "cron_expression": "0 9 * * 1"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Weekly digest"
    assert body["is_active"] is True
    assert body["next_run_at"] is not None


@pytest.mark.asyncio
async def test_create_scheduled_task_rejects_invalid_cron():
    user, headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/scheduled-tasks", headers=headers,
            json={"name": "Bad", "goal_template": "g", "cron_expression": "not-a-cron"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_scheduled_tasks_returns_only_own():
    user, headers = await _auth_user()
    other_user, other_headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/scheduled-tasks", headers=headers,
                          json={"name": "Mine", "goal_template": "g", "cron_expression": "0 9 * * *"})
        await client.post("/api/v1/scheduled-tasks", headers=other_headers,
                          json={"name": "Theirs", "goal_template": "g", "cron_expression": "0 9 * * *"})
        resp = await client.get("/api/v1/scheduled-tasks", headers=headers)

    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert names == ["Mine"]


@pytest.mark.asyncio
async def test_update_scheduled_task_can_pause_and_reschedule():
    user, headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post(
            "/api/v1/scheduled-tasks", headers=headers,
            json={"name": "Toggle me", "goal_template": "g", "cron_expression": "0 9 * * *"},
        )
        sched_id = create.json()["id"]

        resp = await client.patch(f"/api/v1/scheduled-tasks/{sched_id}", headers=headers,
                                  json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    async with AsyncSessionLocal() as db:
        sched = await db.get(ScheduledTask, uuid.UUID(sched_id))
        assert sched.is_active is False


@pytest.mark.asyncio
async def test_update_scheduled_task_rejects_other_users_task():
    user, headers = await _auth_user()
    other_user, other_headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post(
            "/api/v1/scheduled-tasks", headers=headers,
            json={"name": "Mine", "goal_template": "g", "cron_expression": "0 9 * * *"},
        )
        sched_id = create.json()["id"]
        resp = await client.patch(f"/api/v1/scheduled-tasks/{sched_id}", headers=other_headers,
                                  json={"is_active": False})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_scheduled_task():
    user, headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post(
            "/api/v1/scheduled-tasks", headers=headers,
            json={"name": "Delete me", "goal_template": "g", "cron_expression": "0 9 * * *"},
        )
        sched_id = create.json()["id"]
        resp = await client.delete(f"/api/v1/scheduled-tasks/{sched_id}", headers=headers)
    assert resp.status_code == 204

    async with AsyncSessionLocal() as db:
        assert await db.get(ScheduledTask, uuid.UUID(sched_id)) is None


@pytest.mark.asyncio
async def test_get_scheduled_task_404_for_unknown_id():
    user, headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/scheduled-tasks/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
