# Phase 1C — Orchestrator + Task Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the agent brain (LangGraph ReAct loop), the async task pipeline (Celery + Redis), real-time SSE streaming, short-term memory, context-window management, and token budgets — turning the existing tools + sandbox into an end-to-end autonomous agent.

**Architecture:** A FastAPI router enqueues tasks to Celery (Redis DB0 broker). A Celery worker runs the compiled LangGraph `StateGraph` (PLAN→THINK→ACT→OBSERVE→REFLECT→REPORT) checkpointed in PostgreSQL. Each node persists a `task_steps` row (episodic memory, sequential `step_number` = SSE event id) and publishes an event to a Redis pub/sub channel. The SSE endpoint streams live events from Redis and replays missed events from `task_steps` on `Last-Event-ID` reconnect. Short-term memory lives in Redis DB1. Token budgets are checked before each LLM call.

**Tech Stack:** LangGraph 0.2 (`StateGraph`, `AsyncPostgresSaver`), LangChain (`BaseChatModel`, `bind_tools`), `langchain-anthropic`, Celery 5 + Redis, `sse-starlette`, `tiktoken`, `langfuse`, psycopg 3 (checkpointer), existing SQLAlchemy async stack.

---

## Key Architectural Decisions (Phase 1C)

**ADR-1C-01 — Checkpointer connects directly to Postgres (not PgBouncer).**
LangGraph's `AsyncPostgresSaver` uses prepared statements and explicit transaction control that are incompatible with PgBouncer transaction-pooling. The Celery worker's checkpointer therefore connects directly to `postgres:5432` (session mode) using `settings.postgres_direct_url`. The API's SQLAlchemy sessions continue to use PgBouncer (`settings.database_url`). This refines spec ADR-03 ("PgBouncer required for PostgresSaver at scale") for the dev/single-node topology; production routes the checkpointer through a session-mode PgBouncer pool or a dedicated DB role.

**ADR-1C-02 — Custom `act_node`, not LangGraph's prebuilt `ToolNode`.**
Spec §5.2 references `ToolNode(tools)`, but our tools are RPC clients (`app/tools/base.BaseTool`) that require a live `SessionContext` (sandbox endpoint) which the prebuilt `ToolNode` cannot inject. We implement a custom `act_node` that dispatches each tool call to the existing `tool_registry` with the per-run `SessionContext`. The `bind_tools` schema is built from each tool's `input_schema`.

**ADR-1C-03 — Runtime context passed via `config`, not `AgentState`.**
`AgentState` is checkpointed (serialized) so it holds only JSON-serializable data. Live objects (LLM client, event emitter, sandbox endpoint, user_id) are passed to nodes through `config["configurable"]["run_ctx"]`, which LangGraph treats as runtime-only and never serializes.

**ADR-1C-04 — `step_number` is the SSE event id.**
Each persisted `task_steps.step_number` (monotonic per task) doubles as the SSE `id:` field. `Last-Event-ID` reconnect replays `task_steps WHERE step_number > last_id`. This unifies episodic memory and the resumable event stream (BR-TASK-11, BR-FRONT-01).

---

## File Structure

```
backend/app/orchestrator/
    __init__.py
    llm.py            # build_llm() — BaseChatModel factory (ORCH-1)
    state.py          # AgentState TypedDict, Plan/SubTask models
    context.py        # token counting, summarization (ORCH-2)
    prompts.py        # system prompts (EN) + LANGUAGE_INSTRUCTION
    tools_adapter.py  # registry → bind_tools schema; SessionContext build
    events.py         # EventEmitter: persist task_step + Redis publish
    budget.py         # token budget checks (ORCH-3)
    nodes.py          # plan/think/act/observe/reflect/report nodes + routing
    graph.py          # build_graph(checkpointer) + get_checkpointer()
    runner.py         # run_task(): sandbox + ainvoke + lifecycle
backend/app/memory/
    __init__.py
    short_term.py     # Redis DB1 summaries + prefs (MEM-2)
backend/app/repositories/
    __init__.py
    task.py           # task CRUD + cursor pagination + filters
backend/app/schemas/
    task.py           # request/response Pydantic schemas
backend/app/worker/
    __init__.py
    celery_app.py     # Celery app (Redis broker)
    tasks.py          # run_agent_task Celery task + cancellation
backend/app/routers/
    tasks.py          # Task CRUD + SSE endpoints
backend/tests/test_orchestrator/   # node, graph, context, budget tests
backend/tests/test_memory/         # short-term memory tests
backend/tests/test_tasks/          # repository + endpoint + SSE tests
backend/tests/test_worker/         # celery task tests
```

---

## Task 1: Dependencies + Config + LLM Provider Factory

**Files:**
- Modify: `backend/pyproject.toml` (dependencies)
- Modify: `backend/app/config.py` (new fields + psycopg url helper)
- Create: `backend/app/orchestrator/__init__.py`
- Create: `backend/app/orchestrator/llm.py`
- Test: `backend/tests/test_orchestrator/__init__.py`, `backend/tests/test_orchestrator/test_llm.py`

- [ ] **Step 1: Add dependencies to pyproject.toml**

In `backend/pyproject.toml`, add to the `dependencies` list (after `"python-multipart>=0.0.9",`):

```toml
    "langgraph>=0.2.50",
    "langgraph-checkpoint-postgres>=2.0",
    "langchain-core>=0.3",
    "langchain-anthropic>=0.3",
    "langchain-openai>=0.2",
    "celery[redis]>=5.4",
    "langfuse>=2.50",
    "tiktoken>=0.8",
    "psycopg[binary,pool]>=3.2",
```

- [ ] **Step 2: Install dependencies**

Run: `cd backend && pip install -e ".[dev]"`
Expected: resolves and installs langgraph, celery, langfuse, tiktoken, psycopg.

- [ ] **Step 3: Add config fields and psycopg URL helper**

In `backend/app/config.py`, add these fields inside `Settings` (after the `# Search` block) and a helper property. Replace the `# App` block region by inserting after existing fields:

```python
    # LLM
    llm_provider: str = "anthropic"        # anthropic|openai|mistral|groq|deepseek|ollama
    llm_model: str = "claude-sonnet-4-5-20251022"
    llm_api_key: str = ""
    llm_base_url: str = ""                  # Ollama / self-hosted
    llm_timeout_s: int = 120
    context_budget: float = 0.8             # fraction of model window before summarize
    memory_injection_tokens: int = 2000

    # Token budgets
    token_budget_per_task: int = 100000
    token_budget_user_monthly: int = 2000000

    # Agent behavior
    default_max_iterations: int = 30
    max_iterations_cap: int = 50
    hitl_confidence_threshold: float = 0.3
    hitl_timeout_seconds: int = 3600
    worker_concurrency: int = 4
    max_total_failures: int = 10

    # Observability
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
```

Add this property method at the end of the `Settings` class (before `settings = Settings()`):

```python
    @property
    def checkpointer_dsn(self) -> str:
        """psycopg DSN for the LangGraph checkpointer (direct Postgres, ADR-1C-01)."""
        return str(self.postgres_direct_url).replace("postgresql+asyncpg://", "postgresql://")
```

- [ ] **Step 4: Write the failing test for build_llm**

Create `backend/tests/test_orchestrator/__init__.py` (empty file).

Create `backend/tests/test_orchestrator/test_llm.py`:

```python
import pytest
from app.orchestrator.llm import build_llm


def test_build_llm_anthropic_returns_chat_model():
    llm = build_llm(provider="anthropic", model="claude-sonnet-4-5-20251022", api_key="sk-test")
    from langchain_anthropic import ChatAnthropic
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == "claude-sonnet-4-5-20251022"


def test_build_llm_openai_returns_chat_model():
    llm = build_llm(provider="openai", model="gpt-4o", api_key="sk-test")
    from langchain_openai import ChatOpenAI
    assert isinstance(llm, ChatOpenAI)


def test_build_llm_ollama_uses_base_url():
    llm = build_llm(provider="ollama", model="llama3", api_key="", base_url="http://ollama:11434/v1")
    from langchain_openai import ChatOpenAI
    assert isinstance(llm, ChatOpenAI)


def test_build_llm_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        build_llm(provider="madeup", model="x", api_key="y")
```

- [ ] **Step 5: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.orchestrator.llm'`

- [ ] **Step 6: Implement build_llm**

Create `backend/app/orchestrator/__init__.py` (empty file).

Create `backend/app/orchestrator/llm.py`:

```python
"""LLM provider factory (Feature ORCH-1). Provider is config-only — no
provider-specific code outside this module (BR-ORCH-02)."""
from langchain_core.language_models.chat_models import BaseChatModel
from app.config import settings


def build_llm(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout_s: int | None = None,
) -> BaseChatModel:
    provider = (provider or settings.llm_provider).lower()
    model = model or settings.llm_model
    api_key = api_key if api_key is not None else settings.llm_api_key
    base_url = base_url if base_url is not None else settings.llm_base_url
    timeout_s = timeout_s or settings.llm_timeout_s

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=api_key or None, timeout=timeout_s, max_retries=0)

    # OpenAI-compatible providers (openai, groq, deepseek, mistral, ollama)
    openai_compatible = {
        "openai": None,
        "groq": "https://api.groq.com/openai/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "mistral": "https://api.mistral.ai/v1",
        "ollama": base_url or "http://ollama:11434/v1",
    }
    if provider in openai_compatible:
        from langchain_openai import ChatOpenAI
        resolved_base = base_url or openai_compatible[provider]
        return ChatOpenAI(
            model=model,
            api_key=api_key or "not-needed",
            base_url=resolved_base,
            timeout=timeout_s,
            max_retries=0,
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_llm.py -v`
Expected: PASS (4 tests)

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/app/config.py backend/app/orchestrator/ backend/tests/test_orchestrator/
git commit -m "feat(phase-1c): orchestrator deps + config + build_llm provider factory"
```

---

## Task 2: AgentState + Plan Schemas

**Files:**
- Create: `backend/app/orchestrator/state.py`
- Test: `backend/tests/test_orchestrator/test_state.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_orchestrator/test_state.py`:

```python
from app.orchestrator.state import Plan, SubTask, new_plan, mark_subtask_done


def test_plan_round_trips_through_dict():
    plan = Plan(
        goal="Write a report",
        subtasks=[SubTask(id="s1", description="research"), SubTask(id="s2", description="draft")],
    )
    d = plan.model_dump()
    restored = Plan.model_validate(d)
    assert restored.goal == "Write a report"
    assert len(restored.subtasks) == 2
    assert restored.subtasks[0].status == "pending"


