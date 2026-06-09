import pytest
import uuid
from httpx import AsyncClient
from unittest.mock import patch


async def _register_login(client: AsyncClient) -> tuple[str, str]:
    email = f"u_{uuid.uuid4().hex[:6]}@test.com"
    r = await client.post("/api/v1/auth/register",
                          json={"email": email, "password": "Pass1234!Secret"})
    token = r.json()["access_token"]
    return email, token


@pytest.mark.asyncio
async def test_task_rejected_when_tool_not_in_org_allowlist(client: AsyncClient, db_session):
    """If org.allowed_tools is set, submitting a tool outside it returns 422."""
    from app.models.org import Organization, OrganizationMembership
    from app.models.user import User, UserRole
    from sqlalchemy import select
    from datetime import datetime, timezone

    _, token = await _register_login(client)

    result = await db_session.execute(select(User).order_by(User.created_at.desc()))
    user = result.scalars().first()

    org = Organization(
        id=uuid.uuid4(), name="RestrictedOrg",
        slug=f"restricted-{uuid.uuid4().hex[:6]}",
        allowed_tools=["browser", "web_search"],
        max_concurrent_tasks=5,
    )
    db_session.add(org)
    await db_session.flush()
    db_session.add(OrganizationMembership(
        id=uuid.uuid4(), organization_id=org.id, user_id=user.id,
        role=UserRole.user, created_at=datetime.now(timezone.utc),
    ))
    user.active_organization_id = org.id
    await db_session.commit()

    with patch("app.routers.tasks.run_agent_task") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            "/api/v1/tasks",
            json={"goal": "Do something", "options": {"allowed_tools": ["code_executor"]}},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_task_rejected_when_org_concurrent_cap_hit(client: AsyncClient, db_session):
    """If org.max_concurrent_tasks=1, second task submission returns 429."""
    from app.models.org import Organization, OrganizationMembership
    from app.models.user import User, UserRole
    from app.models.task import Task, TaskStatus
    from sqlalchemy import select
    from datetime import datetime, timezone

    _, token = await _register_login(client)
    result = await db_session.execute(select(User).order_by(User.created_at.desc()))
    user = result.scalars().first()

    org = Organization(
        id=uuid.uuid4(), name="TightOrg",
        slug=f"tight-{uuid.uuid4().hex[:6]}",
        max_concurrent_tasks=1,
    )
    db_session.add(org)
    await db_session.flush()
    db_session.add(OrganizationMembership(
        id=uuid.uuid4(), organization_id=org.id, user_id=user.id,
        role=UserRole.user, created_at=datetime.now(timezone.utc),
    ))
    user.active_organization_id = org.id

    running_task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="already running",
        status=TaskStatus.running,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(running_task)
    await db_session.commit()

    with patch("app.routers.tasks.run_agent_task") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            "/api/v1/tasks",
            json={"goal": "Another task", "options": {}},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_task_uses_org_allowed_tools_as_default(client: AsyncClient, db_session):
    """If org.allowed_tools set and request has no allowed_tools, org list is used."""
    from app.models.org import Organization, OrganizationMembership
    from app.models.user import User, UserRole
    from sqlalchemy import select
    from datetime import datetime, timezone

    _, token = await _register_login(client)
    result = await db_session.execute(select(User).order_by(User.created_at.desc()))
    user = result.scalars().first()

    org = Organization(
        id=uuid.uuid4(), name="DefaultToolsOrg",
        slug=f"deftools-{uuid.uuid4().hex[:6]}",
        allowed_tools=["browser", "web_search"],
        max_concurrent_tasks=5,
    )
    db_session.add(org)
    await db_session.flush()
    db_session.add(OrganizationMembership(
        id=uuid.uuid4(), organization_id=org.id, user_id=user.id,
        role=UserRole.user, created_at=datetime.now(timezone.utc),
    ))
    user.active_organization_id = org.id
    await db_session.commit()

    with patch("app.routers.tasks.run_agent_task") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            "/api/v1/tasks",
            json={"goal": "Research something", "options": {}},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    task_data = resp.json()
    assert set(task_data.get("allowed_tools") or []) == {"browser", "web_search"}
