# Phase 1A — Infrastructure + Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the full development environment (Docker Compose with all services), create the complete PostgreSQL schema with Alembic migrations, configure PgBouncer, and implement a working FastAPI backend with JWT auth, API key auth, and rate limiting — the foundation every other Phase 1 sub-plan builds on.

**Architecture:** FastAPI (async, Python 3.12) connects to PostgreSQL via PgBouncer (transaction-mode pool). Alembic manages schema migrations. Auth uses RS256 JWT (access token in response body, refresh token as httpOnly cookie) and API keys with `agentis_sk_` prefix sent via `X-API-Key` header. Redis DB0 is reserved for Celery (Phase 1C); Redis DB1 for cache.

**Tech Stack:** Python 3.12, FastAPI 0.115, SQLAlchemy 2.0 (async + asyncpg), Alembic 1.13, PgBouncer, PyJWT, passlib[bcrypt], pydantic-settings, pytest + pytest-asyncio + httpx, Docker Compose v2, structlog, Redis 7, PostgreSQL 16.

**Spec reference:** `docs/agentis_spec.md` — §3 (Epic 1 Auth), §14 (Data Model), §16 (Security), §17 (Infrastructure), §19 (Config).

---

## Deliverable

At the end of this plan, running `docker compose up` brings up a fully functional environment. An engineer can:
- `POST /api/v1/auth/register` → create account
- `POST /api/v1/auth/login` → get JWT access token + refresh cookie
- `POST /api/v1/auth/refresh` → rotate tokens
- `POST /api/v1/auth/logout` → revoke session
- `GET /api/v1/health` → `{"status": "ok"}` with DB connectivity check
- Use `X-API-Key: agentis_sk_...` on any endpoint
- All tables exist in PostgreSQL with correct indexes and constraints

---

## File Structure

```
agentis/
├── backend/
│   ├── alembic/
│   │   ├── versions/
│   │   │   └── 0001_initial_schema.py     # Full schema from spec §14
│   │   └── env.py                         # Alembic async env config
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                        # FastAPI app + lifespan hooks
│   │   ├── config.py                      # pydantic-settings Settings class
│   │   ├── database.py                    # Async SQLAlchemy engine + session factory
│   │   ├── models/
│   │   │   ├── __init__.py                # Re-exports all models (Alembic needs this)
│   │   │   ├── base.py                    # DeclarativeBase + TimestampMixin
│   │   │   ├── user.py                    # User, RefreshToken, ApiKey
│   │   │   ├── task.py                    # Task, TaskStep, Artifact
│   │   │   ├── org.py                     # Organization, OrganizationMembership
│   │   │   └── audit.py                   # AuditLog
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── common.py                  # ErrorResponse, PaginatedResponse
│   │   │   └── auth.py                    # RegisterRequest, LoginRequest, TokenResponse, etc.
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   └── auth.py                    # /auth/* endpoints
│   │   └── auth/
│   │       ├── __init__.py
│   │       ├── jwt.py                     # create_access_token, decode_token (RS256)
│   │       ├── api_keys.py                # generate_key, hash_key, verify_key
│   │       ├── password.py                # hash_password, verify_password (bcrypt)
│   │       ├── rate_limiter.py            # Redis sliding-window rate limiter
│   │       └── dependencies.py            # get_current_user FastAPI dependency
│   ├── tests/
│   │   ├── conftest.py                    # Fixtures: async test client, test DB, test user
│   │   ├── test_health.py
│   │   ├── test_auth_register.py
│   │   ├── test_auth_login.py
│   │   ├── test_auth_refresh.py
│   │   ├── test_auth_logout.py
│   │   └── test_api_keys.py
│   ├── alembic.ini
│   ├── pyproject.toml
│   └── Dockerfile
├── docker-compose.yml
├── docker-compose.override.yml            # Dev hot-reload volumes
├── pgbouncer/
│   └── pgbouncer.ini
├── squid/
│   └── squid.conf                         # Phase 1: permissive dev config
└── .env.example
```

---

## Task 1: Project Skeleton & Docker Compose

**Files:**
- Create: `backend/pyproject.toml`
- Create: `docker-compose.yml`
- Create: `docker-compose.override.yml`
- Create: `pgbouncer/pgbouncer.ini`
- Create: `.env.example`
- Create: `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config.py`

---

- [ ] **Step 1.1: Create `backend/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agentis-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "pydantic-settings>=2.3",
    "pydantic[email]>=2.7",
    "pyjwt[crypto]>=2.8",
    "passlib[bcrypt]>=1.7",
    "redis>=5.0",
    "structlog>=24.0",
    "sse-starlette>=2.1",
    "httpx>=0.27",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "anyio[trio]>=4.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff.lint]
select = ["E", "F", "I"]
```

- [ ] **Step 1.2: Create `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, RedisDsn


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTIS_", env_file=".env")

    # Database
    database_url: PostgresDsn = "postgresql+asyncpg://agentis:agentis@pgbouncer:5432/agentis"
    postgres_direct_url: PostgresDsn = "postgresql+asyncpg://agentis:agentis@postgres:5432/agentis"

    # Redis
    redis_broker_url: str = "redis://redis:6379/0"
    redis_cache_url: str = "redis://redis:6379/1"

    # Auth
    jwt_private_key_path: str = "/secrets/jwt/private.pem"
    jwt_public_key_path: str = "/secrets/jwt/public.pem"
    jwt_access_ttl: int = 3600          # seconds
    jwt_refresh_ttl: int = 2592000      # 30 days

    # Rate limits
    rate_limit_task_hour: int = 60
    rate_limit_api_hour: int = 1000

    # App
    default_language: str = "fr"
    log_level: str = "INFO"
    environment: str = "development"


settings = Settings()
```

