# Phase 2A — Outils + Mémoire long-terme : Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `doc_parser` and `http_caller` tools to the orchestrator, implement Qdrant-backed long-term memory with Voyage AI embeddings, and activate Celery Beat for memory maintenance jobs.

**Architecture:** New tools follow the existing `BaseTool` / `SandboxRpcClient` pattern. Long-term memory lives in `app/memory/long_term.py` — Qdrant stores vectors, PostgreSQL `memory_entries` stores refs. The REFLECT node extracts memories after each task; the PLAN node injects top-5 relevant memories into context. Beat jobs run `decay` and `prune` every 24h.

**Tech Stack:** qdrant-client, voyageai, httpx (sandbox rpc), Celery Beat, Alembic, pytest-asyncio, unittest.mock.

---

## File Map

### New files
```
backend/app/tools/doc_parser.py
backend/app/tools/http_caller.py
backend/app/memory/long_term.py
backend/app/models/memory.py
backend/app/worker/beat_jobs.py
backend/tests/test_tools/test_doc_parser.py
backend/tests/test_tools/test_http_caller.py
backend/tests/test_memory/test_long_term.py
backend/tests/test_worker/test_beat_jobs.py
backend/alembic/versions/<hash>_add_memory_entries.py
```

### Modified files
```
backend/app/config.py                    — add Qdrant + Voyage AI settings
backend/app/tools/init_registry.py      — register DocParserTool + HttpCallerTool
backend/app/worker/celery_app.py         — add beat_schedule
backend/app/orchestrator/nodes.py        — update plan_node + report_node for long-term memory
backend/app/orchestrator/state.py        — add long_term_memory_block field
docker-compose.yml                       — add qdrant service
```

---

## Task 1: Add Qdrant to docker-compose + config

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add Qdrant service to `docker-compose.yml`**

Add after the `redis` service and before `langfuse`:

```yaml
  qdrant:
    image: qdrant/qdrant:v1.9.2
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:6333/readyz || exit 1"]
      interval: 10s
      retries: 5
      start_period: 15s
```

Also add `qdrant_data:` to the `volumes:` section at the bottom.

- [ ] **Step 2: Add Qdrant + Voyage AI settings to `backend/app/config.py`**

Inside the `Settings` class, add after the `# Observability` block:

```python
    # Qdrant (long-term memory)
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "agentis_memory"

    # Voyage AI (embeddings)
    voyage_api_key: str = ""
    voyage_model: str = "voyage-multilingual-2"
    voyage_embedding_dim: int = 1024

    # HTTP Caller (safe domains — comma-separated, no spaces)
    http_caller_safe_domains: str = ""

    @property
    def http_caller_safe_domain_set(self) -> set[str]:
        if not self.http_caller_safe_domains:
            return set()
        return {d.strip() for d in self.http_caller_safe_domains.split(",") if d.strip()}
```

- [ ] **Step 3: Commit**

```bash
cd /home/yulcom/web/perso/agentis
git add docker-compose.yml backend/app/config.py
git commit -m "feat(2a): add Qdrant service + config settings"
```

---

## Task 2: MemoryEntry model + Alembic migration

**Files:**
- Create: `backend/app/models/memory.py`
- Create: `backend/alembic/versions/<hash>_add_memory_entries.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create `backend/app/models/memory.py`**

```python
from uuid import uuid4, UUID
from datetime import datetime
from sqlalchemy import String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class MemoryEntry(Base):
    """PostgreSQL reference record for a Qdrant memory point (spec §8.3 MEM-3)."""
    __tablename__ = "memory_entries"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    qdrant_point_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
