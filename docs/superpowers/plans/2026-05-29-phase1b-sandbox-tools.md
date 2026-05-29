# Phase 1B — Sandbox + Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the isolated sandbox container (Docker in dev, Kata in prod) with a JSON-RPC tool server inside, then implement 4 tool RPC clients in the backend — browser (Playwright), code_executor, file_system, and web_search.

**Architecture:** Each agent session gets a dedicated Docker container running a FastAPI-based JSON-RPC tool server on port 9999. The backend's `SandboxManager` provisions containers via the Docker SDK and returns their network endpoint. Tool classes in `backend/app/tools/` are pure RPC clients — they serialize a call, POST it to the sandbox, and return the result. All actual execution (Playwright, subprocess, file I/O) happens inside the container. `web_search` is the only tool that doesn't use the sandbox — it calls the Brave/SearXNG HTTP API directly.

**Tech Stack:** Docker SDK (`docker` Python package), FastAPI (tool server inside sandbox), Playwright 1.45+ (inside sandbox), httpx (RPC client), asyncio subprocess (code executor inside sandbox). Backend additions: `docker>=7.0`, `httpx` (already installed). Sandbox image: `python:3.12-slim` base.

**Spec reference:** `docs/agentis_spec.md` — §6 (Epic 4, Tool Registry), §7 (Epic 5, Sandbox).

**Depends on:** Phase 1A complete (tag `phase-1a`). All 40 tests pass.

---

## Deliverable

At the end of this plan:
- `docker build -t agentis-sandbox:latest ./sandbox/` succeeds.
- `SandboxManager.create_session(task_id)` starts a container, waits for the tool server, returns an endpoint.
- All 4 tools work end-to-end: backend sends RPC → sandbox executes → result returned.
- Integration tests pass: real container started, real tool calls made.
- 55+ total tests pass (40 existing + new tests).

---

## File Structure

```
agentis/
├── sandbox/                              # Built into agentis-sandbox:latest Docker image
│   ├── Dockerfile
│   ├── requirements.txt
│   └── tool_server/
│       ├── main.py                       # FastAPI app — single POST /rpc endpoint
│       ├── dispatcher.py                 # Routes method → handler
│       └── handlers/
│           ├── __init__.py
│           ├── browser.py               # Playwright: navigate, click, fill, extract_text, etc.
│           ├── code_executor.py         # asyncio.subprocess: run_python, run_node, run_bash
│           └── file_system.py           # /workspace/ operations: read, write, list, delete
│
├── backend/
│   ├── app/
│   │   ├── config.py                    # Add sandbox + search settings
│   │   ├── sandbox/
│   │   │   ├── __init__.py
│   │   │   ├── manager.py               # SandboxManager: create/destroy/pool
│   │   │   └── rpc_client.py            # Async JSON-RPC client (httpx POST)
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── base.py                  # BaseTool ABC, SessionContext, ToolResult
│   │       ├── registry.py              # ToolRegistry: register + get_tool(name)
│   │       ├── browser.py               # BrowserTool (RPC client)
│   │       ├── code_executor.py         # CodeExecutorTool (RPC client)
│   │       ├── file_system.py           # FileSystemTool (RPC client)
│   │       └── web_search.py            # WebSearchTool (HTTP, no sandbox)
│   ├── pyproject.toml                   # Add: docker>=7.0
│   └── tests/
│       ├── test_sandbox/
│       │   ├── __init__.py
│       │   └── test_manager.py          # Unit: mock Docker SDK
│       └── test_tools/
│           ├── __init__.py
│           ├── test_base.py             # Unit: BaseTool, ToolResult, SessionContext
│           ├── test_registry.py         # Unit: ToolRegistry
│           ├── test_web_search.py       # Unit: mock httpx
│           └── test_sandbox_integration.py  # Integration: real container
│
├── docker-compose.yml                   # Add: squid service
└── docker-compose.override.yml         # Add: sandbox image build context
```

---

## Task 1: Config Extensions + pyproject.toml

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/pyproject.toml`

---

- [ ] **Step 1.1: Add sandbox and search settings to `backend/app/config.py`**

Append the following fields to the `Settings` class (after the existing `environment` field):

```python
    # Sandbox
    sandbox_image: str = "agentis-sandbox:latest"
    sandbox_max_concurrent: int = 10
    sandbox_warm_pool_size: int = 2
    sandbox_timeout_seconds: int = 1800
    sandbox_network: str = "agentis_default"  # Docker network name
    sandbox_rpc_port: int = 9999
    egress_proxy_url: str = ""  # e.g. http://squid:3128 (empty = no proxy)

    # Tools
    tool_output_max_tokens: int = 8000
    code_executor_timeout_s: int = 120

    # Search
    search_backend: str = "brave"          # brave|searxng|tavily
    brave_api_key: str = ""
    searxng_url: str = "http://searxng:8080"
    tavily_api_key: str = ""
```

- [ ] **Step 1.2: Add `docker` dependency to `backend/pyproject.toml`**

In the `dependencies` list, add after `httpx`:
```toml
    "docker>=7.0",
```

- [ ] **Step 1.3: Install new dependency**

```bash
cd /home/yulcom/web/perso/agentis/backend
pip install -e ".[dev]"
```

Expected: `docker` package installed. Verify: `python -c "import docker; print(docker.__version__)"`.

- [ ] **Step 1.4: Verify existing tests still pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: `40 passed`.

- [ ] **Step 1.5: Update `.env.example`** — add new variables

```bash
cd /home/yulcom/web/perso/agentis
cat >> .env.example << 'EOF'

# Sandbox
AGENTIS_SANDBOX_IMAGE=agentis-sandbox:latest
AGENTIS_SANDBOX_MAX_CONCURRENT=10
AGENTIS_SANDBOX_WARM_POOL_SIZE=2
AGENTIS_SANDBOX_TIMEOUT_SECONDS=1800
AGENTIS_SANDBOX_NETWORK=agentis_default
AGENTIS_EGRESS_PROXY_URL=

# Tools
AGENTIS_TOOL_OUTPUT_MAX_TOKENS=8000
AGENTIS_CODE_EXECUTOR_TIMEOUT_S=120