def test_new_plan_helper_builds_plan_from_descriptions():
    plan = new_plan("goal", ["a", "b", "c"])
    assert len(plan.subtasks) == 3
    assert plan.subtasks[1].id == "s2"


def test_mark_subtask_done_updates_status_and_result():
    plan = new_plan("goal", ["a", "b"])
    updated = mark_subtask_done(plan, "s1", result="found it")
    assert updated.subtasks[0].status == "done"
    assert updated.subtasks[0].result == "found it"
    assert updated.subtasks[1].status == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.orchestrator.state'`

- [ ] **Step 3: Implement state.py**

Create `backend/app/orchestrator/state.py`:

```python
"""AgentState (working memory, spec §5.3) and Plan structures.

AgentState is checkpointed by PostgresSaver, so every value must be
JSON-serializable. The Plan is stored as a dict (Plan.model_dump())."""
from typing import Annotated, Any, Literal, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class SubTask(BaseModel):
    id: str
    description: str
    status: Literal["pending", "in_progress", "done", "failed"] = "pending"
    result: Optional[str] = None


class Plan(BaseModel):
    goal: str
    subtasks: list[SubTask] = Field(default_factory=list)


def new_plan(goal: str, descriptions: list[str]) -> Plan:
    return Plan(
        goal=goal,
        subtasks=[SubTask(id=f"s{i+1}", description=d) for i, d in enumerate(descriptions)],
    )


def mark_subtask_done(plan: Plan, subtask_id: str, result: str | None = None) -> Plan:
    for st in plan.subtasks:
        if st.id == subtask_id:
            st.status = "done"
            st.result = result
    return plan


class AgentState(TypedDict, total=False):
    task_id: str
    user_id: str
    goal: str
    language: str                              # "en" | "fr"
    plan: dict                                 # Plan.model_dump()
    messages: Annotated[list[BaseMessage], add_messages]
    scratchpad: str
    iteration: int
    max_iterations: int
    confidence: float
    allowed_tools: list[str]
    artifacts: list[dict[str, Any]]
    failures: int                              # total tool/LLM failures (BR-ORCH-34)
    hitl_pending: bool
    hitl_response: Optional[str]
    partial: bool                              # token budget hit (BR-ORCH-22)
    done: bool                                 # set by report node
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_state.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestrator/state.py backend/tests/test_orchestrator/test_state.py
git commit -m "feat(phase-1c): AgentState TypedDict + Plan/SubTask schemas"
```

---

## Task 3: Token Counting + Context Window Management

**Files:**
- Create: `backend/app/orchestrator/context.py`
- Test: `backend/tests/test_orchestrator/test_context.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_orchestrator/test_context.py`:

```python
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.orchestrator.context import (
    count_tokens,
    count_message_tokens,
    model_window,
    needs_summarization,
    truncate_tool_output,
)


def test_count_tokens_nonzero_for_text():
    assert count_tokens("hello world this is a test") > 0


def test_count_message_tokens_sums_messages():
    msgs = [HumanMessage(content="hi"), AIMessage(content="hello there friend")]
    assert count_message_tokens(msgs) > 0


def test_model_window_known_and_default():
    assert model_window("claude-sonnet-4-5-20251022") == 200_000
    assert model_window("gpt-4o") == 128_000
    assert model_window("some-unknown-model") == 128_000  # safe default


def test_needs_summarization_true_when_over_budget():
    # window 100, budget 0.8 → threshold 80; 90 tokens exceeds
    assert needs_summarization(total_tokens=90, model="x", window_override=100, budget=0.8) is True
    assert needs_summarization(total_tokens=50, model="x", window_override=100, budget=0.8) is False


def test_truncate_tool_output_appends_note_when_over_limit():
    big = "x" * 100_000
    out = truncate_tool_output(big, max_tokens=10)
    assert "OUTPUT TRUNCATED" in out
    assert len(out) < len(big)


def test_truncate_tool_output_passthrough_when_small():
    assert truncate_tool_output("short", max_tokens=1000) == "short"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_context.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement context.py**

Create `backend/app/orchestrator/context.py`:

```python
"""Context window management (Feature ORCH-2). Token counts use tiktoken
cl100k_base as a provider-agnostic approximation."""
import tiktoken
from langchain_core.messages import BaseMessage, SystemMessage

_ENCODER = tiktoken.get_encoding("cl100k_base")

MODEL_CONTEXT_WINDOWS = {
    "claude-sonnet-4-5-20251022": 200_000,
    "claude": 200_000,
    "gpt-4o": 128_000,
    "llama3": 128_000,
    "deepseek": 64_000,
}
_DEFAULT_WINDOW = 128_000


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENCODER.encode(text))


def count_message_tokens(messages: list[BaseMessage]) -> int:
    total = 0
    for m in messages:
        content = m.content if isinstance(m.content, str) else str(m.content)
        total += count_tokens(content) + 4  # per-message overhead
    return total


def model_window(model: str) -> int:
    for key, window in MODEL_CONTEXT_WINDOWS.items():
        if key in model:
            return window
    return _DEFAULT_WINDOW


def needs_summarization(
    total_tokens: int, model: str, window_override: int | None = None, budget: float = 0.8
) -> bool:
    window = window_override if window_override is not None else model_window(model)
    return total_tokens > window * budget


def truncate_tool_output(output: str, max_tokens: int) -> str:
    tokens = _ENCODER.encode(output)
    if len(tokens) <= max_tokens:
        return output
    kept = _ENCODER.decode(tokens[:max_tokens])
    removed_chars = len(output) - len(kept)
    return f"{kept}\n[OUTPUT TRUNCATED — {removed_chars} characters removed. Full output available in task_steps.]"


async def summarize_messages(llm, messages: list[BaseMessage]) -> tuple[list[BaseMessage], int]:
    """Replace the oldest 50% of messages with one LLM summary SystemMessage
    (BR-ORCH-12). Returns (new_messages, tokens_freed)."""
    if len(messages) < 4:
        return messages, 0
    split = len(messages) // 2
    old, recent = messages[:split], messages[split:]
    freed = count_message_tokens(old)
    transcript = "\n".join(
        f"{m.__class__.__name__}: {m.content if isinstance(m.content, str) else str(m.content)}"
        for m in old
    )
    prompt = [
        SystemMessage(content="Summarize the following agent transcript into a concise summary "
                              "of key facts, decisions, and tool results. Preserve information "
                              "needed to continue the task."),
        SystemMessage(content=transcript),
    ]
    resp = await llm.ainvoke(prompt)
    summary = resp.content if isinstance(resp.content, str) else str(resp.content)
    new_messages = [SystemMessage(content=f"[SUMMARY OF EARLIER STEPS]\n{summary}")] + recent
    return new_messages, freed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_context.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestrator/context.py backend/tests/test_orchestrator/test_context.py
git commit -m "feat(phase-1c): context window management — token counting + summarization"
```

---

## Task 4: Short-Term Memory (Redis DB1)

**Files:**
- Create: `backend/app/memory/__init__.py`
- Create: `backend/app/memory/short_term.py`
- Test: `backend/tests/test_memory/__init__.py`, `backend/tests/test_memory/test_short_term.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_memory/__init__.py` (empty).

Create `backend/tests/test_memory/test_short_term.py`:

```python
import pytest
from app.memory.short_term import ShortTermMemory


@pytest.fixture
async def stm():
    m = ShortTermMemory()
    uid = "test-user-stm"
    await m.clear(uid)
    yield m, uid
    await m.clear(uid)
    await m.close()


async def test_store_and_get_recent_summaries(stm):
    m, uid = stm
    await m.store_task_summary(uid, "Did task A")
    await m.store_task_summary(uid, "Did task B")
    recent = await m.get_recent_summaries(uid)
    assert recent[0] == "Did task B"  # most recent first (LPUSH)
    assert "Did task A" in recent


async def test_recent_summaries_capped_at_20(stm):
    m, uid = stm
    for i in range(25):
        await m.store_task_summary(uid, f"summary {i}")
    recent = await m.get_recent_summaries(uid)
    assert len(recent) == 20


async def test_store_and_get_prefs(stm):
    m, uid = stm
    await m.store_pref(uid, "language", "prefers tables in English")
    prefs = await m.get_prefs(uid)
    assert prefs["language"] == "prefers tables in English"


async def test_build_context_block_respects_token_budget(stm):
    m, uid = stm
    for i in range(20):
        await m.store_task_summary(uid, "x" * 500)
    block = await m.build_context_block(uid, max_tokens=100)
    from app.orchestrator.context import count_tokens
    assert count_tokens(block) <= 120  # small allowance over budget for headers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_memory/test_short_term.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement short_term.py**

Create `backend/app/memory/__init__.py` (empty).

Create `backend/app/memory/short_term.py`:

```python
"""Short-term memory (Feature MEM-2). Redis DB1, 24h TTL, scoped per user."""
import redis.asyncio as aioredis
from app.config import settings
from app.orchestrator.context import count_tokens

_TTL_24H = 86_400
_MAX_RECENT = 20


class ShortTermMemory:
    def __init__(self):
        self._redis = aioredis.from_url(settings.redis_cache_url, decode_responses=True)

    def _recent_key(self, user_id: str) -> str:
        return f"mem:short:{user_id}:recent"

    def _prefs_key(self, user_id: str) -> str:
        return f"mem:short:{user_id}:prefs"

    async def store_task_summary(self, user_id: str, summary: str) -> None:
        key = self._recent_key(user_id)
        await self._redis.lpush(key, summary)
        await self._redis.ltrim(key, 0, _MAX_RECENT - 1)
        await self._redis.expire(key, _TTL_24H)

    async def get_recent_summaries(self, user_id: str) -> list[str]:
        return await self._redis.lrange(self._recent_key(user_id), 0, _MAX_RECENT - 1)

    async def store_pref(self, user_id: str, name: str, value: str) -> None:
        key = self._prefs_key(user_id)
        await self._redis.hset(key, name, value)
        await self._redis.expire(key, _TTL_24H)

    async def get_prefs(self, user_id: str) -> dict[str, str]:
        return await self._redis.hgetall(self._prefs_key(user_id))

    async def build_context_block(self, user_id: str, max_tokens: int = 500) -> str:
        """Assemble a short-term memory block for the system prompt (BR-MEM-12),
        capped at max_tokens."""
        prefs = await self.get_prefs(user_id)
        recent = await self.get_recent_summaries(user_id)
        lines: list[str] = []
        if prefs:
            lines.append("User preferences: " + "; ".join(f"{k}={v}" for k, v in prefs.items()))
        block = ""
        for summary in recent:
            candidate = block + f"- {summary}\n"
            header = "\n".join(lines)
            if count_tokens(header + "\nRecent tasks:\n" + candidate) > max_tokens:
                break
            block = candidate
        parts = []
        if lines:
            parts.append("\n".join(lines))
        if block:
            parts.append("Recent tasks:\n" + block.rstrip())
        return "\n".join(parts)

    async def clear(self, user_id: str) -> None:
        await self._redis.delete(self._recent_key(user_id), self._prefs_key(user_id))

    async def close(self) -> None:
        await self._redis.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_memory/test_short_term.py -v`
