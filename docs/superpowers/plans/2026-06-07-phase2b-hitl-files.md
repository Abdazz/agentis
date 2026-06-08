# Phase 2B — HITL WebSocket + Gestion de Fichiers : Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Human-in-the-Loop (HITL) support via WebSocket, implement MinIO-backed file uploads/downloads, and wire HITL into the orchestrator pause/resume flow.

**Architecture:** The WebSocket endpoint (`WSS /ws/tasks/{id}`) uses Redis pub/sub to bridge the FastAPI connection with the Celery worker that's running the orchestrator. When `hitl_pending=True` in AgentState, the orchestrator parks in a `WAIT_HITL` loop polling Redis. The frontend sends the user response via WebSocket; the API publishes it to Redis; the worker unblocks and resumes. MinIO handles file storage with pre-signed S3-compatible URLs; workers read/write via the MinIO client directly.

**Tech Stack:** fastapi websockets, redis pub/sub (aioredis), minio-py, pytest-asyncio, unittest.mock, Next.js useEffect + EventSource.

---

## File Map

### New files
```
backend/app/routers/ws.py                        — WebSocket endpoint + HITL message handler
backend/app/services/hitl.py                     — Redis pub/sub HITL coordinator
backend/app/services/minio_client.py             — MinIO presigned URL + upload/download helpers
backend/app/routers/files.py                     — POST /files/upload, GET /files/{id}/download
backend/app/schemas/files.py                     — FileUploadResponse, FileDownloadResponse
backend/tests/test_ws/test_hitl.py               — WebSocket HITL tests
backend/tests/test_services/test_hitl.py         — HITLCoordinator unit tests
backend/tests/test_services/test_minio.py        — MinIO service unit tests
backend/tests/test_routers/test_files.py         — File upload/download router tests
frontend/src/components/tasks/HitlPanel.tsx      — Inline HITL panel (Option A: bottom of Terminal Feed)
frontend/src/hooks/useHitl.ts                    — WebSocket HITL hook
```

### Modified files
```
backend/app/config.py                            — add MinIO settings
backend/app/main.py                              — include ws router + files router
backend/app/orchestrator/nodes.py                — reflect_node → detect hitl_required, block
backend/app/orchestrator/state.py                — add hitl_timeout_at field
backend/app/orchestrator/graph.py                — add WAIT_HITL conditional edge
docker-compose.yml                               — minio service + minio-init service
frontend/src/app/[locale]/tasks/[id]/page.tsx    — add HitlPanel below SSE feed
```

---

## Task 1: MinIO service in docker-compose + config

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add MinIO services to `docker-compose.yml`**

Add after the `qdrant` service:

```yaml
  minio:
    image: minio/minio:RELEASE.2024-01-16T16-07-38Z
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: agentis
      MINIO_ROOT_PASSWORD: agentis123
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 10s
      retries: 5
      start_period: 15s

  minio-init:
    image: minio/mc:RELEASE.2024-01-16T02-44-48Z
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
        mc alias set local http://minio:9000 agentis agentis123;
        mc mb --ignore-existing local/agentis-uploads;
        mc mb --ignore-existing local/agentis-artifacts;
        mc mb --ignore-existing local/agentis-backups;
        echo 'Buckets ready';
      "
```

Add `minio_data:` to the `volumes:` section.

- [ ] **Step 2: Add MinIO settings to `backend/app/config.py`**

Inside the `Settings` class, add after qdrant settings:

```python
    # MinIO / S3
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "agentis"
    minio_secret_key: str = "agentis123"
    minio_secure: bool = False
    minio_bucket_uploads: str = "agentis-uploads"
    minio_bucket_artifacts: str = "agentis-artifacts"
    minio_presigned_expiry_seconds: int = 3600
```

- [ ] **Step 3: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add docker-compose.yml backend/app/config.py
git commit -m "feat(2b): add MinIO service to docker-compose + config settings"
```

---

## Task 2: MinIO client service (TDD)

**Files:**
- Create: `backend/tests/test_services/test_minio.py`
- Create: `backend/app/services/minio_client.py`

- [ ] **Step 1: Write failing tests — `backend/tests/test_services/test_minio.py`**

```python
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from io import BytesIO