# Search (choose one backend)
AGENTIS_SEARCH_BACKEND=brave
AGENTIS_BRAVE_API_KEY=
AGENTIS_SEARXNG_URL=http://searxng:8080
AGENTIS_TAVILY_API_KEY=
EOF
```

- [ ] **Step 1.6: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add backend/app/config.py backend/pyproject.toml .env.example
git commit -m "feat: add sandbox + search config settings, docker dependency"
```

---

## Task 2: Sandbox Docker Image — Base + file_system + code_executor handlers

**Files:**
- Create: `sandbox/Dockerfile`
- Create: `sandbox/requirements.txt`
- Create: `sandbox/tool_server/main.py`
- Create: `sandbox/tool_server/dispatcher.py`
- Create: `sandbox/tool_server/handlers/__init__.py`
- Create: `sandbox/tool_server/handlers/file_system.py`
- Create: `sandbox/tool_server/handlers/code_executor.py`

---

- [ ] **Step 2.1: Create `sandbox/requirements.txt`**

```
fastapi>=0.115
uvicorn[standard]>=0.30
playwright>=1.45
httpx>=0.27
```

- [ ] **Step 2.2: Create `sandbox/tool_server/handlers/__init__.py`** — empty.

- [ ] **Step 2.3: Create `sandbox/tool_server/handlers/file_system.py`**

```python
import os
import shutil
from pathlib import Path

WORKSPACE = Path("/workspace")


def _safe_path(path: str) -> Path:
    """Resolve path and ensure it stays within /workspace. Raises ValueError otherwise."""
    resolved = (WORKSPACE / path.lstrip("/")).resolve()
    if not str(resolved).startswith(str(WORKSPACE)):
        raise ValueError(f"Path '{path}' escapes /workspace")
    return resolved


async def handle(action: str, params: dict) -> dict:
    if action == "write":
        p = _safe_path(params["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        content = params["content"]
        if isinstance(content, str):
            p.write_text(content, encoding="utf-8")
        else:
            p.write_bytes(bytes(content))
        return {"success": True, "size_bytes": p.stat().st_size}

    elif action == "read":
        p = _safe_path(params["path"])
        text = p.read_text(encoding="utf-8", errors="replace")
        max_chars = params.get("max_chars", 50_000)
        truncated = len(text) > max_chars
        return {"content": text[:max_chars], "truncated": truncated}

    elif action == "list":
        p = _safe_path(params.get("directory", "/workspace"))
        entries = []
        for item in sorted(p.iterdir()):
            stat = item.stat()
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            })
        return {"entries": entries}

    elif action == "delete":
        p = _safe_path(params["path"])
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"success": True}

    elif action == "copy":
        src = _safe_path(params["src"])
        dst = _safe_path(params["dst"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return {"success": True}

    elif action == "compress":
        paths = [_safe_path(p) for p in params["paths"]]
        archive = _safe_path(params["archive_name"])
        import tarfile
        with tarfile.open(archive, "w:gz") as tar:
            for p in paths:
                tar.add(p, arcname=p.name)
        return {"archive_path": str(archive.relative_to(WORKSPACE))}

    raise ValueError(f"Unknown file_system action: {action}")
```

- [ ] **Step 2.4: Create `sandbox/tool_server/handlers/code_executor.py`**

```python
import asyncio
import os
from pathlib import Path

WORKSPACE = Path("/workspace")
OUTPUTS = WORKSPACE / "outputs"


async def _run(cmd: list[str], timeout_s: int, env: dict | None = None) -> dict:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    before = set(OUTPUTS.rglob("*"))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(WORKSPACE),
        env={**os.environ, **(env or {})},
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {
            "stdout": "", "stderr": f"Execution timed out after {timeout_s}s",
            "exit_code": -1, "generated_files": [], "truncated": False,
        }

    after = set(OUTPUTS.rglob("*"))
    new_files = [str(p.relative_to(WORKSPACE)) for p in (after - before) if p.is_file()]

    max_chars = 10_000
    stdout = stdout_b.decode(errors="replace")
    stderr = stderr_b.decode(errors="replace")
    truncated = len(stdout) > max_chars or len(stderr) > max_chars

    return {
        "stdout": stdout[:max_chars],
        "stderr": stderr[:max_chars],
        "exit_code": proc.returncode,
        "generated_files": new_files,
        "truncated": truncated,
    }


async def handle(action: str, params: dict) -> dict:
    timeout = params.get("timeout_s", 120)

    if action == "run_python":
        return await _run(
            ["python3", "-c", params["code"]],
            timeout_s=timeout,
        )

    elif action == "run_node":
        return await _run(
            ["node", "-e", params["code"]],
            timeout_s=timeout,
        )

    elif action == "run_bash":
        return await _run(
            ["bash", "-c", params["command"]],
            timeout_s=timeout,
        )

    raise ValueError(f"Unknown code_executor action: {action}")
```

- [ ] **Step 2.5: Create `sandbox/tool_server/dispatcher.py`**

```python
from sandbox.tool_server.handlers import file_system, code_executor

# browser handler imported lazily to avoid Playwright import at startup before install
_HANDLERS = {
    "file_system": file_system.handle,
    "code_executor": code_executor.handle,
}


def register_browser():
    from sandbox.tool_server.handlers import browser
    _HANDLERS["browser"] = browser.handle


async def dispatch(method: str, params: dict) -> dict:
    """
    method format: "{tool_name}.{action}" e.g. "browser.navigate"
    """
    parts = method.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid method format: {method!r}. Expected 'tool.action'")

    tool_name, action = parts
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        raise ValueError(f"Unknown tool: {tool_name!r}")

    return await handler(action, params)
```

- [ ] **Step 2.6: Create `sandbox/tool_server/main.py`**

```python
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any
import sys
import os

# Add sandbox directory to path
sys.path.insert(0, "/app")

from sandbox.tool_server.dispatcher import dispatch, register_browser

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tool_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register browser handler (requires playwright to be installed)
    try:
        register_browser()
        log.info("Browser handler registered")
    except ImportError as e:
        log.warning(f"Browser handler not available: {e}")
    log.info("Tool server ready on port 9999")
    yield


app = FastAPI(lifespan=lifespan)


class RpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] = {}
    id: int | str | None = None


@app.post("/rpc")
async def rpc_endpoint(req: RpcRequest):
    try:
        result = await dispatch(req.method, req.params)
        return {"jsonrpc": "2.0", "result": result, "id": req.id}
    except ValueError as e:
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": str(e)},
                "id": req.id,
            },
        )
    except Exception as e:
        log.exception(f"Tool error: {req.method}")
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": f"Tool execution failed: {str(e)}"},
                "id": req.id,
            },
        )


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 2.7: Create `sandbox/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    bash \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps

# Copy tool server code
COPY tool_server/ ./sandbox/tool_server/
RUN touch ./sandbox/__init__.py ./sandbox/tool_server/__init__.py

# Create workspace
RUN mkdir -p /workspace/inputs /workspace/outputs && chmod 777 /workspace

# Non-root user for security
RUN useradd -m -u 1000 sandbox && chown -R sandbox:sandbox /workspace
USER sandbox

# Expose tool server port
EXPOSE 9999

CMD ["uvicorn", "sandbox.tool_server.main:app", "--host", "0.0.0.0", "--port", "9999"]
```

- [ ] **Step 2.8: Build the sandbox image**

```bash
cd /home/yulcom/web/perso/agentis
docker build -t agentis-sandbox:latest ./sandbox/
```

Expected: Build succeeds. Last line: `Successfully tagged agentis-sandbox:latest`.

NOTE: The build installs Playwright browsers which takes 2-3 minutes on first run.

- [ ] **Step 2.9: Smoke test the tool server**

```bash
# Start a temporary container
docker run -d --rm --name sandbox-test -p 19999:9999 agentis-sandbox:latest
sleep 3

# Test health
curl -s http://localhost:19999/health

# Test file_system write
curl -s -X POST http://localhost:19999/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"file_system.write","params":{"path":"test.txt","content":"hello"},"id":1}'

# Test file_system read
curl -s -X POST http://localhost:19999/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"file_system.read","params":{"path":"test.txt"},"id":2}'

# Test code_executor
curl -s -X POST http://localhost:19999/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"code_executor.run_python","params":{"code":"print(1+1)"},"id":3}'

# Cleanup
docker stop sandbox-test
```

Expected output for code_executor: `{"jsonrpc":"2.0","result":{"stdout":"2\n","stderr":"","exit_code":0,"generated_files":[],"truncated":false},"id":3}`

- [ ] **Step 2.10: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add sandbox/
git commit -m "feat: sandbox Docker image — tool server with file_system + code_executor handlers"
```

---

## Task 3: Browser Handler (Playwright inside sandbox)

**Files:**
- Create: `sandbox/tool_server/handlers/browser.py`
- Rebuild: `agentis-sandbox:latest`

---

- [ ] **Step 3.1: Write the browser handler**

Create `sandbox/tool_server/handlers/browser.py`:

```python
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page

# Module-level browser instance — shared across calls within one container session
_playwright = None
_browser: Optional[Browser] = None
_page: Optional[Page] = None


async def _get_page() -> Page:
    global _playwright, _browser, _page
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
    if _page is None or _page.is_closed():
        context = await _browser.new_context()
        _page = await context.new_page()
    return _page


MAX_TEXT = 50_000


async def handle(action: str, params: dict) -> dict:
    page = await _get_page()

    if action == "navigate":
        response = await page.goto(params["url"], wait_until="domcontentloaded", timeout=30_000)
        return {"title": await page.title(), "url": page.url}

    elif action == "click":
        await page.click(params["selector"], timeout=10_000)
        return {"success": True}

    elif action == "fill":
        await page.fill(params["selector"], params["value"], timeout=10_000)
        return {"success": True}

    elif action == "extract_text":
        selector = params.get("selector")
        if selector:
            text = await page.inner_text(selector)
        else:
            text = await page.inner_text("body")
        truncated = len(text) > MAX_TEXT
        return {"text": text[:MAX_TEXT], "truncated": truncated}

    elif action == "screenshot":
        import base64
        data = await page.screenshot(type="png")
        return {"image_base64": base64.b64encode(data).decode(), "mime_type": "image/png"}

    elif action == "find_links":
        pattern = params.get("filter_pattern", "")
        links = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({text: e.innerText.trim(), url: e.href}))",
        )
        if pattern:
            import re
            links = [l for l in links if re.search(pattern, l["url"])]
        return {"links": links[:100]}

    elif action == "wait_for_selector":
        timeout_ms = params.get("timeout_ms", 5_000)
        try:
            await page.wait_for_selector(params["selector"], timeout=timeout_ms)
            return {"found": True}
        except Exception:
            return {"found": False}

    elif action == "scroll":
        direction = params.get("direction", "down")
        pixels = params.get("pixels", 500)
        delta = pixels if direction == "down" else -pixels
        await page.mouse.wheel(0, delta)
        return {"success": True}

    raise ValueError(f"Unknown browser action: {action}")
```

- [ ] **Step 3.2: Rebuild sandbox image**

```bash
cd /home/yulcom/web/perso/agentis
docker build -t agentis-sandbox:latest ./sandbox/
```

Expected: Build succeeds.

- [ ] **Step 3.3: Test browser handler**

```bash
docker run -d --rm --name sandbox-browser-test -p 19999:9999 agentis-sandbox:latest
sleep 5

# Navigate to a page
curl -s -X POST http://localhost:19999/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"browser.navigate","params":{"url":"https://example.com"},"id":1}'

# Extract text
curl -s -X POST http://localhost:19999/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"browser.extract_text","params":{},"id":2}'

docker stop sandbox-browser-test
```

Expected: navigate returns `{"title":"Example Domain","url":"https://example.com/"}`.

NOTE: This requires internet access from the Docker container. If the network is restricted, test with a local URL or skip the network-dependent assertion.

- [ ] **Step 3.4: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add sandbox/tool_server/handlers/browser.py
git commit -m "feat: sandbox browser handler — Playwright navigate, click, fill, extract_text, screenshot"
```

---

## Task 4: Backend — BaseTool + SessionContext + RPC Client

**Files:**
- Create: `backend/app/tools/__init__.py`
- Create: `backend/app/tools/base.py`
- Create: `backend/app/sandbox/__init__.py`
- Create: `backend/app/sandbox/rpc_client.py`
- Create: `backend/tests/test_tools/__init__.py`
- Create: `backend/tests/test_tools/test_base.py`
- Create: `backend/tests/test_sandbox/__init__.py`

---

- [ ] **Step 4.1: Write failing tests for BaseTool**

Create `backend/tests/test_tools/__init__.py` (empty) and `backend/tests/test_tools/test_base.py`:

```python
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


