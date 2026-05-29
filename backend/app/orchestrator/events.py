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
