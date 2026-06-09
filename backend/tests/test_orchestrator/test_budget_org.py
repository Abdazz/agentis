import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.orchestrator.budget import check_budgets, BudgetExceeded


@pytest.mark.asyncio
async def test_org_budget_not_exceeded():
    """Should not raise when org budget has room."""
    mock_db = AsyncMock()
    # Two execute calls: user monthly used, then org monthly used
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=lambda: 100_000),   # user monthly
        MagicMock(scalar_one_or_none=lambda: 500_000),   # org monthly
    ])
    await check_budgets(
        mock_db,
        user_id=uuid.uuid4(),
        task_tokens_so_far=5_000,
        estimated_next=1_000,
        per_task_budget=200_000,
        user_monthly_budget=2_000_000,
        org_id=uuid.uuid4(),
        org_monthly_budget=1_000_000,
    )
    # No exception = org budget not exceeded


@pytest.mark.asyncio
async def test_org_budget_exceeded():
    """Should raise BudgetExceeded('org_monthly') when org is over budget."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=lambda: 100_000),    # user monthly (OK)
        MagicMock(scalar_one_or_none=lambda: 999_500),    # org monthly (nearly full)
    ])
    with pytest.raises(BudgetExceeded) as exc_info:
        await check_budgets(
            mock_db,
            user_id=uuid.uuid4(),
            task_tokens_so_far=0,
            estimated_next=1_000,
            per_task_budget=200_000,
            user_monthly_budget=2_000_000,
            org_id=uuid.uuid4(),
            org_monthly_budget=1_000_000,
        )
    assert exc_info.value.scope == "org_monthly"


@pytest.mark.asyncio
async def test_no_org_budget_skips_org_check():
    """When org_id or org_monthly_budget is None, org check is skipped."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: 0))
    await check_budgets(
        mock_db,
        user_id=uuid.uuid4(),
        task_tokens_so_far=0,
        estimated_next=1_000,
        per_task_budget=200_000,
        user_monthly_budget=2_000_000,
        org_id=None,
        org_monthly_budget=None,
    )
    # Only one execute call for user budget, not two
    assert mock_db.execute.call_count == 1
