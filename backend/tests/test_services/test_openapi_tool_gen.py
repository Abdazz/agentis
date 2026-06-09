"""Tests for OpenAPI spec tool auto-generator (Phase 3A Task 5)."""
import pytest
from unittest.mock import AsyncMock, patch


SAMPLE_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Weather API", "version": "1.0"},
    "servers": [{"url": "https://api.weather.example.com"}],
    "paths": {
        "/current": {
            "get": {
                "operationId": "getCurrentWeather",
                "summary": "Get current weather",
                "parameters": [
                    {"name": "city", "in": "query", "required": True,
                     "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "OK"}},
            }
        },
        "/forecast": {
            "post": {
                "operationId": "getForecast",
                "summary": "Get weather forecast",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}, "days": {"type": "integer"}},
                            "required": ["city"],
                        }
                    }},
                },
                "responses": {"200": {"description": "OK"}},
            }
        },
    },
}


def test_generate_tools_from_spec():
    from app.services.openapi_tool_gen import generate_tools_from_spec
    tools = generate_tools_from_spec(SAMPLE_SPEC, spec_url="https://api.weather.example.com/openapi.json")
    assert len(tools) == 2
    names = {t.name for t in tools}
    assert "openapi__getCurrentWeather" in names
    assert "openapi__getForecast" in names


def test_generated_tool_has_correct_input_schema():
    from app.services.openapi_tool_gen import generate_tools_from_spec
    tools = generate_tools_from_spec(SAMPLE_SPEC, spec_url="https://api.weather.example.com/openapi.json")
    get_tool = next(t for t in tools if t.name == "openapi__getCurrentWeather")
    assert "city" in get_tool.input_schema.get("properties", {})


@pytest.mark.asyncio
async def test_fetch_and_generate_from_url():
    from app.services.openapi_tool_gen import fetch_and_generate
    with patch("app.services.openapi_tool_gen._fetch_spec", new=AsyncMock(return_value=SAMPLE_SPEC)):
        tools = await fetch_and_generate("https://api.weather.example.com/openapi.json")
    assert len(tools) == 2


@pytest.mark.asyncio
async def test_openapi_proxy_tool_calls_http_caller():
    from app.services.openapi_tool_gen import OpenApiProxyTool
    from app.tools.base import SessionContext

    tool = OpenApiProxyTool(
        operation_id="getCurrentWeather",
        method="GET",
        base_url="https://api.weather.example.com",
        path="/current",
        description="Get current weather",
        input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
    )

    from app.tools.base import ToolResult
    mock_result = ToolResult(ok=True, data={"status_code": 200, "body": '{"temp": 22}'})
    session = SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="")

    with patch("app.tools.http_caller.HttpCallerTool") as MockHttp:
        instance = MockHttp.return_value
        instance.execute = AsyncMock(return_value=mock_result)
        result = await tool.execute({"city": "Paris"}, session)

    assert result.ok is True
