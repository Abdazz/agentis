import pytest
import uuid
from httpx import AsyncClient
from unittest.mock import patch
from datetime import datetime, timezone
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.auth.password import hash_password


@pytest.mark.asyncio
async def test_list_subtasks_returns_children(client: AsyncClient, db_session):
    user = User(
        id=uuid.uuid4(), email=f"st_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    parent = Task(
        id=uuid.uuid4(), user_id=user.id, goal="parent goal",
        status=TaskStatus.running, agent_role="supervisor",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(parent)
    await db_session.flush()

    child = Task(
        id=uuid.uuid4(), user_id=user.id, goal="child goal",
        status=TaskStatus.completed, parent_task_id=parent.id, agent_role="research",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(child)
    await db_session.commit()

    login = await client.post("/api/v1/auth/login",
                              json={"email": user.email, "password": "Pass1234!Secret"})
    if login.status_code != 200:
        await client.post("/api/v1/auth/register",
                          json={"email": user.email, "password": "Pass1234!Secret"})
        login = await client.post("/api/v1/auth/login",
                                  json={"email": user.email, "password": "Pass1234!Secret"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(f"/api/v1/tasks/{parent.id}/subtasks", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(s["id"] == str(child.id) for s in data)
    assert any(s.get("agent_role") == "research" for s in data)


@pytest.mark.asyncio
async def test_list_subtasks_empty_for_leaf_task(client: AsyncClient, db_session):
    reg = await client.post("/api/v1/auth/register",
                            json={"email": f"st2_{uuid.uuid4().hex[:6]}@test.com",
                                  "password": "Pass1234!Secret"})
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    with patch("app.routers.tasks.run_agent_task") as mock_task:
        mock_task.delay.return_value = None
        task_resp = await client.post("/api/v1/tasks", json={"goal": "single task"}, headers=headers)
    task_id = task_resp.json()["id"]
    resp = await client.get(f"/api/v1/tasks/{task_id}/subtasks", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_subtasks_idor_rejected(client: AsyncClient, db_session):
    reg_a = await client.post("/api/v1/auth/register",
                              json={"email": f"a_{uuid.uuid4().hex[:6]}@test.com",
                                    "password": "Pass1234!Secret"})
    token_a = reg_a.json()["access_token"]
    with patch("app.routers.tasks.run_agent_task") as mock_task:
        mock_task.delay.return_value = None
        task_resp = await client.post("/api/v1/tasks", json={"goal": "private"},
                                      headers={"Authorization": f"Bearer {token_a}"})
    task_id = task_resp.json()["id"]

    reg_b = await client.post("/api/v1/auth/register",
                              json={"email": f"b_{uuid.uuid4().hex[:6]}@test.com",
                                    "password": "Pass1234!Secret"})
    token_b = reg_b.json()["access_token"]
    resp = await client.get(f"/api/v1/tasks/{task_id}/subtasks",
                            headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 404