- [ ] **Step 1.3: Create `backend/app/main.py`**

```python
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import init_db
from app.routers import auth

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    log.info("agentis_api_started", environment=settings.environment)
    yield
    log.info("agentis_api_stopped")


app = FastAPI(
    title="Agentis API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "An unexpected error occurred"}}
    )
```

- [ ] **Step 1.4: Create `docker-compose.yml`**

```yaml
services:
  api:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      - AGENTIS_DATABASE_URL=postgresql+asyncpg://agentis:agentis@pgbouncer:5432/agentis
      - AGENTIS_POSTGRES_DIRECT_URL=postgresql+asyncpg://agentis:agentis@postgres:5432/agentis
      - AGENTIS_REDIS_BROKER_URL=redis://redis:6379/0
      - AGENTIS_REDIS_CACHE_URL=redis://redis:6379/1
      - AGENTIS_JWT_PRIVATE_KEY_PATH=/secrets/jwt/private.pem
      - AGENTIS_JWT_PUBLIC_KEY_PATH=/secrets/jwt/public.pem
    volumes:
      - ./secrets/jwt:/secrets/jwt:ro
    depends_on:
      pgbouncer: {condition: service_healthy}
      redis:     {condition: service_healthy}

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: agentis
      POSTGRES_PASSWORD: agentis
      POSTGRES_DB: agentis
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentis"]
      interval: 5s
      retries: 10

  pgbouncer:
    image: bitnami/pgbouncer:1.22
    environment:
      POSTGRESQL_HOST: postgres
      POSTGRESQL_PORT: 5432
      POSTGRESQL_USERNAME: agentis
      POSTGRESQL_PASSWORD: agentis
      POSTGRESQL_DATABASE: agentis
      PGBOUNCER_POOL_MODE: transaction
      PGBOUNCER_MAX_CLIENT_CONN: 500
      PGBOUNCER_DEFAULT_POOL_SIZE: 20
    ports: ["5432:5432"]
    depends_on:
      postgres: {condition: service_healthy}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h localhost -p 5432"]
      interval: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    command: redis-server --save "" --appendonly no
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 10

  langfuse:
    image: langfuse/langfuse:latest
    ports: ["3001:3000"]
    environment:
      DATABASE_URL: postgresql://agentis:agentis@postgres:5432/langfuse
      NEXTAUTH_SECRET: dev-secret-change-in-prod
      NEXTAUTH_URL: http://localhost:3001
      SALT: dev-salt
    depends_on:
      postgres: {condition: service_healthy}
    # NOTE: Langfuse requires its own DB. Create it before starting:
    # docker compose up postgres -d
    # docker compose exec postgres createdb -U agentis langfuse

volumes:
  postgres_data:
```

- [ ] **Step 1.5: Create `docker-compose.override.yml`** (dev hot-reload)

```yaml
services:
  api:
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./backend:/app
    environment:
      - AGENTIS_ENVIRONMENT=development
      - AGENTIS_LOG_LEVEL=DEBUG
```

- [ ] **Step 1.6: Create `pgbouncer/pgbouncer.ini`**

This file is used in non-Bitnami deployments (K3s Helm). For Docker Compose we use the Bitnami image env vars. Create for documentation:

```ini
[databases]
agentis = host=postgres port=5432 dbname=agentis

[pgbouncer]
pool_mode = transaction
max_client_conn = 500
default_pool_size = 20
reserve_pool_size = 5
listen_addr = *
listen_port = 5432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
logfile = /var/log/pgbouncer/pgbouncer.log
```

- [ ] **Step 1.7: Create `.env.example`**

```env
# Copy to .env and fill in secrets
AGENTIS_LLM_PROVIDER=anthropic
AGENTIS_LLM_MODEL=claude-sonnet-4-5-20251022
AGENTIS_LLM_API_KEY=

AGENTIS_DATABASE_URL=postgresql+asyncpg://agentis:agentis@pgbouncer:5432/agentis
AGENTIS_POSTGRES_DIRECT_URL=postgresql+asyncpg://agentis:agentis@postgres:5432/agentis

AGENTIS_REDIS_BROKER_URL=redis://redis:6379/0
AGENTIS_REDIS_CACHE_URL=redis://redis:6379/1

AGENTIS_JWT_PRIVATE_KEY_PATH=/secrets/jwt/private.pem
AGENTIS_JWT_PUBLIC_KEY_PATH=/secrets/jwt/public.pem

AGENTIS_DEFAULT_LANGUAGE=fr
AGENTIS_ENVIRONMENT=development
AGENTIS_LOG_LEVEL=INFO

AGENTIS_LANGFUSE_HOST=http://langfuse:3000
AGENTIS_LANGFUSE_PUBLIC_KEY=
AGENTIS_LANGFUSE_SECRET_KEY=
```

- [ ] **Step 1.8: Generate RS256 JWT key pair for development**

```bash
mkdir -p secrets/jwt
openssl genrsa -out secrets/jwt/private.pem 2048
openssl rsa -in secrets/jwt/private.pem -pubout -out secrets/jwt/public.pem
echo "secrets/jwt/" >> .gitignore
```

