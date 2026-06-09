"""Seed the marketplace_plugins table with curated community plugins."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

COMMUNITY_PLUGINS = [
    {
        "name": "Weather MCP",
        "slug": "weather-mcp",
        "description": "Live weather data via Open-Meteo (free, no API key)",
        "source_type": "mcp",
        "url": "https://mcp.weather.example.com/sse",
        "version": "1.0.0",
        "author": "community",
    },
    {
        "name": "GitHub OpenAPI",
        "slug": "github-openapi",
        "description": "GitHub REST API v3 — search repos, issues, PRs",
        "source_type": "openapi",
        "url": "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json",
        "version": "1.0.0",
        "author": "community",
    },
    {
        "name": "Wikipedia MCP",
        "slug": "wikipedia-mcp",
        "description": "Search and fetch Wikipedia articles as structured data",
        "source_type": "mcp",
        "url": "https://mcp.wikipedia.example.com/sse",
        "version": "1.0.0",
        "author": "community",
    },
]


async def seed_marketplace_plugins(db: AsyncSession) -> None:
    """Ensure every community plugin has a row in marketplace_plugins (idempotent)."""
    from app.models.marketplace import MarketplacePlugin

    for p in COMMUNITY_PLUGINS:
        result = await db.execute(
            select(MarketplacePlugin).where(MarketplacePlugin.slug == p["slug"])
        )
        if result.scalar_one_or_none() is None:
            db.add(MarketplacePlugin(**p))
    await db.commit()
