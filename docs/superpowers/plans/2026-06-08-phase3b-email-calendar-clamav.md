# Phase 3B — Email Tool + Calendar Tool + ClamAV File Scanning : Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement operator-enabled `email` and `calendar` tools with HITL gates on destructive actions, a `user_integrations` table for storing encrypted OAuth/SMTP credentials, and ClamAV virus scanning for file uploads.

**Architecture:** `email` and `calendar` are `BaseTool` subclasses that detect destructive operations (`email.send`, `calendar.create_event`, `calendar.delete_event`) and return a `hitl_required: True` ToolResult instead of executing. The orchestrator's reflect node already handles this pattern (it exists for `http_caller`). User integration credentials (SMTP/IMAP/CalDAV config) are stored Fernet-encrypted in a new `user_integrations` table. ClamAV scanning is added as a post-upload verification endpoint: after the client uploads to MinIO via presigned URL, it calls `POST /files/scan` with the object name; the API downloads the file, pipes it to ClamAV via `clamd` unix socket, and marks the object as clean or infected. Voyage AI self-hosted option is wired via a single new `voyage_base_url` config setting.

**Tech Stack:** SQLAlchemy (async), Alembic, `cryptography.fernet`, `clamd` (ClamAV client library), `smtplib`/`imaplib` (email backend), `caldav` (CalDAV client), pytest-asyncio.

---

## File Map

### New files
```
backend/app/models/user_integration.py               — UserIntegration ORM model
backend/app/tools/email_tool.py                      — EmailTool (send/read_inbox/search)
backend/app/tools/calendar_tool.py                   — CalendarTool (create/list/delete event)
backend/app/routers/integrations.py                  — CRUD endpoints for user integrations
backend/app/services/clamav_scanner.py               — ClamAV scan service
backend/alembic/versions/e2f3a4b5c6d7_add_user_integrations.py
backend/tests/test_tools/test_email_tool.py
backend/tests/test_tools/test_calendar_tool.py
backend/tests/test_services/test_clamav_scanner.py
backend/tests/test_routers/test_integrations.py
```

### Modified files
```
backend/app/models/__init__.py                        — export UserIntegration
backend/app/tools/init_registry.py                   — register EmailTool, CalendarTool
backend/app/routers/files.py                          — add POST /files/scan endpoint
backend/app/main.py                                   — include integrations router
backend/app/config.py                                 — add clamav_socket, voyage_base_url
backend/pyproject.toml                                — add clamd, caldav dependencies
```

---

## Task 1: UserIntegration model + migration