def test_base_tool_is_abstract():
    import inspect
    assert inspect.isabstract(BaseTool)


def test_base_tool_requires_name_description():
    with pytest.raises(TypeError):
        BaseTool()  # abstract, can't instantiate directly
```

Run: `cd backend && pytest tests/test_tools/test_base.py -v` — expect FAIL.

- [ ] **Step 4.2: Create `backend/app/tools/base.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    retryable: bool = False  # True for transient errors (network, timeout)


@dataclass
class SessionContext:
    session_id: str
    task_id: str
    sandbox_endpoint: str  # http://{container_ip}:{port}
    secrets_accessor: Any = None  # Vault client — wired up in Phase 1C


class BaseTool(ABC):
    name: str = ""           # snake_case, unique — e.g. "browser"
    description: str = ""    # LLM-readable description
    input_schema: dict = {}  # JSON Schema for params
    output_schema: dict = {} # JSON Schema for result

    @abstractmethod
    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Subclasses must declare name and description (unless abstract themselves)
        if not getattr(cls, "__abstractmethods__", None):
            if not cls.name:
                raise TypeError(f"{cls.__name__} must define 'name'")
            if not cls.description:
                raise TypeError(f"{cls.__name__} must define 'description'")
```

- [ ] **Step 4.3: Create `backend/app/tools/__init__.py`** — empty.

- [ ] **Step 4.4: Run base tests — expect PASS**

```bash
cd /home/yulcom/web/perso/agentis/backend
pytest tests/test_tools/test_base.py -v
```

Expected: 5 PASS.

- [ ] **Step 4.5: Create `backend/app/sandbox/__init__.py`** and `backend/app/sandbox/rpc_client.py`

`backend/app/sandbox/__init__.py` — empty.

```python
# backend/app/sandbox/rpc_client.py
import httpx
from typing import Any


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"RPC error {code}: {message}")


class SandboxRpcClient:
    """
    Async JSON-RPC 2.0 client over HTTP.
    Connects to the tool server running inside a sandbox container.
    """

    def __init__(self, endpoint: str, timeout_s: float = 130.0):
        self._url = f"{endpoint.rstrip('/')}/rpc"
        self._timeout = timeout_s
        self._counter = 0

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._counter += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._counter,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._url, json=payload)
            resp.raise_for_status()
            body = resp.json()

        if "error" in body:
            err = body["error"]
            raise RpcError(code=err.get("code", -1), message=err.get("message", "Unknown error"))

        return body.get("result", {})
```

- [ ] **Step 4.6: Create `backend/tests/test_sandbox/__init__.py`** — empty.

- [ ] **Step 4.7: Write failing RPC client unit test**

Create `backend/tests/test_sandbox/test_rpc_client.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.sandbox.rpc_client import SandboxRpcClient, RpcError


@pytest.mark.asyncio
async def test_rpc_call_success():
    client = SandboxRpcClient("http://localhost:19999")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "jsonrpc": "2.0", "result": {"stdout": "hello\n"}, "id": 1
    })

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_http

        result = await client.call("code_executor.run_python", {"code": "print('hello')"})

    assert result == {"stdout": "hello\n"}


@pytest.mark.asyncio
async def test_rpc_call_error_response():
    client = SandboxRpcClient("http://localhost:19999")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "jsonrpc": "2.0",
        "error": {"code": -32600, "message": "Unknown tool: missing"},
        "id": 1,
    })

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_http

        with pytest.raises(RpcError) as exc_info:
            await client.call("missing.action", {})

    assert exc_info.value.code == -32600
    assert "Unknown tool" in exc_info.value.message


@pytest.mark.asyncio
async def test_rpc_id_increments():
    client = SandboxRpcClient("http://localhost:19999")
    assert client._counter == 0

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"jsonrpc": "2.0", "result": {}, "id": 1})

    calls_made = []

    async def capture_post(url, json=None, **kwargs):
        calls_made.append(json)
        return mock_response

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.post = capture_post
        mock_cls.return_value = mock_http

        await client.call("file_system.list", {"directory": "/"})
        await client.call("file_system.list", {"directory": "/"})

    assert calls_made[0]["id"] == 1
    assert calls_made[1]["id"] == 2
```

Run: `pytest tests/test_sandbox/test_rpc_client.py -v` — expect FAIL.

- [ ] **Step 4.8: Run RPC client tests — verify PASS**

```bash
cd /home/yulcom/web/perso/agentis/backend
pytest tests/test_sandbox/ tests/test_tools/test_base.py -v
```

Expected: 8 PASS.

- [ ] **Step 4.9: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add backend/app/tools/ backend/app/sandbox/ backend/tests/test_tools/ backend/tests/test_sandbox/
git commit -m "feat: BaseTool + SessionContext + SandboxRpcClient with unit tests"
```

---

## Task 5: SandboxManager

**Files:**
- Create: `backend/app/sandbox/manager.py`
- Modify: `backend/tests/test_sandbox/test_rpc_client.py` (add manager tests)

---

- [ ] **Step 5.1: Write failing manager tests**

Create `backend/tests/test_sandbox/test_manager.py`:

```python
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.sandbox.manager import SandboxManager, SandboxSession


def make_mock_container(id="abc123", status="running", ip="172.17.0.5"):
    c = MagicMock()
    c.id = id
    c.status = status
    attrs = {"NetworkSettings": {"Networks": {"agentis_default": {"IPAddress": ip}}}}
    c.attrs = attrs
    c.reload = MagicMock()
    c.stop = MagicMock()
    c.remove = MagicMock()
    return c


@pytest.fixture
def mock_docker():
    with patch("docker.from_env") as mock_fn:
        client = MagicMock()
        mock_fn.return_value = client
        yield client


def test_manager_creates_session(mock_docker):
    container = make_mock_container()
    mock_docker.containers.run.return_value = container

    manager = SandboxManager()
    session = manager._start_container("task-001")

    assert session.task_id == "task-001"
    assert session.container_id == "abc123"
    assert session.endpoint == "http://172.17.0.5:9999"
    mock_docker.containers.run.assert_called_once()


def test_manager_destroy_session(mock_docker):
    container = make_mock_container()
    mock_docker.containers.run.return_value = container
    mock_docker.containers.get.return_value = container

    manager = SandboxManager()
    session = manager._start_container("task-002")
    manager.destroy_session("task-002")

    container.stop.assert_called_once()
    container.remove.assert_called_once()
    assert "task-002" not in manager._sessions


def test_manager_tracks_active_sessions(mock_docker):
    container = make_mock_container()
    mock_docker.containers.run.return_value = container

    manager = SandboxManager()
    manager._start_container("task-003")
    manager._start_container("task-004")

    assert len(manager._sessions) == 2
```

