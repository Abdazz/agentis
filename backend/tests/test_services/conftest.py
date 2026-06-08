"""Conftest for test_services — provides no-op overrides for the session-level
DB and Redis fixtures defined in the parent conftest so that pure unit tests
(e.g. MinioService) can run without any running infrastructure."""
import pytest
import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """No-op override: these tests don't need a real database."""
    yield


@pytest_asyncio.fixture(autouse=True)
async def clear_rate_limits():
    """No-op override: these tests don't touch Redis."""
    yield