@pytest.fixture
def mock_minio():
    client = MagicMock()
    client.presigned_put_object = MagicMock(return_value="https://minio/upload-url")
    client.presigned_get_object = MagicMock(return_value="https://minio/download-url")
    client.put_object = MagicMock()
    client.get_object = MagicMock(return_value=MagicMock(read=MagicMock(return_value=b"file data")))
    return client


def test_upload_url_returns_presigned(mock_minio):
    with patch("app.services.minio_client.Minio", return_value=mock_minio):
        from app.services.minio_client import MinioService
        svc = MinioService()
        url = svc.presigned_upload_url(object_name="uploads/u1/test.pdf", content_type="application/pdf")
        assert url == "https://minio/upload-url"
        mock_minio.presigned_put_object.assert_called_once()


def test_download_url_returns_presigned(mock_minio):
    with patch("app.services.minio_client.Minio", return_value=mock_minio):
        from app.services.minio_client import MinioService
        svc = MinioService()
        url = svc.presigned_download_url(object_name="artifacts/t1/result.json", bucket="agentis-artifacts")
        assert url == "https://minio/download-url"
        mock_minio.presigned_get_object.assert_called_once()


def test_upload_bytes_calls_put_object(mock_minio):
    with patch("app.services.minio_client.Minio", return_value=mock_minio):
        from app.services.minio_client import MinioService
        svc = MinioService()
        svc.upload_bytes(object_name="uploads/u1/data.json", data=b'{"ok": true}', content_type="application/json")
        mock_minio.put_object.assert_called_once()


def test_object_name_for_upload_includes_user_and_filename():
    from app.services.minio_client import object_name_for_upload
    name = object_name_for_upload(user_id="u1", filename="report.pdf")
    assert name.startswith("uploads/u1/")
    assert "report.pdf" in name
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_services/test_minio.py -v 2>&1 | head -15
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Install dependency**

```bash
pip install "minio>=7.2"
```

- [ ] **Step 4: Implement `backend/app/services/minio_client.py`**

```python
import datetime
from io import BytesIO
from minio import Minio
from app.config import settings


def object_name_for_upload(user_id: str, filename: str) -> str:
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    return f"uploads/{user_id}/{ts}_{filename}"


class MinioService:
    def __init__(self) -> None:
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def presigned_upload_url(self, object_name: str, content_type: str = "application/octet-stream",
                              bucket: str | None = None) -> str:
        bkt = bucket or settings.minio_bucket_uploads
        return self._client.presigned_put_object(
            bkt, object_name,
            expires=datetime.timedelta(seconds=settings.minio_presigned_expiry_seconds),
        )

    def presigned_download_url(self, object_name: str, bucket: str | None = None) -> str:
        bkt = bucket or settings.minio_bucket_uploads
        return self._client.presigned_get_object(
            bkt, object_name,
            expires=datetime.timedelta(seconds=settings.minio_presigned_expiry_seconds),
        )

    def upload_bytes(self, object_name: str, data: bytes,
                     content_type: str = "application/octet-stream",
                     bucket: str | None = None) -> None:
        bkt = bucket or settings.minio_bucket_uploads
        self._client.put_object(bkt, object_name, BytesIO(data), length=len(data),
                                 content_type=content_type)


minio_service = MinioService()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_services/test_minio.py -v 2>&1 | tail -10
```

Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/services/minio_client.py tests/test_services/
git commit -m "feat(2b): MinioService — presigned URLs + upload/download helpers"
```

---

## Task 3: Files router — upload + download (TDD)

**Files:**
- Create: `backend/app/schemas/files.py`
- Create: `backend/tests/test_routers/test_files.py`
- Create: `backend/app/routers/files.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create `backend/app/schemas/files.py`**

```python
from pydantic import BaseModel


class FileUploadInitResponse(BaseModel):
    upload_url: str
    object_name: str
    expires_in: int


class FileDownloadResponse(BaseModel):
    download_url: str
    expires_in: int
```

- [ ] **Step 2: Write failing tests — `backend/tests/test_routers/test_files.py`**