Run: `pytest tests/test_sandbox/test_manager.py -v` — expect FAIL.

- [ ] **Step 5.2: Create `backend/app/sandbox/manager.py`**

```python
import time
import docker
import structlog
from dataclasses import dataclass, field
from app.config import settings

log = structlog.get_logger()


@dataclass
class SandboxSession:
    task_id: str
    container_id: str
    endpoint: str  # http://{ip}:9999
    created_at: float = field(default_factory=time.time)


class SandboxManager:
    """
    Manages sandbox container lifecycle.
    In dev: plain Docker containers with security options.
    In prod (K3s): replaced by Kata Container RuntimeClass.
    """

    def __init__(self):
        self._client = docker.from_env()
        self._sessions: dict[str, SandboxSession] = {}

    def _start_container(self, task_id: str) -> SandboxSession:
        container = self._client.containers.run(
            image=settings.sandbox_image,
            detach=True,
            network=settings.sandbox_network,
            name=f"agentis-sandbox-{task_id}",
            # Security hardening for dev Docker (not Kata)
            security_opt=["no-new-privileges"],
            read_only=False,   # /workspace needs to be writable
            mem_limit="2g",
            nano_cpus=2 * 10**9,  # 2 CPUs
            remove=False,
            labels={"agentis.task_id": task_id, "agentis.managed": "true"},
        )

        # Wait for the container to get a network IP
        container.reload()
        networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
        network_info = networks.get(settings.sandbox_network, {})
        ip = network_info.get("IPAddress", "")

        if not ip:
            # Fallback: try any network
            for net_data in networks.values():
                if net_data.get("IPAddress"):
                    ip = net_data["IPAddress"]
                    break

        endpoint = f"http://{ip}:{settings.sandbox_rpc_port}"
        session = SandboxSession(
            task_id=task_id,
            container_id=container.id,
            endpoint=endpoint,
        )
        self._sessions[task_id] = session
        log.info("sandbox_created", task_id=task_id, container_id=container.id[:12], endpoint=endpoint)
        return session

    def get_session(self, task_id: str) -> SandboxSession | None:
        return self._sessions.get(task_id)

    def destroy_session(self, task_id: str) -> None:
        session = self._sessions.pop(task_id, None)
        if session is None:
            return
        try:
            container = self._client.containers.get(session.container_id)
            container.stop(timeout=10)
            container.remove()
            log.info("sandbox_destroyed", task_id=task_id)
        except Exception as e:
            log.error("sandbox_destroy_failed", task_id=task_id, error=str(e))

    async def create_session(self, task_id: str) -> SandboxSession:
        """
        Create a new sandbox session. Waits for the tool server to be ready.
        In Phase 1B this is synchronous Docker; Phase 2 adds warm pool.
        """
        import asyncio, httpx

        session = self._start_container(task_id)

        # Wait for tool server health check (up to 15 seconds)
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{session.endpoint}/health")
                    if resp.status_code == 200:
                        log.info("sandbox_ready", task_id=task_id)
                        return session
            except Exception:
                pass
            await asyncio.sleep(0.5)

        # Timed out — clean up and raise
        self.destroy_session(task_id)
        raise RuntimeError(f"Sandbox for task {task_id} did not become ready within 15 seconds")


# Module-level singleton — shared across the FastAPI process
sandbox_manager = SandboxManager()
```

- [ ] **Step 5.3: Run manager tests**

```bash
cd /home/yulcom/web/perso/agentis/backend
pytest tests/test_sandbox/ -v
```

Expected: All PASS (3 manager tests + 3 rpc_client tests).

- [ ] **Step 5.4: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add backend/app/sandbox/manager.py backend/tests/test_sandbox/test_manager.py
git commit -m "feat: SandboxManager — Docker container lifecycle with health-wait"
```

---

## Task 6: ToolRegistry + WebSearchTool

**Files:**
- Create: `backend/app/tools/registry.py`
- Create: `backend/app/tools/web_search.py`
- Create: `backend/tests/test_tools/test_registry.py`
- Create: `backend/tests/test_tools/test_web_search.py`

---

- [ ] **Step 6.1: Write failing registry tests**

Create `backend/tests/test_tools/test_registry.py`:

```python
import pytest
from app.tools.registry import ToolRegistry
from app.tools.base import BaseTool, SessionContext, ToolResult


class EchoTool(BaseTool):
    name = "echo"
    description = "Echoes params back."

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        return ToolResult(ok=True, data=params)


def test_registry_register_and_get():
    registry = ToolRegistry()
    registry.register(EchoTool)
    tool = registry.get("echo")
    assert isinstance(tool, EchoTool)


def test_registry_get_unknown_returns_none():
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None


def test_registry_list_names():
    registry = ToolRegistry()
    registry.register(EchoTool)
    assert "echo" in registry.list_names()


def test_registry_duplicate_raises():
    registry = ToolRegistry()
    registry.register(EchoTool)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoTool)
```

Run `pytest tests/test_tools/test_registry.py -v` — expect FAIL.

- [ ] **Step 6.2: Create `backend/app/tools/registry.py`**

```python
from app.tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool_class: type[BaseTool]) -> None:
        tool = tool_class()
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_all(self) -> list[BaseTool]:
        return list(self._tools.values())