Expected: PASS (4 tests). Requires Redis running on `localhost:6379/1` (already up via docker-compose).

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/ backend/tests/test_memory/
git commit -m "feat(phase-1c): short-term memory — Redis DB1 summaries + prefs (MEM-2)"
```

---

## Task 5: Task Repository + Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/task.py`
- Create: `backend/app/repositories/__init__.py`
- Create: `backend/app/repositories/task.py`
- Test: `backend/tests/test_tasks/__init__.py`, `backend/tests/test_tasks/test_repository.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_tasks/__init__.py` (empty).

Create `backend/tests/test_tasks/test_repository.py`:

```python
import uuid
import pytest
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.task import TaskStatus
from app.auth.password import hash_password
from app.repositories import task as task_repo


@pytest.fixture
async def user():
    async with AsyncSessionLocal() as db:
        u = User(email=f"repo-{uuid.uuid4()}@t.com", password_hash=hash_password("x"), language="en")
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


async def test_create_task_defaults(user):
    async with AsyncSessionLocal() as db:
        t = await task_repo.create_task(db, user_id=user.id, goal="do thing", language="en",
                                        max_iterations=30, allowed_tools=None)
        await db.commit()
        assert t.status == TaskStatus.submitted
        assert t.goal == "do thing"


async def test_list_tasks_filters_by_user_and_status(user):
    async with AsyncSessionLocal() as db:
        await task_repo.create_task(db, user_id=user.id, goal="g1", language="en",
                                    max_iterations=30, allowed_tools=None)
        await db.commit()
    async with AsyncSessionLocal() as db:
        rows, next_cursor = await task_repo.list_tasks(db, user_id=user.id, limit=20)
        assert len(rows) >= 1
        assert all(r.user_id == user.id for r in rows)


async def test_count_running_tasks(user):
    async with AsyncSessionLocal() as db:
        t = await task_repo.create_task(db, user_id=user.id, goal="g", language="en",
                                        max_iterations=30, allowed_tools=None)
        t.status = TaskStatus.running
        await db.commit()
    async with AsyncSessionLocal() as db:
        count = await task_repo.count_running_tasks(db, user_id=user.id)
        assert count >= 1


async def test_cancel_task_sets_cancelled(user):
    async with AsyncSessionLocal() as db:
        t = await task_repo.create_task(db, user_id=user.id, goal="g", language="en",
                                        max_iterations=30, allowed_tools=None)
        t.status = TaskStatus.running
        await db.commit()
        tid = t.id
    async with AsyncSessionLocal() as db:
        ok = await task_repo.cancel_task(db, task_id=tid, user_id=user.id)
        await db.commit()
        assert ok is True
    async with AsyncSessionLocal() as db:
        t = await task_repo.get_task(db, task_id=tid, user_id=user.id)
        assert t.status == TaskStatus.cancelled
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_tasks/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.repositories'`

- [ ] **Step 3: Implement schemas/task.py**

Create `backend/app/schemas/task.py`:

```python
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class TaskOptions(BaseModel):
    max_iterations: Optional[int] = None
    allowed_tools: Optional[list[str]] = None
    notify_webhook: Optional[str] = None


class TaskCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=10000)
    language: Optional[str] = None
    options: TaskOptions = Field(default_factory=TaskOptions)

    @field_validator("language")
    @classmethod
    def validate_language(cls, v):
        if v is not None and v not in ("en", "fr"):
            raise ValueError("language must be 'en' or 'fr'")
        return v


class TaskResponse(BaseModel):
    id: UUID
    goal: str
    status: str
    language: str
    plan: Optional[dict] = None
    max_iterations: int
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    partial: bool
    total_tokens: int
    total_steps: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    stream_url: Optional[str] = None

    model_config = {"from_attributes": True}


class PaginationMeta(BaseModel):
    next_cursor: Optional[str] = None
    has_more: bool
    total: int


class TaskListResponse(BaseModel):
    data: list[TaskResponse]
    pagination: PaginationMeta
```

- [ ] **Step 4: Implement repositories/task.py**

Create `backend/app/repositories/__init__.py` (empty).

Create `backend/app/repositories/task.py`:

```python
"""Task persistence + queries (Features TASK-1, TASK-3, TASK-4)."""
import base64
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.task import Task, TaskStatus

_ACTIVE_RUNNING = (TaskStatus.submitted, TaskStatus.planning, TaskStatus.running,
                   TaskStatus.waiting_for_input)


def _encode_cursor(created_at: datetime, task_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{task_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, tid = raw.split("|")
    return datetime.fromisoformat(ts), UUID(tid)


async def create_task(db: AsyncSession, *, user_id: UUID, goal: str, language: str,
                      max_iterations: int, allowed_tools: list[str] | None,
                      organization_id: UUID | None = None,
                      notify_webhook: str | None = None) -> Task:
    task = Task(
        user_id=user_id, goal=goal, language=language, max_iterations=max_iterations,
        allowed_tools=allowed_tools, organization_id=organization_id,
        notify_webhook=notify_webhook, status=TaskStatus.submitted,
    )
    db.add(task)
    await db.flush()
    return task


async def get_task(db: AsyncSession, *, task_id: UUID, user_id: UUID | None = None,
                   is_admin: bool = False) -> Task | None:
    stmt = select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
    if not is_admin and user_id is not None:
        stmt = stmt.where(Task.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def count_running_tasks(db: AsyncSession, *, user_id: UUID) -> int:
    stmt = select(func.count()).select_from(Task).where(
        Task.user_id == user_id,
        Task.status.in_(_ACTIVE_RUNNING),
        Task.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one()


async def list_tasks(db: AsyncSession, *, user_id: UUID | None, is_admin: bool = False,
                     statuses: list[TaskStatus] | None = None, language: str | None = None,
                     created_after: datetime | None = None, created_before: datetime | None = None,
                     search: str | None = None, after_cursor: str | None = None,
                     limit: int = 20, include_deleted: bool = False) -> tuple[list[Task], str | None]:
    conditions = []
    if not is_admin and user_id is not None:
        conditions.append(Task.user_id == user_id)
    if not include_deleted:
        conditions.append(Task.deleted_at.is_(None))
    if statuses:
        conditions.append(Task.status.in_(statuses))
    if language:
        conditions.append(Task.language == language)
    if created_after:
        conditions.append(Task.created_at >= created_after)
    if created_before:
        conditions.append(Task.created_at <= created_before)
    if search:
        conditions.append(func.to_tsvector("simple", Task.goal).op("@@")(
            func.plainto_tsquery("simple", search)))
    if after_cursor:
        c_ts, c_id = _decode_cursor(after_cursor)
        conditions.append(
            (Task.created_at < c_ts) | and_(Task.created_at == c_ts, Task.id < c_id))

    stmt = (select(Task).where(and_(*conditions))
            .order_by(Task.created_at.desc(), Task.id.desc())
            .limit(limit + 1))
    rows = list((await db.execute(stmt)).scalars().all())

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)
    return rows, next_cursor


async def cancel_task(db: AsyncSession, *, task_id: UUID, user_id: UUID,
                      is_admin: bool = False) -> bool:
    """Cancel a task from any state except completed/failed (BR-TASK-20).
    Idempotent (BR-TASK-23): cancelling an already-cancelled task returns True."""
    task = await get_task(db, task_id=task_id, user_id=user_id, is_admin=is_admin)
    if task is None:
        return False
    if task.status in (TaskStatus.completed, TaskStatus.failed):
        return False
    if task.status == TaskStatus.cancelled:
        return True
    task.status = TaskStatus.cancelled
    task.completed_at = datetime.now(timezone.utc)
    return True
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_tasks/test_repository.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/task.py backend/app/repositories/ backend/tests/test_tasks/
git commit -m "feat(phase-1c): task repository (CRUD, cursor pagination, filters) + schemas"
```

---

## Task 6: Event Emitter (Episodic Persistence + Redis Pub/Sub)

**Files:**
- Create: `backend/app/orchestrator/events.py`
- Test: `backend/tests/test_orchestrator/test_events.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_orchestrator/test_events.py`:

```python
import uuid
import pytest
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.task import TaskStepType
from app.auth.password import hash_password
from app.repositories import task as task_repo
from app.orchestrator.events import EventEmitter


@pytest.fixture
async def task_id():
    async with AsyncSessionLocal() as db:
        u = User(email=f"evt-{uuid.uuid4()}@t.com", password_hash=hash_password("x"))
        db.add(u)
        await db.flush()
        t = await task_repo.create_task(db, user_id=u.id, goal="g", language="en",
                                        max_iterations=30, allowed_tools=None)
        await db.commit()
        return t.id


async def test_emit_persists_step_with_incrementing_number(task_id):
    emitter = EventEmitter(task_id)
    n1 = await emitter.emit(TaskStepType.think, {"content": "thinking"})
    n2 = await emitter.emit(TaskStepType.tool_call, {"tool": "web_search"})
    assert n1 == 1
    assert n2 == 2
    await emitter.close()


async def test_emitted_steps_are_replayable(task_id):
    emitter = EventEmitter(task_id)
    await emitter.emit(TaskStepType.think, {"content": "a"})
    await emitter.emit(TaskStepType.report, {"summary": "done"})
    steps = await emitter.replay(after_step=0)
    assert len(steps) == 2
    assert steps[0]["step_number"] == 1
    assert steps[1]["type"] == "report"
    await emitter.close()


async def test_replay_after_step_skips_earlier(task_id):
    emitter = EventEmitter(task_id)
    await emitter.emit(TaskStepType.think, {"content": "a"})
    await emitter.emit(TaskStepType.think, {"content": "b"})
    steps = await emitter.replay(after_step=1)
    assert len(steps) == 1
    assert steps[0]["step_number"] == 2
    await emitter.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement events.py**

Create `backend/app/orchestrator/events.py`:

```python
"""EventEmitter: persists each agent step to task_steps (episodic memory,
ADR-1C-04) and publishes a live event to Redis pub/sub for SSE consumers."""
import json
from datetime import datetime, timezone
from uuid import UUID
import redis.asyncio as aioredis
from sqlalchemy import select, func
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.task import TaskStep, TaskStepType


