import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.tools.web_search import WebSearchTool
from app.tools.base import SessionContext


@pytest.fixture
def session():
    return SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="http://localhost:19999")


@pytest.fixture
def tool():
    return WebSearchTool()


@pytest.mark.asyncio
async def test_web_search_tool_name(tool):
    assert tool.name == "web_search"


@pytest.mark.asyncio
async def test_web_search_no_api_key_returns_empty(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.web_search.settings.brave_api_key", "")
    monkeypatch.setattr("app.tools.web_search.settings.search_backend", "brave")

    result = await tool.execute({"query": "test"}, session)
    assert result.ok is True
    assert result.data["results"] == []


@pytest.mark.asyncio
async def test_web_search_returns_results(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.web_search.settings.brave_api_key", "fake-key")
    monkeypatch.setattr("app.tools.web_search.settings.search_backend", "brave")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "results": [
            {"title": "Test", "url": "https://example.com", "description": "A test page"},
        ]
    })

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_http

        result = await tool.execute({"query": "test"}, session)

    assert result.ok is True
    assert result.data["results"][0]["title"] == "Test"


@pytest.mark.asyncio
async def test_web_search_caps_at_20(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.web_search.settings.brave_api_key", "fake-key")
    monkeypatch.setattr("app.tools.web_search.settings.search_backend", "brave")

    captured_params = {}

    async def fake_get(url, headers=None, params=None, **kwargs):
        captured_params.update(params or {})
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json = MagicMock(return_value={"results": []})
        return m

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = fake_get
        mock_cls.return_value = mock_http

        await tool.execute({"query": "test", "num_results": 999}, session)

    assert captured_params.get("count") == 20