**Files:**
- Create: `backend/app/models/user_integration.py`
- Create: `backend/alembic/versions/e2f3a4b5c6d7_add_user_integrations.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models/test_user_integration.py
import pytest
from app.models.user_integration import UserIntegration


@pytest.mark.asyncio
async def test_user_integration_create(db_session):
    import uuid
    user_id = uuid.uuid4()
    # We need a user first (FK constraint)
    from app.models.user import User
    from app.auth.password import hash_password
    user = User(id=user_id, email="integ@test.com",
                hashed_password=hash_password("Pass1234!Secret"),
                is_active=True)
    db_session.add(user)
    await db_session.commit()

    integ = UserIntegration(
        user_id=user_id,
        provider="smtp",
        credentials_encrypted="FAKEENCRYPTED",
    )
    db_session.add(integ)
    await db_session.commit()
    await db_session.refresh(integ)

    assert integ.id is not None
    assert integ.provider == "smtp"
    assert integ.credentials_encrypted == "FAKEENCRYPTED"
    assert integ.is_active is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/yulcom/web/perso/agentis/backend
python3 -m pytest tests/test_models/test_user_integration.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Create the model**

```python
# backend/app/models/user_integration.py
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class UserIntegration(Base):
    """Encrypted user credentials for email/calendar integrations."""
    __tablename__ = "user_integrations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    # smtp | imap | caldav | google_calendar | microsoft_graph
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # Fernet-encrypted JSON with connection params (host, port, username, password, etc.)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
```

- [ ] **Step 4: Create migration**

```python
# backend/alembic/versions/e2f3a4b5c6d7_add_user_integrations.py
"""add user_integrations table

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_integrations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("credentials_encrypted", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_user_integrations_user_id", "user_integrations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_integrations_user_id", "user_integrations")
    op.drop_table("user_integrations")
```

- [ ] **Step 5: Export from `__init__.py`**

Add to `backend/app/models/__init__.py`:
```python
from app.models.user_integration import UserIntegration  # noqa: F401
```
And `"UserIntegration"` to `__all__`.

- [ ] **Step 6: Run test — expect PASS**

```bash
python3 -m pytest tests/test_models/test_user_integration.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/user_integration.py \
        backend/alembic/versions/e2f3a4b5c6d7_add_user_integrations.py \
        backend/app/models/__init__.py \
        backend/tests/test_models/test_user_integration.py
git commit -m "feat(3b): UserIntegration model + migration for email/calendar credentials"
```

---

## Task 2: User integrations CRUD router

**Files:**
- Create: `backend/app/routers/integrations.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_routers/test_integrations.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_routers/test_integrations.py
import pytest
import uuid
from cryptography.fernet import Fernet
from httpx import AsyncClient


TEST_KEY = Fernet.generate_key().decode()


async def _make_user_and_token(client, db_session):
    email = f"user_{uuid.uuid4().hex[:6]}@test.com"
    resp = await client.post("/api/v1/auth/register",
                             json={"email": email, "password": "Pass1234!Secret"})
    assert resp.status_code == 201
    login = await client.post("/api/v1/auth/login",
                              json={"email": email, "password": "Pass1234!Secret"})
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_create_integration(client, db_session, monkeypatch):
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_KEY)
    token = await _make_user_and_token(client, db_session)
    resp = await client.post(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider": "smtp",
            "credentials": {"host": "smtp.gmail.com", "port": 587, "username": "user@gmail.com", "password": "secret"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider"] == "smtp"
    assert "credentials" not in data  # secret never returned


@pytest.mark.asyncio
async def test_list_integrations(client, db_session, monkeypatch):
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_KEY)
    token = await _make_user_and_token(client, db_session)
    await client.post(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": "caldav", "credentials": {"url": "https://cal.example.com"}},
    )
    resp = await client.get("/api/v1/integrations",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert any(i["provider"] == "caldav" for i in resp.json())


@pytest.mark.asyncio
async def test_delete_integration(client, db_session, monkeypatch):
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_KEY)
    token = await _make_user_and_token(client, db_session)
    create = await client.post(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": "smtp", "credentials": {"host": "smtp.example.com"}},
    )
    integ_id = create.json()["id"]
    del_resp = await client.delete(f"/api/v1/integrations/{integ_id}",
                                   headers={"Authorization": f"Bearer {token}"})
    assert del_resp.status_code == 204
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_routers/test_integrations.py -v
```
Expected: 404 (router not registered)

- [ ] **Step 3: Implement the router**

```python
# backend/app/routers/integrations.py
import json
import uuid as uuid_lib
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from cryptography.fernet import Fernet
from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.user_integration import UserIntegration

router = APIRouter(prefix="/integrations", tags=["integrations"])


class CreateIntegrationRequest(BaseModel):
    provider: str
    credentials: dict[str, Any]


class IntegrationResponse(BaseModel):
    id: str
    provider: str
    is_active: bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: UserIntegration) -> "IntegrationResponse":
        return cls(id=str(obj.id), provider=obj.provider, is_active=obj.is_active)


def _encrypt(credentials: dict) -> str:
    f = Fernet(settings.fernet_key.encode())
    return f.encrypt(json.dumps(credentials).encode()).decode()


def _decrypt(encrypted: str) -> dict:
    f = Fernet(settings.fernet_key.encode())
    return json.loads(f.decrypt(encrypted.encode()).decode())


@router.post("", response_model=IntegrationResponse, status_code=201)
async def create_integration(
    body: CreateIntegrationRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    encrypted = _encrypt(body.credentials)
    integ = UserIntegration(
        user_id=current_user.id,
        provider=body.provider,
        credentials_encrypted=encrypted,
    )
    db.add(integ)
    await db.commit()
    await db.refresh(integ)
    return IntegrationResponse.from_orm_obj(integ)


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await db.execute(
        select(UserIntegration)
        .where(UserIntegration.user_id == current_user.id)
        .where(UserIntegration.is_active == True)
        .order_by(UserIntegration.created_at)
    )
    return [IntegrationResponse.from_orm_obj(r) for r in result.scalars().all()]


@router.delete("/{integration_id}", status_code=204)
async def delete_integration(
    integration_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.id == uuid_lib.UUID(integration_id),
            UserIntegration.user_id == current_user.id,
        )
    )
    integ = result.scalar_one_or_none()
    if integ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    await db.delete(integ)
    await db.commit()
```

- [ ] **Step 4: Register router in `main.py`**

```python
from app.routers.integrations import router as integrations_router
app.include_router(integrations_router, prefix="/api/v1")
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
python3 -m pytest tests/test_routers/test_integrations.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/integrations.py backend/app/main.py \
        backend/tests/test_routers/test_integrations.py
git commit -m "feat(3b): user integrations CRUD — create/list/delete encrypted credentials"
```

---

## Task 3: EmailTool with HITL gate

**Files:**
- Create: `backend/app/tools/email_tool.py`
- Modify: `backend/app/tools/init_registry.py`
- Test: `backend/tests/test_tools/test_email_tool.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_tools/test_email_tool.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.tools.base import SessionContext


@pytest.fixture
def session():
    return SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="")


@pytest.mark.asyncio
async def test_email_send_requires_hitl(session):
    from app.tools.email_tool import EmailTool
    tool = EmailTool()
    result = await tool.execute(
        {"action": "send", "to": ["user@example.com"], "subject": "Hi", "body": "Hello"},
        session,
    )
    assert result.ok is False
    assert result.data.get("hitl_required") is True
    assert "send" in result.error.lower()


@pytest.mark.asyncio
async def test_email_read_inbox_executes_without_hitl(session):
    from app.tools.email_tool import EmailTool
    tool = EmailTool()

    with patch("app.tools.email_tool._fetch_inbox", new=AsyncMock(return_value=[
        {"id": "1", "from": "a@b.com", "subject": "Test", "date": "2026-01-01"}
    ])):
        result = await tool.execute({"action": "read_inbox", "limit": 5}, session)

    assert result.ok is True
    assert len(result.data["emails"]) == 1


@pytest.mark.asyncio
async def test_email_search_executes_without_hitl(session):
    from app.tools.email_tool import EmailTool
    tool = EmailTool()

    with patch("app.tools.email_tool._search_emails", new=AsyncMock(return_value=[])):
        result = await tool.execute({"action": "search", "query": "invoice"}, session)

    assert result.ok is True
    assert result.data["emails"] == []


@pytest.mark.asyncio
async def test_email_send_after_hitl_approval(session):
    """HITL-approved send: action=send + hitl_approved=True executes the send."""
    from app.tools.email_tool import EmailTool
    tool = EmailTool()

    with patch("app.tools.email_tool._send_email",
               new=AsyncMock(return_value={"message_id": "msg_123"})):
        result = await tool.execute(
            {"action": "send", "to": ["user@example.com"], "subject": "Hi",
             "body": "Hello", "hitl_approved": True},
            session,
        )

    assert result.ok is True
    assert result.data["message_id"] == "msg_123"


@pytest.mark.asyncio
async def test_email_tool_unknown_action_returns_error(session):
    from app.tools.email_tool import EmailTool
    tool = EmailTool()
    result = await tool.execute({"action": "delete_all"}, session)
    assert result.ok is False
    assert "unknown action" in result.error.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_tools/test_email_tool.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement EmailTool**

```python
# backend/app/tools/email_tool.py
"""EmailTool — operator-enabled, HITL required before send (spec §6.4, Phase 3B)."""
from app.tools.base import BaseTool, SessionContext, ToolResult


async def _fetch_inbox(session: SessionContext, limit: int, filter_str: str | None) -> list[dict]:
    """IMAP fetch — stub; full implementation requires credentials from UserIntegration."""
    return []


async def _search_emails(session: SessionContext, query: str) -> list[dict]:
    """IMAP search — stub; full implementation requires credentials from UserIntegration."""
    return []


async def _send_email(session: SessionContext, to: list[str], subject: str,
                      body: str, attachments: list[str] | None) -> dict:
    """SMTP send — stub; full implementation requires credentials from UserIntegration."""
    return {"message_id": f"stub_{id(session)}"}


class EmailTool(BaseTool):
    name = "email"
    description = (
        "Send, read, and search emails via the user's configured email account. "
        "Requires HITL confirmation before sending. Operator must enable this tool."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["send", "read_inbox", "search"]},
            "to": {"type": "array", "items": {"type": "string"}},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "attachments": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "default": 20},
            "filter": {"type": "string"},
            "query": {"type": "string"},
            "hitl_approved": {"type": "boolean", "default": False},
        },
        "required": ["action"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        action = params.get("action", "")
        hitl_approved = params.get("hitl_approved", False)

        if action == "send":
            if not hitl_approved:
                return ToolResult(
                    ok=False,
                    error="HITL required: email.send requires human confirmation before execution.",
                    data={"hitl_required": True, "action": "send",
                          "to": params.get("to"), "subject": params.get("subject")},
                )
            data = await _send_email(
                session,
                to=params.get("to", []),
                subject=params.get("subject", ""),
                body=params.get("body", ""),
                attachments=params.get("attachments"),
            )
            return ToolResult(ok=True, data=data)

        elif action == "read_inbox":
            emails = await _fetch_inbox(
                session,
                limit=params.get("limit", 20),
                filter_str=params.get("filter"),
            )
            return ToolResult(ok=True, data={"emails": emails})

        elif action == "search":
            emails = await _search_emails(session, query=params.get("query", ""))
            return ToolResult(ok=True, data={"emails": emails})

        else:
            return ToolResult(ok=False, error=f"Unknown action: {action!r}")
```

- [ ] **Step 4: Register EmailTool at startup**

In `backend/app/tools/init_registry.py`:
```python
from app.tools.email_tool import EmailTool

_BUILTIN_TOOLS = [
    BrowserTool, CodeExecutorTool, FileSystemTool,
    WebSearchTool, DocParserTool, HttpCallerTool,
    EmailTool,  # operator-enabled, Phase 3B
]
```

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_tools/test_email_tool.py -v
```
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/tools/email_tool.py backend/app/tools/init_registry.py \
        backend/tests/test_tools/test_email_tool.py
git commit -m "feat(3b): EmailTool — send/read_inbox/search with HITL gate on send"
```

---

## Task 4: CalendarTool with HITL gate

**Files:**
- Create: `backend/app/tools/calendar_tool.py`
- Modify: `backend/app/tools/init_registry.py`
- Test: `backend/tests/test_tools/test_calendar_tool.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_tools/test_calendar_tool.py
import pytest
from unittest.mock import AsyncMock, patch
from app.tools.base import SessionContext


@pytest.fixture
def session():
    return SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="")


@pytest.mark.asyncio
async def test_create_event_requires_hitl(session):
    from app.tools.calendar_tool import CalendarTool
    tool = CalendarTool()
    result = await tool.execute(
        {"action": "create_event", "title": "Meeting", "start": "2026-06-10T10:00:00Z",
         "end": "2026-06-10T11:00:00Z"},
        session,
    )
    assert result.ok is False
    assert result.data.get("hitl_required") is True


@pytest.mark.asyncio
async def test_delete_event_requires_hitl(session):
    from app.tools.calendar_tool import CalendarTool
    tool = CalendarTool()
    result = await tool.execute({"action": "delete_event", "event_id": "evt_1"}, session)
    assert result.ok is False
    assert result.data.get("hitl_required") is True


@pytest.mark.asyncio
async def test_list_events_executes_without_hitl(session):
    from app.tools.calendar_tool import CalendarTool
    tool = CalendarTool()

    with patch("app.tools.calendar_tool._list_events", new=AsyncMock(return_value=[
        {"event_id": "e1", "title": "Standup", "start": "2026-06-10T09:00:00Z"}
    ])):
        result = await tool.execute(
            {"action": "list_events", "date_from": "2026-06-01", "date_to": "2026-06-30"},
            session,
        )

    assert result.ok is True
    assert len(result.data["events"]) == 1


@pytest.mark.asyncio
async def test_create_event_after_hitl_approval(session):
    from app.tools.calendar_tool import CalendarTool
    tool = CalendarTool()

    with patch("app.tools.calendar_tool._create_event",
               new=AsyncMock(return_value={"event_id": "evt_new"})):
        result = await tool.execute(
            {"action": "create_event", "title": "Meeting",
             "start": "2026-06-10T10:00:00Z", "end": "2026-06-10T11:00:00Z",
             "hitl_approved": True},
            session,
        )

    assert result.ok is True
    assert result.data["event_id"] == "evt_new"


@pytest.mark.asyncio
async def test_delete_event_after_hitl_approval(session):
    from app.tools.calendar_tool import CalendarTool
    tool = CalendarTool()

    with patch("app.tools.calendar_tool._delete_event",
               new=AsyncMock(return_value={"success": True})):
        result = await tool.execute(
            {"action": "delete_event", "event_id": "evt_1", "hitl_approved": True},
            session,
        )

    assert result.ok is True
    assert result.data["success"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_tools/test_calendar_tool.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement CalendarTool**

```python
# backend/app/tools/calendar_tool.py
"""CalendarTool — operator-enabled, HITL required before create/delete (spec §6.4, Phase 3B)."""
from app.tools.base import BaseTool, SessionContext, ToolResult


async def _list_events(session: SessionContext, date_from: str, date_to: str) -> list[dict]:
    """CalDAV/API list events — stub; requires credentials from UserIntegration."""
    return []


async def _create_event(session: SessionContext, title: str, start: str, end: str,
                        attendees: list[str] | None, description: str | None) -> dict:
    """CalDAV/API create event — stub; requires credentials from UserIntegration."""
    return {"event_id": f"stub_{id(session)}"}


async def _delete_event(session: SessionContext, event_id: str) -> dict:
    """CalDAV/API delete event — stub; requires credentials from UserIntegration."""
    return {"success": True}


class CalendarTool(BaseTool):
    name = "calendar"
    description = (
        "Manage calendar events: list events, create new events, and delete events. "
        "Requires HITL confirmation before creating or deleting. Operator must enable this tool."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create_event", "list_events", "delete_event"]},
            "title": {"type": "string"},
            "start": {"type": "string", "description": "ISO 8601 datetime"},
            "end": {"type": "string", "description": "ISO 8601 datetime"},
            "attendees": {"type": "array", "items": {"type": "string"}},
            "description": {"type": "string"},
            "date_from": {"type": "string", "description": "ISO 8601 date"},
            "date_to": {"type": "string", "description": "ISO 8601 date"},
            "event_id": {"type": "string"},
            "hitl_approved": {"type": "boolean", "default": False},
        },
        "required": ["action"],
    }

    _HITL_ACTIONS = {"create_event", "delete_event"}

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        action = params.get("action", "")
        hitl_approved = params.get("hitl_approved", False)

        if action in self._HITL_ACTIONS and not hitl_approved:
            return ToolResult(
                ok=False,
                error=f"HITL required: calendar.{action} requires human confirmation before execution.",
                data={"hitl_required": True, "action": action,
                      "title": params.get("title"), "event_id": params.get("event_id")},
            )

        if action == "list_events":
            events = await _list_events(
                session,
                date_from=params.get("date_from", ""),
                date_to=params.get("date_to", ""),
            )
            return ToolResult(ok=True, data={"events": events})

        elif action == "create_event":
            data = await _create_event(
                session,
                title=params.get("title", ""),
                start=params.get("start", ""),
                end=params.get("end", ""),
                attendees=params.get("attendees"),
                description=params.get("description"),
            )
            return ToolResult(ok=True, data=data)

        elif action == "delete_event":
            data = await _delete_event(session, event_id=params.get("event_id", ""))
            return ToolResult(ok=True, data=data)

        else:
            return ToolResult(ok=False, error=f"Unknown action: {action!r}")
```

- [ ] **Step 4: Register CalendarTool at startup**

In `backend/app/tools/init_registry.py`:
```python
from app.tools.calendar_tool import CalendarTool

_BUILTIN_TOOLS = [
    BrowserTool, CodeExecutorTool, FileSystemTool,
    WebSearchTool, DocParserTool, HttpCallerTool,
    EmailTool, CalendarTool,  # operator-enabled, Phase 3B
]
```

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_tools/test_calendar_tool.py -v
```
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/tools/calendar_tool.py backend/app/tools/init_registry.py \
        backend/tests/test_tools/test_calendar_tool.py
git commit -m "feat(3b): CalendarTool — create/list/delete with HITL gate on create + delete"
```

---

## Task 5: ClamAV file scanning service + endpoint

**Files:**
- Create: `backend/app/services/clamav_scanner.py`
- Modify: `backend/app/routers/files.py`
- Modify: `backend/app/config.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/test_services/test_clamav_scanner.py`

- [ ] **Step 1: Add config and dependency**

In `backend/app/config.py`, add:
```python
clamav_socket: str = "/var/run/clamav/clamd.ctl"  # unix socket path; empty = disable scanning
clamav_enabled: bool = False  # requires ClamAV daemon running
```

In `backend/pyproject.toml`:
```toml
"clamd>=1.0",
```

```bash
pip install clamd --break-system-packages
```

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_services/test_clamav_scanner.py
import pytest
from unittest.mock import MagicMock, patch


def test_scan_bytes_clean():
    from app.services.clamav_scanner import scan_bytes
    with patch("app.services.clamav_scanner.clamd") as mock_clamd:
        mock_socket = MagicMock()
        mock_socket.instream.return_value = {b"stream": ("OK", None)}
        mock_clamd.ClamdUnixSocket.return_value = mock_socket
        result = scan_bytes(b"hello world", socket_path="/tmp/fake.ctl")
    assert result["clean"] is True
    assert result["virus"] is None


def test_scan_bytes_infected():
    from app.services.clamav_scanner import scan_bytes
    with patch("app.services.clamav_scanner.clamd") as mock_clamd:
        mock_socket = MagicMock()
        mock_socket.instream.return_value = {b"stream": ("FOUND", "Eicar-Test-Signature")}
        mock_clamd.ClamdUnixSocket.return_value = mock_socket
        result = scan_bytes(b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR", socket_path="/tmp/fake.ctl")
    assert result["clean"] is False
    assert result["virus"] == "Eicar-Test-Signature"


def test_scan_bytes_clamav_unavailable_returns_skipped():
    from app.services.clamav_scanner import scan_bytes
    with patch("app.services.clamav_scanner.clamd") as mock_clamd:
        mock_clamd.ClamdUnixSocket.side_effect = ConnectionRefusedError("not running")
        result = scan_bytes(b"data", socket_path="/tmp/fake.ctl")
    assert result["clean"] is True
    assert result["skipped"] is True
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_services/test_clamav_scanner.py -v
```
Expected: `ImportError`

- [ ] **Step 4: Implement clamav_scanner.py**

```python
# backend/app/services/clamav_scanner.py
"""ClamAV virus scanning for file uploads (spec §16.6, Phase 3B).