def channel_for(task_id) -> str:
    return f"task:{task_id}:events"


# Map internal step type → SSE event type (spec §9.4)
_SSE_TYPE = {
    TaskStepType.think: "think",
    TaskStepType.tool_call: "tool_call",
    TaskStepType.tool_result: "tool_result",
    TaskStepType.reflect: "reflect",
    TaskStepType.plan_update: "plan_updated",
    TaskStepType.user_input: "user_input_required",
    TaskStepType.context_summarized: "context_summarized",
    TaskStepType.report: "task_completed",
}


class EventEmitter:
    def __init__(self, task_id: UUID):
        self.task_id = task_id
        self._redis = aioredis.from_url(settings.redis_cache_url, decode_responses=True)

    async def emit(self, step_type: TaskStepType, content: dict, *, tokens_used: int = 0,
                   duration_ms: int | None = None, sse_type: str | None = None) -> int:
        """Persist a task step and publish to Redis. Returns the step_number."""
        async with AsyncSessionLocal() as db:
            next_number = (await db.execute(
                select(func.coalesce(func.max(TaskStep.step_number), 0) + 1)
                .where(TaskStep.task_id == self.task_id)
            )).scalar_one()
            step = TaskStep(
                task_id=self.task_id, step_number=next_number, step_type=step_type,
                content=content, tokens_used=tokens_used, duration_ms=duration_ms,
                created_at=datetime.now(timezone.utc),
            )
            db.add(step)
            await db.commit()

        event = {
            "id": next_number,
            "type": sse_type or _SSE_TYPE.get(step_type, step_type.value),
            "data": content,
        }
        await self._redis.publish(channel_for(self.task_id), json.dumps(event, default=str))
        return next_number

    async def replay(self, after_step: int = 0) -> list[dict]:
        """Read persisted steps with step_number > after_step (Last-Event-ID, BR-TASK-11)."""
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(TaskStep).where(
                    TaskStep.task_id == self.task_id,
                    TaskStep.step_number > after_step,
                ).order_by(TaskStep.step_number)
            )).scalars().all()
        return [
            {"step_number": r.step_number,
             "type": _SSE_TYPE.get(r.step_type, r.step_type.value),
             "data": r.content}
            for r in rows
        ]

    async def close(self) -> None:
        await self._redis.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_events.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestrator/events.py backend/tests/test_orchestrator/test_events.py
git commit -m "feat(phase-1c): EventEmitter — episodic task_steps + Redis pub/sub for SSE"
```

---

## Task 7: Token Budget Enforcement

**Files:**
- Create: `backend/app/orchestrator/budget.py`
- Test: `backend/tests/test_orchestrator/test_budget.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_orchestrator/test_budget.py`:

```python
import uuid
import pytest
from app.database import AsyncSessionLocal
from app.models.user import User
from app.auth.password import hash_password
from app.orchestrator.budget import BudgetExceeded, check_budgets


@pytest.fixture
async def user():
    async with AsyncSessionLocal() as db:
        u = User(email=f"budget-{uuid.uuid4()}@t.com", password_hash=hash_password("x"),
                 token_used_this_month=0)
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


async def test_check_budgets_passes_under_limit(user):
    async with AsyncSessionLocal() as db:
        # task_tokens=100, estimate next=5000, per-task budget high → ok
        await check_budgets(db, user_id=user.id, task_tokens_so_far=100,
                            estimated_next=5000, per_task_budget=100000)


async def test_check_budgets_raises_when_per_task_exceeded(user):
    async with AsyncSessionLocal() as db:
        with pytest.raises(BudgetExceeded, match="per_task"):
            await check_budgets(db, user_id=user.id, task_tokens_so_far=99000,
                                estimated_next=5000, per_task_budget=100000)


