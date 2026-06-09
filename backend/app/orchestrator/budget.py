"""Token budget enforcement (Feature ORCH-3). Checked before each LLM call."""
from typing import Optional
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.user import User


class BudgetExceeded(Exception):
    def __init__(self, scope: str):
        self.scope = scope
        super().__init__(f"Token budget exceeded: {scope}")


async def check_budgets(
    db: AsyncSession,
    *,
    user_id: UUID,
    task_tokens_so_far: int,
    estimated_next: int,
    per_task_budget: int | None = None,
    user_monthly_budget: int | None = None,
    org_id: Optional[UUID] = None,
    org_monthly_budget: Optional[int] = None,
) -> None:
    """Raise BudgetExceeded if the next LLM call would breach any budget
    (BR-ORCH-20/21). Caller halts gracefully with a partial report (BR-ORCH-22)."""
    per_task_budget = per_task_budget or settings.token_budget_per_task
    user_monthly_budget = user_monthly_budget or settings.token_budget_user_monthly

    if task_tokens_so_far + estimated_next > per_task_budget:
        raise BudgetExceeded("per_task")

    used_user = (await db.execute(
        select(User.token_used_this_month).where(User.id == user_id)
    )).scalar_one_or_none() or 0
    if used_user + estimated_next > user_monthly_budget:
        raise BudgetExceeded("user_monthly")

    # Per-org monthly budget check (BR-ORCH-20 tier 3)
    if org_id is not None and org_monthly_budget is not None:
        from app.models.task import Task, TaskStep
        used_org = (await db.execute(
            select(func.coalesce(func.sum(TaskStep.tokens_used), 0))
            .join(Task, Task.id == TaskStep.task_id)
            .join(User, User.id == Task.user_id)
            .where(User.active_organization_id == org_id)
        )).scalar_one_or_none() or 0
        if used_org + estimated_next > org_monthly_budget:
            raise BudgetExceeded("org_monthly")


async def record_usage(db: AsyncSession, *, user_id: UUID, tokens: int) -> None:
    """Increment the user's monthly token counter (BR-ORCH-24)."""
    user = await db.get(User, user_id)
    if user is not None:
        user.token_used_this_month = (user.token_used_this_month or 0) + tokens
