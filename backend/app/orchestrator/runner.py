"""Task runner: orchestrates sandbox lifecycle, graph execution, status
transitions, budgets, and cancellation (Features TASK-1/3, ORCH-3/5)."""
from datetime import datetime, timezone
from uuid import UUID
import structlog
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
from app.orchestrator.observability import get_langfuse_callbacks

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
        parent_task_id = task.parent_task_id  # None for top-level tasks

        # Load user and their active org for LLM override + budget (BR-ADMIN-21, BR-ORCH-20)
        from sqlalchemy import select as _select
        from app.models.org import Organization
        from app.models.user import User as _User
        user_row = await db.get(_User, user_id)
        org_llm_provider = None
        org_llm_model = None
        org_monthly_budget = None
        org_id_for_budget = None
        if user_row is not None and user_row.active_organization_id is not None:
            result = await db.execute(
                _select(Organization).where(
                    Organization.id == user_row.active_organization_id,
                    Organization.deleted_at.is_(None),
                )
            )
            org = result.scalar_one_or_none()
            if org is not None:
                org_llm_provider = org.llm_provider
                org_llm_model = org.llm_model
                org_monthly_budget = org.token_budget_monthly
                org_id_for_budget = org.id

    await _set_status(task_id, TaskStatus.planning, started_at=datetime.now(timezone.utc))

    try:
        if not skip_sandbox:
            session = await sandbox_manager.create_session(task_id_str)
            sandbox_endpoint = session.endpoint

        llm = llm or build_llm(provider=org_llm_provider, model=org_llm_model)
        memory_block = await stm.build_context_block(str(user_id), max_tokens=500)
        run_ctx = RunContext(llm=llm, emitter=emitter, sandbox_endpoint=sandbox_endpoint,
                             user_id=str(user_id), task_id=task_id_str,
                             allowed_tools=allowed_tools, memory_block=memory_block,
                             org_id=str(org_id_for_budget) if org_id_for_budget else None,
                             org_monthly_budget=org_monthly_budget)

        initial: AgentState = {
            "task_id": task_id_str, "user_id": str(user_id), "goal": goal,
            "language": language, "messages": [], "scratchpad": "", "iteration": 0,
            "max_iterations": max_iter, "confidence": 0.0,
            "allowed_tools": allowed_tools or [], "artifacts": [], "failures": 0,
            "partial": False, "done": False,
        }

        await _set_status(task_id, TaskStatus.running)
        config = {"configurable": {"thread_id": task_id_str, "run_ctx": run_ctx},
                  "recursion_limit": max_iter * 4 + 10,
                  "callbacks": get_langfuse_callbacks()}

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
        # Notify supervisor if this is a child task (Phase 4A)
        if parent_task_id is not None:
            try:
                from app.services.agent_team_bus import get_agent_team_bus
                bus = get_agent_team_bus()
                await bus.publish(str(parent_task_id), {
                    "subtask_id": task_id_str,
                    "status": "completed",
                    "result": summary,
                })
            except Exception:
                log.warning("agent_bus_publish_failed", task_id=task_id_str)
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