async def test_check_budgets_raises_when_user_monthly_exceeded(user):
    async with AsyncSessionLocal() as db:
        u = await db.get(User, user.id)
        u.token_used_this_month = 1_999_000
        await db.commit()
    async with AsyncSessionLocal() as db:
        with pytest.raises(BudgetExceeded, match="user_monthly"):
            await check_budgets(db, user_id=user.id, task_tokens_so_far=100,
                                estimated_next=5000, per_task_budget=100000,
                                user_monthly_budget=2_000_000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_budget.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement budget.py**

Create `backend/app/orchestrator/budget.py`:

```python
"""Token budget enforcement (Feature ORCH-3). Checked before each LLM call."""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.user import User


class BudgetExceeded(Exception):
    def __init__(self, scope: str):
        self.scope = scope
        super().__init__(f"Token budget exceeded: {scope}")


async def check_budgets(db: AsyncSession, *, user_id: UUID, task_tokens_so_far: int,
                        estimated_next: int, per_task_budget: int | None = None,
                        user_monthly_budget: int | None = None) -> None:
    """Raise BudgetExceeded if the next LLM call would breach any budget
    (BR-ORCH-20/21). Caller halts gracefully with a partial report (BR-ORCH-22)."""
    per_task_budget = per_task_budget or settings.token_budget_per_task
    user_monthly_budget = user_monthly_budget or settings.token_budget_user_monthly

    if task_tokens_so_far + estimated_next > per_task_budget:
        raise BudgetExceeded("per_task")

    used = (await db.execute(
        select(User.token_used_this_month).where(User.id == user_id)
    )).scalar_one_or_none() or 0
    if used + estimated_next > user_monthly_budget:
        raise BudgetExceeded("user_monthly")


async def record_usage(db: AsyncSession, *, user_id: UUID, tokens: int) -> None:
    """Increment the user's monthly token counter (BR-ORCH-24)."""
    user = await db.get(User, user_id)
    if user is not None:
        user.token_used_this_month = (user.token_used_this_month or 0) + tokens
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_budget.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestrator/budget.py backend/tests/test_orchestrator/test_budget.py
git commit -m "feat(phase-1c): token budget enforcement (per-task + per-user/month)"
```

---

## Task 8: Prompts + Tools Adapter

**Files:**
- Create: `backend/app/orchestrator/prompts.py`
- Create: `backend/app/orchestrator/tools_adapter.py`
- Test: `backend/tests/test_orchestrator/test_tools_adapter.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_orchestrator/test_tools_adapter.py`:

```python
from app.orchestrator.tools_adapter import build_tool_schemas, filter_tools
from app.tools.registry import ToolRegistry
from app.tools.web_search import WebSearchTool
from app.tools.file_system import FileSystemTool


def test_build_tool_schemas_produces_anthropic_format():
    reg = ToolRegistry()
    reg.register(WebSearchTool)
    schemas = build_tool_schemas(reg, allowed=None)
    assert len(schemas) == 1
    s = schemas[0]
    assert s["name"] == "web_search"
    assert "description" in s
    assert s["input_schema"]["type"] == "object"


def test_filter_tools_respects_allowlist():
    reg = ToolRegistry()
    reg.register(WebSearchTool)
    reg.register(FileSystemTool)
    schemas = build_tool_schemas(reg, allowed=["web_search"])
    names = [s["name"] for s in schemas]
    assert names == ["web_search"]


def test_filter_tools_none_allows_all():
    reg = ToolRegistry()
    reg.register(WebSearchTool)
    reg.register(FileSystemTool)
    assert len(filter_tools(reg, None)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_tools_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement prompts.py**

Create `backend/app/orchestrator/prompts.py`:

```python
"""System prompts (English only — spec ADR). User language injected as a final
instruction (BR §11.2)."""

LANGUAGE_INSTRUCTION = {
    "en": "Respond to the user in English.",
    "fr": "Réponds à l'utilisateur en français.",
}

PLAN_SYSTEM = """You are Agentis, an autonomous AI agent. Decompose the user's goal \
into an ordered list of concrete sub-tasks. Return ONLY a JSON object of the form:
{"subtasks": ["first concrete step", "second concrete step", ...]}
Keep it to 2-6 sub-tasks. Each sub-task must be actionable with the available tools."""

THINK_SYSTEM = """You are Agentis, an autonomous AI agent executing a plan. \
Given the goal, current plan, and observations so far, either call exactly one tool \
to make progress, or — if the goal is fully achieved — respond with your final answer \
and DO NOT call any tool. Think step by step. Prefer the most direct tool for each step."""

REFLECT_SYSTEM = """You are Agentis reflecting on progress. Given the goal, plan, and \
latest observation, assess progress. Return ONLY a JSON object:
{"confidence": 0.0-1.0, "decision": "continue|report", "completed_subtask_ids": ["s1"], \
"note": "one sentence"}
Set decision="report" only when the goal is fully met or no further progress is possible."""

REPORT_SYSTEM = """You are Agentis producing the final report. Summarize what was \
accomplished for the user's goal in 2-5 sentences. List any artifacts produced. \
Be concrete and reference actual results from the observations."""


def system_with_language(base: str, language: str, memory_block: str = "") -> str:
    parts = [base]
    if memory_block:
        parts.append("\n## Relevant context from memory:\n" + memory_block)
    parts.append("\n" + LANGUAGE_INSTRUCTION.get(language, LANGUAGE_INSTRUCTION["en"]))
    return "\n".join(parts)
```

- [ ] **Step 4: Implement tools_adapter.py**

Create `backend/app/orchestrator/tools_adapter.py`:

```python
"""Bridge between the Agentis ToolRegistry and LangChain's bind_tools (ADR-1C-02)."""
from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry


def filter_tools(registry: ToolRegistry, allowed: list[str] | None) -> list[BaseTool]:
    tools = registry.get_all()
    if allowed is None:
        return tools
    allowset = set(allowed)
    return [t for t in tools if t.name in allowset]


def build_tool_schemas(registry: ToolRegistry, allowed: list[str] | None) -> list[dict]:
    """Anthropic-native tool schema list for ChatModel.bind_tools()."""
    schemas = []
    for tool in filter_tools(registry, allowed):
        schema = tool.input_schema or {"type": "object", "properties": {}}
        schemas.append({
            "name": tool.name,
            "description": tool.description,
            "input_schema": schema,
        })
    return schemas
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_tools_adapter.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/orchestrator/prompts.py backend/app/orchestrator/tools_adapter.py backend/tests/test_orchestrator/test_tools_adapter.py
git commit -m "feat(phase-1c): system prompts (EN + language injection) + tools adapter"
```

---

## Task 9: Orchestrator Nodes + Routing

**Files:**
- Create: `backend/app/orchestrator/nodes.py`
- Test: `backend/tests/test_orchestrator/test_nodes.py`

This task implements the six node functions and the two routing functions. Nodes read the live `RunContext` (LLM, emitter, sandbox endpoint) from `config["configurable"]["run_ctx"]` (ADR-1C-03).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_orchestrator/test_nodes.py`:

```python
import uuid
import json
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from app.database import AsyncSessionLocal
from app.models.user import User
from app.auth.password import hash_password
from app.repositories import task as task_repo
from app.orchestrator.events import EventEmitter
from app.orchestrator.nodes import (
    plan_node, reflect_node, report_node, route_after_think, route_after_reflect, RunContext,
)
from app.orchestrator.state import AgentState


@pytest.fixture
async def ctx():
    async with AsyncSessionLocal() as db:
        u = User(email=f"node-{uuid.uuid4()}@t.com", password_hash=hash_password("x"))
        db.add(u)
        await db.flush()
        t = await task_repo.create_task(db, user_id=u.id, goal="g", language="en",
                                        max_iterations=30, allowed_tools=None)
        await db.commit()
        uid, tid = u.id, t.id
    emitter = EventEmitter(tid)
    rc = RunContext(llm=None, emitter=emitter, sandbox_endpoint="", user_id=str(uid),
                    task_id=str(tid), allowed_tools=None)
    yield rc
    await emitter.close()


def _config(rc):
    return {"configurable": {"run_ctx": rc}}


async def test_plan_node_builds_plan_from_llm_json(ctx):
    ctx.llm = GenericFakeChatModel(messages=iter([
        AIMessage(content=json.dumps({"subtasks": ["search the web", "write summary"]})),
    ]))
    state: AgentState = {"task_id": ctx.task_id, "user_id": ctx.user_id, "goal": "g",
                         "language": "en", "messages": [], "iteration": 0}
    out = await plan_node(state, _config(ctx))
    assert len(out["plan"]["subtasks"]) == 2
    assert out["plan"]["subtasks"][0]["description"] == "search the web"


async def test_route_after_think_to_act_when_tool_calls():
    msg = AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "x"}, "id": "c1"}])
    state = {"messages": [msg], "iteration": 1, "max_iterations": 30, "failures": 0}
    assert route_after_think(state) == "act"


async def test_route_after_think_to_report_when_no_tool_calls():
    state = {"messages": [AIMessage(content="final answer")], "iteration": 1,
             "max_iterations": 30, "failures": 0}
    assert route_after_think(state) == "report"


async def test_route_after_think_to_report_when_max_iterations():
    msg = AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "c1"}])
    state = {"messages": [msg], "iteration": 30, "max_iterations": 30, "failures": 0}
    assert route_after_think(state) == "report"


async def test_reflect_node_parses_confidence_and_decision(ctx):
    ctx.llm = GenericFakeChatModel(messages=iter([
        AIMessage(content=json.dumps({"confidence": 0.9, "decision": "report",
                                      "completed_subtask_ids": [], "note": "done"})),
    ]))
    state: AgentState = {"task_id": ctx.task_id, "user_id": ctx.user_id, "goal": "g",
                         "language": "en", "messages": [HumanMessage(content="obs")],
                         "plan": {"goal": "g", "subtasks": []}, "iteration": 1}
    out = await reflect_node(state, _config(ctx))
    assert out["confidence"] == 0.9
    assert route_after_reflect({**state, **out}) == "report"


async def test_report_node_sets_done_and_summary(ctx):
    ctx.llm = GenericFakeChatModel(messages=iter([AIMessage(content="All done. Report ready.")]))
    state: AgentState = {"task_id": ctx.task_id, "user_id": ctx.user_id, "goal": "g",
                         "language": "en", "messages": [HumanMessage(content="obs")],
                         "plan": {"goal": "g", "subtasks": []}, "iteration": 2}
    out = await report_node(state, _config(ctx))
    assert out["done"] is True
    assert "result_summary" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_nodes.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement nodes.py**

Create `backend/app/orchestrator/nodes.py`:

```python
"""LangGraph node functions for the ReAct loop (spec §5.2).

Runtime objects are read from config["configurable"]["run_ctx"] (ADR-1C-03)."""
import json
import time
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID
from langchain_core.messages import (AIMessage, HumanMessage, SystemMessage,
                                     ToolMessage, BaseMessage)
from langchain_core.runnables import RunnableConfig
from app.config import settings
from app.models.task import TaskStepType
from app.tools.base import SessionContext
from app.tools.registry import tool_registry
from app.orchestrator.state import AgentState, Plan, new_plan
from app.orchestrator.context import truncate_tool_output, count_message_tokens
from app.orchestrator import prompts
from app.orchestrator.tools_adapter import build_tool_schemas


@dataclass
class RunContext:
    llm: Any
    emitter: Any
    sandbox_endpoint: str
    user_id: str
    task_id: str
    allowed_tools: Optional[list[str]]
    memory_block: str = ""


def _ctx(config: RunnableConfig) -> RunContext:
    return config["configurable"]["run_ctx"]


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction from an LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    return {}


async def plan_node(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    goal = state["goal"]
    sys = prompts.system_with_language(prompts.PLAN_SYSTEM, state.get("language", "en"),
                                       ctx.memory_block)
    resp = await ctx.llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=goal)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        descriptions = _extract_json(content).get("subtasks", [])
    except (json.JSONDecodeError, ValueError):
        descriptions = []
    if not descriptions:
        descriptions = [goal]
    plan = new_plan(goal, descriptions)
    tokens = count_message_tokens([resp])
    await ctx.emitter.emit(TaskStepType.plan_update, plan.model_dump(),
                           tokens_used=tokens, sse_type="plan_created")
    return {"plan": plan.model_dump(), "iteration": 0,
            "messages": [SystemMessage(content=sys), HumanMessage(content=goal)]}


async def think_node(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    schemas = build_tool_schemas(tool_registry, ctx.allowed_tools)
    sys = prompts.system_with_language(prompts.THINK_SYSTEM, state.get("language", "en"),
                                       ctx.memory_block)
    plan_msg = HumanMessage(content=f"Current plan: {json.dumps(state.get('plan', {}))}")
    messages: list[BaseMessage] = [SystemMessage(content=sys), plan_msg] + state["messages"]
    llm = ctx.llm.bind_tools(schemas) if schemas else ctx.llm
    resp = await llm.ainvoke(messages)
    tokens = count_message_tokens([resp])
    await ctx.emitter.emit(TaskStepType.think,
                           {"content": resp.content if isinstance(resp.content, str) else str(resp.content),
                            "tokens": tokens},
                           tokens_used=tokens)
    return {"messages": [resp], "iteration": state.get("iteration", 0) + 1}


async def act_node(state: AgentState, config: RunnableConfig) -> dict:
    """Dispatch each tool call from the last AIMessage to the registry (ADR-1C-02)."""
    ctx = _ctx(config)
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", []) or []
    session = SessionContext(session_id=ctx.task_id, task_id=ctx.task_id,
                             sandbox_endpoint=ctx.sandbox_endpoint)
    tool_messages: list[BaseMessage] = []
    failures = state.get("failures", 0)
    for call in tool_calls:
        name, args, call_id = call["name"], call.get("args", {}), call["id"]
        tool = tool_registry.get(name)
        start = time.time()
        await ctx.emitter.emit(TaskStepType.tool_call, {"tool": name, "params": args, "call_id": call_id})
        if tool is None:
            result_text = f"Error: tool '{name}' is not available."
            failures += 1
        else:
            result = await tool.execute(args, session)
            duration = int((time.time() - start) * 1000)
            if result.ok:
                result_text = truncate_tool_output(json.dumps(result.data, default=str),
                                                    settings.tool_output_max_tokens)
            else:
                result_text = f"Error: {result.error}"
                failures += 1
            await ctx.emitter.emit(TaskStepType.tool_result,
                                   {"tool": name, "output": result.data if result.ok else result.error,
                                    "call_id": call_id, "ok": result.ok},
                                   duration_ms=duration)
        tool_messages.append(ToolMessage(content=result_text, tool_call_id=call_id))
    return {"messages": tool_messages, "failures": failures}


async def observe_node(state: AgentState, config: RunnableConfig) -> dict:
    """Normalize tool outputs into the scratchpad (spec §5.2 OBSERVE)."""
    recent = [m for m in state["messages"][-5:] if isinstance(m, ToolMessage)]
    additions = "\n".join(m.content for m in recent)
    scratchpad = (state.get("scratchpad", "") + "\n" + additions).strip()
    return {"scratchpad": scratchpad}


async def reflect_node(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    sys = prompts.REFLECT_SYSTEM
    context = (f"Goal: {state['goal']}\nPlan: {json.dumps(state.get('plan', {}))}\n"
               f"Latest observations:\n{state.get('scratchpad', '')[-2000:]}")
    resp = await ctx.llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=context)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        parsed = _extract_json(content)
    except (json.JSONDecodeError, ValueError):
        parsed = {}
    confidence = float(parsed.get("confidence", 0.5))
    decision = parsed.get("decision", "continue")

    plan = Plan.model_validate(state.get("plan", {"goal": state["goal"], "subtasks": []}))
    for sid in parsed.get("completed_subtask_ids", []):
        for st in plan.subtasks:
            if st.id == sid:
                st.status = "done"
    tokens = count_message_tokens([resp])
    await ctx.emitter.emit(TaskStepType.reflect,
                           {"confidence": confidence, "decision": decision,
                            "note": parsed.get("note", "")}, tokens_used=tokens)
    await ctx.emitter.emit(TaskStepType.plan_update, plan.model_dump(), sse_type="plan_updated")
    return {"confidence": confidence, "plan": plan.model_dump(),
            "_reflect_decision": decision}


async def report_node(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    sys = prompts.system_with_language(prompts.REPORT_SYSTEM, state.get("language", "en"))
    context = (f"Goal: {state['goal']}\nObservations:\n{state.get('scratchpad', '')[-4000:]}")
    if state.get("partial"):
        context += "\n\nNOTE: Token budget reached — produce a PARTIAL report of progress so far."
    resp = await ctx.llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=context)])
    summary = resp.content if isinstance(resp.content, str) else str(resp.content)
    tokens = count_message_tokens([resp])
    await ctx.emitter.emit(TaskStepType.report,
                           {"summary": summary, "artifacts": state.get("artifacts", [])},
                           tokens_used=tokens, sse_type="task_completed")
    return {"done": True, "result_summary": summary, "messages": [resp]}