```

- [ ] **Step 2: Register in `backend/app/models/__init__.py`**

Check what's currently in `__init__.py` and add:

```python
from app.models.memory import MemoryEntry  # noqa: F401
```

- [ ] **Step 3: Generate Alembic migration**

```bash
cd /home/yulcom/web/perso/agentis/backend
alembic revision --autogenerate -m "add_memory_entries"
```

Verify the generated file in `alembic/versions/` creates table `memory_entries` with all columns. If autogenerate fails (DB not running), write the migration manually:

```python
"""add_memory_entries

Revision ID: <generated>
Revises: 8fca78cf1516
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '<generated>'
down_revision = '8fca78cf1516'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'memory_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tasks.id', ondelete='SET NULL'), nullable=True),
        sa.Column('qdrant_point_id', sa.String(64), nullable=False, unique=True),
        sa.Column('importance', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('accessed_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_memory_entries_user_id', 'memory_entries', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_memory_entries_user_id', 'memory_entries')
    op.drop_table('memory_entries')
```

- [ ] **Step 4: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/models/memory.py app/models/__init__.py alembic/versions/
git commit -m "feat(2a): MemoryEntry model + Alembic migration"
```

---

## Task 3: `app/memory/long_term.py` — Qdrant + Voyage AI (TDD)

**Files:**
- Create: `backend/tests/test_memory/test_long_term.py`
- Create: `backend/app/memory/long_term.py`

- [ ] **Step 1: Create `backend/tests/test_memory/__init__.py`**

```bash
touch /home/yulcom/web/perso/agentis/backend/tests/test_memory/__init__.py
```

- [ ] **Step 2: Write failing tests — `backend/tests/test_memory/test_long_term.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


@pytest.fixture
def mock_qdrant():
    client = MagicMock()
    client.collection_exists = MagicMock(return_value=False)
    client.create_collection = MagicMock()
    client.upsert = MagicMock()
    client.search = MagicMock(return_value=[])
    client.delete = MagicMock()
    client.scroll = MagicMock(return_value=([], None))
    return client


@pytest.fixture
def mock_voyage():
    with patch("app.memory.long_term.voyageai") as m:
        client = MagicMock()
        client.embed = MagicMock(return_value=MagicMock(embeddings=[[0.1] * 1024]))
        m.Client.return_value = client
        yield m


def test_init_creates_collection_if_missing(mock_qdrant, mock_voyage, monkeypatch):
    monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
    with patch("app.memory.long_term.QdrantClient", return_value=mock_qdrant):
        from app.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        ltm.ensure_collection()
        mock_qdrant.create_collection.assert_called_once()


def test_init_skips_creation_if_collection_exists(mock_qdrant, mock_voyage, monkeypatch):
    mock_qdrant.collection_exists.return_value = True
    monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
    with patch("app.memory.long_term.QdrantClient", return_value=mock_qdrant):
        from app.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        ltm.ensure_collection()
        mock_qdrant.create_collection.assert_not_called()


@pytest.mark.asyncio
async def test_store_memory_upserts_to_qdrant(mock_qdrant, mock_voyage, monkeypatch):
    monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
    with patch("app.memory.long_term.QdrantClient", return_value=mock_qdrant):
        from app.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        user_id = str(uuid4())
        task_id = str(uuid4())
        point_id = await ltm.store(
            user_id=user_id,
            task_id=task_id,
            content="The user prefers concise answers.",
            summary="User communication style preference",
            tags=["preference"],
            language="fr",
        )
        assert point_id is not None
        mock_qdrant.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_search_returns_empty_list_on_no_results(mock_qdrant, mock_voyage, monkeypatch):
    monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
    mock_qdrant.search.return_value = []
    with patch("app.memory.long_term.QdrantClient", return_value=mock_qdrant):
        from app.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        results = await ltm.search(user_id=str(uuid4()), query="user preferences", top_k=5)
        assert results == []


@pytest.mark.asyncio
async def test_search_filters_by_user_id(mock_qdrant, mock_voyage, monkeypatch):
    monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
    mock_result = MagicMock()
    mock_result.payload = {"content": "User likes Python", "user_id": "u1", "summary": ""}
    mock_result.score = 0.95
    mock_qdrant.search.return_value = [mock_result]
    with patch("app.memory.long_term.QdrantClient", return_value=mock_qdrant):
        from app.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        results = await ltm.search(user_id="u1", query="Python", top_k=5)
        assert len(results) == 1
        assert results[0]["content"] == "User likes Python"
        # Verify filter was passed
        call_kwargs = mock_qdrant.search.call_args[1]
        assert call_kwargs.get("query_filter") is not None
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_memory/test_long_term.py -v 2>&1 | head -20
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.memory.long_term'`

- [ ] **Step 4: Install dependencies**

```bash
cd /home/yulcom/web/perso/agentis/backend
pip install "qdrant-client>=1.9" "voyageai>=0.2"
```

- [ ] **Step 5: Implement `backend/app/memory/long_term.py`**

```python
"""Long-term memory via Qdrant + Voyage AI embeddings (spec §8.3 MEM-3)."""
import uuid
from typing import Any
import voyageai
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
)
from app.config import settings


class LongTermMemory:
    def __init__(self) -> None:
        self._qdrant = QdrantClient(url=settings.qdrant_url)
        self._voyage = voyageai.Client(api_key=settings.voyage_api_key) if settings.voyage_api_key else None
        self._collection = settings.qdrant_collection

    def ensure_collection(self) -> None:
        """Idempotent collection init (BR-MEM-27, BR-MEM-28)."""
        if self._qdrant.collection_exists(self._collection):
            return
        self._qdrant.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=settings.voyage_embedding_dim, distance=Distance.COSINE),
        )

    def _embed(self, text: str) -> list[float]:
        if not self._voyage:
            return [0.0] * settings.voyage_embedding_dim
        result = self._voyage.embed([text], model=settings.voyage_model)
        return result.embeddings[0]

    async def store(
        self,
        user_id: str,
        task_id: str,
        content: str,
        summary: str,
        tags: list[str] | None = None,
        language: str = "fr",
        importance: float = 1.0,
    ) -> str:
        """Embed + upsert a memory. Returns the Qdrant point ID."""
        vector = self._embed(content)
        point_id = str(uuid.uuid4())
        self._qdrant.upsert(
            collection_name=self._collection,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "user_id": user_id,
                    "task_id": task_id,
                    "content": content,
                    "summary": summary,
                    "tags": tags or [],
                    "language": language,
                    "importance": importance,
                },
            )],
        )
        return point_id

    async def search(self, user_id: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Hybrid search scoped to user_id. Returns list of {content, summary, score}."""
        vector = self._embed(query)
        user_filter = Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))])
        results = self._qdrant.search(
            collection_name=self._collection,
            query_vector=vector,
            query_filter=user_filter,
            limit=top_k,
        )
        return [
            {
                "content": r.payload.get("content", ""),
                "summary": r.payload.get("summary", ""),
                "score": r.score,
            }
            for r in results
        ]

    def decay_all(self, factor: float = 0.95) -> int:
        """Reduce importance by factor for all points. Returns count updated."""
        offset = None
        updated = 0
        while True:
            points, offset = self._qdrant.scroll(
                collection_name=self._collection, limit=100, offset=offset, with_payload=True
            )
            if not points:
                break
            for p in points:
                new_imp = float(p.payload.get("importance", 1.0)) * factor
                self._qdrant.set_payload(
                    collection_name=self._collection,
                    payload={"importance": new_imp},
                    points=[p.id],
                )
                updated += 1
            if offset is None:
                break
        return updated

    def prune(self, threshold: float = 0.05) -> int:
        """Delete points with importance < threshold. Returns count deleted."""
        low_imp_filter = Filter(must=[
            FieldCondition(key="importance", range={"lt": threshold})
        ])
        result = self._qdrant.delete(
            collection_name=self._collection,
            points_selector=low_imp_filter,
        )
        return getattr(result, "deleted", 0)