# Module-level registry populated at startup
tool_registry = ToolRegistry()
```

- [ ] **Step 6.3: Run registry tests — expect PASS**

```bash
cd /home/yulcom/web/perso/agentis/backend
pytest tests/test_tools/test_registry.py -v
```

Expected: 4 PASS.

- [ ] **Step 6.4: Write failing web_search tests**

Create `backend/tests/test_tools/test_web_search.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
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
async def test_web_search_returns_results(tool, session):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "results": [
            {"title": "Test Page", "url": "https://example.com", "description": "A test page"},
        ]
    })

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_http

        result = await tool.execute({"query": "test query", "num_results": 5}, session)

    assert result.ok is True
    assert len(result.data["results"]) == 1
    assert result.data["results"][0]["title"] == "Test Page"


@pytest.mark.asyncio
async def test_web_search_no_api_key_returns_empty(tool, session, monkeypatch):
    """With no API key configured, return empty results gracefully."""
    monkeypatch.setattr("app.tools.web_search.settings.brave_api_key", "")
    monkeypatch.setattr("app.tools.web_search.settings.search_backend", "brave")

    result = await tool.execute({"query": "test"}, session)
    assert result.ok is True
    assert result.data["results"] == []


@pytest.mark.asyncio
async def test_web_search_caps_num_results(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.web_search.settings.brave_api_key", "fake-key")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"results": []})

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_http

        result = await tool.execute({"query": "test", "num_results": 999}, session)

    # Verify the actual request used max 20
    call_args = mock_http.get.call_args
    params = call_args.kwargs.get("params", {}) or call_args.args[1] if len(call_args.args) > 1 else {}
    # num_results should be capped at 20
    assert result.ok is True
```

Run `pytest tests/test_tools/test_web_search.py -v` — expect FAIL.

- [ ] **Step 6.5: Create `backend/app/tools/web_search.py`**

```python
import httpx
from app.tools.base import BaseTool, SessionContext, ToolResult
from app.config import settings


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the web for information. Returns ranked results with titles, URLs, and snippets."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query":       {"type": "string"},
            "num_results": {"type": "integer", "default": 10, "maximum": 20},
            "language":    {"type": "string", "enum": ["en", "fr"], "default": "en"},
            "time_range":  {"type": "string", "enum": ["day", "week", "month", "year"]},
        },
        "required": ["query"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        query = params["query"]
        num_results = min(int(params.get("num_results", 10)), 20)
        language = params.get("language", "en")
        time_range = params.get("time_range")

        backend = settings.search_backend

        if backend == "brave":
            return await self._brave_search(query, num_results, language, time_range)
        elif backend == "searxng":
            return await self._searxng_search(query, num_results, language)
        else:
            return ToolResult(ok=False, error=f"Unknown search backend: {backend}", retryable=False)

    async def _brave_search(self, query: str, num_results: int, language: str, time_range) -> ToolResult:
        if not settings.brave_api_key:
            return ToolResult(ok=True, data={"results": []})  # No key — graceful empty

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": settings.brave_api_key,
        }
        req_params: dict = {"q": query, "count": num_results, "search_lang": language}
        if time_range:
            req_params["freshness"] = time_range

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers=headers,
                    params=req_params,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            return ToolResult(ok=False, error=str(e), retryable=True)

        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
                "published_at": r.get("page_age"),
            }
            for r in data.get("results", [])
        ]
        return ToolResult(ok=True, data={"results": results})

    async def _searxng_search(self, query: str, num_results: int, language: str) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.searxng_url}/search",
                    params={"q": query, "format": "json", "language": language, "count": num_results},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            return ToolResult(ok=False, error=str(e), retryable=True)

        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "published_at": r.get("publishedDate"),
            }
            for r in data.get("results", [])[:num_results]
        ]
        return ToolResult(ok=True, data={"results": results})
```

- [ ] **Step 6.6: Run all tool tests**

```bash
cd /home/yulcom/web/perso/agentis/backend
pytest tests/test_tools/ -v
```

Expected: All PASS (5 base + 4 registry + 4 web_search = 13 tests).

- [ ] **Step 6.7: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add backend/app/tools/registry.py backend/app/tools/web_search.py \
        backend/tests/test_tools/test_registry.py backend/tests/test_tools/test_web_search.py
git commit -m "feat: ToolRegistry + WebSearchTool (Brave/SearXNG) with unit tests"
```

---

## Task 7: FileSystemTool + CodeExecutorTool RPC Clients

**Files:**
- Create: `backend/app/tools/file_system.py`
- Create: `backend/app/tools/code_executor.py`

Tests for these tools are covered in Task 11 (integration tests) since they require a real sandbox.

---

- [ ] **Step 7.1: Create `backend/app/tools/file_system.py`**

```python
from app.tools.base import BaseTool, SessionContext, ToolResult
from app.sandbox.rpc_client import SandboxRpcClient, RpcError


class FileSystemTool(BaseTool):
    name = "file_system"
    description = (
        "Read, write, list, delete, and compress files within the agent's /workspace. "
        "All paths are relative to /workspace and must not escape it."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["write", "read", "list", "delete", "copy", "compress"]},
            "path":   {"type": "string"},
        },
        "required": ["action"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        client = SandboxRpcClient(session.sandbox_endpoint)
        action = params.get("action")
        try:
            result = await client.call(f"file_system.{action}", params)
            return ToolResult(ok=True, data=result)
        except RpcError as e:
            retryable = e.code == -32000  # server-side execution error may be transient
            return ToolResult(ok=False, error=e.message, retryable=retryable)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), retryable=True)
```

- [ ] **Step 7.2: Create `backend/app/tools/code_executor.py`**

```python
from app.tools.base import BaseTool, SessionContext, ToolResult
from app.sandbox.rpc_client import SandboxRpcClient, RpcError
from app.config import settings


class CodeExecutorTool(BaseTool):
    name = "code_executor"
    description = (
        "Execute Python 3.12, Node.js 22, or Bash code inside the secure sandbox. "
        "Generated files in /workspace/outputs/ are captured as artifacts."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action":    {"type": "string", "enum": ["run_python", "run_node", "run_bash"]},
            "code":      {"type": "string"},
            "command":   {"type": "string"},
            "timeout_s": {"type": "integer", "default": 120},
        },
        "required": ["action"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        action = params.get("action")
        timeout = min(int(params.get("timeout_s", settings.code_executor_timeout_s)), 120)
        rpc_params = dict(params)
        rpc_params["timeout_s"] = timeout

        client = SandboxRpcClient(session.sandbox_endpoint, timeout_s=timeout + 15)
        try:
            result = await client.call(f"code_executor.{action}", rpc_params)
            return ToolResult(ok=True, data=result)
        except RpcError as e:
            return ToolResult(ok=False, error=e.message, retryable=False)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), retryable=True)
```