def route_after_think(state: AgentState) -> str:
    if state.get("iteration", 0) >= state.get("max_iterations", settings.default_max_iterations):
        return "report"
    if state.get("failures", 0) >= settings.max_total_failures:
        return "report"
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "act"
    return "report"


def route_after_reflect(state: AgentState) -> str:
    if state.get("_reflect_decision") == "report":
        return "report"
    if state.get("iteration", 0) >= state.get("max_iterations", settings.default_max_iterations):
        return "report"
    return "think"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_nodes.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestrator/nodes.py backend/tests/test_orchestrator/test_nodes.py
git commit -m "feat(phase-1c): orchestrator nodes (plan/think/act/observe/reflect/report) + routing"
```

---

## Task 10: Graph Assembly + Checkpointer + Runner

**Files:**
- Create: `backend/app/orchestrator/graph.py`
- Create: `backend/app/orchestrator/runner.py`
- Test: `backend/tests/test_orchestrator/test_graph.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_orchestrator/test_graph.py`:

```python
import uuid
import json
import pytest
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.task import Task, TaskStatus
from app.auth.password import hash_password
from app.repositories import task as task_repo
from app.orchestrator.runner import run_task


class _ScriptedLLM(GenericFakeChatModel):
    """Fake chat model that ignores bind_tools (returns self)."""
    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture
async def task_and_user():
    async with AsyncSessionLocal() as db:
        u = User(email=f"graph-{uuid.uuid4()}@t.com", password_hash=hash_password("x"))
        db.add(u)
        await db.flush()
        t = await task_repo.create_task(db, user_id=u.id, goal="say hello", language="en",
                                        max_iterations=5, allowed_tools=[])
        await db.commit()
        return t.id, u.id


async def test_run_task_no_tools_completes(task_and_user):
    """PLAN → THINK (no tool call → final answer) → REPORT → COMPLETED."""
    task_id, user_id = task_and_user
    # plan response, think response (no tools = final), report response
    llm = _ScriptedLLM(messages=iter([
        AIMessage(content=json.dumps({"subtasks": ["greet the user"]})),
        AIMessage(content="Hello! Goal achieved."),
        AIMessage(content="I greeted the user successfully."),
    ]))
    await run_task(str(task_id), llm=llm, skip_sandbox=True)

    async with AsyncSessionLocal() as db:
        t = await db.get(Task, task_id)
        assert t.status == TaskStatus.completed
        assert t.result_summary is not None
        assert t.total_steps > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_graph.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement graph.py**

Create `backend/app/orchestrator/graph.py`:

```python
"""LangGraph StateGraph assembly + checkpointer (spec §5.2, ADR-1C-01)."""
from contextlib import asynccontextmanager
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from app.config import settings
from app.orchestrator.state import AgentState
from app.orchestrator import nodes


def build_graph(checkpointer=None):
    graph = StateGraph(AgentState)
    graph.add_node("plan", nodes.plan_node)
    graph.add_node("think", nodes.think_node)
    graph.add_node("act", nodes.act_node)
    graph.add_node("observe", nodes.observe_node)
    graph.add_node("reflect", nodes.reflect_node)
    graph.add_node("report", nodes.report_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "think")
    graph.add_conditional_edges("think", nodes.route_after_think,
                                {"act": "act", "report": "report"})
    graph.add_edge("act", "observe")
    graph.add_edge("observe", "reflect")
    graph.add_conditional_edges("reflect", nodes.route_after_reflect,
                                {"think": "think", "report": "report"})
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)


@asynccontextmanager
async def checkpointer_context():
    """Yield an AsyncPostgresSaver backed by a direct-Postgres pool (ADR-1C-01)."""
    async with AsyncConnectionPool(
        conninfo=settings.checkpointer_dsn,
        max_size=4,
        kwargs={"autocommit": True, "prepare_threshold": None},
        open=False,
    ) as pool:
        await pool.open()
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        yield checkpointer
```

- [ ] **Step 4: Implement runner.py**

Create `backend/app/orchestrator/runner.py`:

```python
"""Task runner: orchestrates sandbox lifecycle, graph execution, status
transitions, budgets, and cancellation (Features TASK-1/3, ORCH-3/5)."""
from datetime import datetime, timezone
from uuid import UUID
import structlog
from langchain_core.messages import AIMessage
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.task import Task, TaskStatus, TaskStepType
from app.orchestrator.budget import BudgetExceeded, record_usage
from app.orchestrator.events import EventEmitter
from app.orchestrator.graph import build_graph, checkpointer_context
from app.orchestrator.llm import build_llm
from app.orchestrator.nodes import RunContext
from app.orchestrator.state import AgentState
from app.memory.short_term import ShortTermMemory
from app.sandbox.manager import sandbox_manager

log = structlog.get_logger()


async def _set_status(task_id: UUID, status: TaskStatus, **fields) -> Task | None:
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return None
        task.status = status
        for k, v in fields.items():
            setattr(task, k, v)
        await db.commit()
        return task


async def run_task(task_id_str: str, llm=None, skip_sandbox: bool = False) -> None:
    """Run the agent loop for a task. `llm`/`skip_sandbox` are test seams."""
    task_id = UUID(task_id_str)
    emitter = EventEmitter(task_id)
    stm = ShortTermMemory()
    sandbox_endpoint = ""

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None or task.status in (TaskStatus.cancelled, TaskStatus.completed,
                                           TaskStatus.failed):
            await emitter.close()
            await stm.close()
            return
        user_id = task.user_id
        goal, language = task.goal, task.language
        max_iter = min(task.max_iterations, settings.max_iterations_cap)
        allowed_tools = task.allowed_tools

    await _set_status(task_id, TaskStatus.planning, started_at=datetime.now(timezone.utc))

    try:
        if not skip_sandbox:
            session = await sandbox_manager.create_session(task_id_str)
            sandbox_endpoint = session.endpoint

        llm = llm or build_llm()
        memory_block = await stm.build_context_block(str(user_id), max_tokens=500)
        run_ctx = RunContext(llm=llm, emitter=emitter, sandbox_endpoint=sandbox_endpoint,
                             user_id=str(user_id), task_id=task_id_str,
                             allowed_tools=allowed_tools, memory_block=memory_block)

        initial: AgentState = {
            "task_id": task_id_str, "user_id": str(user_id), "goal": goal,
            "language": language, "messages": [], "scratchpad": "", "iteration": 0,
            "max_iterations": max_iter, "confidence": 0.0,
            "allowed_tools": allowed_tools or [], "artifacts": [], "failures": 0,
            "partial": False, "done": False,
        }

        await _set_status(task_id, TaskStatus.running)
        config = {"configurable": {"thread_id": task_id_str, "run_ctx": run_ctx},
                  "recursion_limit": max_iter * 4 + 10}

        async with checkpointer_context() as checkpointer:
            agent = build_graph(checkpointer)
            final_state = None
            try:
                final_state = await agent.ainvoke(initial, config=config)
            except BudgetExceeded as e:
                log.warning("budget_exceeded", task_id=task_id_str, scope=e.scope)
                # Graceful partial report (BR-ORCH-22)
                partial_state = {**initial, "partial": True}
                final_state = await _partial_report(agent, partial_state, config)

        summary = (final_state or {}).get("result_summary", "")
        total_tokens = await _sum_task_tokens(task_id)
        total_steps = await _count_task_steps(task_id)
        async with AsyncSessionLocal() as db:
            await record_usage(db, user_id=user_id, tokens=total_tokens)
            await db.commit()
        await _set_status(task_id, TaskStatus.completed,
                          result_summary=summary,
                          partial=(final_state or {}).get("partial", False),
                          total_tokens=total_tokens, total_steps=total_steps,
                          completed_at=datetime.now(timezone.utc))
        # Short-term memory (MEM-2)
        if summary:
            await stm.store_task_summary(str(user_id), summary[:400])

    except Exception as e:
        log.error("task_failed", task_id=task_id_str, error=str(e))
        await emitter.emit(TaskStepType.report,
                           {"error": str(e), "error_code": "agent_error", "retryable": False},
                           sse_type="task_failed")
        await _set_status(task_id, TaskStatus.failed, error_message=str(e)[:1000],
                          error_code="agent_error", completed_at=datetime.now(timezone.utc))
    finally:
        if not skip_sandbox and sandbox_endpoint:
            sandbox_manager.destroy_session(task_id_str)
        await emitter.close()
        await stm.close()


async def _partial_report(agent, state, config):
    """Invoke only the report node for a partial report when budget is hit."""
    from app.orchestrator.nodes import report_node
    out = await report_node(state, config)
    return {**state, **out}


async def _sum_task_tokens(task_id: UUID) -> int:
    from sqlalchemy import select, func
    from app.models.task import TaskStep
    async with AsyncSessionLocal() as db:
        return (await db.execute(
            select(func.coalesce(func.sum(TaskStep.tokens_used), 0))
            .where(TaskStep.task_id == task_id))).scalar_one()


async def _count_task_steps(task_id: UUID) -> int:
    from sqlalchemy import select, func
    from app.models.task import TaskStep
    async with AsyncSessionLocal() as db:
        return (await db.execute(
            select(func.count()).select_from(TaskStep)
            .where(TaskStep.task_id == task_id))).scalar_one()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_orchestrator/test_graph.py -v`
Expected: PASS (1 test). Requires Postgres reachable at `postgres_direct_url` (localhost:5436 in dev). The checkpointer creates its tables via `setup()` on first run.

- [ ] **Step 6: Commit**

```bash
git add backend/app/orchestrator/graph.py backend/app/orchestrator/runner.py backend/tests/test_orchestrator/test_graph.py
git commit -m "feat(phase-1c): graph assembly + AsyncPostgresSaver checkpointer + task runner"
```

---

## Task 11: Celery App + Worker Task

**Files:**
- Create: `backend/app/worker/__init__.py`
- Create: `backend/app/worker/celery_app.py`
- Create: `backend/app/worker/tasks.py`
- Test: `backend/tests/test_worker/__init__.py`, `backend/tests/test_worker/test_tasks.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_worker/__init__.py` (empty).

Create `backend/tests/test_worker/test_tasks.py`:

```python
import uuid
import pytest
from unittest.mock import patch, AsyncMock
from app.worker.tasks import run_agent_task
from app.worker.celery_app import celery_app


def test_celery_app_configured():
    assert celery_app.conf.task_serializer == "json"
    assert "redis" in celery_app.conf.broker_url


def test_run_agent_task_invokes_runner():
    """The Celery task runs the async runner via asyncio."""
    tid = str(uuid.uuid4())
    with patch("app.worker.tasks.run_task", new=AsyncMock()) as mock_run:
        run_agent_task.run(tid)  # .run() executes the task body synchronously
        mock_run.assert_awaited_once_with(tid)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_worker/test_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement celery_app.py**

Create `backend/app/worker/__init__.py` (empty).

Create `backend/app/worker/celery_app.py`:

```python
"""Celery application (spec: Task Queue, Redis DB0 broker)."""
from celery import Celery
from app.config import settings

celery_app = Celery(
    "agentis",
    broker=settings.redis_broker_url,
    backend=settings.redis_broker_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=settings.worker_concurrency,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)
```

- [ ] **Step 4: Implement tasks.py**

Create `backend/app/worker/tasks.py`:

```python
"""Celery task entry points. Each task bridges sync Celery → async runner."""
import asyncio
import structlog
from app.worker.celery_app import celery_app
from app.orchestrator.runner import run_task

log = structlog.get_logger()


@celery_app.task(name="agentis.run_agent", bind=True)
def run_agent_task(self, task_id: str) -> None:
    log.info("celery_run_agent_start", task_id=task_id, celery_id=self.request.id)
    asyncio.run(run_task(task_id))
    log.info("celery_run_agent_done", task_id=task_id)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_worker/test_tasks.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/worker/ backend/tests/test_worker/
git commit -m "feat(phase-1c): Celery app + run_agent_task worker entry point"
```

---

## Task 12: Task CRUD Endpoints

**Files:**
- Create: `backend/app/routers/tasks.py`
- Modify: `backend/app/main.py` (include router)
- Test: `backend/tests/test_tasks/test_endpoints.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_tasks/test_endpoints.py`:

```python
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from app.main import app
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.task import Task, TaskStatus
from app.auth.password import hash_password
from app.auth.jwt import create_access_token


async def _auth_user():
    async with AsyncSessionLocal() as db:
        u = User(email=f"ep-{uuid.uuid4()}@t.com", password_hash=hash_password("x"), language="en")
        db.add(u)
        await db.commit()
        await db.refresh(u)
        token = create_access_token(str(u.id), u.role.value)
        return u, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def no_enqueue():
    with patch("app.routers.tasks.run_agent_task") as mock:
        mock.delay.return_value = None
        yield mock


async def test_create_task_returns_201_and_stream_url(no_enqueue):
    user, headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/tasks", headers=headers,
                                 json={"goal": "do a thing", "language": "en"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "submitted"
    assert body["stream_url"].endswith("/stream")
    no_enqueue.delay.assert_called_once()


async def test_create_task_clamps_max_iterations(no_enqueue):
    user, headers = await _auth_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/tasks", headers=headers,
                                 json={"goal": "g", "options": {"max_iterations": 9999}})
    assert resp.status_code == 201
    async with AsyncSessionLocal() as db:
        t = await db.get(Task, uuid.UUID(resp.json()["id"]))
        assert t.max_iterations == 50  # clamped to cap (BR-TASK-03)


async def test_concurrency_limit_returns_429(no_enqueue):
    user, headers = await _auth_user()
    async with AsyncSessionLocal() as db:
        for _ in range(5):
            db.add(Task(user_id=user.id, goal="g", language="en", status=TaskStatus.running))
        await db.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/tasks", headers=headers, json={"goal": "g"})
    assert resp.status_code == 429


async def test_list_tasks_returns_own_tasks(no_enqueue):
    user, headers = await _auth_user()
    async with AsyncSessionLocal() as db:
        db.add(Task(user_id=user.id, goal="listme", language="en", status=TaskStatus.submitted))
        await db.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/tasks", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body and "pagination" in body
    assert any(t["goal"] == "listme" for t in body["data"])


