import uuid
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app
from app.database import get_db


@pytest_asyncio.fixture
async def auth_client(db_session: AsyncSession):
    """Authenticated HTTPX client. Uses a unique email per fixture call to avoid conflicts."""
    unique_email = f"metest_{uuid.uuid4().hex[:8]}@example.com"
    test_user = {
        "email": unique_email,
        "password": "Secure123!Pass",
        "name": "Test User",
    }

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            reg = await c.post("/api/v1/auth/register", json=test_user)
            assert reg.status_code == 201, f"Registration failed: {reg.text}"
            token = reg.json()["access_token"]
            c.headers.update({"Authorization": f"Bearer {token}"})
            yield c
    finally:
        app.dependency_overrides.clear()
