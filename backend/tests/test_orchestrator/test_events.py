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
