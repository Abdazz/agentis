import pytest
from app.tools.base import BaseTool, ToolResult, SessionContext


def test_tool_result_ok():
    r = ToolResult(ok=True, data={"key": "value"})
    assert r.ok is True
    assert r.data == {"key": "value"}
    assert r.error is None


def test_tool_result_error():
    r = ToolResult(ok=False, error="something failed", retryable=True)
    assert r.ok is False
    assert r.error == "something failed"
    assert r.retryable is True


def test_session_context_fields():
    ctx = SessionContext(
        session_id="sess-1",
        task_id="task-1",
        sandbox_endpoint="http://localhost:19999",
    )
    assert ctx.session_id == "sess-1"
    assert ctx.sandbox_endpoint == "http://localhost:19999"
    assert ctx.secrets_accessor is None


def test_base_tool_is_abstract():
    import inspect
    assert inspect.isabstract(BaseTool)


def test_base_tool_cannot_instantiate():
    with pytest.raises(TypeError):
        BaseTool()


def test_concrete_tool_without_name_raises():
    with pytest.raises(TypeError, match="must define"):
        class NoNameTool(BaseTool):
            description = "has description but no name"
            async def execute(self, params, session):
                pass
