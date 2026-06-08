# Phase 2C — Admin Dashboard + Observabilité : Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the admin dashboard (sidebar layout, usage metrics, user management, audit log) and wire up Prometheus metrics + structured logging with Loki.

**Architecture:** Admin routes live under `/admin` with a dedicated server-side layout that checks the `admin` or `operator` role via Next.js middleware. The backend exposes `/api/v1/admin/*` endpoints guarded by `require_admin` dependency. Prometheus metrics are exposed on `/metrics` (internal port 9090); structlog emits JSON to stdout, captured by Docker's logging driver and forwarded to Loki. The audit log writes to a new `audit_events` PostgreSQL table on every sensitive action.

**Tech Stack:** Next.js 15 App Router, shadcn/ui (Card, Table, Badge, Sidebar), fastapi-admin (custom — no third-party), prometheus-client, structlog, python-loki-logger, Alembic.

---

## File Map

### New files
```
backend/app/routers/admin.py                     — GET /admin/stats, GET /admin/users, PATCH /admin/users/{id}, GET /admin/audit
backend/app/models/audit.py                      — AuditEvent model
backend/app/services/audit.py                    — write_audit_event() helper
backend/app/observability/metrics.py             — Prometheus counters/histograms + /metrics route
backend/app/observability/logging.py             — structlog config + Loki handler
backend/alembic/versions/<hash>_add_audit_events.py
backend/tests/test_routers/test_admin.py
backend/tests/test_services/test_audit.py
frontend/src/app/[locale]/admin/layout.tsx       — Admin sidebar layout + role guard
frontend/src/app/[locale]/admin/page.tsx         — Dashboard: KPI cards + token usage chart
frontend/src/app/[locale]/admin/users/page.tsx   — User list table with role badge + suspend toggle
frontend/src/app/[locale]/admin/audit/page.tsx   — Audit log table with filters
frontend/src/components/admin/AdminSidebar.tsx   — Sidebar nav: Dashboard, Users, Audit, Tools, LLM Config
frontend/src/components/admin/KpiCard.tsx        — Reusable KPI card
frontend/src/components/admin/TokenUsageBar.tsx  — Monthly token usage bar
```

### Modified files
```
backend/app/auth/dependencies.py                 — add require_admin dependency
backend/app/main.py                              — include admin + metrics routers; init structlog
backend/app/config.py                            — add Loki + Prometheus settings
docker-compose.yml                               — add prometheus + loki services
frontend/src/components/layout/Nav.tsx           — add "Admin" link (admin/operator only)
frontend/src/middleware.ts                        — protect /admin/* routes by role
```

---

## Task 1: AuditEvent model + migration

