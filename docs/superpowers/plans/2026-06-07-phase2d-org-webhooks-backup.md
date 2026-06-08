# Phase 2D — Organisations + Webhooks + Backup : Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-user Organization model, user-configured webhooks with HMAC-SHA256 signatures and 5× retry, and automated PostgreSQL + Qdrant backups via Celery Beat. Also wire Celery Beat jobs from Phase 2A that reset monthly token counters and clean up artifacts.

**Architecture:** `organizations` and `organization_members` tables added via Alembic. Each user gains an `active_organization_id` FK. Webhooks are stored in `user_webhooks` with Fernet-encrypted secret; the `WebhookDispatcher` runs as a Celery task with exponential backoff. Backups use `pg_dump` (piped to MinIO) and Qdrant snapshot API (also stored in MinIO). Beat jobs added to `celery_app.py` beat schedule.

**Tech Stack:** SQLAlchemy (async), Alembic, Fernet (cryptography), httpx (webhook dispatch), Celery Beat, MinIO (backup storage), pytest-asyncio.

---

## File Map

### New files
```
backend/app/models/organization.py              — Organization + OrganizationMember models
backend/app/models/webhook.py                   — UserWebhook model
backend/app/routers/organizations.py            — CRUD org endpoints
backend/app/routers/webhooks.py                 — CRUD webhook endpoints
backend/app/services/webhook_dispatcher.py      — send_webhook() Celery task + HMAC signing
backend/app/worker/backup_jobs.py               — backup_postgres + backup_qdrant Beat tasks
backend/alembic/versions/<hash>_add_orgs_webhooks.py
backend/tests/test_routers/test_organizations.py
backend/tests/test_routers/test_webhooks.py
backend/tests/test_services/test_webhook_dispatcher.py
backend/tests/test_worker/test_backup_jobs.py
```

### Modified files
```
backend/app/models/user.py                       — add active_organization_id FK
backend/app/worker/celery_app.py                 — add remaining beat jobs
backend/app/worker/beat_jobs.py                  — add cleanup_artifacts + reset_monthly_tokens
backend/app/main.py                              — include orgs + webhooks routers
backend/app/config.py                            — add FERNET_KEY setting
```

---

## Task 1: Organization + OrganizationMember + UserWebhook models + migration

**Files:**
- Create: `backend/app/models/organization.py`
- Create: `backend/app/models/webhook.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<hash>_add_orgs_webhooks.py`

- [ ] **Step 1: Create `backend/app/models/organization.py`**

```python
from uuid import uuid4, UUID
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    members: Mapped[list["OrganizationMember"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    organization: Mapped["Organization"] = relationship(back_populates="members")
```

- [ ] **Step 2: Create `backend/app/models/webhook.py`**

```python
from uuid import uuid4, UUID
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class UserWebhook(Base):
    __tablename__ = "user_webhooks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[str] = mapped_column(String(512), nullable=False, default="task_completed")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
```

- [ ] **Step 3: Add `active_organization_id` to `backend/app/models/user.py`**

In the `User` model class, add:

```python
    active_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
```

- [ ] **Step 4: Register models in `backend/app/models/__init__.py`**

```python
from app.models.organization import Organization, OrganizationMember  # noqa: F401
from app.models.webhook import UserWebhook  # noqa: F401
```

- [ ] **Step 5: Write Alembic migration**

```bash
cd /home/yulcom/web/perso/agentis/backend
alembic revision --autogenerate -m "add_orgs_webhooks"
```

If autogenerate not available (DB offline), write manually. The migration must:
- CREATE `organizations` (id, name, slug UNIQUE, created_at)
- CREATE `organization_members` (id, organization_id FK, user_id FK, role, joined_at)
- CREATE `user_webhooks` (id, user_id FK, url, secret_encrypted, events, is_active, created_at)
- ALTER TABLE `users` ADD COLUMN `active_organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL`

Verify the generated file creates all tables. Run:

```bash
alembic upgrade head
```

Expected: migration applies without errors.

- [ ] **Step 6: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/models/ alembic/versions/
git commit -m "feat(2d): Organization, OrganizationMember, UserWebhook models + migration"
```

---

## Task 2: Add FERNET_KEY config + webhook encryption helper

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add Fernet key to `backend/app/config.py`**

```python
    # Webhook security
    fernet_key: str = ""  # Must be set in production: Fernet.generate_key().decode()