Expected: `secrets/jwt/private.pem` and `secrets/jwt/public.pem` exist.

- [ ] **Step 1.9: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install hatch

COPY pyproject.toml .
RUN pip install -e .

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 1.10: Verify Docker Compose starts cleanly**

```bash
docker compose up postgres pgbouncer redis -d
docker compose ps
```

Expected: postgres, pgbouncer, redis all show `healthy`.

- [ ] **Step 1.11: Commit**

```bash
git init
git add .
git commit -m "feat: project skeleton — Docker Compose, FastAPI config, JWT key generation"
```

---

## Task 2: Database Models & Async SQLAlchemy

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/task.py`
- Create: `backend/app/models/org.py`
- Create: `backend/app/models/audit.py`
- Create: `backend/app/models/__init__.py`

---

- [ ] **Step 2.1: Write the failing test for database connectivity**

Create `backend/tests/test_health.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **Step 2.2: Run to verify it fails (no DB yet)**

```bash
cd backend
pip install -e ".[dev]"
pytest tests/test_health.py -v
```

Expected: FAIL — `asyncpg` connection refused (postgres not running for test).

- [ ] **Step 2.3: Create `backend/app/database.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.config import settings


engine = create_async_engine(
    str(settings.database_url),
    pool_pre_ping=True,
    # NullPool for PgBouncer transaction mode — PgBouncer manages the pool
    poolclass=NullPool,
    echo=settings.environment == "development",
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    # Verify connectivity on startup — raises on failure
    async with engine.connect() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
```

- [ ] **Step 2.4: Create `backend/app/models/base.py`**

```python
from datetime import datetime, timezone
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

- [ ] **Step 2.5: Create `backend/app/models/user.py`**

```python
import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, Enum, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"
    operator = "operator"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.user
    )
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="fr")
    token_used_this_month: Mapped[int] = mapped_column(nullable=False, default=0)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        # Case-insensitive email lookup
        Index("idx_users_email_lower", text("lower(email)"), unique=True),
        Index("idx_users_active", "deleted_at", postgresql_where=text("deleted_at IS NULL")),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        Index("idx_refresh_tokens_hash", "token_hash"),
        Index("idx_refresh_tokens_user", "user_id"),
    )


class ApiKey(TimestampMixin, Base):
    __tablename__ = "api_keys"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(100))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="api_keys")

    __table_args__ = (
        Index("idx_api_keys_hash", "key_hash"),
        Index("idx_api_keys_user", "user_id"),
    )
```

- [ ] **Step 2.6: Create `backend/app/models/task.py`**

```python
import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, Enum, ForeignKey, Integer, BigInteger, Boolean, JSON, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class TaskStatus(str, enum.Enum):
    submitted = "submitted"
    planning = "planning"
    running = "running"
    waiting_for_input = "waiting_for_input"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TaskStepType(str, enum.Enum):
    think = "think"
    tool_call = "tool_call"
    tool_result = "tool_result"
    reflect = "reflect"
    plan_update = "plan_update"
    user_input = "user_input"
    context_summarized = "context_summarized"
    report = "report"


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    goal: Mapped[str] = mapped_column(String(10000), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"), nullable=False, default=TaskStatus.submitted
    )
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="fr")
    plan: Mapped[Optional[dict]] = mapped_column(JSON)
    allowed_tools: Mapped[Optional[list]] = mapped_column(JSON)
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    result_summary: Mapped[Optional[str]] = mapped_column(String)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000))
    error_code: Mapped[Optional[str]] = mapped_column(String(50))
    partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notify_webhook: Mapped[Optional[str]] = mapped_column(String(500))
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    steps: Mapped[list["TaskStep"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_tasks_user_status", "user_id", "status", "created_at"),
        Index("idx_tasks_status", "status", postgresql_where=text("deleted_at IS NULL")),
        Index("idx_tasks_active", "deleted_at", postgresql_where=text("deleted_at IS NULL")),
    )


class TaskStep(Base):
    __tablename__ = "task_steps"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[TaskStepType] = mapped_column(Enum(TaskStepType, name="task_step_type"), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    task: Mapped["Task"] = relationship(back_populates="steps")

    __table_args__ = (
        Index("idx_task_steps_task", "task_id", "step_number"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    task: Mapped["Task"] = relationship(back_populates="artifacts")

    __table_args__ = (
        Index("idx_artifacts_task", "task_id"),
        Index("idx_artifacts_expiry", "expires_at", postgresql_where=text("deleted_at IS NULL")),
    )
```

- [ ] **Step 2.7: Create `backend/app/models/org.py`**

```python
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, ForeignKey, Integer, BigInteger, JSON, UniqueConstraint, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin
from app.models.user import UserRole


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    llm_provider: Mapped[Optional[str]] = mapped_column(String(50))
    llm_model: Mapped[Optional[str]] = mapped_column(String(100))
    allowed_tools: Mapped[Optional[list]] = mapped_column(JSON)
    token_budget_monthly: Mapped[Optional[int]] = mapped_column(BigInteger)
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["OrganizationMembership"]] = relationship(back_populates="organization")


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False, default=UserRole.user)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_membership"),
    )
```

- [ ] **Step 2.8: Create `backend/app/models/audit.py`**

```python
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, JSON, Index, INET
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    # No FK constraints intentionally — append-only, immutable

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_id: Mapped[Optional[UUID]]
    organization_id: Mapped[Optional[UUID]]
    session_id: Mapped[Optional[UUID]]
    task_id: Mapped[Optional[UUID]]
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))  # IPv4/IPv6 as text
    outcome: Mapped[Optional[str]] = mapped_column(String(20))
    request_id: Mapped[Optional[UUID]]

    __table_args__ = (
        Index("idx_audit_user_time", "user_id", "created_at"),
        Index("idx_audit_task", "task_id", "created_at"),
        Index("idx_audit_event_type", "event_type", "created_at"),
    )