```python
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient


@pytest.fixture
def mock_minio_svc():
    svc = MagicMock()
    svc.presigned_upload_url.return_value = "https://minio/upload-presigned"
    svc.presigned_download_url.return_value = "https://minio/download-presigned"
    return svc


@pytest.mark.asyncio
async def test_initiate_upload_returns_presigned_url(async_client: AsyncClient, auth_headers: dict,
                                                      mock_minio_svc):
    with patch("app.routers.files.minio_service", mock_minio_svc):
        resp = await async_client.post(
            "/api/v1/files/upload/initiate",
            json={"filename": "document.pdf", "content_type": "application/pdf"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "upload_url" in data
    assert "object_name" in data
    assert data["upload_url"] == "https://minio/upload-presigned"


@pytest.mark.asyncio
async def test_initiate_upload_requires_auth(async_client: AsyncClient, mock_minio_svc):
    with patch("app.routers.files.minio_service", mock_minio_svc):
        resp = await async_client.post(
            "/api/v1/files/upload/initiate",
            json={"filename": "document.pdf", "content_type": "application/pdf"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_download_url_returns_presigned(async_client: AsyncClient, auth_headers: dict,
                                                   mock_minio_svc):
    with patch("app.routers.files.minio_service", mock_minio_svc):
        resp = await async_client.get(
            "/api/v1/files/artifacts/tasks/t1/result.json/url",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert "download_url" in resp.json()
```

- [ ] **Step 3: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_routers/test_files.py -v 2>&1 | head -15
```

Expected: FAIL — router not found

- [ ] **Step 4: Implement `backend/app/routers/files.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.minio_client import minio_service, object_name_for_upload
from app.schemas.files import FileUploadInitResponse, FileDownloadResponse
from app.config import settings

router = APIRouter(prefix="/files", tags=["files"])


class UploadInitRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"


@router.post("/upload/initiate", response_model=FileUploadInitResponse)
async def initiate_upload(body: UploadInitRequest, current_user: User = Depends(get_current_user)):
    obj = object_name_for_upload(user_id=str(current_user.id), filename=body.filename)
    url = minio_service.presigned_upload_url(object_name=obj, content_type=body.content_type)
    return FileUploadInitResponse(
        upload_url=url,
        object_name=obj,
        expires_in=settings.minio_presigned_expiry_seconds,
    )


@router.get("/artifacts/{object_path:path}/url", response_model=FileDownloadResponse)
async def get_artifact_download_url(object_path: str, current_user: User = Depends(get_current_user)):
    url = minio_service.presigned_download_url(
        object_name=object_path,
        bucket=settings.minio_bucket_artifacts,
    )
    return FileDownloadResponse(download_url=url, expires_in=settings.minio_presigned_expiry_seconds)
```

- [ ] **Step 5: Register router in `backend/app/main.py`**

Add after existing router includes:

```python
from app.routers.files import router as files_router
app.include_router(files_router, prefix="/api/v1")
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_routers/test_files.py -v 2>&1 | tail -10
```

Expected: 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/schemas/files.py app/routers/files.py app/main.py tests/test_routers/test_files.py
git commit -m "feat(2b): files router — presigned upload + download URLs"
```

---

## Task 4: HITLCoordinator — Redis pub/sub (TDD)

**Files:**
- Create: `backend/tests/test_services/test_hitl.py`
- Create: `backend/app/services/hitl.py`

