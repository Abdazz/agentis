import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from app.main import app
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.task import Task, TaskStatus
from app.auth.password import hash_password
from app.auth.jwt import create_access_token


async def _auth_user():
    async with AsyncSessionLocal() as db:
        u = User(email=f"ep-{uuid.uuid4()}@t.com", password_hash=hash_password("x"), language="en")
        db.add(u)
        await db.commit()
        await db.refresh(u)
        token = create_access_token(str(u.id), u.role.value)
        return u, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def no_enqueue():
    with patch("app.routers.tasks.run_agent_task") as mock:
        mock.delay.return_value = None
        yield mock


async def test_create_task_returns_201_and_stream_url(no_enqueue):
    user, headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/tasks", headers=headers,
                                 json={"goal": "do a thing", "language": "en"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "submitted"
    assert body["stream_url"].endswith("/stream")
    no_enqueue.delay.assert_called_once()


async def test_create_task_clamps_max_iterations(no_enqueue):
    user, headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/tasks", headers=headers,
                                 json={"goal": "g", "options": {"max_iterations": 9999}})
    assert resp.status_code == 201
    async with AsyncSessionLocal() as db:
        t = await db.get(Task, uuid.UUID(resp.json()["id"]))
        assert t.max_iterations == 50  # clamped to cap (BR-TASK-03)


async def test_concurrency_limit_returns_429(no_enqueue):
    user, headers = await _auth_user()
    async with AsyncSessionLocal() as db:
        for _ in range(5):
            db.add(Task(user_id=user.id, goal="g", language="en", status=TaskStatus.running))
        await db.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/tasks", headers=headers, json={"goal": "g"})
    assert resp.status_code == 429


async def test_list_tasks_returns_own_tasks(no_enqueue):
    user, headers = await _auth_user()
    async with AsyncSessionLocal() as db:
        db.add(Task(user_id=user.id, goal="listme", language="en", status=TaskStatus.submitted))
        await db.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/tasks", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body and "pagination" in body
    assert any(t["goal"] == "listme" for t in body["data"])


async def test_cancel_task_returns_200(no_enqueue):
    user, headers = await _auth_user()
    async with AsyncSessionLocal() as db:
        t = Task(user_id=user.id, goal="g", language="en", status=TaskStatus.running)
        db.add(t)
        await db.commit()
        tid = str(t.id)
    transport = ASGITransport(app=app)
    with patch("app.routers.tasks.celery_app.control.revoke"):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(f"/api/v1/tasks/{tid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_create_task_uses_accept_language_header_when_body_omits_it(no_enqueue):
    user, headers = await _auth_user()
    headers = {**headers, "Accept-Language": "fr-FR,fr;q=0.9"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/tasks", headers=headers,
                                 json={"goal": "do a thing"})
    assert resp.status_code == 201
    async with AsyncSessionLocal() as db:
        t = await db.get(Task, uuid.UUID(resp.json()["id"]))
        assert t.language == "fr"


async def test_create_task_detects_language_from_goal_text(no_enqueue):
    user, headers = await _auth_user()  # account language defaults to "en"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/tasks", headers=headers,
            json={"goal": "Recherche les derniers articles sur l'intelligence "
                          "artificielle et fais-moi un résumé détaillé, s'il te plaît."},
        )
    assert resp.status_code == 201
    async with AsyncSessionLocal() as db:
        t = await db.get(Task, uuid.UUID(resp.json()["id"]))
        assert t.language == "fr"  # detected, overriding the "en" account default


async def test_create_task_falls_back_to_account_language_when_ambiguous(no_enqueue):
    user, headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/tasks", headers=headers, json={"goal": "ok"})
    assert resp.status_code == 201
    async with AsyncSessionLocal() as db:
        t = await db.get(Task, uuid.UUID(resp.json()["id"]))
        assert t.language == user.language  # "en", the account default
