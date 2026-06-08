"""Fixtures for WebSocket HITL tests."""
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient
from app.models.user import User, UserRole
from app.auth.jwt import create_access_token
from app.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://agentis:agentis@localhost:5436/agentis_test"

_ws_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
_WSSessionLocal = async_sessionmaker(_ws_engine, expire_on_commit=False)


@pytest.fixture(scope="module")
def starlette_client():
    """Module-scoped Starlette TestClient — lifespan runs once per module."""
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


@pytest_asyncio.fixture
async def test_user() -> User:
    """Create and *commit* a real user in the test DB for WS auth.

    Uses its own session so the user is visible to verify_token_string
    which opens its own AsyncSessionLocal.
    """
    user = User(
        id=uuid.uuid4(),
        email=f"ws_test_{uuid.uuid4().hex[:8]}@example.com",
        role=UserRole.user,
    )
    async with _WSSessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    yield user
    # Clean up after test
    async with _WSSessionLocal() as session:
        u = await session.get(User, user.id)
        if u:
            await session.delete(u)
            await session.commit()


@pytest_asyncio.fixture
async def test_user_token(test_user: User) -> str:
    """Return a valid JWT token for the test user."""
    return create_access_token(user_id=str(test_user.id), role=test_user.role.value)