```

- [ ] **Step 2.9: Create `backend/app/models/__init__.py`**

```python
# Import all models so Alembic autogenerate can discover them
from app.models.base import Base
from app.models.user import User, RefreshToken, ApiKey, UserRole
from app.models.task import Task, TaskStep, Artifact, TaskStatus, TaskStepType
from app.models.org import Organization, OrganizationMembership
from app.models.audit import AuditLog

__all__ = [
    "Base", "User", "RefreshToken", "ApiKey", "UserRole",
    "Task", "TaskStep", "Artifact", "TaskStatus", "TaskStepType",
    "Organization", "OrganizationMembership", "AuditLog",
]
```

- [ ] **Step 2.10: Create `backend/tests/conftest.py`**

```python
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.main import app
from app.database import get_db
from app.models import Base

# Use a separate test database.
# Tests run on the host machine; add `ports: ["5432:5432"]` to the postgres
# service in docker-compose.override.yml so the host can connect.
TEST_DATABASE_URL = "postgresql+asyncpg://agentis:agentis@localhost:5432/agentis_test"

test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

> **Note:** The test DB (`agentis_test`) must exist before running tests. Create it:
> ```bash
> docker compose up postgres -d
> docker compose exec postgres createdb -U agentis agentis_test
> ```

- [ ] **Step 2.11: Run health test — should pass now**

```bash
cd backend
docker compose up postgres pgbouncer -d
pytest tests/test_health.py -v
```

Expected: PASS.

- [ ] **Step 2.12: Commit**

```bash
git add backend/app/models/ backend/app/database.py backend/app/config.py backend/tests/conftest.py
git commit -m "feat: SQLAlchemy models — users, tasks, orgs, audit_log with indexes and enums"
```

---

## Task 3: Alembic Migrations

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial_schema.py`

---

- [ ] **Step 3.1: Initialize Alembic**

```bash
cd backend
alembic init alembic
```

Expected: `alembic/` directory and `alembic.ini` created.

- [ ] **Step 3.2: Update `backend/alembic.ini`** — point to direct Postgres URL (bypasses PgBouncer for migrations)

Edit `alembic.ini`, replace:
```ini
sqlalchemy.url = driver://user:pass@localhost/dbname
```
With:
```ini
# URL is set dynamically in env.py from AGENTIS_POSTGRES_DIRECT_URL
sqlalchemy.url =
```

- [ ] **Step 3.3: Replace `backend/alembic/env.py`**

```python
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.config import settings
from app.models import Base  # imports all models for autogenerate

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use DIRECT postgres URL (not PgBouncer) for migrations
config.set_main_option("sqlalchemy.url", str(settings.postgres_direct_url))

target_metadata = Base.metadata


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


run_migrations_online()
```

- [ ] **Step 3.4: Generate the initial migration**

```bash
cd backend
docker compose up postgres -d
alembic revision --autogenerate -m "initial_schema"
```

Expected: A file `alembic/versions/XXXX_initial_schema.py` created with all table definitions. Review it to confirm all tables and indexes are present.

- [ ] **Step 3.5: Apply the migration**

```bash
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> XXXX, initial_schema
```

- [ ] **Step 3.6: Write a test that verifies the schema**

Add to `backend/tests/test_health.py`:

```python
from sqlalchemy import text
from app.database import engine


@pytest.mark.asyncio
async def test_schema_tables_exist():
    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ))
        tables = {row[0] for row in result}
    expected = {"users", "tasks", "task_steps", "artifacts", "organizations",
                "organization_memberships", "audit_log", "refresh_tokens", "api_keys"}
    assert expected.issubset(tables)
```

- [ ] **Step 3.7: Run migration test**

```bash
pytest tests/test_health.py -v
```

Expected: Both tests PASS.

- [ ] **Step 3.8: Commit**

```bash
git add alembic/ alembic.ini
git commit -m "feat: Alembic migration — initial schema with all tables and indexes"
```

---

## Task 4: Auth — Password & JWT Utilities

**Files:**
- Create: `backend/app/auth/password.py`
- Create: `backend/app/auth/jwt.py`
- Create: `backend/app/auth/api_keys.py`
- Create: `backend/app/schemas/common.py`
- Create: `backend/app/schemas/auth.py`

---

- [ ] **Step 4.1: Write failing tests for password hashing**

Create `backend/tests/test_auth_password.py`:
```python
from app.auth.password import hash_password, verify_password


def test_hash_is_not_plaintext():
    hashed = hash_password("SuperSecret123!")
    assert hashed != "SuperSecret123!"
    assert hashed.startswith("$2b$")


def test_correct_password_verifies():
    hashed = hash_password("SuperSecret123!")
    assert verify_password("SuperSecret123!", hashed) is True


