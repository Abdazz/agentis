"""Task CRUD + SSE endpoints (Features TASK-1/3/4, §15.3)."""
import json
from datetime import datetime
from uuid import UUID
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
import redis.asyncio as aioredis
from app.config import settings
from app.database import get_db, AsyncSessionLocal
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.task import TaskStatus
from app.repositories import task as task_repo
from app.schemas.task import TaskCreate, TaskResponse, TaskListResponse, PaginationMeta
from app.orchestrator.events import EventEmitter, channel_for
from app.worker.tasks import run_agent_task
from app.worker.celery_app import celery_app
from app.sandbox.manager import sandbox_manager
from sqlalchemy import select
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
    from app.models.org import Organization

    # Load user's active org (if any)
    org = None
    if user.active_organization_id is not None:
        result = await db.execute(
            select(Organization).where(
                Organization.id == user.active_organization_id,
                Organization.deleted_at.is_(None),
            )
        )
        org = result.scalar_one_or_none()

    # Concurrency limit from org or default 5 (BR-TASK-07)
    max_concurrent = org.max_concurrent_tasks if org is not None else 5
    running = await task_repo.count_running_tasks(db, user_id=user.id)
    if running >= max_concurrent:
        raise HTTPException(status_code=429, detail={
            "code": "concurrency_limit",
            "message": f"You have reached the maximum of {max_concurrent} concurrent running tasks.",
        })

    # Per-org tool restriction enforcement (BR-ADMIN-13)
    requested_tools = body.options.allowed_tools
    if org is not None and org.allowed_tools is not None:
        allowed_set = set(org.allowed_tools)
        if requested_tools:
            disallowed = set(requested_tools) - allowed_set
            if disallowed:
                raise HTTPException(status_code=422, detail={
                    "code": "invalid_input",
                    "message": f"Tools not allowed for this organization: {sorted(disallowed)}",
                })
        else:
            # Default to org's allowed tools when none specified
            requested_tools = org.allowed_tools

    # Defaults + clamping (BR-TASK-02/03)
    language = body.language or user.language
    requested = body.options.max_iterations or settings.default_max_iterations
    max_iterations = min(requested, settings.max_iterations_cap)
    task = await task_repo.create_task(
        db, user_id=user.id, goal=body.goal, language=language,
        max_iterations=max_iterations, allowed_tools=requested_tools,
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
    # Read status before cancel to detect idempotent re-cancel (BR-TASK-23)
    existing = await task_repo.get_task(db, task_id=task_id, user_id=user.id, is_admin=is_admin)
    if existing is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Task not found"})
    already_cancelled = existing.status == TaskStatus.cancelled
    ok = await task_repo.cancel_task(db, task_id=task_id, user_id=user.id, is_admin=is_admin)
    if not ok:
        raise HTTPException(status_code=409, detail={
            "code": "not_cancellable",
            "message": f"Task in status {existing.status.value} cannot be cancelled"})
    await db.commit()
    if not already_cancelled:
        # Cancellation sequence (BR-TASK-21): revoke Celery task, stop sandbox, emit event
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


@router.get("/{task_id}/subtasks", response_model=list[TaskResponse])
async def list_subtasks(
    task_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    """Return child tasks for a supervisor task (Phase 4A)."""
    from app.models.task import Task
    parent = await db.get(Task, task_id)
    if parent is None or parent.deleted_at is not None or parent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Task not found"})
    result = await db.execute(
        select(Task).where(
            Task.parent_task_id == task_id,
            Task.deleted_at.is_(None),
        ).order_by(Task.created_at)
    )
    return [_to_response(t, request) for t in result.scalars().all()]


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
        async with AsyncSessionLocal() as fresh:
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
