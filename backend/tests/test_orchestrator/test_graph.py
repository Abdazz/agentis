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
