# Phase 3C — Per-Org Advanced Config: LLM Override, Tool Restrictions, Token Budgets : Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the already-modelled `Organization` columns (`llm_provider`, `llm_model`, `allowed_tools`, `token_budget_monthly`, `max_concurrent_tasks`) into runtime enforcement: per-org LLM override in the runner, tool restriction validation at task submission, per-org token budget in the budget engine, concurrent-task cap from org config, and a new operator endpoint `PATCH /admin/organizations/{id}` to manage all of it.

**Architecture:** No new DB tables — all columns already exist on the `organizations` table (Phase 2D migration). Four surgical changes: (1) `admin.py` gets a new PATCH endpoint, (2) `tasks.py` loads the user's active org and enforces `allowed_tools` + `max_concurrent_tasks`, (3) `runner.py` passes `org.llm_provider`/`org.llm_model` to `build_llm()`, (4) `budget.py` gets a third budget tier for per-org monthly tokens.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest-asyncio. No new dependencies.

---

## File Map

### New files
```
backend/tests/test_routers/test_admin_orgs.py         — admin org config PATCH endpoint tests
backend/tests/test_routers/test_tasks_org_enforcement.py  — tool restriction + concurrency tests
backend/tests/test_orchestrator/test_budget_org.py    — per-org budget tests
backend/tests/test_orchestrator/test_runner_llm_override.py  — per-org LLM override tests
```

### Modified files
```
backend/app/routers/admin.py                          — add PATCH /admin/organizations/{id}
backend/app/routers/tasks.py                          — enforce org allowed_tools + max_concurrent_tasks
backend/app/orchestrator/budget.py                    — add org_monthly budget tier
backend/app/orchestrator/runner.py                    — load active org, pass llm override + org budget
```

---

## Task 1: Admin org config PATCH endpoint

**Files:**
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_routers/test_admin_orgs.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_routers/test_admin_orgs.py
import pytest
import uuid
from httpx import AsyncClient


async def _make_user_and_token(client: AsyncClient, role: str = "user") -> tuple[str, str]:
    email = f"u_{uuid.uuid4().hex[:6]}@test.com"
    resp = await client.post("/api/v1/auth/register",
                             json={"email": email, "password": "Pass1234!Secret"})
    token = resp.json()["access_token"]
    return email, token