# Module-level singleton
long_term_memory = LongTermMemory()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_memory/test_long_term.py -v 2>&1 | tail -15
```

Expected: 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/memory/long_term.py tests/test_memory/
git commit -m "feat(2a): long-term memory module (Qdrant + Voyage AI)"
```

---

## Task 4: Celery Beat — memory decay + prune jobs (TDD)

**Files:**
- Create: `backend/tests/test_worker/test_beat_jobs.py`
- Create: `backend/app/worker/beat_jobs.py`
- Modify: `backend/app/worker/celery_app.py`

- [ ] **Step 1: Write failing tests — `backend/tests/test_worker/test_beat_jobs.py`**

```python
import pytest
from unittest.mock import MagicMock, patch


def test_decay_memory_importance_calls_decay():
    mock_ltm = MagicMock()
    mock_ltm.decay_all.return_value = 42
    with patch("app.worker.beat_jobs.long_term_memory", mock_ltm):
        from app.worker.beat_jobs import decay_memory_importance
        result = decay_memory_importance()
        mock_ltm.decay_all.assert_called_once_with(factor=0.95)
        assert result["updated"] == 42


def test_prune_memory_calls_prune():
    mock_ltm = MagicMock()
    mock_ltm.prune.return_value = 3
    with patch("app.worker.beat_jobs.long_term_memory", mock_ltm):
        from app.worker.beat_jobs import prune_memory
        result = prune_memory()
        mock_ltm.prune.assert_called_once_with(threshold=0.05)
        assert result["deleted"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_worker/test_beat_jobs.py -v 2>&1 | head -15
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.worker.beat_jobs'`