```

- [ ] **Step 2: Verify cryptography is installed**

```bash
pip show cryptography
```

If not installed: `pip install "cryptography>=42.0"`

- [ ] **Step 3: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/config.py
git commit -m "feat(2d): add fernet_key config for webhook secret encryption"
```

---

## Task 3: Organizations router (TDD)

**Files:**
- Create: `backend/tests/test_routers/test_organizations.py`
- Create: `backend/app/routers/organizations.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing tests — `backend/tests/test_routers/test_organizations.py`**

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_organization(async_client: AsyncClient, auth_headers: dict):
    resp = await async_client.post(
        "/api/v1/organizations",
        json={"name": "Acme Corp", "slug": "acme"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "acme"
    assert data["name"] == "Acme Corp"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_org_duplicate_slug_fails(async_client: AsyncClient, auth_headers: dict):
    await async_client.post("/api/v1/organizations", json={"name": "A", "slug": "dup"}, headers=auth_headers)
    resp = await async_client.post("/api/v1/organizations", json={"name": "B", "slug": "dup"}, headers=auth_headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_my_organizations(async_client: AsyncClient, auth_headers: dict):
    await async_client.post("/api/v1/organizations", json={"name": "Org1", "slug": "org1-test"}, headers=auth_headers)
    resp = await async_client.get("/api/v1/organizations", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert any(o["slug"] == "org1-test" for o in resp.json())


@pytest.mark.asyncio
async def test_set_active_organization(async_client: AsyncClient, auth_headers: dict):
    r = await async_client.post("/api/v1/organizations", json={"name": "Active Org", "slug": "active-org-test"}, headers=auth_headers)
    org_id = r.json()["id"]
    resp = await async_client.patch("/api/v1/organizations/active", json={"organization_id": org_id}, headers=auth_headers)
    assert resp.status_code == 200
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_routers/test_organizations.py -v 2>&1 | head -15
```

Expected: FAIL — 404

- [ ] **Step 3: Implement `backend/app/routers/organizations.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.organization import Organization, OrganizationMember
from app.db import get_db

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrgCreate(BaseModel):
    name: str
    slug: str


class SetActiveOrg(BaseModel):
    organization_id: str


@router.post("", status_code=201)
async def create_organization(body: OrgCreate, current_user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(Organization).where(Organization.slug == body.slug))
    if existing:
        raise HTTPException(status_code=409, detail="Slug already taken")

    org = Organization(name=body.name, slug=body.slug)
    db.add(org)
    await db.flush()

    member = OrganizationMember(organization_id=org.id, user_id=current_user.id, role="owner")
    db.add(member)
    await db.commit()
    await db.refresh(org)
    return {"id": str(org.id), "name": org.name, "slug": org.slug}


@router.get("")
async def list_my_organizations(current_user: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == current_user.id)
    )
    orgs = result.scalars().all()
    return [{"id": str(o.id), "name": o.name, "slug": o.slug} for o in orgs]


@router.patch("/active")
async def set_active_organization(body: SetActiveOrg, current_user: User = Depends(get_current_user),
                                   db: AsyncSession = Depends(get_db)):
    import uuid
    org = await db.get(Organization, uuid.UUID(body.organization_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    current_user.active_organization_id = org.id
    await db.commit()
    return {"active_organization_id": str(org.id)}
```

- [ ] **Step 4: Register in `backend/app/main.py`**

