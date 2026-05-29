"""
Integration tests: start a real agentis-sandbox container and test all sandbox tools.
Requires: docker run access + agentis-sandbox:latest image built.

Run with: pytest -m slow tests/test_tools/test_sandbox_integration.py -v
Skip with: pytest -m "not slow"
"""
import pytest
import docker
import time
import httpx

from app.sandbox.rpc_client import SandboxRpcClient, RpcError
from app.tools.base import SessionContext
from app.tools.file_system import FileSystemTool
from app.tools.code_executor import CodeExecutorTool


@pytest.fixture(scope="module")
def sandbox_container():
    """Start a sandbox container, yield its endpoint, stop and remove on teardown."""
    client = docker.from_env()

    container = client.containers.run(
        "agentis-sandbox:latest",
        detach=True,
        ports={"9999/tcp": None},   # random available host port
        name="agentis-integration-test",
        remove=False,
    )

    container.reload()
    port_info = container.ports.get("9999/tcp")
    if not port_info:
        container.stop()
        container.remove()
        pytest.fail("Sandbox container did not expose port 9999")

    port = port_info[0]["HostPort"]
    endpoint = f"http://localhost:{port}"

    # Wait for tool server to be ready (up to 30s)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{endpoint}/health", timeout=2.0)
            if resp.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        container.stop()
        container.remove()
        pytest.fail("Sandbox container did not become ready within 30 seconds")

    yield endpoint

    container.stop()
    container.remove()


@pytest.fixture
def session(sandbox_container):
    return SessionContext(
        session_id="integration-test",
        task_id="integration-task",
        sandbox_endpoint=sandbox_container,
    )


# --- file_system tests ---

@pytest.mark.slow
@pytest.mark.asyncio
async def test_file_system_write_and_read(session):
    tool = FileSystemTool()
    write_result = await tool.execute(
        {"action": "write", "path": "hello.txt", "content": "Hello Phase 1B!"},
        session,
    )
    assert write_result.ok is True
    assert write_result.data["size_bytes"] > 0

    read_result = await tool.execute(
        {"action": "read", "path": "hello.txt"},
        session,
    )
    assert read_result.ok is True
    assert "Hello Phase 1B!" in read_result.data["content"]
    assert read_result.data["truncated"] is False


@pytest.mark.slow
@pytest.mark.asyncio
async def test_file_system_list(session):
    tool = FileSystemTool()
    result = await tool.execute({"action": "list", "directory": "."}, session)
    assert result.ok is True
    assert isinstance(result.data["entries"], list)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_file_system_path_traversal_rejected(session):
    tool = FileSystemTool()
    result = await tool.execute(
        {"action": "read", "path": "../../etc/passwd"},
        session,
    )
    # Must fail — path escapes /workspace
    assert result.ok is False
    assert "escape" in result.error.lower()


# --- code_executor tests ---

@pytest.mark.slow
@pytest.mark.asyncio
async def test_code_executor_python(session):
    tool = CodeExecutorTool()
    result = await tool.execute(
        {"action": "run_python", "code": "print(2 + 2)"},
        session,
    )
    assert result.ok is True
    assert result.data["stdout"].strip() == "4"
    assert result.data["exit_code"] == 0


@pytest.mark.slow
@pytest.mark.asyncio
async def test_code_executor_bash(session):
    tool = CodeExecutorTool()
    result = await tool.execute(
        {"action": "run_bash", "command": "echo 'Phase 1B works'"},
        session,
    )
    assert result.ok is True
    assert "Phase 1B works" in result.data["stdout"]


@pytest.mark.slow
@pytest.mark.asyncio
async def test_code_executor_python_generates_file(session):
    tool = CodeExecutorTool()
    result = await tool.execute(
        {
            "action": "run_python",
            "code": (
                "import pathlib\n"
                "pathlib.Path('/workspace/outputs/result.txt').write_text('output data')\n"
                "print('done')"
            ),
        },
        session,
    )
    assert result.ok is True
    assert result.data["exit_code"] == 0
    assert any("result.txt" in f for f in result.data["generated_files"])


@pytest.mark.slow
@pytest.mark.asyncio
async def test_code_executor_timeout(session):
    tool = CodeExecutorTool()
    result = await tool.execute(
        {"action": "run_python", "code": "import time; time.sleep(200)", "timeout_s": 2},
        session,
    )
    assert result.ok is True  # timeout is a bounded result, not a tool failure
    assert result.data["exit_code"] == -1
    assert "timed out" in result.data["stderr"].lower()
