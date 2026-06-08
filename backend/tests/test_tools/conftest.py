"""Local conftest for test_tools — overrides session-scoped DB/Redis fixtures
so that unit tests with mocks can run without a live PostgreSQL or Redis."""
import pytest
import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """No-op override: tool tests are pure unit tests with mocks."""
    yield


@pytest_asyncio.fixture(autouse=True)
async def clear_rate_limits():
    """No-op override: no Redis available in unit test environment."""
    yield