```python
from app.routers.organizations import router as orgs_router
app.include_router(orgs_router, prefix="/api/v1")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_routers/test_organizations.py -v 2>&1 | tail -10
```

Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/routers/organizations.py app/main.py tests/test_routers/test_organizations.py
git commit -m "feat(2d): organizations router — create, list, set active org"
```

---

## Task 4: Webhooks router (TDD)

**Files:**
- Create: `backend/tests/test_routers/test_webhooks.py`
- Create: `backend/app/routers/webhooks.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing tests — `backend/tests/test_routers/test_webhooks.py`**

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_webhook(async_client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setenv("AGENTIS_FERNET_KEY", "J9u8Rl_cZ-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi=")
    resp = await async_client.post(
        "/api/v1/webhooks",
        json={"url": "https://example.com/hook", "secret": "mysecret", "events": "task_completed"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["url"] == "https://example.com/hook"
    assert "secret" not in data  # secret must not be returned


@pytest.mark.asyncio
async def test_list_webhooks(async_client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setenv("AGENTIS_FERNET_KEY", "J9u8Rl_cZ-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi=")
    await async_client.post("/api/v1/webhooks", json={"url": "https://ex.com/h", "secret": "s", "events": "task_completed"}, headers=auth_headers)
    resp = await async_client.get("/api/v1/webhooks", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_delete_webhook(async_client: AsyncClient, auth_headers: dict, monkeypatch):
    monkeypatch.setenv("AGENTIS_FERNET_KEY", "J9u8Rl_cZ-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi=")
    r = await async_client.post("/api/v1/webhooks", json={"url": "https://del.com/h", "secret": "s2", "events": "task_completed"}, headers=auth_headers)
    wh_id = r.json()["id"]
    resp = await async_client.delete(f"/api/v1/webhooks/{wh_id}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_invalid_url_rejected(async_client: AsyncClient, auth_headers: dict):
    resp = await async_client.post(
        "/api/v1/webhooks",
        json={"url": "not-a-url", "secret": "s", "events": "task_completed"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_routers/test_webhooks.py -v 2>&1 | head -15
```

Expected: FAIL — 404

- [ ] **Step 3: Implement `backend/app/routers/webhooks.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, HttpUrl
from cryptography.fernet import Fernet
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.webhook import UserWebhook
from app.db import get_db
from app.config import settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _fernet() -> Fernet:
    key = settings.fernet_key
    if not key:
        raise HTTPException(status_code=500, detail="Webhook encryption not configured")
    return Fernet(key.encode() if isinstance(key, str) else key)


class WebhookCreate(BaseModel):
    url: HttpUrl
    secret: str
    events: str = "task_completed"


@router.post("", status_code=201)
async def create_webhook(body: WebhookCreate, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    f = _fernet()
    encrypted = f.encrypt(body.secret.encode()).decode()
    wh = UserWebhook(
        user_id=current_user.id,
        url=str(body.url),
        secret_encrypted=encrypted,
        events=body.events,
    )
    db.add(wh)
    await db.commit()
    await db.refresh(wh)
    return {"id": str(wh.id), "url": wh.url, "events": wh.events, "is_active": wh.is_active}


@router.get("")
async def list_webhooks(current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserWebhook).where(UserWebhook.user_id == current_user.id))
    whs = result.scalars().all()
    return [{"id": str(w.id), "url": w.url, "events": w.events, "is_active": w.is_active} for w in whs]


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: str, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    import uuid
    wh = await db.get(UserWebhook, uuid.UUID(webhook_id))
    if not wh or wh.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(wh)
    await db.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Register in `backend/app/main.py`**

```python
from app.routers.webhooks import router as webhooks_router
app.include_router(webhooks_router, prefix="/api/v1")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_routers/test_webhooks.py -v 2>&1 | tail -10
```

Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/routers/webhooks.py app/main.py tests/test_routers/test_webhooks.py
git commit -m "feat(2d): webhooks router — create/list/delete with Fernet-encrypted secret"
```

---

## Task 5: Webhook dispatcher Celery task (TDD)

**Files:**
- Create: `backend/tests/test_services/test_webhook_dispatcher.py`
- Create: `backend/app/services/webhook_dispatcher.py`
- Modify: `backend/app/worker/celery_app.py`

- [ ] **Step 1: Write failing tests — `backend/tests/test_services/test_webhook_dispatcher.py`**

```python
import pytest
import hmac
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch


def test_compute_signature_is_hmac_sha256():
    from app.services.webhook_dispatcher import compute_hmac_signature
    secret = "mysecret"
    payload = '{"event": "task_completed"}'
    sig = compute_hmac_signature(secret, payload)
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    assert sig == expected


def test_compute_signature_different_secrets_differ():
    from app.services.webhook_dispatcher import compute_hmac_signature
    payload = '{"event": "task_completed"}'
    assert compute_hmac_signature("a", payload) != compute_hmac_signature("b", payload)


@pytest.mark.asyncio
async def test_dispatch_webhook_sends_post_with_signature():
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("app.services.webhook_dispatcher.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        from app.services.webhook_dispatcher import dispatch_webhook_request
        result = await dispatch_webhook_request(
            url="https://example.com/hook",
            secret="mysecret",
            payload={"event": "task_completed", "task_id": "t1"},
        )
        assert result is True
        call_kwargs = mock_client.post.call_args[1]
        assert "X-Agentis-Signature" in call_kwargs["headers"]


@pytest.mark.asyncio
async def test_dispatch_webhook_returns_false_on_non_2xx():
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch("app.services.webhook_dispatcher.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        from app.services.webhook_dispatcher import dispatch_webhook_request
        result = await dispatch_webhook_request(
            url="https://example.com/hook",
            secret="mysecret",
            payload={"event": "task_completed"},
        )
        assert result is False
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_services/test_webhook_dispatcher.py -v 2>&1 | head -15
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `backend/app/services/webhook_dispatcher.py`**

```python
"""Webhook dispatcher with HMAC-SHA256 signing + retry (spec §15 WH-1..5)."""
import hmac
import hashlib
import json
import asyncio
import httpx
from cryptography.fernet import Fernet
from app.config import settings
from app.worker.celery_app import celery_app


def compute_hmac_signature(secret: str, payload_str: str) -> str:
    return hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()


def decrypt_secret(encrypted: str) -> str:
    f = Fernet(settings.fernet_key.encode())
    return f.decrypt(encrypted.encode()).decode()


async def dispatch_webhook_request(url: str, secret: str, payload: dict) -> bool:
    """Send a single webhook POST. Returns True on 2xx, False otherwise."""
    payload_str = json.dumps(payload, separators=(",", ":"))
    sig = compute_hmac_signature(secret, payload_str)
    headers = {
        "Content-Type": "application/json",
        "X-Agentis-Signature": f"sha256={sig}",
        "User-Agent": "Agentis-Webhook/1.0",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, content=payload_str, headers=headers)
        return 200 <= resp.status_code < 300


@celery_app.task(name="webhooks.dispatch", bind=True, max_retries=5)
def dispatch_webhook_task(self, webhook_id: str, event: str, payload: dict):
    """Celery task: send webhook with exponential backoff on failure."""
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    async def _run():
        from app.models.webhook import UserWebhook
        from app.db import get_async_session

        async with get_async_session() as session:
            import uuid
            wh = await session.get(UserWebhook, uuid.UUID(webhook_id))
            if not wh or not wh.is_active:
                return

            secret = decrypt_secret(wh.secret_encrypted)
            success = await dispatch_webhook_request(url=wh.url, secret=secret, payload=payload)

            if not success:
                delay = 2 ** self.request.retries * 30  # 30s, 60s, 120s, 240s, 480s
                raise self.retry(countdown=delay)

    asyncio.run(_run())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_services/test_webhook_dispatcher.py -v 2>&1 | tail -10
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/services/webhook_dispatcher.py tests/test_services/test_webhook_dispatcher.py
git commit -m "feat(2d): WebhookDispatcher — HMAC-SHA256 signing + Celery 5× exponential retry"
```

---

## Task 6: Remaining Beat jobs — token reset + artifact cleanup + backups (TDD)

**Files:**
- Create: `backend/tests/test_worker/test_backup_jobs.py`
- Create: `backend/app/worker/backup_jobs.py`
- Modify: `backend/app/worker/beat_jobs.py`
- Modify: `backend/app/worker/celery_app.py`

- [ ] **Step 1: Write failing tests — `backend/tests/test_worker/test_backup_jobs.py`**

```python
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


def test_backup_postgres_calls_pg_dump():
    with patch("app.worker.backup_jobs.subprocess.run") as mock_run, \
         patch("app.worker.backup_jobs.minio_service") as mock_minio:
        mock_run.return_value = MagicMock(returncode=0, stdout=b"dump-data")
        mock_minio.upload_bytes = MagicMock()
        from app.worker.backup_jobs import backup_postgres
        result = backup_postgres()
        mock_run.assert_called_once()
        mock_minio.upload_bytes.assert_called_once()
        assert result["success"] is True


def test_backup_qdrant_calls_snapshot_api():
    with patch("app.worker.backup_jobs.httpx.post") as mock_post, \
         patch("app.worker.backup_jobs.httpx.get") as mock_get, \
         patch("app.worker.backup_jobs.minio_service") as mock_minio:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"result": {"name": "snap.snapshot"}})
        mock_get.return_value = MagicMock(status_code=200, content=b"snapshot-data")
        mock_minio.upload_bytes = MagicMock()
        from app.worker.backup_jobs import backup_qdrant
        result = backup_qdrant()
        assert result["success"] is True
        mock_minio.upload_bytes.assert_called_once()


def test_cleanup_artifacts_removes_old_objects():
    with patch("app.worker.beat_jobs.minio_service") as mock_minio:
        mock_minio._client = MagicMock()
        mock_minio._client.list_objects = MagicMock(return_value=[])
        from app.worker.beat_jobs import cleanup_artifacts
        result = cleanup_artifacts()
        assert "deleted" in result
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_worker/test_backup_jobs.py -v 2>&1 | head -15
```

Expected: FAIL — module not found

- [ ] **Step 3: Create `backend/app/worker/backup_jobs.py`**

```python
"""Backup Celery tasks: PostgreSQL dump to MinIO + Qdrant snapshot (spec §18 BK-1..3)."""
import subprocess
import datetime
import httpx
from app.worker.celery_app import celery_app
from app.services.minio_client import minio_service
from app.config import settings


@celery_app.task(name="beat.backup_postgres")
def backup_postgres() -> dict:
    """pg_dump → gzip → upload to agentis-backups bucket."""
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    object_name = f"backups/postgres/{ts}.sql.gz"

    result = subprocess.run(
        ["pg_dump", "--format=custom", settings.postgres_direct_url],
        capture_output=True,
    )
    if result.returncode != 0:
        return {"success": False, "error": result.stderr.decode()}

    minio_service.upload_bytes(
        object_name=object_name,
        data=result.stdout,
        content_type="application/octet-stream",
        bucket=settings.minio_bucket_backups,
    )
    return {"success": True, "object": object_name, "size_bytes": len(result.stdout)}


@celery_app.task(name="beat.backup_qdrant")
def backup_qdrant() -> dict:
    """Create Qdrant snapshot → download → upload to MinIO."""
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    collection = settings.qdrant_collection

    # Create snapshot
    resp = httpx.post(
        f"{settings.qdrant_url}/collections/{collection}/snapshots",
        timeout=120.0,
    )
    if resp.status_code not in (200, 201):
        return {"success": False, "error": resp.text}

    snap_name = resp.json()["result"]["name"]
    snap_resp = httpx.get(
        f"{settings.qdrant_url}/collections/{collection}/snapshots/{snap_name}",
        timeout=300.0,
    )

    object_name = f"backups/qdrant/{ts}_{snap_name}"
    minio_service.upload_bytes(
        object_name=object_name,
        data=snap_resp.content,
        content_type="application/octet-stream",
        bucket=settings.minio_bucket_backups,
    )
    return {"success": True, "object": object_name, "size_bytes": len(snap_resp.content)}
```

- [ ] **Step 4: Add remaining Beat jobs to `backend/app/worker/beat_jobs.py`**

```python
@celery_app.task(name="beat.cleanup_artifacts")
def cleanup_artifacts() -> dict:
    """Delete MinIO artifact objects older than 30 days (spec §18 BK-4)."""
    import datetime
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    objects = minio_service._client.list_objects(
        settings.minio_bucket_artifacts, recursive=True
    )
    deleted = 0
    for obj in objects:
        if obj.last_modified and obj.last_modified.replace(tzinfo=None) < cutoff:
            minio_service._client.remove_object(settings.minio_bucket_artifacts, obj.object_name)
            deleted += 1
    return {"deleted": deleted}


@celery_app.task(name="beat.reset_monthly_tokens")
def reset_monthly_tokens() -> dict:
    """Reset token_used_this_month to 0 for all users on the 1st of each month."""
    import asyncio
    from sqlalchemy import update

    async def _run():
        from app.db import get_async_session
        from app.models.user import User
        async with get_async_session() as session:
            result = await session.execute(update(User).values(token_used_this_month=0))
            await session.commit()
            return result.rowcount

    count = asyncio.run(_run())
    return {"reset": count}
```

Also add the import at top of `beat_jobs.py`:

```python
from app.services.minio_client import minio_service
from app.config import settings
```

- [ ] **Step 5: Update `backend/app/worker/celery_app.py` beat schedule** — add the 4 remaining jobs:

```python
celery_app.conf.beat_schedule.update({
    "cleanup-artifacts-weekly": {
        "task": "beat.cleanup_artifacts",
        "schedule": 604800.0,  # every 7 days
    },
    "reset-monthly-tokens": {
        "task": "beat.reset_monthly_tokens",
        "schedule": crontab(day_of_month="1", hour="0", minute="0"),
    },
    "backup-postgres-daily": {
        "task": "beat.backup_postgres",
        "schedule": 86400.0,
    },
    "backup-qdrant-daily": {
        "task": "beat.backup_qdrant",
        "schedule": 86400.0,
    },
})

celery_app.conf.include = [
    "app.worker.tasks",
    "app.worker.beat_jobs",
    "app.worker.backup_jobs",
    "app.services.webhook_dispatcher",
]
```

Add this import at the top of `celery_app.py`:

```python
from celery.schedules import crontab
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_worker/ -v 2>&1 | tail -15
```

Expected: All 5 Beat job tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/worker/backup_jobs.py app/worker/beat_jobs.py app/worker/celery_app.py \
        tests/test_worker/test_backup_jobs.py
git commit -m "feat(2d): Beat jobs — artifact cleanup, monthly token reset, Postgres+Qdrant backup"
```

---

## Task 7: Run full test suite + final audit

- [ ] **Step 1: Run complete backend test suite**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest --tb=short -q 2>&1 | tail -20
```

Expected: All tests pass. Note the total count.

- [ ] **Step 2: Verify no import errors**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -c "from app.main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit if any fixes were needed**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add -u
git commit -m "fix(2d): final import fixes after full test suite run"
```

---

## Task 8: Vérification manuelle navigateur (Phase 2D)

- [ ] **Step 1: Démarrer la stack complète**

```bash
cd /home/yulcom/web/perso/agentis
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose ps
```

Expected: tous les services `Up`, migration `add_orgs_webhooks` appliquée.

- [ ] **Step 2: Test création d'organisation**

Via le skill `verify`, ouvrir `http://localhost:3000`, se connecter, aller dans Paramètres. Vérifier qu'il est possible de créer une organisation et de la définir comme active.

- [ ] **Step 3: Test webhook**

Dans Paramètres > Webhooks, créer un webhook pointant vers `https://webhook.site/<uuid>` (ou un endpoint de test local). Soumettre une tâche. Vérifier que le webhook est déclenché (logs Celery worker) après `task_completed`.

- [ ] **Step 4: Vérifier les buckets MinIO**

```bash
curl -s http://localhost:9000/agentis-backups/ 2>&1 | head -5
```

Ou ouvrir la console MinIO `http://localhost:9001` et vérifier le bucket `agentis-backups`.

- [ ] **Step 5: Test manuel du Beat schedule**

Déclencher manuellement une tâche Beat :

```bash
docker compose exec worker celery -A app.worker.celery_app call beat.decay_memory_importance
```

Expected: résultat JSON `{"updated": N}` dans les logs.

- [ ] **Step 6: Commit final Phase 2 complète**

```bash
cd /home/yulcom/web/perso/agentis
git add .
git commit -m "feat: Phase 2 complete — tools, memory, HITL, MinIO, admin, observability, orgs, webhooks, backup"
```

---

## Self-Review Checklist

Spec coverage vérifiée contre `docs/superpowers/specs/2026-06-07-phase2-design.md` :

| Item spec | Tâche plan |
|-----------|-----------|
| BR-MEM-20..31 — long-term Qdrant memory | Phase 2A Task 3 |
| BR-TOOL-doc_parser | Phase 2A Task 5 |
| BR-TOOL-http_caller + HITL guard | Phase 2A Task 6 |
| Celery Beat — decay + prune | Phase 2A Task 4 |
| MinIO buckets + presigned URLs | Phase 2B Task 1-3 |
| HITL WebSocket endpoint | Phase 2B Task 5 |
| Orchestrator pause/resume | Phase 2B Task 6 |
| HitlPanel UI — Option A inline | Phase 2B Task 7 |
| AuditEvent + audit service | Phase 2C Task 1-2 |
| Admin dashboard + RBAC guard | Phase 2C Task 3 |
| Prometheus + structlog + Loki | Phase 2C Task 4 |
| Admin sidebar layout | Phase 2C Task 5-6 |
| Organization model + CRUD | Phase 2D Task 1+3 |
| Webhooks + Fernet + HMAC | Phase 2D Task 4-5 |
| Beat: cleanup_artifacts, reset_tokens | Phase 2D Task 6 |
| Beat: backup_postgres, backup_qdrant | Phase 2D Task 6 |