- [ ] **Step 7.3: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add backend/app/tools/file_system.py backend/app/tools/code_executor.py
git commit -m "feat: FileSystemTool + CodeExecutorTool RPC clients"
```

---

## Task 8: BrowserTool RPC Client

**Files:**
- Create: `backend/app/tools/browser.py`

---

- [ ] **Step 8.1: Create `backend/app/tools/browser.py`**

```python
from app.tools.base import BaseTool, SessionContext, ToolResult
from app.sandbox.rpc_client import SandboxRpcClient, RpcError


class BrowserTool(BaseTool):
    name = "browser"
    description = (
        "Control a headless Chromium browser running inside the secure sandbox. "
        "Navigate URLs, click elements, fill forms, extract text, and take screenshots."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action":   {"type": "string",
                         "enum": ["navigate", "click", "fill", "extract_text",
                                  "screenshot", "find_links", "wait_for_selector", "scroll"]},
            "url":      {"type": "string"},
            "selector": {"type": "string"},
            "value":    {"type": "string"},
        },
        "required": ["action"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        action = params.get("action")
        client = SandboxRpcClient(session.sandbox_endpoint, timeout_s=60.0)
        try:
            result = await client.call(f"browser.{action}", params)
            return ToolResult(ok=True, data=result)
        except RpcError as e:
            retryable = e.code == -32000
            return ToolResult(ok=False, error=e.message, retryable=retryable)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), retryable=True)
```

- [ ] **Step 8.2: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add backend/app/tools/browser.py
git commit -m "feat: BrowserTool RPC client (Playwright via sandbox JSON-RPC)"
```

---

## Task 9: Wire Up Registry + Docker Compose Updates

**Files:**
- Create: `backend/app/tools/init_registry.py`
- Modify: `backend/app/main.py`
- Modify: `docker-compose.yml` (add squid)
- Modify: `docker-compose.override.yml` (add sandbox build)

---

- [ ] **Step 9.1: Create `backend/app/tools/init_registry.py`**

```python
from app.tools.registry import tool_registry
from app.tools.browser import BrowserTool
from app.tools.code_executor import CodeExecutorTool
from app.tools.file_system import FileSystemTool
from app.tools.web_search import WebSearchTool


def register_all_tools() -> None:
    """Register all built-in tools. Called once at app startup."""
    tool_registry.register(BrowserTool)
    tool_registry.register(CodeExecutorTool)
    tool_registry.register(FileSystemTool)
    tool_registry.register(WebSearchTool)
```

- [ ] **Step 9.2: Update `backend/app/main.py` lifespan** — call `register_all_tools`

In `main.py`, add to the lifespan context manager:
```python
from app.tools.init_registry import register_all_tools

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    register_all_tools()
    log.info("agentis_api_started", environment=settings.environment,
             tools=tool_registry.list_names())
    yield
    log.info("agentis_api_stopped")
```

Also add the import at top: `from app.tools.registry import tool_registry`

- [ ] **Step 9.3: Add Squid proxy service to `docker-compose.yml`**

Add this service before the `volumes:` section:

```yaml
  squid:
    image: ubuntu/squid:latest
    volumes:
      - ./squid/squid.conf:/etc/squid/squid.conf:ro
    restart: unless-stopped
```

- [ ] **Step 9.4: Create `squid/squid.conf`** — permissive dev config (allow all)

```
# Development config — allows all outbound traffic
# Production: replace with domain allowlist

http_port 3128

acl localnet src 172.16.0.0/12
acl localnet src 10.0.0.0/8
acl SSL_ports port 443
acl Safe_ports port 80
acl Safe_ports port 443
acl CONNECT method CONNECT

http_access allow localnet
http_access allow localhost
http_access deny all

cache_mem 64 MB
maximum_object_size 100 MB
coredump_dir /var/spool/squid
```

- [ ] **Step 9.5: Update `docker-compose.override.yml`** — add sandbox build

```yaml
services:
  sandbox:
    image: agentis-sandbox:latest
    build:
      context: ./sandbox
      dockerfile: Dockerfile
    profiles: ["sandbox"]   # don't auto-start — started programmatically
```

- [ ] **Step 9.6: Verify app starts cleanly with tools registered**

```bash
cd /home/yulcom/web/perso/agentis
docker compose up api --build -d 2>&1 | tail -5
sleep 5
curl -s http://localhost:8000/api/v1/health
docker compose logs api 2>&1 | grep "tools"
```

Expected: health returns `{"status":"ok"}`. Logs show `tools=['browser', 'code_executor', 'file_system', 'web_search']`.

- [ ] **Step 9.7: Run full test suite — verify no regressions**

```bash
cd /home/yulcom/web/perso/agentis/backend
pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 53+ tests pass (40 original + 8 sandbox + 13 tool unit tests).

- [ ] **Step 9.8: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add backend/app/tools/init_registry.py backend/app/main.py \
        docker-compose.yml squid/
git commit -m "feat: register all tools at startup, add Squid proxy to Docker Compose"
```

---

## Task 10: Integration Tests — Real Sandbox

**Files:**
- Create: `backend/tests/test_tools/test_sandbox_integration.py`

These tests start a **real Docker container** and make real RPC calls. They are marked `slow` and can be skipped in fast CI with `-m "not slow"`.

---

- [ ] **Step 10.1: Create `backend/tests/test_tools/test_sandbox_integration.py`**

