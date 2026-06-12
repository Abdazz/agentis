"""Tests for /api/v1/templates endpoints and template_id on POST /tasks (E1)."""
import uuid as _uuid
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from unittest.mock import patch

from app.models.user import User, UserRole
from app.models.task_template import TaskTemplate
from app.auth.password import hash_password
from app.auth.jwt import create_access_token


async def _make_user(db_session, role: UserRole = UserRole.user) -> tuple[User, dict]:
    """Create a user via the db_session fixture (rolled back after each test)."""
    email = f"tmpl-{_uuid.uuid4().hex[:8]}@test.com"
    u = User(
        id=_uuid.uuid4(),
        email=email,
        password_hash=hash_password("Pass1234!"),
        role=role,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(u)
    await db_session.flush()
    token = create_access_token(str(u.id), u.role.value)
    return u, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_templates_empty(client: AsyncClient, db_session):
    """GET /templates returns an empty list for a fresh user with no templates."""
    _, headers = await _make_user(db_session)
    # Create a private template for another user to ensure isolation
    other, _ = await _make_user(db_session)
    private = TaskTemplate(
        id=_uuid.uuid4(),
        name="Other Private",
        goal_template="private goal",
        is_public=False,
        created_by=other.id,
    )
    db_session.add(private)
    await db_session.flush()

    resp = await client.get("/api/v1/templates", headers=headers)
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert str(private.id) not in ids


@pytest.mark.asyncio
async def test_create_template_returns_201(client: AsyncClient, db_session):
    """POST /templates creates a template and returns 201."""
    _, headers = await _make_user(db_session)
    payload = {
        "name": "Research Template",
        "description": "A template for research tasks",
        "goal_template": "Research the following topic: {topic}",
        "category": "research",
        "is_public": True,
    }
    resp = await client.post("/api/v1/templates", json=payload, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Research Template"
    assert body["goal_template"] == "Research the following topic: {topic}"
    assert body["category"] == "research"
    assert body["is_public"] is True
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_list_templates_returns_created(client: AsyncClient, db_session):
    """GET /templates returns a template that was previously created."""
    _, headers = await _make_user(db_session)
    create_resp = await client.post(
        "/api/v1/templates",
        json={"name": "My Template", "goal_template": "Do this: {goal}", "is_public": False},
        headers=headers,
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/templates", headers=headers)
    assert list_resp.status_code == 200
    ids = [t["id"] for t in list_resp.json()]
    assert template_id in ids


@pytest.mark.asyncio
async def test_list_templates_filters_by_category(client: AsyncClient, db_session):
    """GET /templates?category= filters by category."""
    _, headers = await _make_user(db_session)
    await client.post(
        "/api/v1/templates",
        json={"name": "Code Template", "goal_template": "Write code: {spec}", "category": "code"},
        headers=headers,
    )
    await client.post(
        "/api/v1/templates",
        json={"name": "Writing Template", "goal_template": "Write an article: {topic}", "category": "writing"},
        headers=headers,
    )

    code_resp = await client.get("/api/v1/templates?category=code", headers=headers)
    assert code_resp.status_code == 200
    results = code_resp.json()
    assert all(t["category"] == "code" for t in results)
    names = [t["name"] for t in results]
    assert "Code Template" in names
    assert "Writing Template" not in names


@pytest.mark.asyncio
async def test_delete_template_as_owner_returns_204(client: AsyncClient, db_session):
    """DELETE /templates/{id} as owner succeeds with 204."""
    _, headers = await _make_user(db_session)
    create_resp = await client.post(
        "/api/v1/templates",
        json={"name": "ToDelete", "goal_template": "Delete me"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/templates/{template_id}", headers=headers)
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_template_as_non_owner_returns_403(client: AsyncClient, db_session):
    """DELETE /templates/{id} as a different user returns 403."""
    _, owner_headers = await _make_user(db_session)
    _, other_headers = await _make_user(db_session)

    create_resp = await client.post(
        "/api/v1/templates",
        json={"name": "OwnerOnly", "goal_template": "Private goal", "is_public": False},
        headers=owner_headers,
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/templates/{template_id}", headers=other_headers)
    assert del_resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_template_as_admin_succeeds(client: AsyncClient, db_session):
    """DELETE /templates/{id} as admin can delete another user's template."""
    _, owner_headers = await _make_user(db_session, role=UserRole.user)
    _, admin_headers = await _make_user(db_session, role=UserRole.admin)

    create_resp = await client.post(
        "/api/v1/templates",
        json={"name": "AdminTarget", "goal_template": "Admin can delete this"},
        headers=owner_headers,
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/templates/{template_id}", headers=admin_headers)
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_post_task_with_template_id_uses_template_goal(client: AsyncClient, db_session):
    """POST /tasks with template_id uses the template goal."""
    _, headers = await _make_user(db_session)

    create_resp = await client.post(
        "/api/v1/templates",
        json={"name": "Task Template", "goal_template": "Use this template goal"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    with patch("app.routers.tasks.run_agent_task") as mock_task:
        mock_task.delay.return_value = None
        task_resp = await client.post(
            "/api/v1/tasks",
            json={"template_id": template_id},
            headers=headers,
        )

    assert task_resp.status_code == 201
    assert task_resp.json()["goal"] == "Use this template goal"


@pytest.mark.asyncio
async def test_post_task_with_template_id_and_goal_concatenates(client: AsyncClient, db_session):
    """POST /tasks with template_id + goal concatenates them."""
    _, headers = await _make_user(db_session)

    create_resp = await client.post(
        "/api/v1/templates",
        json={"name": "Concat Template", "goal_template": "Template prefix"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    with patch("app.routers.tasks.run_agent_task") as mock_task:
        mock_task.delay.return_value = None
        task_resp = await client.post(
            "/api/v1/tasks",
            json={"template_id": template_id, "goal": "User suffix"},
            headers=headers,
        )

    assert task_resp.status_code == 201
    assert task_resp.json()["goal"] == "Template prefix\n\nUser suffix"


@pytest.mark.asyncio
async def test_post_task_with_unknown_template_id_returns_404(client: AsyncClient, db_session):
    """POST /tasks with a non-existent template_id returns 404."""
    _, headers = await _make_user(db_session)

    with patch("app.routers.tasks.run_agent_task") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            "/api/v1/tasks",
            json={"template_id": str(_uuid.uuid4())},
            headers=headers,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_task_with_private_template_of_other_user_returns_404(client: AsyncClient, db_session):
    """POST /tasks cannot use another user's private template (returns 404)."""
    owner, owner_headers = await _make_user(db_session)
    _, other_headers = await _make_user(db_session)

    # Owner creates a private template
    create_resp = await client.post(
        "/api/v1/templates",
        json={"name": "Private", "goal_template": "Secret goal", "is_public": False},
        headers=owner_headers,
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    # Other user tries to use it via POST /tasks
    with patch("app.routers.tasks.run_agent_task") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            "/api/v1/tasks",
            json={"template_id": template_id},
            headers=other_headers,
        )

    assert resp.status_code == 404