- [ ] **Step 3: Create `backend/app/worker/beat_jobs.py`**

```python
"""Celery Beat periodic jobs (Phase 2A–2D)."""
from app.worker.celery_app import celery_app
from app.memory.long_term import long_term_memory


@celery_app.task(name="beat.decay_memory_importance")
def decay_memory_importance() -> dict:
    """Reduce importance of all memory entries by 5% (BR-MEM-29)."""
    updated = long_term_memory.decay_all(factor=0.95)
    return {"updated": updated}


@celery_app.task(name="beat.prune_memory")
def prune_memory() -> dict:
    """Delete memory entries with importance < 0.05 (BR-MEM-31)."""
    deleted = long_term_memory.prune(threshold=0.05)
    return {"deleted": deleted}
```

- [ ] **Step 4: Update `backend/app/worker/celery_app.py` — add beat schedule**

Add after `celery_app.conf.update(...)`:

```python
celery_app.conf.beat_schedule = {
    "decay-memory-importance-daily": {
        "task": "beat.decay_memory_importance",
        "schedule": 86400.0,  # every 24h
    },
    "prune-memory-daily": {
        "task": "beat.prune_memory",
        "schedule": 86400.0,  # every 24h
    },
}

celery_app.conf.include = ["app.worker.tasks", "app.worker.beat_jobs"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_worker/test_beat_jobs.py -v 2>&1 | tail -10
```

Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/worker/beat_jobs.py app/worker/celery_app.py tests/test_worker/test_beat_jobs.py
git commit -m "feat(2a): Celery Beat jobs — memory decay + prune"
```

---

## Task 5: `tools/doc_parser.py` — RPC client (TDD)

**Files:**
- Create: `backend/tests/test_tools/test_doc_parser.py`
- Create: `backend/app/tools/doc_parser.py`

- [ ] **Step 1: Write failing tests — `backend/tests/test_tools/test_doc_parser.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.tools.base import SessionContext


@pytest.fixture
def session():
    return SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="http://sandbox:9999")


@pytest.fixture
def tool():
    from app.tools.doc_parser import DocParserTool
    return DocParserTool()


def test_doc_parser_name(tool):
    assert tool.name == "doc_parser"