**Files:**
- Create: `backend/app/models/audit.py`
- Create: `backend/alembic/versions/<hash>_add_audit_events.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create `backend/app/models/audit.py`**

```python
from uuid import uuid4, UUID
from datetime import datetime
from sqlalchemy import String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
```

- [ ] **Step 2: Register in `backend/app/models/__init__.py`**

```python
from app.models.audit import AuditEvent  # noqa: F401
```

- [ ] **Step 3: Write Alembic migration**

```python
"""add_audit_events

Revision ID: <generated>
Revises: <previous_revision>
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '<generated>'
down_revision = '<previous>'  # fill in after generating
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'audit_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('actor_id', sa.String(64), nullable=False),
        sa.Column('actor_email', sa.String(255), nullable=False),
        sa.Column('action', sa.String(128), nullable=False),
        sa.Column('resource_type', sa.String(64), nullable=False),
        sa.Column('resource_id', sa.String(64), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_audit_events_actor_id', 'audit_events', ['actor_id'])
    op.create_index('ix_audit_events_action', 'audit_events', ['action'])
    op.create_index('ix_audit_events_created_at', 'audit_events', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_audit_events_created_at', 'audit_events')
    op.drop_index('ix_audit_events_action', 'audit_events')
    op.drop_index('ix_audit_events_actor_id', 'audit_events')
    op.drop_table('audit_events')
```

Run to generate actual revision:

```bash
cd /home/yulcom/web/perso/agentis/backend
alembic revision --autogenerate -m "add_audit_events"
```

- [ ] **Step 4: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/models/audit.py app/models/__init__.py alembic/versions/
git commit -m "feat(2c): AuditEvent model + Alembic migration"
```

---

## Task 2: Audit service (TDD)

**Files:**
- Create: `backend/tests/test_services/test_audit.py`
- Create: `backend/app/services/audit.py`

- [ ] **Step 1: Write failing tests — `backend/tests/test_services/test_audit.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


@pytest.mark.asyncio
async def test_write_audit_event_inserts_row():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    with patch("app.services.audit.get_async_session") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.services.audit import write_audit_event
        await write_audit_event(
            actor_id=str(uuid4()),
            actor_email="admin@test.com",
            action="user.suspend",
            resource_type="user",
            resource_id=str(uuid4()),
            metadata={"reason": "spam"},
        )
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_write_audit_event_stores_correct_action():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    added_obj = None

    def capture_add(obj):
        nonlocal added_obj
        added_obj = obj

    mock_session.add.side_effect = capture_add

    with patch("app.services.audit.get_async_session") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.services.audit import write_audit_event
        await write_audit_event(
            actor_id="u1",
            actor_email="a@b.com",
            action="llm.config.update",
            resource_type="llm_config",
        )
        assert added_obj is not None
        assert added_obj.action == "llm.config.update"
        assert added_obj.actor_email == "a@b.com"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_services/test_audit.py -v 2>&1 | head -15
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.audit'`

- [ ] **Step 3: Implement `backend/app/services/audit.py`**

```python
"""Audit event persistence (spec §14 AUDIT-1)."""
from contextlib import asynccontextmanager
from app.models.audit import AuditEvent
from app.db import get_async_session


async def write_audit_event(
    actor_id: str,
    actor_email: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Persist a single audit event. Fire-and-forget — never raises."""
    event = AuditEvent(
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_=metadata or {},
    )
    async with get_async_session() as session:
        session.add(event)
        await session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_services/test_audit.py -v 2>&1 | tail -10
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/services/audit.py tests/test_services/test_audit.py
git commit -m "feat(2c): write_audit_event service — PostgreSQL audit persistence"
```

---

## Task 3: `require_admin` dependency + admin router (TDD)

**Files:**
- Modify: `backend/app/auth/dependencies.py`
- Create: `backend/tests/test_routers/test_admin.py`
- Create: `backend/app/routers/admin.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add `require_admin` to `backend/app/auth/dependencies.py`**

```python
from fastapi import HTTPException, status

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Allow only admin and operator roles (spec §3.2 RBAC)."""
    if current_user.role not in ("admin", "operator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
```