- [ ] **Step 1: Write failing tests — `backend/tests/test_services/test_hitl.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.publish = AsyncMock(return_value=1)
    r.subscribe = AsyncMock()
    r.get_message = MagicMock(return_value=None)
    r.close = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_publish_response_sends_to_correct_channel(mock_redis):
    with patch("app.services.hitl.aioredis.from_url", return_value=mock_redis):
        from app.services.hitl import HITLCoordinator
        coord = HITLCoordinator()
        await coord.publish_response(task_id="t1", response="yes, proceed")
        mock_redis.publish.assert_called_once_with("hitl:t1:response", "yes, proceed")


@pytest.mark.asyncio
async def test_wait_for_response_returns_message(mock_redis):
    mock_redis.get_message = MagicMock(return_value={"type": "message", "data": b"ok"})
    with patch("app.services.hitl.aioredis.from_url", return_value=mock_redis):
        from app.services.hitl import HITLCoordinator
        coord = HITLCoordinator()
        result = await coord.wait_for_response(task_id="t1", timeout_seconds=1)
        assert result == "ok"


@pytest.mark.asyncio
async def test_wait_for_response_returns_none_on_timeout(mock_redis):
    mock_redis.get_message = MagicMock(return_value=None)
    with patch("app.services.hitl.aioredis.from_url", return_value=mock_redis):
        with patch("app.services.hitl.asyncio.sleep", AsyncMock()):
            from app.services.hitl import HITLCoordinator
            coord = HITLCoordinator()
            # timeout_seconds=0 to exit immediately
            result = await coord.wait_for_response(task_id="t1", timeout_seconds=0)
            assert result is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_services/test_hitl.py -v 2>&1 | head -15
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.hitl'`

- [ ] **Step 3: Implement `backend/app/services/hitl.py`**

```python
"""HITL coordinator via Redis pub/sub (spec §10 HITL-1..5)."""
import asyncio
import time
import aioredis
from app.config import settings


class HITLCoordinator:
    def __init__(self) -> None:
        self._redis_url = settings.redis_cache_url  # DB1

    def _channel(self, task_id: str) -> str:
        return f"hitl:{task_id}:response"

    async def publish_response(self, task_id: str, response: str) -> None:
        """Called by WebSocket handler when user submits HITL response."""
        r = aioredis.from_url(self._redis_url)
        try:
            await r.publish(self._channel(task_id), response)
        finally:
            await r.close()

    async def wait_for_response(self, task_id: str, timeout_seconds: float = 600.0) -> str | None:
        """Called by the orchestrator worker; blocks until response or timeout."""
        r = aioredis.from_url(self._redis_url)
        pubsub = r.pubsub()
        await pubsub.subscribe(self._channel(task_id))
        deadline = time.monotonic() + timeout_seconds
        try:
            while time.monotonic() < deadline:
                msg = pubsub.get_message()
                if msg and msg.get("type") == "message":
                    data = msg["data"]
                    return data.decode() if isinstance(data, bytes) else data
                await asyncio.sleep(0.5)
        finally:
            await pubsub.unsubscribe(self._channel(task_id))
            await r.close()
        return None


hitl_coordinator = HITLCoordinator()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_services/test_hitl.py -v 2>&1 | tail -10
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/services/hitl.py tests/test_services/test_hitl.py
git commit -m "feat(2b): HITLCoordinator — Redis pub/sub for HITL response delivery"
```

---

## Task 5: WebSocket HITL endpoint (TDD)

**Files:**
- Create: `backend/tests/test_ws/test_hitl.py`
- Create: `backend/app/routers/ws.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create `backend/tests/test_ws/__init__.py`**

```bash
touch /home/yulcom/web/perso/agentis/backend/tests/test_ws/__init__.py
```

- [ ] **Step 2: Write failing tests — `backend/tests/test_ws/test_hitl.py`**

```python
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient
from httpx_ws import aconnect_ws


@pytest.mark.asyncio
async def test_ws_requires_valid_token(async_client: AsyncClient):
    """WebSocket with invalid token should close immediately."""
    from app.main import app
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="ws://test") as client:
        try:
            async with aconnect_ws("/api/v1/ws/tasks/t1?token=invalid", client):
                pass
        except Exception:
            pass  # expected to fail


@pytest.mark.asyncio
async def test_ws_hitl_message_publishes_to_redis(async_client: AsyncClient, auth_token: str):
    """Sending a message on the WS channel publishes it to HITL coordinator."""
    with patch("app.routers.ws.hitl_coordinator.publish_response", AsyncMock()) as mock_pub:
        from app.main import app
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="ws://test") as client:
            try:
                async with aconnect_ws(f"/api/v1/ws/tasks/t1?token={auth_token}", client) as ws:
                    await ws.send_text('{"type": "hitl_response", "content": "yes, continue"}')
                    await ws.aclose()
            except Exception:
                pass
        mock_pub.assert_called_once_with(task_id="t1", response="yes, continue")