@pytest.mark.asyncio
async def test_parse_calls_sandbox_rpc(tool, session):
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value={"text": "Hello world", "metadata": {}, "truncated": False})
    with patch("app.tools.doc_parser.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute({"action": "parse", "file_path": "/workspace/doc.pdf"}, session)
    assert result.ok is True
    assert result.data["text"] == "Hello world"
    mock_client.call.assert_called_once_with("doc_parser.parse", {"action": "parse", "file_path": "/workspace/doc.pdf"})


@pytest.mark.asyncio
async def test_extract_tables_calls_sandbox_rpc(tool, session):
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value={"tables": []})
    with patch("app.tools.doc_parser.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute({"action": "extract_tables", "file_path": "/workspace/data.xlsx"}, session)
    assert result.ok is True
    mock_client.call.assert_called_once_with("doc_parser.extract_tables", {"action": "extract_tables", "file_path": "/workspace/data.xlsx"})


@pytest.mark.asyncio
async def test_rpc_error_returns_not_ok(tool, session):
    from app.sandbox.rpc_client import RpcError
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(side_effect=RpcError(code=-32000, message="File not found"))
    with patch("app.tools.doc_parser.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute({"action": "parse", "file_path": "/workspace/missing.pdf"}, session)
    assert result.ok is False
    assert "File not found" in result.error
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_tools/test_doc_parser.py -v 2>&1 | head -15
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.tools.doc_parser'`

- [ ] **Step 3: Implement `backend/app/tools/doc_parser.py`**

```python
from app.tools.base import BaseTool, SessionContext, ToolResult
from app.sandbox.rpc_client import SandboxRpcClient, RpcError


class DocParserTool(BaseTool):
    name = "doc_parser"
    description = (
        "Parse documents (PDF, DOCX, XLSX, HTML, Markdown) running inside the secure sandbox. "
        "Extract text content, tables, and metadata. Convert between formats."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["parse", "extract_tables", "convert"],
                "description": "parse → full text+metadata; extract_tables → structured tables; convert → new format file",
            },
            "file_path": {"type": "string", "description": "Absolute path inside /workspace"},
            "target_format": {
                "type": "string",
                "enum": ["markdown", "txt", "json", "csv"],
                "description": "Required for 'convert' action",
            },
        },
        "required": ["action", "file_path"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        action = params.get("action", "parse")
        client = SandboxRpcClient(session.sandbox_endpoint, timeout_s=120.0)
        method = f"doc_parser.{action}"
        try:
            result = await client.call(method, params)
            return ToolResult(ok=True, data=result)
        except RpcError as e:
            return ToolResult(ok=False, error=e.message, retryable=e.code == -32000)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), retryable=True)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_tools/test_doc_parser.py -v 2>&1 | tail -10
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/tools/doc_parser.py tests/test_tools/test_doc_parser.py
git commit -m "feat(2a): DocParserTool — RPC client for Docling sandbox"
```

---

## Task 6: `tools/http_caller.py` — RPC client (TDD)

**Files:**
- Create: `backend/tests/test_tools/test_http_caller.py`
- Create: `backend/app/tools/http_caller.py`

- [ ] **Step 1: Write failing tests — `backend/tests/test_tools/test_http_caller.py`**

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.tools.base import SessionContext


@pytest.fixture
def session():
    return SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="http://sandbox:9999")


@pytest.fixture
def tool():
    from app.tools.http_caller import HttpCallerTool
    return HttpCallerTool()


def test_http_caller_name(tool):
    assert tool.name == "http_caller"


@pytest.mark.asyncio
async def test_get_request_executes_directly(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.http_caller.settings.http_caller_safe_domain_set", set())
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value={"status": 200, "body": "OK", "headers": {}, "duration_ms": 50})
    with patch("app.tools.http_caller.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute(
            {"method": "GET", "url": "https://example.com/api/data"}, session
        )
    assert result.ok is True
    assert result.data["status"] == 200
    mock_client.call.assert_called_once()


@pytest.mark.asyncio
async def test_non_get_to_safe_domain_executes(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.http_caller.settings.http_caller_safe_domain_set",
                        {"api.github.com"})
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value={"status": 201, "body": "{}", "headers": {}, "duration_ms": 80})
    with patch("app.tools.http_caller.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute(
            {"method": "POST", "url": "https://api.github.com/repos/x/y/issues", "body": "{}"}, session
        )
    assert result.ok is True
    mock_client.call.assert_called_once()


