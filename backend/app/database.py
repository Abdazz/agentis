from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from app.config import settings


engine = create_async_engine(
    str(settings.database_url),
    pool_pre_ping=True,
    poolclass=NullPool,  # PgBouncer transaction mode requires NullPool
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
    """Verify DB connectivity on startup — raises on failure."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