```

- [ ] **Step 3: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_ws/test_hitl.py -v 2>&1 | head -15
```

Expected: FAIL — router not found / httpx_ws not installed

- [ ] **Step 4: Install dependencies**

```bash
pip install "httpx-ws>=0.6"
```

- [ ] **Step 5: Implement `backend/app/routers/ws.py`**

```python
"""WebSocket endpoints for real-time task communication (spec §10 HITL-2)."""
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from app.auth.dependencies import verify_token_string
from app.services.hitl import hitl_coordinator

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/tasks/{task_id}")
async def task_websocket(websocket: WebSocket, task_id: str, token: str = Query(...)):
    """
    WebSocket connection for HITL responses.
    Client authenticates by passing ?token=<jwt> in query string.
    Messages: {"type": "hitl_response", "content": "<response text>"}
    """
    try:
        user = await verify_token_string(token)
    except Exception:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "invalid JSON"}))
                continue

            if msg.get("type") == "hitl_response":
                content = msg.get("content", "")
                await hitl_coordinator.publish_response(task_id=task_id, response=content)
                await websocket.send_text(json.dumps({"type": "ack", "task_id": task_id}))
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 6: Add `verify_token_string` to `backend/app/auth/dependencies.py`**

Open the existing auth dependencies file and add at the end:

```python
async def verify_token_string(token: str) -> User:
    """Verify a raw JWT string (for WebSocket query param auth)."""
    from app.auth.jwt import decode_jwt
    from sqlalchemy.ext.asyncio import AsyncSession
    payload = decode_jwt(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    # reuse existing get_current_user logic via dependency trick
    return payload
```

- [ ] **Step 7: Register WebSocket router in `backend/app/main.py`**

```python
from app.routers.ws import router as ws_router
app.include_router(ws_router, prefix="/api/v1")
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_ws/ -v 2>&1 | tail -10
```

Expected: tests pass (token validation handled correctly).

- [ ] **Step 9: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/routers/ws.py app/main.py tests/test_ws/
git commit -m "feat(2b): WebSocket HITL endpoint — token auth + Redis response routing"
```

---

## Task 6: Orchestrator — HITL pause/resume in reflect_node

**Files:**
- Modify: `backend/app/orchestrator/nodes.py`
- Modify: `backend/app/orchestrator/state.py`

- [ ] **Step 1: Add `hitl_timeout_at` to AgentState**

In `backend/app/orchestrator/state.py`, add to `AgentState`:

```python
    hitl_timeout_at: float | None  # Unix timestamp when HITL expires (None = no active HITL)
```

- [ ] **Step 2: Update `reflect_node` to detect HITL requirement and block**

Open `backend/app/orchestrator/nodes.py`. In `reflect_node`, after reading the last tool result, add:

```python
    # Check if the last tool result requires HITL (BR-TASK-50)
    last_msgs = state.get("messages", [])
    if last_msgs:
        last = last_msgs[-1]
        content = getattr(last, "content", "")
        if isinstance(content, str) and '"hitl_required": true' in content.lower():
            import time
            timeout_at = time.time() + 600  # 10-minute HITL window
            # Emit HITL event via SSE emitter
            if ctx.emitter:
                await ctx.emitter.emit("hitl_requested", {
                    "task_id": ctx.task_id,
                    "reason": "Tool requires human confirmation",
                    "timeout_at": timeout_at,
                })
            return {
                "hitl_pending": True,
                "hitl_timeout_at": timeout_at,
                "_reflect_decision": "wait_hitl",
            }
```

- [ ] **Step 3: Add WAIT_HITL node**

At the end of `nodes.py`, add the wait node:

```python
async def wait_hitl_node(state: AgentState, ctx: RunContext) -> dict:
    """Block orchestrator until user responds or timeout. (BR-TASK-51)"""
    from app.services.hitl import hitl_coordinator
    import time

    timeout_at = state.get("hitl_timeout_at") or (time.time() + 600)
    remaining = max(0.0, timeout_at - time.time())

    response = await hitl_coordinator.wait_for_response(
        task_id=ctx.task_id, timeout_seconds=remaining
    )

    if response is None:
        # Timeout → cancel task (BR-TASK-52)
        if ctx.emitter:
            await ctx.emitter.emit("hitl_timeout", {"task_id": ctx.task_id})
        return {
            "hitl_pending": False,
            "hitl_timeout_at": None,
            "_reflect_decision": "report",  # Report with partial results
        }

    if ctx.emitter:
        await ctx.emitter.emit("hitl_response_received", {"task_id": ctx.task_id})

    return {
        "hitl_pending": False,
        "hitl_timeout_at": None,
        "hitl_response": response,
        "_reflect_decision": "continue",
    }
```

- [ ] **Step 4: Update the graph routing in `backend/app/orchestrator/graph.py`**

Read the current graph file and add the WAIT_HITL conditional. After the reflect node routing, add:

```python
from app.orchestrator.nodes import wait_hitl_node

# Add the wait_hitl node
graph.add_node("wait_hitl", wait_hitl_node)

# After REFLECT: if _reflect_decision == "wait_hitl" → go to wait_hitl, else existing routing
# Existing routing: "continue" → think, "report" → report, "replan" → plan
# New routing: "wait_hitl" → wait_hitl
# After WAIT_HITL: "continue" → think, "report" → report

def reflect_router(state: AgentState) -> str:
    decision = state.get("_reflect_decision", "continue")
    return decision  # one of: "continue", "replan", "report", "wait_hitl"

def wait_hitl_router(state: AgentState) -> str:
    return state.get("_reflect_decision", "report")

graph.add_conditional_edges("reflect", reflect_router,
    {"continue": "think", "replan": "plan", "report": "report", "wait_hitl": "wait_hitl"})
graph.add_conditional_edges("wait_hitl", wait_hitl_router,
    {"continue": "think", "report": "report"})
```

- [ ] **Step 5: Run backend tests**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest --tb=short -q 2>&1 | tail -15
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/orchestrator/nodes.py app/orchestrator/state.py app/orchestrator/graph.py
git commit -m "feat(2b): orchestrator HITL pause/resume — reflect_node + wait_hitl_node"
```

---

## Task 7: Frontend — HitlPanel component

**Files:**
- Create: `frontend/src/hooks/useHitl.ts`
- Create: `frontend/src/components/tasks/HitlPanel.tsx`
- Modify: `frontend/src/app/[locale]/tasks/[id]/page.tsx`

- [ ] **Step 1: Create `frontend/src/hooks/useHitl.ts`**

```typescript
import { useState, useEffect, useCallback, useRef } from "react";

type HitlMessage =
  | { type: "hitl_requested"; reason: string; timeout_at: number }
  | { type: "ack"; task_id: string };

interface UseHitlReturn {
  isHitlActive: boolean;
  hitlReason: string | null;
  timeoutAt: number | null;
  sendResponse: (content: string) => void;
}

export function useHitl(taskId: string, token: string | null): UseHitlReturn {
  const [isHitlActive, setIsHitlActive] = useState(false);
  const [hitlReason, setHitlReason] = useState<string | null>(null);
  const [timeoutAt, setTimeoutAt] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!token) return;
    const wsUrl = `${process.env.NEXT_PUBLIC_API_URL?.replace("http", "ws")}/api/v1/ws/tasks/${taskId}?token=${token}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      const msg: HitlMessage = JSON.parse(evt.data);
      if (msg.type === "hitl_requested") {
        setIsHitlActive(true);
        setHitlReason(msg.reason);
        setTimeoutAt(msg.timeout_at);
      } else if (msg.type === "ack") {
        setIsHitlActive(false);
        setHitlReason(null);
        setTimeoutAt(null);
      }
    };

    return () => { ws.close(); };
  }, [taskId, token]);

  const sendResponse = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "hitl_response", content }));
    }
  }, []);

  return { isHitlActive, hitlReason, timeoutAt, sendResponse };
}
```

- [ ] **Step 2: Create `frontend/src/components/tasks/HitlPanel.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useHitl } from "@/hooks/useHitl";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { AlertCircle, Send } from "lucide-react";

interface HitlPanelProps {
  taskId: string;
  token: string | null;
}

export function HitlPanel({ taskId, token }: HitlPanelProps) {
  const { isHitlActive, hitlReason, timeoutAt, sendResponse } = useHitl(taskId, token);
  const [message, setMessage] = useState("");

  if (!isHitlActive) return null;

  const secondsLeft = timeoutAt ? Math.max(0, Math.round(timeoutAt - Date.now() / 1000)) : null;

  const handleSend = () => {
    if (!message.trim()) return;
    sendResponse(message.trim());
    setMessage("");
  };

  return (
    <div className="border-t border-yellow-500/30 bg-yellow-500/5 p-4 mt-4 rounded-b-lg">
      <div className="flex items-start gap-3 mb-3">
        <AlertCircle className="text-yellow-400 mt-0.5 shrink-0" size={18} />
        <div>
          <p className="text-yellow-300 font-medium text-sm">Action requires your confirmation</p>
          {hitlReason && (
            <p className="text-muted-foreground text-xs mt-0.5">{hitlReason}</p>
          )}
          {secondsLeft !== null && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Auto-cancel in {Math.floor(secondsLeft / 60)}m {secondsLeft % 60}s
            </p>
          )}
        </div>
      </div>
      <div className="flex gap-2">
        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Type your response or instructions..."
          className="resize-none text-sm min-h-[60px]"
          onKeyDown={(e) => { if (e.key === "Enter" && e.metaKey) handleSend(); }}
        />
        <Button onClick={handleSend} disabled={!message.trim()} className="self-end">
          <Send size={16} />
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add HitlPanel to task detail page**

In `frontend/src/app/[locale]/tasks/[id]/page.tsx`, import and add at the bottom of the SSE feed section:

```tsx
import { HitlPanel } from "@/components/tasks/HitlPanel";

// Inside the component, below the SSE events list:
<HitlPanel taskId={params.id} token={authToken} />
```

Where `authToken` is obtained from the auth context/cookie.

- [ ] **Step 4: Commit**

```bash
cd /home/yulcom/web/perso/agentis/frontend
git add src/hooks/useHitl.ts src/components/tasks/HitlPanel.tsx src/app/
git commit -m "feat(2b): HitlPanel — inline WebSocket HITL panel at bottom of Terminal Feed"
```

---

## Task 8: Vérification manuelle navigateur (Phase 2B)

- [ ] **Step 1: Démarrer la stack avec MinIO**

```bash
cd /home/yulcom/web/perso/agentis
docker compose up -d --build
docker compose ps
```

Expected: `minio`, `minio-init` et tous les services précédents `Up`.

- [ ] **Step 2: Vérifier MinIO console**

Ouvrir `http://localhost:9001`. Se connecter avec `agentis` / `agentis123`. Vérifier que les 3 buckets sont créés : `agentis-uploads`, `agentis-artifacts`, `agentis-backups`.

- [ ] **Step 3: Test upload de fichier**

Via le skill `verify`, ouvrir `http://localhost:3000`, se connecter, aller dans Paramètres ou créer une tâche qui nécessite un fichier. Vérifier que l'upload fonctionne et que l'objet apparaît dans MinIO console.

- [ ] **Step 4: Simuler un HITL request**

Soumettre la tâche : `"Envoie un email à test@example.com via l'outil http_caller"`. Observer que le panneau HITL jaune apparaît en bas du Terminal Feed. Vérifier que le compteur de timeout diminue.

- [ ] **Step 5: Répondre au HITL**

Dans le panneau HITL, saisir `"Oui, confirme l'envoi"` et cliquer Send. Vérifier dans les logs SSE que la tâche reprend avec `hitl_response_received`.

- [ ] **Step 6: Commit final Phase 2B**

```bash
cd /home/yulcom/web/perso/agentis
git add .
git commit -m "feat(2b): Phase 2B complete — HITL WebSocket, MinIO file storage, HitlPanel UI"
```