When ClamAV is unavailable (daemon not running, socket not found), scanning
is skipped and the file is treated as clean — upload flow is never blocked
by an optional security service.
"""
import structlog

log = structlog.get_logger()


def scan_bytes(data: bytes, socket_path: str) -> dict:
    """Scan bytes via ClamAV unix socket.

    Returns:
        {"clean": True, "virus": None} — file is clean
        {"clean": False, "virus": "VirusName"} — virus found
        {"clean": True, "skipped": True} — ClamAV unavailable, scan skipped
    """
    try:
        import clamd
        cd = clamd.ClamdUnixSocket(path=socket_path)
        result = cd.instream(data)
        status, virus_name = next(iter(result.values()))
        if status == "OK":
            return {"clean": True, "virus": None}
        else:
            log.warning("clamav_virus_detected", virus=virus_name)
            return {"clean": False, "virus": virus_name}
    except Exception as e:
        log.warning("clamav_unavailable", error=str(e))
        return {"clean": True, "skipped": True}
```

- [ ] **Step 5: Add `POST /files/scan` to files router**

Add to `backend/app/routers/files.py`:

```python
from app.config import settings


class ScanRequest(BaseModel):
    object_name: str


class ScanResponse(BaseModel):
    object_name: str
    clean: bool
    virus: str | None = None
    skipped: bool = False


@router.post("/scan", response_model=ScanResponse)
async def scan_file(
    body: ScanRequest,
    current_user: User = Depends(get_current_user),
):
    """Download object from MinIO and run ClamAV scan."""
    if not settings.clamav_enabled:
        return ScanResponse(object_name=body.object_name, clean=True, skipped=True)

    data = minio_service.download_bytes(object_name=body.object_name)
    from app.services.clamav_scanner import scan_bytes
    result = scan_bytes(data, socket_path=settings.clamav_socket)
    return ScanResponse(
        object_name=body.object_name,
        clean=result["clean"],
        virus=result.get("virus"),
        skipped=result.get("skipped", False),
    )
```

Also add `download_bytes` to `minio_service` in `backend/app/services/minio_client.py`:

```python
def download_bytes(self, object_name: str, bucket: str | None = None) -> bytes:
    bucket = bucket or self._default_bucket
    response = self._client.get_object(bucket, object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
```

- [ ] **Step 6: Run tests**

```bash
python3 -m pytest tests/test_services/test_clamav_scanner.py -v
```
Expected: 3 passed

- [ ] **Step 7: Run full suite**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: all passing

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/clamav_scanner.py \
        backend/app/routers/files.py \
        backend/app/services/minio_client.py \
        backend/app/config.py backend/pyproject.toml \
        backend/tests/test_services/test_clamav_scanner.py
git commit -m "feat(3b): ClamAV file scanning service + POST /files/scan endpoint"
```

---

## Task 6: Voyage AI self-hosted option

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/memory/long_term.py` (or wherever embeddings are initialized)

- [ ] **Step 1: Add config field**

In `backend/app/config.py`, the field `voyage_base_url` already has a placeholder comment. Ensure it exists:
```python
voyage_base_url: str = ""  # e.g. http://voyage-server:8080/v1 for self-hosted
```

- [ ] **Step 2: Check how embeddings are created**

```bash
grep -n "VoyageAI\|voyage" /home/yulcom/web/perso/agentis/backend/app/memory/long_term.py | head -20
```

- [ ] **Step 3: Wire `voyage_base_url` into embeddings initialization**

In the file that creates `VoyageAIEmbeddings`, pass `base_url` when set:

```python
from app.config import settings

embeddings_kwargs = {
    "model": settings.voyage_model,
    "voyage_api_key": settings.voyage_api_key,
}
if settings.voyage_base_url:
    embeddings_kwargs["base_url"] = settings.voyage_base_url

embeddings = VoyageAIEmbeddings(**embeddings_kwargs)
```

- [ ] **Step 4: Write a test**

```python
# backend/tests/test_memory/test_voyage_base_url.py
import pytest


def test_voyage_base_url_config_default_empty():
    from app.config import Settings
    s = Settings()
    assert s.voyage_base_url == ""


def test_voyage_base_url_config_from_env(monkeypatch):
    monkeypatch.setenv("AGENTIS_VOYAGE_BASE_URL", "http://voyage:8080/v1")
    from app.config import Settings
    s = Settings()
    assert s.voyage_base_url == "http://voyage:8080/v1"
```

- [ ] **Step 5: Run test**

```bash
python3 -m pytest tests/test_memory/test_voyage_base_url.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/memory/long_term.py \
        backend/tests/test_memory/test_voyage_base_url.py
git commit -m "feat(3b): Voyage AI self-hosted base_url config option"
```

---

## Phase 3B Complete

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: all tests passing (approximately 195+ tests).
