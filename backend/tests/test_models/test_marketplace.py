import uuid
import pytest
from sqlalchemy import select
from app.models.marketplace import MarketplacePlugin


class TestMarketplacePluginModel:
    """Test MarketplacePlugin model."""

    def test_instantiation(self):
        """Test MarketplacePlugin object instantiation."""
        plugin = MarketplacePlugin(
            id=uuid.uuid4(),
            name="weather",
            slug="weather-mcp",
            description="Live weather data via Open-Meteo",
            source_type="mcp",
            url="https://weather.example.com/mcp",
            version="1.0.0",
            author="community",
            installed=False,
            registered_tool_name=None,
        )
        assert plugin.name == "weather"
        assert plugin.slug == "weather-mcp"
        assert plugin.source_type == "mcp"
        assert plugin.url == "https://weather.example.com/mcp"


@pytest.mark.asyncio
async def test_marketplace_plugin_insert(db_session):
    """Test MarketplacePlugin insertion into database."""
    plugin = MarketplacePlugin(
        name="calculator",
        slug="calculator-tool",
        description="Simple calculator plugin",
        source_type="openapi",
        url="https://calc.example.com/openapi.json",
        version="2.0.0",
        author="user123",
        installed=True,
        registered_tool_name="calc_tool",
    )
    db_session.add(plugin)
    await db_session.commit()
    await db_session.refresh(plugin)

    assert plugin.id is not None
    assert plugin.name == "calculator"
    assert plugin.slug == "calculator-tool"
    assert plugin.installed is True
    assert plugin.registered_tool_name == "calc_tool"
    assert plugin.created_at is not None
    assert plugin.updated_at is not None


@pytest.mark.asyncio
async def test_marketplace_plugin_unique_slug(db_session):
    """Test that slug is unique."""
    from sqlalchemy.exc import IntegrityError

    unique_slug = f"plugin-{uuid.uuid4().hex[:8]}"
    db_session.add(
        MarketplacePlugin(
            name="first",
            slug=unique_slug,
            description="First plugin",
            source_type="mcp",
            url="https://example.com/1",
        )
    )
    await db_session.commit()

    db_session.add(
        MarketplacePlugin(
            name="second",
            slug=unique_slug,
            description="Second plugin",
            source_type="mcp",
            url="https://example.com/2",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