async def test_cancel_task_returns_200(no_enqueue):
    user, headers = await _auth_user()
    async with AsyncSessionLocal() as db:
        t = Task(user_id=user.id, goal="g", language="en", status=TaskStatus.running)
        db.add(t)
        await db.commit()
        tid = str(t.id)
    transport = ASGITransport(app=app)
    with patch("app.routers.tasks.celery_app.control.revoke"):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(f"/api/v1/tasks/{tid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_tasks/test_endpoints.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routers.tasks'`

- [ ] **Step 3: Implement routers/tasks.py**

Create `backend/app/routers/tasks.py`:

```python
"""Task CRUD + SSE endpoints (Features TASK-1/3/4, §15.3)."""
import asyncio
import json
from datetime import datetime
from uuid import UUID
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
import redis.asyncio as aioredis
from app.config import settings
from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.task import TaskStatus
from app.repositories import task as task_repo
from app.schemas.task import TaskCreate, TaskResponse, TaskListResponse, PaginationMeta
from app.orchestrator.events import EventEmitter, channel_for
from app.worker.tasks import run_agent_task
from app.worker.celery_app import celery_app
from app.sandbox.manager import sandbox_manager
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()
router = APIRouter()


def _to_response(task, request: Request | None = None) -> TaskResponse:
    resp = TaskResponse.model_validate(task)
    if request is not None:
        resp.stream_url = f"/api/v1/tasks/{task.id}/stream"
    return resp


@router.post("", status_code=201, response_model=TaskResponse)
async def create_task(body: TaskCreate, request: Request,
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    # Concurrency limit (BR-TASK-07)
    running = await task_repo.count_running_tasks(db, user_id=user.id)
    if running >= 5:
        raise HTTPException(status_code=429, detail={
            "code": "concurrency_limit",
            "message": "You have reached the maximum of 5 concurrent running tasks.",
        })
    # Defaults + clamping (BR-TASK-02/03)
    language = body.language or user.language
    requested = body.options.max_iterations or settings.default_max_iterations
    max_iterations = min(requested, settings.max_iterations_cap)
    task = await task_repo.create_task(
        db, user_id=user.id, goal=body.goal, language=language,
        max_iterations=max_iterations, allowed_tools=body.options.allowed_tools,
        notify_webhook=body.options.notify_webhook,
    )
    await db.commit()
    await db.refresh(task)
    run_agent_task.delay(str(task.id))
    resp = _to_response(task, request)
    return JSONResponse(status_code=201, content=json.loads(resp.model_dump_json()))


@router.get("", response_model=TaskListResponse)
async def list_tasks(request: Request, user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db),
                     after: str | None = None, limit: int = Query(20, ge=1, le=100),
                     status: str | None = None, language: str | None = None,
                     created_after: datetime | None = None,
                     created_before: datetime | None = None, search: str | None = None):
    statuses = None
    if status:
        statuses = [TaskStatus(s) for s in status.split(",")]
    is_admin = user.role.value in ("admin", "operator")
    rows, next_cursor = await task_repo.list_tasks(
        db, user_id=user.id, is_admin=False, statuses=statuses, language=language,
        created_after=created_after, created_before=created_before, search=search,
        after_cursor=after, limit=limit)
    data = [_to_response(t, request) for t in rows]
    return TaskListResponse(data=data, pagination=PaginationMeta(
        next_cursor=next_cursor, has_more=next_cursor is not None, total=len(data)))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: UUID, request: Request, user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    is_admin = user.role.value in ("admin", "operator")
    task = await task_repo.get_task(db, task_id=task_id, user_id=user.id, is_admin=is_admin)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Task not found"})
    return _to_response(task, request)


@router.delete("/{task_id}", response_model=TaskResponse)
async def cancel_task(task_id: UUID, request: Request, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    is_admin = user.role.value in ("admin", "operator")
    ok = await task_repo.cancel_task(db, task_id=task_id, user_id=user.id, is_admin=is_admin)
    if not ok:
        task = await task_repo.get_task(db, task_id=task_id, user_id=user.id, is_admin=is_admin)
        if task is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Task not found"})
        raise HTTPException(status_code=409, detail={
            "code": "not_cancellable", "message": f"Task in status {task.status.value} cannot be cancelled"})
    await db.commit()
    # Cancellation sequence (BR-TASK-21): revoke Celery task, stop sandbox
    try:
        celery_app.control.revoke(str(task_id), terminate=True)
    except Exception as e:
        log.warning("celery_revoke_failed", task_id=str(task_id), error=str(e))
    sandbox_manager.destroy_session(str(task_id))
    emitter = EventEmitter(task_id)
    await emitter.emit_failed_cancelled()
    await emitter.close()
    task = await task_repo.get_task(db, task_id=task_id, user_id=user.id, is_admin=is_admin)
    return _to_response(task, request)


@router.get("/{task_id}/stream")
async def stream_task(task_id: UUID, request: Request, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    is_admin = user.role.value in ("admin", "operator")
    task = await task_repo.get_task(db, task_id=task_id, user_id=user.id, is_admin=is_admin)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Task not found"})

    last_event_id = request.headers.get("Last-Event-ID")
    after_step = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
    terminal = {TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled}

    async def event_generator():
        emitter = EventEmitter(task_id)
        # Replay missed events (BR-TASK-11)
        for step in await emitter.replay(after_step=after_step):
            yield {"id": str(step["step_number"]), "event": step["type"],
                   "data": json.dumps(step["data"], default=str)}
        await emitter.close()

        # If task already terminal, end after replay (BR-TASK-12)
        async with AsyncSession(db.bind) as fresh:
            t = await task_repo.get_task(fresh, task_id=task_id, user_id=user.id, is_admin=is_admin)
            if t and t.status in terminal:
                return

        # Live subscription
        redis = aioredis.from_url(settings.redis_cache_url, decode_responses=True)
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel_for(task_id))
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30.0)
                if msg is None:
                    yield {"event": "heartbeat", "data": "{}"}  # BR-FRONT-04
                    continue
                event = json.loads(msg["data"])
                yield {"id": str(event["id"]), "event": event["type"],
                       "data": json.dumps(event["data"], default=str)}
                if event["type"] in ("task_completed", "task_failed"):
                    break
        finally:
            await pubsub.unsubscribe(channel_for(task_id))
            await pubsub.aclose()
            await redis.aclose()

    return EventSourceResponse(event_generator())
```

- [ ] **Step 4: Add the cancelled-event helper to EventEmitter**

In `backend/app/orchestrator/events.py`, add this method to the `EventEmitter` class (after `replay`):

```python
    async def emit_failed_cancelled(self) -> int:
        """Emit a task_failed event with reason 'cancelled' (BR-TASK-21.5)."""
        return await self.emit(
            TaskStepType.report,
            {"error": "Task cancelled by user", "error_code": "cancelled", "retryable": False},
            sse_type="task_failed",
        )
```

- [ ] **Step 5: Wire the router into main.py**

In `backend/app/main.py`, after the existing auth import and include, add:

Modify the import line `from app.routers import auth` to:

```python
from app.routers import auth, tasks
```

Add after `app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])`:

```python
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_tasks/test_endpoints.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/tasks.py backend/app/main.py backend/app/orchestrator/events.py backend/tests/test_tasks/test_endpoints.py
git commit -m "feat(phase-1c): task CRUD endpoints (POST/GET/DELETE) + concurrency + clamping"
```

---

## Task 13: SSE Stream Test + Langfuse Wiring + Compose Worker + Final Integration

**Files:**
- Create: `backend/app/orchestrator/observability.py`
- Modify: `backend/app/orchestrator/runner.py` (attach Langfuse callback)
- Modify: `docker-compose.yml` (worker service)
- Modify: `docker-compose.override.yml` (worker dev hot-reload)
- Test: `backend/tests/test_tasks/test_sse_stream.py`

- [ ] **Step 1: Write the failing SSE replay test**

Create `backend/tests/test_tasks/test_sse_stream.py`:

```python
import uuid
import json
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.task import Task, TaskStatus, TaskStepType
from app.auth.password import hash_password
from app.auth.jwt import create_access_token
from app.repositories import task as task_repo
from app.orchestrator.events import EventEmitter


async def test_stream_replays_persisted_steps_for_terminal_task():
    async with AsyncSessionLocal() as db:
        u = User(email=f"sse-{uuid.uuid4()}@t.com", password_hash=hash_password("x"), language="en")
        db.add(u)
        await db.flush()
        t = await task_repo.create_task(db, user_id=u.id, goal="g", language="en",
                                        max_iterations=5, allowed_tools=None)
        t.status = TaskStatus.completed
        await db.commit()
        tid, token = t.id, create_access_token(str(u.id), u.role.value)

    emitter = EventEmitter(tid)
    await emitter.emit(TaskStepType.think, {"content": "thinking"})
    await emitter.emit(TaskStepType.report, {"summary": "done"}, sse_type="task_completed")
    await emitter.close()

    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"}
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10) as client:
        async with client.stream("GET", f"/api/v1/tasks/{tid}/stream", headers=headers) as resp:
            assert resp.status_code == 200
            body = ""
            async for chunk in resp.aiter_text():
                body += chunk
    assert "thinking" in body
    assert "task_completed" in body
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_tasks/test_sse_stream.py -v`
Expected: PASS if Task 12 implemented the stream correctly. If it hangs, the terminal-task early-return in `event_generator` needs verification. Fix `stream_task` so a terminal task returns after replay without subscribing.

- [ ] **Step 3: Implement observability.py**

Create `backend/app/orchestrator/observability.py`:

```python
"""Langfuse integration (spec §12). No-op when Langfuse is not configured."""
import structlog
from app.config import settings

log = structlog.get_logger()


def get_langfuse_callbacks() -> list:
    """Return a list of LangChain callback handlers for LLM tracing.
    Empty list when Langfuse keys are absent (dev default)."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return []
    try:
        from langfuse.callback import CallbackHandler
        return [CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host or "http://langfuse:3000",
        )]
    except Exception as e:
        log.warning("langfuse_init_failed", error=str(e))
        return []
```

- [ ] **Step 4: Attach Langfuse callbacks in the runner config**

In `backend/app/orchestrator/runner.py`, add the import near the top:

```python
from app.orchestrator.observability import get_langfuse_callbacks
```

Modify the `config` dict construction in `run_task` to include callbacks:

```python
        config = {"configurable": {"thread_id": task_id_str, "run_ctx": run_ctx},
                  "recursion_limit": max_iter * 4 + 10,
                  "callbacks": get_langfuse_callbacks()}
```

- [ ] **Step 5: Add the worker service to docker-compose.yml**

In `docker-compose.yml`, add a `worker` service that reuses the API image but runs Celery. Add after the `api` service definition:

```yaml
  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A app.worker.celery_app worker --loglevel=info --concurrency=4
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock   # sandbox container management
    networks:
      - agentis_default
```

- [ ] **Step 6: Add worker hot-reload to docker-compose.override.yml**

In `docker-compose.override.yml`, add:

```yaml
  worker:
    volumes:
      - ./backend:/app
      - /var/run/docker.sock:/var/run/docker.sock
    command: watchmedo auto-restart --directory=/app/app --pattern="*.py" --recursive -- celery -A app.worker.celery_app worker --loglevel=info --concurrency=2
    environment:
      AGENTIS_POSTGRES_DIRECT_URL: postgresql+asyncpg://agentis:agentis@postgres:5432/agentis
```

- [ ] **Step 7: Run the full test suite**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest -q -m "not slow"`
Expected: all prior + new tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/orchestrator/observability.py backend/app/orchestrator/runner.py docker-compose.yml docker-compose.override.yml backend/tests/test_tasks/test_sse_stream.py
git commit -m "feat(phase-1c): Langfuse callbacks + Celery worker compose service + SSE stream test"
```

---

## Task 14: End-to-End Integration Test (slow)

**Files:**
- Test: `backend/tests/test_integration_orchestrator.py`

- [ ] **Step 1: Write the slow integration test**

Create `backend/tests/test_integration_orchestrator.py`:

```python
"""End-to-end: submit a no-tool task through the full graph with a fake LLM,
verify it completes, persists steps, and is replayable. Marked slow because it
exercises the real PostgresSaver checkpointer."""
import uuid
import json
import pytest
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.task import Task, TaskStatus, TaskStep
from app.auth.password import hash_password
from app.repositories import task as task_repo
from app.orchestrator.runner import run_task
from sqlalchemy import select


class _FakeLLM(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@pytest.mark.slow
async def test_full_run_completes_and_persists_steps():
    async with AsyncSessionLocal() as db:
        u = User(email=f"e2e-{uuid.uuid4()}@t.com", password_hash=hash_password("x"), language="en")
        db.add(u)
        await db.flush()
        t = await task_repo.create_task(db, user_id=u.id, goal="greet the user", language="en",
                                        max_iterations=3, allowed_tools=[])
        await db.commit()
        tid = t.id

    llm = _FakeLLM(messages=iter([
        AIMessage(content=json.dumps({"subtasks": ["greet"]})),    # plan
        AIMessage(content="Hello, goal met."),                      # think → no tools → report
        AIMessage(content="I greeted the user."),                   # report
    ]))
    await run_task(str(tid), llm=llm, skip_sandbox=True)

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, tid)
        assert task.status == TaskStatus.completed
        assert task.total_steps >= 2
        steps = (await db.execute(
            select(TaskStep).where(TaskStep.task_id == tid).order_by(TaskStep.step_number)
        )).scalars().all()
        assert steps[0].step_number == 1
        assert any(s.step_type.value == "report" for s in steps)
```

- [ ] **Step 2: Run the slow test**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest tests/test_integration_orchestrator.py -v -m slow`
Expected: PASS (1 test). Requires Postgres (direct URL) + Redis up.

- [ ] **Step 3: Run the entire suite (fast)**

Run: `cd backend && PATH="$HOME/.local/bin:$PATH" pytest -q -m "not slow"`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_integration_orchestrator.py
git commit -m "test(phase-1c): end-to-end orchestrator integration test (slow)"
```

---

## Notes for the Implementer

- **GenericFakeChatModel import path:** `from langchain_core.language_models.fake_chat_models import GenericFakeChatModel`. If unavailable in the installed version, use `langchain_core.language_models.fake.FakeListChatModel` and adapt tests (it returns strings, not AIMessages — wrap accordingly). Verify the import early in Task 9.
- **Checkpointer tables:** `AsyncPostgresSaver.setup()` creates `checkpoints`, `checkpoint_writes`, `checkpoint_blobs` tables in the direct-Postgres database. These are LangGraph-managed (not Alembic). This is expected and documented in ADR-1C-01. Do not add them to Alembic migrations.
- **conftest env:** The existing `tests/conftest.py` sets `AGENTIS_POSTGRES_DIRECT_URL` to localhost:5436. Confirm `settings.checkpointer_dsn` resolves to a reachable psycopg DSN (`postgresql://...@localhost:5436/...`) in the test environment. If `postgres_direct_url` is not set for tests, add it to conftest env setdefaults.
- **Redis pub/sub in tests:** `EventEmitter` publishes to Redis even in unit tests; this is harmless (no subscriber). The `redis_cache_url` points at DB1 (localhost:6379/1) in tests.
- **No `allowed_tools=[]` vs `None`:** `[]` means "no tools allowed" (THINK gets no tool schemas → always reports). `None` means "all tools". The runner passes the task's stored value through unchanged.
- **Cancellation mid-run (BR-ORCH-41):** Full graceful in-loop cancellation (Redis shutdown flag checked each iteration) is deferred; Task 12 implements revoke + sandbox stop + status flip, which satisfies AC-TASK-20/21 for the common case. A follow-up can add the per-iteration shutdown-flag check in `think_node`.

---

## Self-Review (completed by plan author)

**Spec coverage:**
- TASK-1 submission + clamping + concurrency → Task 12 ✓
- TASK-3 cancellation (revoke + sandbox stop + event) → Task 12 ✓
- TASK-4 history/filtering/pagination → Task 5 + 12 ✓
- TASK-2 monitoring / SSE + Last-Event-ID replay + heartbeat → Task 6 + 12 + 13 ✓
- ORCH-1 LLM provider factory → Task 1 ✓
- ORCH-2 context window mgmt → Task 3 ✓
- ORCH-3 token budgets → Task 7 + runner ✓
- ORCH-4 retry/failure cap → routing (`max_total_failures`) ✓ (exponential backoff per-tool deferred — noted)
- §5.2 full ReAct graph + PostgresSaver → Task 9 + 10 ✓
- MEM-2 short-term memory → Task 4 + runner ✓
- Langfuse → Task 13 ✓
- Celery queue → Task 11 ✓

**Deferred (documented):** HITL WebSocket (Phase 2 per spec §20), long-term Qdrant memory (Phase 2), per-iteration graceful shutdown flag (noted), exponential tool backoff (noted). These are correctly out of Phase 1C scope or flagged as follow-ups.

**Type consistency:** `EventEmitter.emit(step_type, content, ...)` signature consistent across nodes/runner/router. `RunContext` fields consistent between `nodes.py` and `runner.py`. `task_repo` function signatures consistent between repository and router/tests.
