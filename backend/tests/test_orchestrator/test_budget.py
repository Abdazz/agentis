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