@pytest.mark.asyncio
async def test_non_get_to_unsafe_domain_requires_hitl(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.http_caller.settings.http_caller_safe_domain_set", set())
    result = await tool.execute(
        {"method": "POST", "url": "https://external.example.com/webhook", "body": "data"}, session
    )
    assert result.ok is False
    assert result.data.get("hitl_required") is True
    assert result.data.get("method") == "POST"
    assert result.data.get("url") == "https://external.example.com/webhook"


@pytest.mark.asyncio
async def test_rpc_error_returns_not_ok(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.http_caller.settings.http_caller_safe_domain_set", set())
    from app.sandbox.rpc_client import RpcError
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(side_effect=RpcError(code=-32001, message="Timeout"))
    with patch("app.tools.http_caller.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute(
            {"method": "GET", "url": "https://slow.example.com"}, session
        )
    assert result.ok is False
    assert "Timeout" in result.error
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_tools/test_http_caller.py -v 2>&1 | head -15
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.tools.http_caller'`

- [ ] **Step 3: Implement `backend/app/tools/http_caller.py`**

```python
from urllib.parse import urlparse
from app.tools.base import BaseTool, SessionContext, ToolResult
from app.sandbox.rpc_client import SandboxRpcClient, RpcError
from app.config import settings


class HttpCallerTool(BaseTool):
    name = "http_caller"
    description = (
        "Make HTTP requests to external APIs from inside the secure sandbox. "
        "GET requests are free. Non-GET requests to domains not on the safe list require human confirmation (HITL)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "method":  {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
            "url":     {"type": "string"},
            "headers": {"type": "object", "additionalProperties": {"type": "string"}},
            "body":    {"type": "string"},
            "timeout": {"type": "integer", "default": 30},
        },
        "required": ["method", "url"],
    }

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    def _needs_hitl(self, method: str, url: str) -> bool:
        if method.upper() == "GET":
            return False
        domain = self._domain(url)
        return domain not in settings.http_caller_safe_domain_set

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        method = params.get("method", "GET").upper()
        url = params.get("url", "")

        if self._needs_hitl(method, url):
            return ToolResult(
                ok=False,
                error=f"HITL required: {method} {url} needs human confirmation before execution.",
                retryable=False,
                data={"hitl_required": True, "method": method, "url": url},
            )

        client = SandboxRpcClient(session.sandbox_endpoint, timeout_s=float(params.get("timeout", 30)) + 5)
        try:
            result = await client.call("http_caller.request", params)
            return ToolResult(ok=True, data=result)
        except RpcError as e:
            return ToolResult(ok=False, error=e.message, retryable=e.code == -32000)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), retryable=True)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest tests/test_tools/test_http_caller.py -v 2>&1 | tail -10
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/tools/http_caller.py tests/test_tools/test_http_caller.py
git commit -m "feat(2a): HttpCallerTool — RPC client with HITL guard for non-GET requests"
```

---

## Task 7: Register tools + update orchestrator nodes

**Files:**
- Modify: `backend/app/tools/init_registry.py`
- Modify: `backend/app/orchestrator/nodes.py`
- Modify: `backend/app/orchestrator/state.py`

- [ ] **Step 1: Register new tools in `backend/app/tools/init_registry.py`**

```python
from app.tools.registry import tool_registry
from app.tools.browser import BrowserTool
from app.tools.code_executor import CodeExecutorTool
from app.tools.file_system import FileSystemTool
from app.tools.web_search import WebSearchTool
from app.tools.doc_parser import DocParserTool
from app.tools.http_caller import HttpCallerTool


def register_all_tools() -> None:
    """Register all built-in tools. Called once at app startup."""
    tool_registry.register(BrowserTool)
    tool_registry.register(CodeExecutorTool)
    tool_registry.register(FileSystemTool)
    tool_registry.register(WebSearchTool)
    tool_registry.register(DocParserTool)
    tool_registry.register(HttpCallerTool)
```

- [ ] **Step 2: Add `long_term_context` field to `AgentState` in `backend/app/orchestrator/state.py`**

In the `AgentState` TypedDict, add after `hitl_response`:

```python
    long_term_context: str  # injected memories from Qdrant (built at plan time)
```

- [ ] **Step 3: Update `plan_node` in `backend/app/orchestrator/nodes.py` to inject long-term memory**

At the top of the file, add import:

```python
from app.memory.long_term import long_term_memory
```

In `plan_node`, after `goal = state["goal"]`, add:

```python
    # Fetch relevant long-term memories (BR-MEM-21)
    lt_memories = await long_term_memory.search(user_id=ctx.user_id, query=goal, top_k=5)
    lt_block = ""
    if lt_memories:
        lt_block = "\n\nRELEVANT MEMORIES FROM PAST SESSIONS:\n" + "\n".join(
            f"- {m['summary']}: {m['content'][:200]}" for m in lt_memories
        )
```

Then update the call to `prompts.system_with_language` in `plan_node` to pass `lt_block`:

```python
    sys = prompts.system_with_language(prompts.PLAN_SYSTEM, state.get("language", "en"),
                                       ctx.memory_block + lt_block)
```

Also store in state return:

```python
    return {"plan": plan.model_dump(), "iteration": 0,
            "messages": [SystemMessage(content=sys), HumanMessage(content=goal)],
            "long_term_context": lt_block}
```

- [ ] **Step 4: Update `report_node` to persist memories**

In `report_node`, before the `return` statement, add:

```python
    # Persist key findings to long-term memory (BR-MEM-20)
    if summary and ctx.user_id:
        try:
            await long_term_memory.store(
                user_id=ctx.user_id,
                task_id=ctx.task_id,
                content=summary[:1000],
                summary=state["goal"][:200],
                language=state.get("language", "fr"),
            )
        except Exception:
            pass  # Memory persistence failure must not block task completion
```

- [ ] **Step 5: Run full backend test suite**

```bash
cd /home/yulcom/web/perso/agentis/backend
python -m pytest --tb=short -q 2>&1 | tail -15
```

Expected: All tests pass (127+ tests).

- [ ] **Step 6: Commit**

```bash
cd /home/yulcom/web/perso/agentis/backend
git add app/tools/init_registry.py app/orchestrator/nodes.py app/orchestrator/state.py
git commit -m "feat(2a): register doc_parser + http_caller; inject long-term memory in plan+report nodes"
```

---

## Task 8: Vérification manuelle navigateur (Phase 2A)

- [ ] **Step 1: Démarrer la stack**

```bash
cd /home/yulcom/web/perso/agentis
docker compose up -d --build
```

Attendre que tous les services soient healthy :

```bash
docker compose ps
```

Expected: `api`, `worker`, `postgres`, `pgbouncer`, `redis`, `qdrant` tous `Up` ou `healthy`.

- [ ] **Step 2: Appliquer la migration**

```bash
docker compose exec api alembic upgrade head
```

Expected: migration `add_memory_entries` appliquée.

- [ ] **Step 3: Vérifier Qdrant accessible**

```bash
curl http://localhost:6333/readyz
```

Expected: `{"result": "ok"}`

- [ ] **Step 4: Test navigateur — soumettre une tâche de recherche web**

Utiliser le skill `verify` pour ouvrir `http://localhost:3000`, se connecter, et soumettre la tâche :
`"Recherche les 3 principaux frameworks Python pour le machine learning et résume leurs différences"`

Vérifier dans le SSE feed que les événements THINK et TOOL apparaissent.

- [ ] **Step 5: Vérifier mémoire persistée dans Qdrant**

```bash
curl -X POST http://localhost:6333/collections/agentis_memory/points/scroll \
  -H "Content-Type: application/json" \
  -d '{"limit": 5, "with_payload": true}'
```

Expected: au moins 1 point inséré avec `content` correspondant au résumé de la tâche.

- [ ] **Step 6: Soumettre une 2e tâche similaire et vérifier l'injection mémoire**

Soumettre : `"Compare scikit-learn et XGBoost pour la classification"`

Dans les logs SSE, le PLAN devrait contenir `RELEVANT MEMORIES FROM PAST SESSIONS`.

- [ ] **Step 7: Commit final Phase 2A**

```bash
cd /home/yulcom/web/perso/agentis
git add .
git commit -m "feat(2a): Phase 2A complete — doc_parser, http_caller, Qdrant long-term memory, Celery beat jobs"
```