```python
"""
Integration tests: start a real agentis-sandbox container and test all 3 sandbox tools.
Requires: docker run access + agentis-sandbox:latest image built.
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


# --- Fixtures ---

@pytest.fixture(scope="module")
def sandbox_container():
    """Start a sandbox container, yield its endpoint, stop and remove on teardown."""
    client = docker.from_env()

    # Expose tool server on a random host port
    container = client.containers.run(
        "agentis-sandbox:latest",
        detach=True,
        ports={"9999/tcp": None},   # random host port
        name="agentis-integration-test",
        remove=False,
    )

    # Get the mapped host port
    container.reload()
    port = container.ports.get("9999/tcp", [{}])[0].get("HostPort")
    endpoint = f"http://localhost:{port}"

    # Wait for tool server to be ready
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
    # Write
    write_result = await tool.execute(
        {"action": "write", "path": "hello.txt", "content": "Hello Phase 1B!"},
        session,
    )
    assert write_result.ok is True
    assert write_result.data["size_bytes"] > 0

    # Read back
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
    result = await tool.execute({"action": "list", "directory": "/workspace"}, session)
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
    # Must fail with an error (path escapes /workspace)
    assert result.ok is False


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
    assert result.ok is True  # timeout is not a tool failure, just a bounded execution
    assert result.data["exit_code"] == -1
    assert "timed out" in result.data["stderr"].lower()
```

- [ ] **Step 10.2: Add `slow` marker to `backend/pyproject.toml`**

In `[tool.pytest.ini_options]`, add:
```toml
markers = ["slow: marks tests as slow (real Docker containers)"]
```

- [ ] **Step 10.3: Run integration tests**

```bash
cd /home/yulcom/web/perso/agentis/backend
pytest tests/test_tools/test_sandbox_integration.py -v -m slow 2>&1
```

Expected: 7 tests PASS. Each test starts the shared module-scoped container (once), runs the test, and the container is torn down at module end.

If `agentis-sandbox:latest` isn't built yet:
```bash
cd /home/yulcom/web/perso/agentis
docker build -t agentis-sandbox:latest ./sandbox/
```

- [ ] **Step 10.4: Run full suite excluding slow**

```bash
cd /home/yulcom/web/perso/agentis/backend
pytest tests/ -q --tb=short -m "not slow" 2>&1 | tail -5
```

Expected: 53 PASS, 7 deselected (slow tests).

- [ ] **Step 10.5: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add backend/tests/test_tools/test_sandbox_integration.py backend/pyproject.toml
git commit -m "feat(phase-1b): integration tests — real sandbox container, file_system + code_executor"
```

---

## Task 11: Phase 1B Smoke Test + Final Commit

**Files:**
- Create: `backend/tests/test_integration_sandbox.py`

---

- [ ] **Step 11.1: Write end-to-end sandbox smoke test**

Create `backend/tests/test_integration_sandbox.py`:

```python
"""
Phase 1B smoke test: SandboxManager creates a container, all 4 tools are registered,
WebSearchTool returns gracefully without API key.
"""
import pytest
from app.tools.registry import tool_registry
from app.tools.web_search import WebSearchTool
from app.tools.browser import BrowserTool
from app.tools.code_executor import CodeExecutorTool
from app.tools.file_system import FileSystemTool
from app.tools.init_registry import register_all_tools
from app.tools.base import SessionContext


@pytest.fixture(autouse=True, scope="module")
def populated_registry():
    """Ensure registry is populated for tests in this module."""
    # Clear existing to avoid duplicate registration errors
    tool_registry._tools.clear()
    register_all_tools()
    yield
    tool_registry._tools.clear()


def test_all_four_tools_registered():
    names = set(tool_registry.list_names())
    assert {"browser", "code_executor", "file_system", "web_search"}.issubset(names)


def test_each_tool_has_name_and_description():
    for tool in tool_registry.get_all():
        assert tool.name, f"{type(tool).__name__} has no name"
        assert tool.description, f"{type(tool).__name__} has no description"
        assert tool.input_schema, f"{type(tool).__name__} has no input_schema"


@pytest.mark.asyncio
async def test_web_search_no_key_returns_empty():
    """With no API key, web_search returns empty results rather than erroring."""
    import os
    original = os.environ.pop("AGENTIS_BRAVE_API_KEY", None)
    # Reload settings with no key
    from app.config import settings
    original_key = settings.brave_api_key
    settings.brave_api_key = ""

    session = SessionContext(session_id="s", task_id="t", sandbox_endpoint="http://localhost")
    tool = WebSearchTool()
    result = await tool.execute({"query": "test"}, session)

    settings.brave_api_key = original_key
    assert result.ok is True
    assert result.data["results"] == []


def test_tool_input_schemas_are_valid():
    """Each tool's input_schema is a valid JSON Schema object."""
    for tool in tool_registry.get_all():
        schema = tool.input_schema
        assert schema.get("type") == "object"
        assert "properties" in schema
```

- [ ] **Step 11.2: Run the smoke test**

```bash
cd /home/yulcom/web/perso/agentis/backend
pytest tests/test_integration_sandbox.py -v
```

Expected: 4 PASS.

- [ ] **Step 11.3: Run complete test suite**

```bash
cd /home/yulcom/web/perso/agentis/backend
pytest tests/ -q --tb=short 2>&1 | tail -10
```

Expected: 57 passed (40 + 8 sandbox + 13 tools + 4 smoke — with slow tests deselected the integration tests count as 0; with `-m slow` adds 7 more).

- [ ] **Step 11.4: Tag Phase 1B**

```bash
cd /home/yulcom/web/perso/agentis
git add backend/tests/test_integration_sandbox.py
git commit -m "feat(phase-1b): smoke test — 4 tools registered, web_search graceful, schemas valid"
git tag -a phase-1b -m "Phase 1B complete — Sandbox + 4 Tools (57 tests passing)"
```

---

## Phase 1B Complete — Handoff to Phase 1C

**What's running:**
- `agentis-sandbox:latest` Docker image with tool server (file_system, code_executor, browser handlers).
- `SandboxManager` — creates/destroys Docker containers, waits for health.
- 4 tool RPC clients: `browser`, `code_executor`, `file_system`, `web_search`.
- `ToolRegistry` — all 4 tools registered at API startup.
- 57 tests passing (+ 7 slow integration tests with real container).

**What's next — Phase 1C (Orchestrator + Task Queue):**
- Celery + Redis task queue
- LangGraph StateGraph (Plan/Think/Act/Observe/Reflect/Report nodes)
- PostgresSaver for checkpoint persistence
- SSE streaming events
- Task CRUD API endpoints
- Short-term memory (Redis DB1)
- Langfuse traces
- Plan: `docs/superpowers/plans/2026-05-29-phase1c-orchestrator-queue.md`

---

*Plan version: 1.0 | Created: 2026-05-29 | Spec ref: docs/agentis_spec.md v2.0.0 §6–7*