- [ ] **Step 2: Write failing tests — `backend/tests/test_routers/test_admin.py`**

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_stats_requires_admin(async_client: AsyncClient, auth_headers: dict):
    """Regular user should get 403 on admin endpoints."""
    resp = await async_client.get("/api/v1/admin/stats", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_stats_returns_data_for_admin(async_client: AsyncClient, admin_headers: dict):
    """Admin user gets usage stats."""
    resp = await async_client.get("/api/v1/admin/stats", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks_today" in data
    assert "active_users" in data
    assert "tokens_this_month" in data


@pytest.mark.asyncio
async def test_admin_users_list_paginated(async_client: AsyncClient, admin_headers: dict):
    """GET /admin/users returns paginated user list."""
    resp = await async_client.get("/api/v1/admin/users?limit=10&offset=0", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_admin_audit_log_returns_list(async_client: AsyncClient, admin_headers: dict):
    """GET /admin/audit returns audit event list."""
    resp = await async_client.get("/api/v1/admin/audit?limit=20", headers=admin_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json().get("items"), list)
```

Note: `admin_headers` fixture creates a user with `role="admin"` and returns its auth headers. Add this to `tests/conftest.py` if missing:

```python
@pytest_asyncio.fixture
async def admin_headers(async_client: AsyncClient) -> dict:
    email = f"admin_{uuid4().hex[:8]}@test.com"
    # Create user then promote to admin directly in DB
    resp = await async_client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!"})
    assert resp.status_code == 201
    # Promote role in DB
    async with get_async_session() as session:
        from sqlalchemy import update
        from app.models.user import User
        await session.execute(update(User).where(User.email == email).values(role="admin"))
        await session.commit()
    resp2 = await async_client.post("/api/v1/auth/login", json={"email": email, "password": "Pass1234!"})
    token = resp2.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 3: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_routers/test_admin.py -v 2>&1 | head -15
```

Expected: FAIL — admin router 404

- [ ] **Step 4: Implement `backend/app/routers/admin.py`**

```python
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import require_admin
from app.models.user import User
from app.models.task import Task
from app.models.audit import AuditEvent
from app.db import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def get_stats(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    tasks_today = await db.scalar(
        select(func.count(Task.id)).where(Task.created_at >= today_start)
    )
    active_users = await db.scalar(
        select(func.count(func.distinct(Task.user_id))).where(Task.created_at >= today_start)
    )
    tokens_this_month = await db.scalar(
        select(func.coalesce(func.sum(User.token_used_this_month), 0))
    )

    return {
        "tasks_today": tasks_today or 0,
        "active_users": active_users or 0,
        "tokens_this_month": tokens_this_month or 0,
    }


@router.get("/users")
async def list_users(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total = await db.scalar(select(func.count(User.id)))
    result = await db.execute(select(User).offset(offset).limit(limit).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "name": u.name,
                "role": u.role,
                "is_active": u.is_active,
                "token_used_this_month": u.token_used_this_month,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import write_audit_event
    import uuid
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")

    allowed_fields = {"is_active", "role"}
    for field in allowed_fields:
        if field in body:
            setattr(user, field, body[field])

    await db.commit()
    await write_audit_event(
        actor_id=str(admin.id),
        actor_email=admin.email,
        action="user.update",
        resource_type="user",
        resource_id=user_id,
        metadata={k: v for k, v in body.items() if k in allowed_fields},
    )
    return {"id": user_id, "updated": True}


@router.get("/audit")
async def list_audit_events(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    action: str | None = Query(None),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(AuditEvent).order_by(AuditEvent.created_at.desc())
    if action:
        q = q.where(AuditEvent.action == action)
    total = await db.scalar(select(func.count(AuditEvent.id)))
    result = await db.execute(q.offset(offset).limit(limit))
    events = result.scalars().all()
    return {
        "items": [
            {
                "id": str(e.id),
                "actor_email": e.actor_email,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        "total": total,
    }
```

- [ ] **Step 5: Register in `backend/app/main.py`**

```python
from app.routers.admin import router as admin_router
app.include_router(admin_router, prefix="/api/v1")
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_routers/test_admin.py -v 2>&1 | tail -10
```

Expected: 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/auth/dependencies.py app/routers/admin.py app/main.py tests/test_routers/test_admin.py
git commit -m "feat(2c): admin router — stats, users list, audit log; require_admin guard"
```

---

## Task 4: Prometheus metrics + structlog

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/observability/metrics.py`
- Create: `backend/app/observability/logging.py`
- Modify: `backend/app/main.py`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add observability settings to `backend/app/config.py`**

```python
    # Observability
    prometheus_enabled: bool = True
    loki_url: str = ""
    loki_app_name: str = "agentis-backend"
```

- [ ] **Step 2: Install dependencies**

```bash
pip install "prometheus-client>=0.20" "structlog>=24.0" "python-loki-logger>=1.0"
```

- [ ] **Step 3: Create `backend/app/observability/__init__.py`**

```bash
touch /home/yulcom/web/perso/agentis/backend/app/observability/__init__.py
```

- [ ] **Step 4: Implement `backend/app/observability/metrics.py`**

```python
"""Prometheus metrics registry (spec §17 OBS-1)."""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter
from fastapi.responses import Response

# Counters
tasks_created_total = Counter("agentis_tasks_created_total", "Tasks created", ["status"])
tool_calls_total = Counter("agentis_tool_calls_total", "Tool calls", ["tool_name", "success"])
llm_tokens_total = Counter("agentis_llm_tokens_total", "LLM tokens consumed", ["provider", "model"])
hitl_requests_total = Counter("agentis_hitl_requests_total", "HITL requests triggered")
hitl_responses_total = Counter("agentis_hitl_responses_total", "HITL responses received", ["outcome"])

# Histograms
task_duration_seconds = Histogram(
    "agentis_task_duration_seconds", "Task completion time",
    buckets=[5, 15, 30, 60, 120, 300, 600, 1800]
)
tool_duration_seconds = Histogram(
    "agentis_tool_duration_seconds", "Tool call duration", ["tool_name"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60]
)

# Gauges
active_tasks_gauge = Gauge("agentis_active_tasks", "Currently running tasks")
sandbox_sessions_gauge = Gauge("agentis_sandbox_sessions", "Active sandbox sessions")

# Router
metrics_router = APIRouter(tags=["metrics"])


@metrics_router.get("/metrics")
async def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 5: Implement `backend/app/observability/logging.py`**

```python
"""Structlog configuration with optional Loki handler (spec §17 OBS-4)."""
import logging
import structlog
from app.config import settings


def configure_logging() -> None:
    """Call once at startup. Sets up structlog JSON renderer + optional Loki handler."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    if settings.loki_url:
        try:
            from logging_loki import LokiHandler
            loki_handler = LokiHandler(
                url=f"{settings.loki_url}/loki/api/v1/push",
                tags={"app": settings.loki_app_name},
                version="1",
            )
            loki_handler.setLevel(logging.INFO)
            logging.getLogger().addHandler(loki_handler)
        except ImportError:
            pass  # Loki optional
```

- [ ] **Step 6: Wire up in `backend/app/main.py`**

Add at the top of the startup sequence:

```python
from app.observability.metrics import metrics_router
from app.observability.logging import configure_logging

# In lifespan or at module level:
configure_logging()
app.include_router(metrics_router)  # no prefix — /metrics is standard
```

- [ ] **Step 7: Add Prometheus + Loki to `docker-compose.yml`**

Add after the `qdrant` service:

```yaml
  prometheus:
    image: prom/prometheus:v2.51.2
    ports:
      - "9090:9090"
    volumes:
      - ./infra/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    depends_on:
      - api

  loki:
    image: grafana/loki:3.0.0
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml

  grafana:
    image: grafana/grafana:11.0.0
    ports:
      - "3001:3000"
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: Admin
    volumes:
      - grafana_data:/var/lib/grafana
    depends_on:
      - prometheus
      - loki
```

Add `grafana_data:` to the volumes section.

- [ ] **Step 8: Create `infra/prometheus.yml`**

```bash
mkdir -p /home/yulcom/web/perso/agentis/infra
```

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: agentis-backend
    static_configs:
      - targets: ["api:8000"]
    metrics_path: /metrics
```

- [ ] **Step 9: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add backend/app/observability/ backend/app/main.py backend/app/config.py \
        docker-compose.yml infra/prometheus.yml
git commit -m "feat(2c): Prometheus metrics + structlog/Loki observability stack"
```

---

## Task 5: Frontend — Admin sidebar layout + role guard

**Files:**
- Create: `frontend/src/components/admin/AdminSidebar.tsx`
- Create: `frontend/src/app/[locale]/admin/layout.tsx`
- Modify: `frontend/src/middleware.ts`

- [ ] **Step 1: Create `frontend/src/components/admin/AdminSidebar.tsx`**

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, ScrollText, Wrench, Cpu } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/admin", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/users", label: "Utilisateurs", icon: Users },
  { href: "/admin/audit", label: "Audit Log", icon: ScrollText },
  { href: "/admin/tools", label: "Outils", icon: Wrench },
  { href: "/admin/llm", label: "LLM Config", icon: Cpu },
];

export function AdminSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-52 shrink-0 border-r border-border bg-card flex flex-col min-h-screen">
      <div className="px-4 py-4 border-b border-border">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Agentis · Admin
        </span>
      </div>
      <nav className="flex-1 p-2 space-y-0.5">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== "/admin" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                active
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
```

- [ ] **Step 2: Create `frontend/src/app/[locale]/admin/layout.tsx`**

```tsx
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { redirect } from "next/navigation";
import { getServerSession } from "@/lib/auth-server";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const session = await getServerSession();

  if (!session || !["admin", "operator"].includes(session.role)) {
    redirect("/");
  }

  return (
    <div className="flex min-h-screen">
      <AdminSidebar />
      <main className="flex-1 p-6 overflow-auto">{children}</main>
    </div>
  );
}
```

- [ ] **Step 3: Update `frontend/src/middleware.ts` to protect /admin routes**

Add to the matcher and role check:

```typescript
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.includes("/admin")) {
    const token = request.cookies.get("auth_token")?.value;
    if (!token) {
      return NextResponse.redirect(new URL("/login", request.url));
    }
    // Role check happens in layout server component (can read from JWT)
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next|favicon).*)"],
};
```

- [ ] **Step 4: Commit**

```bash
cd /home/yulcom/web/perso/agentis/frontend
git add src/components/admin/AdminSidebar.tsx src/app/
git commit -m "feat(2c): admin sidebar layout + middleware role guard"
```

---

## Task 6: Frontend — Dashboard page + KPI components

**Files:**
- Create: `frontend/src/components/admin/KpiCard.tsx`
- Create: `frontend/src/components/admin/TokenUsageBar.tsx`
- Create: `frontend/src/app/[locale]/admin/page.tsx`

- [ ] **Step 1: Create `frontend/src/components/admin/KpiCard.tsx`**

```tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { LucideIcon } from "lucide-react";

interface KpiCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  description?: string;
}

export function KpiCard({ title, value, icon: Icon, description }: KpiCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <Icon size={16} className="text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {description && <p className="text-xs text-muted-foreground mt-1">{description}</p>}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/admin/TokenUsageBar.tsx`**

```tsx
interface TokenUsageBarProps {
  used: number;
  limit: number;
  label?: string;
}

export function TokenUsageBar({ used, limit, label = "Tokens ce mois" }: TokenUsageBarProps) {
  const pct = Math.min(100, Math.round((used / (limit || 1)) * 100));
  const color = pct > 85 ? "bg-destructive" : pct > 60 ? "bg-yellow-500" : "bg-primary";

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{(used / 1_000_000).toFixed(1)}M / {(limit / 1_000_000).toFixed(0)}M</span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-muted-foreground text-right">{pct}% utilisé</p>
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/src/app/[locale]/admin/page.tsx`**

```tsx
import { Activity, Users, CheckCircle, Clock } from "lucide-react";
import { KpiCard } from "@/components/admin/KpiCard";
import { TokenUsageBar } from "@/components/admin/TokenUsageBar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

async function getAdminStats() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://api:8000";
  // In a real app, pass the auth cookie server-side
  try {
    const res = await fetch(`${apiUrl}/api/v1/admin/stats`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function AdminDashboardPage() {
  const stats = await getAdminStats();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground text-sm mt-1">Vue d&apos;ensemble de la plateforme</p>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard title="Tâches aujourd'hui" value={stats?.tasks_today ?? "—"} icon={Activity} />
        <KpiCard title="Utilisateurs actifs" value={stats?.active_users ?? "—"} icon={Users} />
        <KpiCard title="Tâches terminées" value={stats?.tasks_completed ?? "—"} icon={CheckCircle} />
        <KpiCard title="Temps moyen" value={stats?.avg_duration_s ? `${stats.avg_duration_s}s` : "—"} icon={Clock} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Utilisation tokens</CardTitle>
        </CardHeader>
        <CardContent>
          <TokenUsageBar
            used={stats?.tokens_this_month ?? 0}
            limit={10_000_000}
          />
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Create `frontend/src/app/[locale]/admin/users/page.tsx`**

```tsx
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

async function getUsers() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://api:8000";
  try {
    const res = await fetch(`${apiUrl}/api/v1/admin/users?limit=50`, { cache: "no-store" });
    if (!res.ok) return { items: [], total: 0 };
    return res.json();
  } catch {
    return { items: [], total: 0 };
  }
}

const roleBadge: Record<string, string> = {
  admin: "bg-red-500/15 text-red-400 border-red-500/30",
  operator: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  user: "bg-blue-500/15 text-blue-400 border-blue-500/30",
};

export default async function AdminUsersPage() {
  const { items, total } = await getUsers();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Utilisateurs</h1>
        <span className="text-sm text-muted-foreground">{total} total</span>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Email</TableHead>
            <TableHead>Nom</TableHead>
            <TableHead>Rôle</TableHead>
            <TableHead>Statut</TableHead>
            <TableHead className="text-right">Tokens (mois)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((u: any) => (
            <TableRow key={u.id}>
              <TableCell className="font-mono text-sm">{u.email}</TableCell>
              <TableCell>{u.name ?? "—"}</TableCell>
              <TableCell>
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs border ${roleBadge[u.role] ?? ""}`}>
                  {u.role}
                </span>
              </TableCell>
              <TableCell>
                <Badge variant={u.is_active ? "default" : "destructive"}>
                  {u.is_active ? "Actif" : "Suspendu"}
                </Badge>
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {(u.token_used_this_month ?? 0).toLocaleString("fr")}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 5: Create `frontend/src/app/[locale]/admin/audit/page.tsx`**

```tsx
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

async function getAuditEvents() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://api:8000";
  try {
    const res = await fetch(`${apiUrl}/api/v1/admin/audit?limit=50`, { cache: "no-store" });
    if (!res.ok) return { items: [] };
    return res.json();
  } catch {
    return { items: [] };
  }
}

export default async function AdminAuditPage() {
  const { items } = await getAuditEvents();

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Audit Log</h1>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Date</TableHead>
            <TableHead>Acteur</TableHead>
            <TableHead>Action</TableHead>
            <TableHead>Ressource</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((e: any) => (
            <TableRow key={e.id}>
              <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                {new Date(e.created_at).toLocaleString("fr")}
              </TableCell>
              <TableCell className="font-mono text-xs">{e.actor_email}</TableCell>
              <TableCell>
                <code className="bg-muted px-1.5 py-0.5 rounded text-xs">{e.action}</code>
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {e.resource_type}{e.resource_id ? ` / ${e.resource_id.slice(0, 8)}…` : ""}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

- [ ] **Step 6: Add "Admin" link to main Nav for admin/operator users**

In `frontend/src/components/layout/Nav.tsx`, add a conditional link:

```tsx
{session?.role && ["admin", "operator"].includes(session.role) && (
  <Link href="/admin" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
    Admin
  </Link>
)}
```

- [ ] **Step 7: Commit**

```bash
cd /home/yulcom/web/perso/agentis/frontend
git add src/components/admin/ src/app/
git commit -m "feat(2c): admin dashboard — KPI cards, users table, audit log, sidebar layout"
```

---

## Task 7: Vérification manuelle navigateur (Phase 2C)

- [ ] **Step 1: Démarrer la stack complète**

```bash
cd /home/yulcom/web/perso/agentis
docker compose up -d --build
docker compose ps
```

Expected: `prometheus`, `loki`, `grafana`, plus tous les services précédents.

- [ ] **Step 2: Vérifier /metrics**

```bash
curl http://localhost:8000/metrics | grep agentis_tasks
```

Expected: compteurs Prometheus présents.

- [ ] **Step 3: Vérifier Prometheus**

Ouvrir `http://localhost:9090/targets`. Le target `agentis-backend` doit être `UP`.

- [ ] **Step 4: Vérifier Grafana**

Ouvrir `http://localhost:3001`. Vérifier la connexion à Prometheus comme datasource. Créer un dashboard simple avec la métrique `agentis_tasks_created_total`.

- [ ] **Step 5: Test dashboard admin navigateur**

Utiliser le skill `verify` pour :
1. Se connecter en tant qu'admin sur `http://localhost:3000`
2. Vérifier que le lien "Admin" apparaît dans la Nav
3. Ouvrir `/admin` — vérifier les KPI cards
4. Ouvrir `/admin/users` — vérifier la table
5. Ouvrir `/admin/audit` — vérifier le log (vide est OK)

- [ ] **Step 6: Vérifier que les utilisateurs non-admin sont redirigés**

Se connecter avec un compte `user` ordinaire. Tenter d'accéder à `http://localhost:3000/admin`. Vérifier la redirection vers `/`.

- [ ] **Step 7: Commit final Phase 2C**

```bash
cd /home/yulcom/web/perso/agentis
git add .
git commit -m "feat(2c): Phase 2C complete — admin dashboard, audit log, Prometheus/Grafana observability"
```