def test_wrong_password_fails():
    hashed = hash_password("SuperSecret123!")
    assert verify_password("WrongPassword!", hashed) is False
```

Run:
```bash
pytest tests/test_auth_password.py -v
```
Expected: FAIL — `app.auth.password` not found.

- [ ] **Step 4.2: Create `backend/app/auth/password.py`**

```python
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def validate_password_strength(password: str) -> None:
    """Raises ValueError if password does not meet requirements."""
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    if not any(c.isupper() for c in password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one digit")
```

- [ ] **Step 4.3: Run password tests — verify they pass**

```bash
pytest tests/test_auth_password.py -v
```
Expected: 3 PASS.

- [ ] **Step 4.4: Write failing JWT tests**

Create `backend/tests/test_auth_jwt.py`:
```python
import pytest
from datetime import timedelta
from app.auth.jwt import create_access_token, decode_access_token, TokenExpiredError, TokenInvalidError


def test_create_and_decode_token():
    token = create_access_token(user_id="abc-123", role="user")
    payload = decode_access_token(token)
    assert payload["sub"] == "abc-123"
    assert payload["role"] == "user"


def test_expired_token_raises():
    token = create_access_token(user_id="abc", role="user", ttl=timedelta(seconds=-1))
    with pytest.raises(TokenExpiredError):
        decode_access_token(token)


def test_tampered_token_raises():
    token = create_access_token(user_id="abc", role="user")
    tampered = token[:-4] + "xxxx"
    with pytest.raises(TokenInvalidError):
        decode_access_token(tampered)
```

Run:
```bash
pytest tests/test_auth_jwt.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 4.5: Create `backend/app/auth/jwt.py`**

```python
import jwt
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app.config import settings


class TokenExpiredError(Exception):
    pass


class TokenInvalidError(Exception):
    pass


def _load_private_key() -> str:
    return Path(settings.jwt_private_key_path).read_text()


def _load_public_key() -> str:
    return Path(settings.jwt_public_key_path).read_text()


def create_access_token(
    user_id: str,
    role: str,
    org_id: str | None = None,
    ttl: timedelta | None = None,
) -> str:
    if ttl is None:
        ttl = timedelta(seconds=settings.jwt_access_ttl)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "org_id": org_id,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, _load_private_key(), algorithm="RS256")


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, _load_public_key(), algorithms=["RS256"])
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except jwt.PyJWTError as e:
        raise TokenInvalidError(f"Invalid token: {e}")
```

- [ ] **Step 4.6: Run JWT tests — verify they pass**

```bash
pytest tests/test_auth_jwt.py -v
```
Expected: 3 PASS.

- [ ] **Step 4.7: Write failing API key tests**

Create `backend/tests/test_api_keys.py`:
```python
from app.auth.api_keys import generate_api_key, hash_api_key, verify_api_key


def test_key_has_correct_prefix():
    key, _ = generate_api_key()
    assert key.startswith("agentis_sk_")


def test_hash_differs_from_key():
    key, key_hash = generate_api_key()
    assert key != key_hash


def test_verify_correct_key():
    key, key_hash = generate_api_key()
    assert verify_api_key(key, key_hash) is True


def test_verify_wrong_key():
    _, key_hash = generate_api_key()
    assert verify_api_key("agentis_sk_wrong", key_hash) is False
```

- [ ] **Step 4.8: Create `backend/app/auth/api_keys.py`**

```python
import hashlib
import secrets
import base64


def generate_api_key() -> tuple[str, str]:
    """Returns (plaintext_key, sha256_hash). Store only the hash."""
    random_bytes = secrets.token_bytes(32)
    key_body = base64.b62encode(random_bytes).decode() if hasattr(base64, 'b62encode') else random_bytes.hex()
    # Use hex for compatibility (base62 not in stdlib)
    key_body = random_bytes.hex()
    plaintext = f"agentis_sk_{key_body}"
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, key_hash


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(key: str, stored_hash: str) -> bool:
    return hashlib.sha256(key.encode()).hexdigest() == stored_hash
```

- [ ] **Step 4.9: Run API key tests**

```bash
pytest tests/test_api_keys.py -v
```
Expected: 4 PASS.

- [ ] **Step 4.10: Create `backend/app/schemas/common.py`**

```python
from typing import Any, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    pagination: "PaginationMeta"


class PaginationMeta(BaseModel):
    next_cursor: str | None
    has_more: bool
    total: int
```

- [ ] **Step 4.11: Create `backend/app/schemas/auth.py`**

```python
from pydantic import BaseModel, EmailStr, field_validator
from app.auth.password import validate_password_strength


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None
    language: str = "fr"

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        validate_password_strength(v)
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    role: str
    language: str


class ApiKeyCreateRequest(BaseModel):
    label: str | None = None


class ApiKeyResponse(BaseModel):
    id: str
    label: str | None
    created_at: str
    expires_at: str | None
    last_used_at: str | None
```

- [ ] **Step 4.12: Commit auth utilities**

```bash
git add backend/app/auth/ backend/app/schemas/ backend/tests/
git commit -m "feat: auth utilities — bcrypt password, RS256 JWT, API key generation"
```

---

## Task 5: Auth Endpoints (Register, Login, Refresh, Logout)

**Files:**
- Create: `backend/app/auth/dependencies.py`
- Create: `backend/app/routers/auth.py`
- Modify: `backend/app/main.py` (register router)

---

- [ ] **Step 5.1: Write failing registration test**

Create `backend/tests/test_auth_register.py`:
```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post("/api/v1/auth/register", json={
        "email": "alice@example.com",
        "password": "Secure123!Pass",
        "name": "Alice",
        "language": "en"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["email"] == "alice@example.com"
    assert "access_token" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "bob@example.com", "password": "Secure123!Pass"}
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    response = await client.post("/api/v1/auth/register", json={
        "email": "carol@example.com",
        "password": "weak"
    })
    assert response.status_code == 422
```

Run:
```bash
pytest tests/test_auth_register.py -v
```
Expected: FAIL — routes not defined.

- [ ] **Step 5.2: Create `backend/app/auth/dependencies.py`**

```python
from fastapi import Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User, ApiKey
from app.auth.jwt import decode_access_token, TokenExpiredError, TokenInvalidError
from app.auth.api_keys import hash_api_key


async def get_current_user(
    request: Request,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    # Check API key first
    if x_api_key:
        key_hash = hash_api_key(x_api_key)
        result = await db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "Invalid API key"})
        user = await db.get(User, api_key.user_id)
        return user

    # Fall back to JWT Bearer
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "Missing credentials"})
    token = auth_header[7:]
    try:
        payload = decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail={"code": "token_expired", "message": "Access token expired"})
    except TokenInvalidError:
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "Invalid token"})

    user = await db.get(User, payload["sub"])
    if not user or user.deleted_at:
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "User not found"})
    return user
```

- [ ] **Step 5.3: Create `backend/app/routers/auth.py`**

```python
import hashlib, secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User, RefreshToken, ApiKey
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse, ApiKeyCreateRequest, ApiKeyResponse
from app.auth.password import hash_password, verify_password
from app.auth.jwt import create_access_token, decode_access_token, TokenInvalidError, TokenExpiredError
from app.auth.api_keys import generate_api_key
from app.auth.dependencies import get_current_user
from app.config import settings

router = APIRouter()

REFRESH_COOKIE = "refresh_token"
REFRESH_TTL = settings.jwt_refresh_ttl  # seconds


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        samesite="strict",
        secure=settings.environment != "development",
        max_age=REFRESH_TTL,
        path="/api/v1/auth",
    )


@router.post("/register", status_code=201)
async def register(payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    # Check email uniqueness (case-insensitive)
    existing = await db.execute(
        select(User).where(func.lower(User.email) == payload.email.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail={"code": "email_taken", "message": "Email already registered"})

    user = User(
        email=payload.email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        language=payload.language,
    )
    db.add(user)
    await db.flush()  # get user.id

    # Issue tokens
    access_token = create_access_token(str(user.id), user.role.value)
    refresh_token_raw = secrets.token_hex(32)
    refresh_token_hash = hashlib.sha256(refresh_token_raw.encode()).hexdigest()
    refresh = RefreshToken(
        user_id=user.id,
        token_hash=refresh_token_hash,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TTL),
    )
    db.add(refresh)
    await db.commit()

    _set_refresh_cookie(response, refresh_token_raw)
    return {
        "user": UserResponse(id=str(user.id), email=user.email, name=user.name, role=user.role.value, language=user.language),
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_ttl,
    }


@router.post("/login")
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(func.lower(User.email) == payload.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials", "message": "Invalid email or password"})
    if user.deleted_at:
        raise HTTPException(status_code=401, detail={"code": "account_disabled", "message": "Account disabled"})

    access_token = create_access_token(str(user.id), user.role.value)
    refresh_token_raw = secrets.token_hex(32)
    refresh = RefreshToken(
        user_id=user.id,
        token_hash=hashlib.sha256(refresh_token_raw.encode()).hexdigest(),
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TTL),
    )
    db.add(refresh)
    await db.commit()

    _set_refresh_cookie(response, refresh_token_raw)
    return {"access_token": access_token, "token_type": "bearer", "expires_in": settings.jwt_access_ttl}


@router.post("/refresh")
async def refresh_token(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "No refresh token"})

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
    )
    stored = result.scalar_one_or_none()

    if not stored:
        # Possible replay attack: revoke all tokens for user if token_hash is known
        # (we don't know the user here without the token, so just reject)
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "Invalid or expired refresh token"})

    # Rotate: revoke old token
    stored.revoked_at = now

    # Issue new pair
    user = await db.get(User, stored.user_id)
    new_access_token = create_access_token(str(user.id), user.role.value)
    new_raw = secrets.token_hex(32)
    new_stored = RefreshToken(
        user_id=user.id,
        token_hash=hashlib.sha256(new_raw.encode()).hexdigest(),
        created_at=now,
        expires_at=now + timedelta(seconds=REFRESH_TTL),
    )
    db.add(new_stored)
    await db.commit()

    _set_refresh_cookie(response, new_raw)
    return {"access_token": new_access_token, "token_type": "bearer", "expires_in": settings.jwt_access_ttl}


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        stored = result.scalar_one_or_none()
        if stored:
            stored.revoked_at = datetime.now(timezone.utc)
            await db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    return {"message": "Logged out"}


@router.post("/api-keys", status_code=201)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Enforce max 10 active keys
    count_result = await db.execute(
        select(func.count()).select_from(ApiKey).where(
            ApiKey.user_id == current_user.id,
            ApiKey.revoked_at.is_(None),
        )
    )
    if count_result.scalar() >= 10:
        raise HTTPException(status_code=422, detail={"code": "too_many_keys", "message": "Maximum 10 active API keys"})

    plaintext, key_hash = generate_api_key()
    api_key = ApiKey(user_id=current_user.id, key_hash=key_hash, label=payload.label)
    db.add(api_key)
    await db.commit()
    # Return plaintext ONCE — never stored
    return {"key": plaintext, "id": str(api_key.id), "label": api_key.label}


@router.get("/api-keys")
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id, ApiKey.revoked_at.is_(None))
    )
    keys = result.scalars().all()
    return [ApiKeyResponse(
        id=str(k.id), label=k.label,
        created_at=k.created_at.isoformat(),
        expires_at=k.expires_at.isoformat() if k.expires_at else None,
        last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
    ) for k in keys]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from uuid import UUID
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == UUID(key_id), ApiKey.user_id == current_user.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "API key not found"})
    key.revoked_at = datetime.now(timezone.utc)
    await db.commit()
```

- [ ] **Step 5.4: Update `backend/app/main.py`** — add auth router

```python
# Add to imports:
from app.routers import auth as auth_router

# Add to app setup (after existing include_router):
app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["auth"])
```

(The router was already added in Task 1. Verify it's present.)

- [ ] **Step 5.5: Run auth tests**

```bash
pytest tests/test_auth_register.py tests/test_auth_password.py tests/test_auth_jwt.py tests/test_api_keys.py -v
```

Expected: All PASS.

- [ ] **Step 5.6: Write and run login/refresh/logout tests**

Create `backend/tests/test_auth_login.py`:
```python
import pytest
from httpx import AsyncClient

USER = {"email": "logintest@example.com", "password": "Secure123!Pass"}


@pytest.fixture(autouse=True)
async def create_user(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=USER)


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    response = await client.post("/api/v1/auth/login", json=USER)
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    response = await client.post("/api/v1/auth/login", json={
        "email": USER["email"], "password": "WrongPass123!"
    })
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
```

Create `backend/tests/test_auth_refresh.py`:
```python
import pytest
from httpx import AsyncClient

USER = {"email": "refreshtest@example.com", "password": "Secure123!Pass"}


@pytest.mark.asyncio
async def test_refresh_rotates_token(client: AsyncClient):
    reg = await client.post("/api/v1/auth/register", json=USER)
    old_token = reg.json()["access_token"]

    refresh_resp = await client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    new_token = refresh_resp.json()["access_token"]
    assert new_token != old_token
    # New refresh cookie was set
    assert "refresh_token" in refresh_resp.cookies


@pytest.mark.asyncio
async def test_refresh_without_cookie_fails(client: AsyncClient):
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
```

```bash
pytest tests/ -v
```
Expected: All tests PASS.

- [ ] **Step 5.7: Commit**

```bash
git add backend/app/routers/auth.py backend/app/auth/dependencies.py backend/tests/
git commit -m "feat: auth endpoints — register, login, refresh, logout, API keys (JWT RS256 + rotation)"
```

---

## Task 6: Rate Limiting Middleware

**Files:**
- Create: `backend/app/auth/rate_limiter.py`
- Modify: `backend/app/main.py` (add rate limit middleware)

---

- [ ] **Step 6.1: Write failing rate limit test**

Create `backend/tests/test_rate_limiting.py`:
```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_rate_limit_triggers_429(client: AsyncClient, monkeypatch):
    """Patch rate limit to 3/hour for this test."""
    import app.auth.rate_limiter as rl
    monkeypatch.setattr(rl, "TASK_LIMIT_PER_HOUR", 3)

    # 3 requests should succeed
    for _ in range(3):
        r = await client.post("/api/v1/auth/login", json={
            "email": "nouser@example.com", "password": "pass"
        })
        assert r.status_code in (200, 401)  # 401 = wrong creds, not rate limited

    # 4th should be rate limited
    r = await client.post("/api/v1/auth/login", json={
        "email": "nouser@example.com", "password": "pass"
    })
    assert r.status_code == 429
    assert "Retry-After" in r.headers
```

- [ ] **Step 6.2: Create `backend/app/auth/rate_limiter.py`**

```python
import time
import redis.asyncio as aioredis
from fastapi import Request, HTTPException
from app.config import settings

TASK_LIMIT_PER_HOUR = settings.rate_limit_task_hour
API_LIMIT_PER_HOUR = settings.rate_limit_api_hour
WINDOW_SECONDS = 3600


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_cache_url, decode_responses=True)


async def check_rate_limit(request: Request, limit: int) -> None:
    """
    Sliding window rate limiter using Redis sorted sets.
    Raises 429 if the client exceeds `limit` requests in 1 hour.
    """
    # Use IP + path as key for unauthenticated; user_id when available
    client_id = request.client.host if request.client else "unknown"
    if hasattr(request.state, "user_id"):
        client_id = f"user:{request.state.user_id}"

    key = f"ratelimit:{client_id}:{request.url.path}"
    now = time.time()
    window_start = now - WINDOW_SECONDS

    redis = await _get_redis()
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, WINDOW_SECONDS)
    results = await pipe.execute()
    await redis.aclose()

    count = results[2]
    remaining = max(0, limit - count)
    reset_at = int(now) + WINDOW_SECONDS

    if count > limit:
        raise HTTPException(
            status_code=429,
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_at),
                "Retry-After": str(WINDOW_SECONDS),
            },
            detail={"code": "rate_limited", "message": "Rate limit exceeded. Try again later."},
        )
```

- [ ] **Step 6.3: Add rate limit dependency to auth router**

In `backend/app/routers/auth.py`, add to `/login` endpoint:

```python
from fastapi import Depends
from app.auth.rate_limiter import check_rate_limit

@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(lambda req=Request: check_rate_limit(req, limit=60)),
):
    ...
```

- [ ] **Step 6.4: Run rate limiting test**

```bash
pytest tests/test_rate_limiting.py -v
```

Expected: PASS (with Redis running via `docker compose up redis -d`).

- [ ] **Step 6.5: Commit**

```bash
git add backend/app/auth/rate_limiter.py backend/app/routers/auth.py backend/tests/test_rate_limiting.py
git commit -m "feat: Redis sliding-window rate limiter with X-RateLimit headers"
```

---

## Task 7: Structlog Logging Setup

**Files:**
- Create: `backend/app/logging_config.py`
- Modify: `backend/app/main.py` (configure logging on startup)

---

- [ ] **Step 7.1: Create `backend/app/logging_config.py`**

```python
import logging
import structlog
from app.config import settings


def configure_logging() -> None:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer() if settings.environment != "development"
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
```

- [ ] **Step 7.2: Add request logging middleware to `backend/app/main.py`**

```python
import uuid
import structlog
from fastapi import Request
from app.logging_config import configure_logging

configure_logging()
log = structlog.get_logger()

# Add BEFORE the lifespan:
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path, method=request.method)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    log.info("http_request", status_code=response.status_code)
    return response
```

- [ ] **Step 7.3: Test that logs appear on API call**

```bash
docker compose up api -d
curl http://localhost:8000/api/v1/health
docker compose logs api
```

Expected: Structured JSON log with `{"event": "http_request", "status_code": 200, ...}`.

- [ ] **Step 7.4: Commit**

```bash
git add backend/app/logging_config.py backend/app/main.py
git commit -m "feat: structlog JSON logging with request_id propagation"
```

---

## Task 8: End-to-End Integration Smoke Test

**Files:**
- Create: `backend/tests/test_integration_auth.py`

---

- [ ] **Step 8.1: Write the full auth integration test**

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_auth_flow(client: AsyncClient):
    """Register → login → use token → refresh → logout → verify token invalid."""
    # 1. Register
    reg = await client.post("/api/v1/auth/register", json={
        "email": "integration@example.com",
        "password": "Secure123!Pass",
        "name": "Integration Test"
    })
    assert reg.status_code == 201
    access_token = reg.json()["access_token"]

    # 2. Use access token
    me_resp = await client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    # /settings not implemented yet — 404 is fine, not 401
    assert me_resp.status_code in (200, 404)

    # 3. Refresh
    refresh_resp = await client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    new_token = refresh_resp.json()["access_token"]
    assert new_token != access_token

    # 4. Logout
    logout_resp = await client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200

    # 5. Refresh after logout should fail
    post_logout = await client.post("/api/v1/auth/refresh")
    assert post_logout.status_code == 401


@pytest.mark.asyncio
async def test_api_key_flow(client: AsyncClient):
    """Register → create API key → use it on a request."""
    reg = await client.post("/api/v1/auth/register", json={
        "email": "apikey@example.com",
        "password": "Secure123!Pass",
    })
    access_token = reg.json()["access_token"]

    # Create API key
    key_resp = await client.post(
        "/api/v1/auth/api-keys",
        json={"label": "CI key"},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert key_resp.status_code == 201
    api_key = key_resp.json()["key"]
    assert api_key.startswith("agentis_sk_")

    # Use API key on a request
    list_resp = await client.get(
        "/api/v1/auth/api-keys",
        headers={"X-API-Key": api_key}
    )
    assert list_resp.status_code == 200
    keys = list_resp.json()
    assert len(keys) == 1
    assert keys[0]["label"] == "CI key"
```

- [ ] **Step 8.2: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: All tests PASS. Note any failures and fix before proceeding.

- [ ] **Step 8.3: Verify Docker Compose full stack**

```bash
docker compose up --build -d
curl http://localhost:8000/api/v1/health
```

Expected: `{"status": "ok"}`.

- [ ] **Step 8.4: Final commit for Phase 1A**

```bash
git add .
git commit -m "feat(phase-1a): complete infrastructure + auth — PostgreSQL, Alembic, PgBouncer, FastAPI, JWT RS256, API keys, rate limiting, structlog"
```

---

## Phase 1A Complete — Handoff to Phase 1B

**What's running:**
- `docker compose up` brings up: PostgreSQL 16 + PgBouncer + Redis 7 + FastAPI + Langfuse.
- Full schema migrated with indexes and ENUMs.
- Auth system: registration, login, JWT refresh/rotation, API keys, rate limiting.
- Structured logging with `X-Request-ID` propagation.

**What's next — Phase 1B (Sandbox + Tools):**
- `sandbox/` Docker image with Playwright + tool JSON-RPC server
- `SandboxManager` in the backend
- 4 tool RPC clients: `browser`, `code_executor`, `file_system`, `web_search`
- Plan: `docs/superpowers/plans/2026-05-29-phase1b-sandbox-tools.md`

---

*Plan version: 1.0 | Created: 2026-05-29 | Spec ref: docs/agentis_spec.md v2.0.0*
