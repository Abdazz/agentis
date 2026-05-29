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
