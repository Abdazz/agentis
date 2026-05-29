import pytest
from app.memory.short_term import ShortTermMemory


@pytest.fixture
async def stm():
    m = ShortTermMemory()
    uid = "test-user-stm"
    await m.clear(uid)
    yield m, uid
    await m.clear(uid)
    await m.close()


async def test_store_and_get_recent_summaries(stm):
    m, uid = stm
    await m.store_task_summary(uid, "Did task A")
    await m.store_task_summary(uid, "Did task B")
    recent = await m.get_recent_summaries(uid)
    assert recent[0] == "Did task B"  # most recent first (LPUSH)
    assert "Did task A" in recent


async def test_recent_summaries_capped_at_20(stm):
    m, uid = stm
    for i in range(25):
        await m.store_task_summary(uid, f"summary {i}")
    recent = await m.get_recent_summaries(uid)
    assert len(recent) == 20


async def test_store_and_get_prefs(stm):
    m, uid = stm
    await m.store_pref(uid, "language", "prefers tables in English")
    prefs = await m.get_prefs(uid)
    assert prefs["language"] == "prefers tables in English"


async def test_build_context_block_respects_token_budget(stm):
    m, uid = stm
    for i in range(20):
        await m.store_task_summary(uid, "x" * 500)
    block = await m.build_context_block(uid, max_tokens=100)
    from app.orchestrator.context import count_tokens
    assert count_tokens(block) <= 120  # small allowance over budget for headers
