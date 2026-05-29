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