async def _make_operator_token(client: AsyncClient, db_session) -> str:
    from app.models.user import User, UserRole
    from app.auth.password import hash_password
    from datetime import datetime, timezone
    op = User(
        id=uuid.uuid4(), email=f"op_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        role=UserRole.operator,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(op)
    await db_session.commit()
    login = await client.post("/api/v1/auth/login",
                              json={"email": op.email, "password": "Pass1234!Secret"})
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_patch_org_requires_operator(client: AsyncClient, db_session):
    _, user_token = await _make_user_and_token(client)
    # Create org first
    org_r = await client.post(
        "/api/v1/organizations",
        json={"name": "TestOrg", "slug": f"testorg-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    org_id = org_r.json()["id"]
    resp = await client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"max_concurrent_tasks": 10},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_org_sets_max_concurrent_tasks(client: AsyncClient, db_session):
    op_token = await _make_operator_token(client, db_session)
    _, user_token = await _make_user_and_token(client)
    org_r = await client.post(
        "/api/v1/organizations",
        json={"name": "OrgA", "slug": f"orga-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    org_id = org_r.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"max_concurrent_tasks": 10},
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["max_concurrent_tasks"] == 10


@pytest.mark.asyncio
async def test_patch_org_sets_llm_override(client: AsyncClient, db_session):
    op_token = await _make_operator_token(client, db_session)
    _, user_token = await _make_user_and_token(client)
    org_r = await client.post(
        "/api/v1/organizations",
        json={"name": "OrgB", "slug": f"orgb-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    org_id = org_r.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"llm_provider": "groq", "llm_model": "llama-3-70b"},
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["llm_provider"] == "groq"
    assert resp.json()["llm_model"] == "llama-3-70b"


@pytest.mark.asyncio
async def test_patch_org_sets_token_budget(client: AsyncClient, db_session):
    op_token = await _make_operator_token(client, db_session)
    _, user_token = await _make_user_and_token(client)
    org_r = await client.post(
        "/api/v1/organizations",
        json={"name": "OrgC", "slug": f"orgc-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    org_id = org_r.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/organizations/{org_id}",
        json={"token_budget_monthly": 5_000_000},
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["token_budget_monthly"] == 5_000_000


@pytest.mark.asyncio
async def test_patch_org_nonexistent_returns_404(client: AsyncClient, db_session):
    op_token = await _make_operator_token(client, db_session)
    fake_id = str(uuid.uuid4())
    resp = await client.patch(
        f"/api/v1/admin/organizations/{fake_id}",
        json={"max_concurrent_tasks": 3},
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python3 -m pytest tests/test_routers/test_admin_orgs.py -v
```
Expected: `404 Not Found` (endpoint does not exist yet)

- [ ] **Step 3: Add the endpoint to admin.py**

Open `backend/app/routers/admin.py`. Add these imports at the top (after existing imports):

```python
from typing import Optional
from pydantic import BaseModel
from app.models.org import Organization
```

Then add the Pydantic schema and route at the end of the file:

```python
class PatchOrgRequest(BaseModel):
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    allowed_tools: Optional[list[str]] = None  # [] = all tools; None = no change
    token_budget_monthly: Optional[int] = None  # None = no change; 0 = remove limit
    max_concurrent_tasks: Optional[int] = None


class OrgConfigResponse(BaseModel):
    id: str
    name: str
    slug: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    allowed_tools: Optional[list[str]] = None
    token_budget_monthly: Optional[int] = None
    max_concurrent_tasks: int

    model_config = {"from_attributes": True}


@router.patch("/organizations/{org_id}", response_model=OrgConfigResponse)
async def patch_organization_config(
    org_id: str,
    body: PatchOrgRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Operator endpoint: configure per-org LLM override, tool restrictions, token budget."""
    import uuid as uuid_lib
    result = await db.execute(
        select(Organization).where(
            Organization.id == uuid_lib.UUID(org_id),
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    if body.llm_provider is not None:
        org.llm_provider = body.llm_provider or None  # empty string → None
    if body.llm_model is not None:
        org.llm_model = body.llm_model or None
    if body.allowed_tools is not None:
        org.allowed_tools = body.allowed_tools if body.allowed_tools else None  # [] → None (all allowed)
    if body.token_budget_monthly is not None:
        org.token_budget_monthly = body.token_budget_monthly if body.token_budget_monthly > 0 else None
    if body.max_concurrent_tasks is not None:
        org.max_concurrent_tasks = body.max_concurrent_tasks

    await db.commit()
    await db.refresh(org)
    return OrgConfigResponse(
        id=str(org.id), name=org.name, slug=org.slug,
        llm_provider=org.llm_provider, llm_model=org.llm_model,
        allowed_tools=org.allowed_tools, token_budget_monthly=org.token_budget_monthly,
        max_concurrent_tasks=org.max_concurrent_tasks,
    )
```

Also add `from fastapi import status` and `from sqlalchemy import select` to the imports if not already present. Check the file's existing imports first with `grep -n "^from\|^import" backend/app/routers/admin.py`.

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_routers/test_admin_orgs.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin.py \
        backend/tests/test_routers/test_admin_orgs.py
git commit -m "feat(3c): PATCH /admin/organizations/{id} — operator org LLM/tools/budget config"
```

---

## Task 2: Per-org tool restrictions + concurrent cap at task submission

**Files:**
- Modify: `backend/app/routers/tasks.py`
- Test: `backend/tests/test_routers/test_tasks_org_enforcement.py`

The `create_task` endpoint currently hardcodes `running >= 5`. It needs to:
1. Load the user's active org (if any)
2. Use `org.max_concurrent_tasks` as the limit (default 5 if no org)
3. Validate `body.options.allowed_tools` is a subset of `org.allowed_tools` (if org has restrictions)

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_routers/test_tasks_org_enforcement.py
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

    # Find the registered user
    result = await db_session.execute(select(User).order_by(User.created_at.desc()))
    user = result.scalars().first()

    # Create an org with restricted tools and set as user's active org
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

    # Try to submit a task requesting a tool not in the org's allowed list
    with patch("app.worker.tasks.run_agent_task") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            "/api/v1/tasks",
            json={"goal": "Do something", "options": {"allowed_tools": ["code_executor"]}},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 422
    assert "not allowed" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()


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

    # Org with max_concurrent_tasks=1
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

    # Simulate one running task already
    running_task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="already running",
        status=TaskStatus.running,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(running_task)
    await db_session.commit()

    with patch("app.worker.tasks.run_agent_task") as mock_task:
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

    with patch("app.worker.tasks.run_agent_task") as mock_task:
        mock_task.delay.return_value = None
        resp = await client.post(
            "/api/v1/tasks",
            json={"goal": "Research something", "options": {}},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201
    task_data = resp.json()
    # The task's allowed_tools should have been set to the org's list
    assert set(task_data.get("allowed_tools") or []) == {"browser", "web_search"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_routers/test_tasks_org_enforcement.py -v
```
Expected: test 1 fails (422 not returned), test 2 fails (hardcoded limit 5 doesn't respect org), test 3 fails

- [ ] **Step 3: Modify tasks.py create_task**

In `backend/app/routers/tasks.py`, replace the `create_task` function body. The current function is around lines 34–58. Read the exact content first, then apply this logic:

```python
@router.post("", status_code=201, response_model=TaskResponse)
async def create_task(body: TaskCreate, request: Request,
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    from app.models.org import Organization

    # Load user's active org (if any)
    org = None
    if user.active_organization_id is not None:
        result = await db.execute(
            select(Organization).where(
                Organization.id == user.active_organization_id,
                Organization.deleted_at.is_(None),
            )
        )
        org = result.scalar_one_or_none()

    # Concurrency limit from org or default 5 (BR-TASK-07)
    max_concurrent = org.max_concurrent_tasks if org is not None else 5
    running = await task_repo.count_running_tasks(db, user_id=user.id)
    if running >= max_concurrent:
        raise HTTPException(status_code=429, detail={
            "code": "concurrency_limit",
            "message": f"You have reached the maximum of {max_concurrent} concurrent running tasks.",
        })

    # Per-org tool restriction enforcement (BR-ADMIN-13)
    requested_tools = body.options.allowed_tools
    if org is not None and org.allowed_tools is not None:
        allowed_set = set(org.allowed_tools)
        if requested_tools:
            disallowed = set(requested_tools) - allowed_set
            if disallowed:
                raise HTTPException(status_code=422, detail={
                    "code": "invalid_input",
                    "message": f"Tools not allowed for this organization: {sorted(disallowed)}",
                })
        else:
            # Default to org's allowed tools when none specified
            requested_tools = org.allowed_tools

    # Defaults + clamping (BR-TASK-02/03)
    language = body.language or user.language
    requested = body.options.max_iterations or settings.default_max_iterations
    max_iterations = min(requested, settings.max_iterations_cap)
    task = await task_repo.create_task(
        db, user_id=user.id, goal=body.goal, language=language,
        max_iterations=max_iterations, allowed_tools=requested_tools,
        notify_webhook=body.options.notify_webhook,
    )
    await db.commit()
    await db.refresh(task)
    run_agent_task.delay(str(task.id))
    resp = _to_response(task, request)
    return JSONResponse(status_code=201, content=json.loads(resp.model_dump_json()))
```

Also ensure `from sqlalchemy import select` is at the top of the file (it should already be imported via `get_db`).

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_routers/test_tasks_org_enforcement.py -v
```
Expected: 3 passed

- [ ] **Step 5: Run full suite to check no regressions**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/tasks.py \
        backend/tests/test_routers/test_tasks_org_enforcement.py
git commit -m "feat(3c): per-org tool restrictions + concurrent task cap at task submission"
```

---

## Task 3: Per-org token budget enforcement

**Files:**
- Modify: `backend/app/orchestrator/budget.py`
- Modify: `backend/app/orchestrator/runner.py`
- Test: `backend/tests/test_orchestrator/test_budget_org.py`

The spec (BR-ORCH-20) requires three budget tiers: per-task, per-user/month, per-org/month. Currently only the first two exist. Add the third.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_orchestrator/test_budget_org.py
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.orchestrator.budget import check_budgets, BudgetExceeded


@pytest.mark.asyncio
async def test_org_budget_not_exceeded():
    """Should not raise when org budget has room."""
    mock_db = AsyncMock()
    # User has used 100k tokens this month; org used 500k of 1M budget
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=lambda: 100_000),  # user monthly used
        MagicMock(scalar_one_or_none=lambda: 500_000),  # org monthly used
    ])
    # Should not raise
    await check_budgets(
        mock_db,
        user_id=uuid.uuid4(),
        task_tokens_so_far=5_000,
        estimated_next=1_000,
        per_task_budget=200_000,
        user_monthly_budget=2_000_000,
        org_id=uuid.uuid4(),
        org_monthly_budget=1_000_000,
    )


@pytest.mark.asyncio
async def test_org_budget_exceeded():
    """Should raise BudgetExceeded('org_monthly') when org is over budget."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=lambda: 100_000),  # user monthly used
        MagicMock(scalar_one_or_none=lambda: 999_500),  # org monthly used (nearly full)
    ])
    with pytest.raises(BudgetExceeded) as exc_info:
        await check_budgets(
            mock_db,
            user_id=uuid.uuid4(),
            task_tokens_so_far=0,
            estimated_next=1_000,
            per_task_budget=200_000,
            user_monthly_budget=2_000_000,
            org_id=uuid.uuid4(),
            org_monthly_budget=1_000_000,
        )
    assert exc_info.value.scope == "org_monthly"


@pytest.mark.asyncio
async def test_no_org_budget_skips_org_check():
    """When org_id or org_monthly_budget is None, org check is skipped."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: 0))
    # No org_id — should complete without querying org usage
    await check_budgets(
        mock_db,
        user_id=uuid.uuid4(),
        task_tokens_so_far=0,
        estimated_next=1_000,
        per_task_budget=200_000,
        user_monthly_budget=2_000_000,
        org_id=None,
        org_monthly_budget=None,
    )
    # Only one execute call for user budget, not two
    assert mock_db.execute.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_orchestrator/test_budget_org.py -v
```
Expected: fail (check_budgets signature doesn't accept org_id/org_monthly_budget)

- [ ] **Step 3: Update budget.py**

Replace `backend/app/orchestrator/budget.py` entirely:

```python
"""Token budget enforcement (Feature ORCH-3). Checked before each LLM call."""
from uuid import UUID
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.user import User


class BudgetExceeded(Exception):
    def __init__(self, scope: str):
        self.scope = scope
        super().__init__(f"Token budget exceeded: {scope}")


async def check_budgets(
    db: AsyncSession,
    *,
    user_id: UUID,
    task_tokens_so_far: int,
    estimated_next: int,
    per_task_budget: int | None = None,
    user_monthly_budget: int | None = None,
    org_id: Optional[UUID] = None,
    org_monthly_budget: Optional[int] = None,
) -> None:
    """Raise BudgetExceeded if the next LLM call would breach any budget
    (BR-ORCH-20/21). Caller halts gracefully with a partial report (BR-ORCH-22)."""
    per_task_budget = per_task_budget or settings.token_budget_per_task
    user_monthly_budget = user_monthly_budget or settings.token_budget_user_monthly

    if task_tokens_so_far + estimated_next > per_task_budget:
        raise BudgetExceeded("per_task")

    used_user = (await db.execute(
        select(User.token_used_this_month).where(User.id == user_id)
    )).scalar_one_or_none() or 0
    if used_user + estimated_next > user_monthly_budget:
        raise BudgetExceeded("user_monthly")

    # Per-org monthly budget check (BR-ORCH-20 tier 3)
    if org_id is not None and org_monthly_budget is not None:
        from app.models.task import Task, TaskStep
        used_org = (await db.execute(
            select(func.coalesce(func.sum(TaskStep.tokens_used), 0))
            .join(Task, Task.id == TaskStep.task_id)
            .join(User, User.id == Task.user_id)
            .where(User.active_organization_id == org_id)
        )).scalar_one_or_none() or 0
        if used_org + estimated_next > org_monthly_budget:
            raise BudgetExceeded("org_monthly")


async def record_usage(db: AsyncSession, *, user_id: UUID, tokens: int) -> None:
    """Increment the user's monthly token counter (BR-ORCH-24)."""
    user = await db.get(User, user_id)
    if user is not None:
        user.token_used_this_month = (user.token_used_this_month or 0) + tokens
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_orchestrator/test_budget_org.py -v
```
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestrator/budget.py \
        backend/tests/test_orchestrator/test_budget_org.py
git commit -m "feat(3c): per-org monthly token budget — third tier in check_budgets"
```

---

## Task 4: Wire per-org LLM override into runner

**Files:**
- Modify: `backend/app/orchestrator/runner.py`
- Test: `backend/tests/test_orchestrator/test_runner_llm_override.py`

The runner calls `build_llm()` with no arguments, always using global settings. It needs to load the user's active org and pass `org.llm_provider`/`org.llm_model` when set.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_orchestrator/test_runner_llm_override.py
"""Tests that runner.py picks up the per-org LLM override (BR-ADMIN-21)."""
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_runner_uses_org_llm_provider(db_session):
    """When user's active org has llm_provider set, runner passes it to build_llm."""
    from app.models.user import User, UserRole
    from app.models.org import Organization, OrganizationMembership
    from app.models.task import Task, TaskStatus
    from app.auth.password import hash_password

    org = Organization(
        id=uuid.uuid4(), name="GroqOrg", slug=f"groq-{uuid.uuid4().hex[:6]}",
        llm_provider="groq", llm_model="llama-3-70b", max_concurrent_tasks=5,
    )
    db_session.add(org)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(), email=f"runner_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        active_organization_id=org.id,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    db_session.add(OrganizationMembership(
        id=uuid.uuid4(), organization_id=org.id, user_id=user.id,
        role=UserRole.user, created_at=datetime.now(timezone.utc),
    ))

    task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="test goal",
        status=TaskStatus.pending, language="en",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    await db_session.commit()

    captured_calls = []

    def mock_build_llm(**kwargs):
        captured_calls.append(kwargs)
        return MagicMock()

    with patch("app.orchestrator.runner.build_llm", side_effect=mock_build_llm), \
         patch("app.orchestrator.runner.sandbox_manager") as mock_sandbox, \
         patch("app.orchestrator.runner.build_graph") as mock_graph, \
         patch("app.orchestrator.runner.checkpointer_context") as mock_cp, \
         patch("app.orchestrator.runner.get_langfuse_callbacks", return_value=[]):
        mock_sandbox.create_session = AsyncMock(return_value=MagicMock(endpoint=""))
        mock_graph.return_value.ainvoke = AsyncMock(return_value={
            "result_summary": "done", "partial": False, "artifacts": []
        })
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.orchestrator.runner import run_task
        await run_task(str(task.id), skip_sandbox=True)

    # build_llm should have been called with the org's overrides
    assert len(captured_calls) == 1
    assert captured_calls[0].get("provider") == "groq"
    assert captured_calls[0].get("model") == "llama-3-70b"


@pytest.mark.asyncio
async def test_runner_uses_global_llm_when_no_org(db_session):
    """When user has no active org, runner uses global settings (provider=None)."""
    from app.models.user import User
    from app.models.task import Task, TaskStatus
    from app.auth.password import hash_password

    user = User(
        id=uuid.uuid4(), email=f"noorg_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        active_organization_id=None,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="no-org task",
        status=TaskStatus.pending, language="en",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    await db_session.commit()

    captured_calls = []

    def mock_build_llm(**kwargs):
        captured_calls.append(kwargs)
        return MagicMock()

    with patch("app.orchestrator.runner.build_llm", side_effect=mock_build_llm), \
         patch("app.orchestrator.runner.sandbox_manager") as mock_sandbox, \
         patch("app.orchestrator.runner.build_graph") as mock_graph, \
         patch("app.orchestrator.runner.checkpointer_context") as mock_cp, \
         patch("app.orchestrator.runner.get_langfuse_callbacks", return_value=[]):
        mock_sandbox.create_session = AsyncMock(return_value=MagicMock(endpoint=""))
        mock_graph.return_value.ainvoke = AsyncMock(return_value={
            "result_summary": "done", "partial": False, "artifacts": []
        })
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.orchestrator.runner import run_task
        await run_task(str(task.id), skip_sandbox=True)

    assert len(captured_calls) == 1
    # No org override → provider and model should not be passed (or be None)
    assert captured_calls[0].get("provider") is None
    assert captured_calls[0].get("model") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_orchestrator/test_runner_llm_override.py -v
```
Expected: fail (runner doesn't load org or pass kwargs to build_llm)

- [ ] **Step 3: Update runner.py**

In `backend/app/orchestrator/runner.py`, modify `run_task` to load the user's active org and pass its LLM config + budget to `build_llm` and `check_budgets`.

Replace the `run_task` function (lines 34–116). The key changes are: after loading the task, load the user and their active org; pass org LLM config to `build_llm()`; pass org budget to context where `check_budgets` is called.

```python
async def run_task(task_id_str: str, llm=None, skip_sandbox: bool = False) -> None:
    """Run the agent loop for a task. `llm`/`skip_sandbox` are test seams."""
    task_id = UUID(task_id_str)
    emitter = EventEmitter(task_id)
    stm = ShortTermMemory()
    sandbox_endpoint = ""

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None or task.status in (TaskStatus.cancelled, TaskStatus.completed,
                                           TaskStatus.failed):
            await emitter.close()
            await stm.close()
            return
        user_id = task.user_id
        goal, language = task.goal, task.language
        max_iter = min(task.max_iterations, settings.max_iterations_cap)
        allowed_tools = task.allowed_tools

        # Load user's active org for per-org LLM override + budget (BR-ADMIN-21, BR-ORCH-20)
        from app.models.org import Organization
        from sqlalchemy import select as _select
        user = await db.get(Task.__class__, task_id)  # just to get user
        from app.models.user import User as _User
        user_row = await db.get(_User, user_id)
        org = None
        org_llm_provider = None
        org_llm_model = None
        org_monthly_budget = None
        org_id_for_budget = None
        if user_row is not None and user_row.active_organization_id is not None:
            result = await db.execute(
                _select(Organization).where(
                    Organization.id == user_row.active_organization_id,
                    Organization.deleted_at.is_(None),
                )
            )
            org = result.scalar_one_or_none()
            if org is not None:
                org_llm_provider = org.llm_provider
                org_llm_model = org.llm_model
                org_monthly_budget = org.token_budget_monthly
                org_id_for_budget = org.id

    await _set_status(task_id, TaskStatus.planning, started_at=datetime.now(timezone.utc))

    try:
        if not skip_sandbox:
            session = await sandbox_manager.create_session(task_id_str)
            sandbox_endpoint = session.endpoint

        llm = llm or build_llm(provider=org_llm_provider, model=org_llm_model)
        memory_block = await stm.build_context_block(str(user_id), max_tokens=500)
        run_ctx = RunContext(llm=llm, emitter=emitter, sandbox_endpoint=sandbox_endpoint,
                             user_id=str(user_id), task_id=task_id_str,
                             allowed_tools=allowed_tools, memory_block=memory_block,
                             org_id=str(org_id_for_budget) if org_id_for_budget else None,
                             org_monthly_budget=org_monthly_budget)

        initial: AgentState = {
            "task_id": task_id_str, "user_id": str(user_id), "goal": goal,
            "language": language, "messages": [], "scratchpad": "", "iteration": 0,
            "max_iterations": max_iter, "confidence": 0.0,
            "allowed_tools": allowed_tools or [], "artifacts": [], "failures": 0,
            "partial": False, "done": False,
        }

        await _set_status(task_id, TaskStatus.running)
        config = {"configurable": {"thread_id": task_id_str, "run_ctx": run_ctx},
                  "recursion_limit": max_iter * 4 + 10,
                  "callbacks": get_langfuse_callbacks()}

        async with checkpointer_context() as checkpointer:
            agent = build_graph(checkpointer)
            final_state = None
            try:
                final_state = await agent.ainvoke(initial, config=config)
            except BudgetExceeded as e:
                log.warning("budget_exceeded", task_id=task_id_str, scope=e.scope)
                partial_state = {**initial, "partial": True}
                final_state = await _partial_report(agent, partial_state, config)

        summary = (final_state or {}).get("result_summary", "")
        total_tokens = await _sum_task_tokens(task_id)
        total_steps = await _count_task_steps(task_id)
        async with AsyncSessionLocal() as db:
            await record_usage(db, user_id=user_id, tokens=total_tokens)
            await db.commit()
        await _set_status(task_id, TaskStatus.completed,
                          result_summary=summary,
                          partial=(final_state or {}).get("partial", False),
                          total_tokens=total_tokens, total_steps=total_steps,
                          completed_at=datetime.now(timezone.utc))
        if summary:
            await stm.store_task_summary(str(user_id), summary[:400])

    except Exception as e:
        log.error("task_failed", task_id=task_id_str, error=str(e))
        await emitter.emit(TaskStepType.report,
                           {"error": str(e), "error_code": "agent_error", "retryable": False},
                           sse_type="task_failed")
        await _set_status(task_id, TaskStatus.failed, error_message=str(e)[:1000],
                          error_code="agent_error", completed_at=datetime.now(timezone.utc))
    finally:
        if not skip_sandbox and sandbox_endpoint:
            sandbox_manager.destroy_session(task_id_str)
        await emitter.close()
        await stm.close()
```

**Important:** `RunContext` currently does not have `org_id` or `org_monthly_budget` fields. Check `backend/app/orchestrator/nodes.py` for the `RunContext` dataclass and add these two optional fields:

```python
# In RunContext dataclass
org_id: str | None = None
org_monthly_budget: int | None = None
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_orchestrator/test_runner_llm_override.py -v
```
Expected: 2 passed

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add backend/app/orchestrator/runner.py \
        backend/app/orchestrator/nodes.py \
        backend/tests/test_orchestrator/test_runner_llm_override.py
git commit -m "feat(3c): per-org LLM override in runner — pass org.llm_provider/model to build_llm"
```

---

## Phase 3C Complete

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: all tests passing (approximately 200+ tests total).

All three Phase 3C capabilities are now live:
- `PATCH /admin/organizations/{id}` — operator configures org LLM, tools, budgets
- Task submission validates org tool restrictions + uses org's concurrent task cap
- Runner loads org LLM override and passes to `build_llm()`
- Budget engine enforces per-org monthly token limit
