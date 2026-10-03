import asyncio
import time
import pytest
from unittest.mock import AsyncMock

from app.orchestrator.circuit_breaker import (
    CircuitBreaker, GuardedChatModel, LLMUnavailableError, get_circuit_breaker,
)


def test_breaker_closed_initially():
    breaker = CircuitBreaker()
    assert breaker.is_open() is False


def test_breaker_opens_after_threshold_failures_in_window():
    breaker = CircuitBreaker(failure_threshold=3, window_s=60, cooldown_s=30)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open() is False
    breaker.record_failure()
    assert breaker.is_open() is True


def test_breaker_ignores_failures_outside_window():
    breaker = CircuitBreaker(failure_threshold=3, window_s=0.05, cooldown_s=30)
    breaker.record_failure()
    breaker.record_failure()
    time.sleep(0.1)  # both failures age out of the window
    breaker.record_failure()
    assert breaker.is_open() is False


def test_breaker_closes_after_cooldown():
    breaker = CircuitBreaker(failure_threshold=1, window_s=60, cooldown_s=0.05)
    breaker.record_failure()
    assert breaker.is_open() is True
    time.sleep(0.1)
    assert breaker.is_open() is False


def test_success_clears_failure_history():
    breaker = CircuitBreaker(failure_threshold=3, window_s=60, cooldown_s=30)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    assert breaker.is_open() is False  # only 1 failure since the reset


def test_get_circuit_breaker_returns_same_instance_for_same_key():
    a = get_circuit_breaker("anthropic:claude-test")
    b = get_circuit_breaker("anthropic:claude-test")
    assert a is b


def test_get_circuit_breaker_isolates_different_keys():
    a = get_circuit_breaker("anthropic:claude-isolated-a")
    b = get_circuit_breaker("groq:llama-isolated-b")
    a.record_failure()
    a.record_failure()
    a.record_failure()
    assert a.is_open() is True
    assert b.is_open() is False


@pytest.mark.asyncio
async def test_guarded_ainvoke_raises_when_open():
    inner = AsyncMock()
    breaker = CircuitBreaker(failure_threshold=1, window_s=60, cooldown_s=30)
    breaker.record_failure()
    guarded = GuardedChatModel(inner, breaker, timeout_s=1)

    with pytest.raises(LLMUnavailableError):
        await guarded.ainvoke(["msg"])
    inner.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_guarded_ainvoke_passes_through_on_success():
    inner = AsyncMock()
    inner.ainvoke = AsyncMock(return_value="ok")
    breaker = CircuitBreaker()
    guarded = GuardedChatModel(inner, breaker, timeout_s=1)

    result = await guarded.ainvoke(["msg"])
    assert result == "ok"
    assert breaker.is_open() is False


@pytest.mark.asyncio
async def test_guarded_ainvoke_retries_once_on_timeout_then_succeeds():
    inner = AsyncMock()
    calls = {"n": 0}

    async def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(10)  # will exceed the tiny timeout below
        return "ok"

    inner.ainvoke = flaky
    breaker = CircuitBreaker()
    guarded = GuardedChatModel(inner, breaker, timeout_s=0.05)

    result = await guarded.ainvoke(["msg"])
    assert result == "ok"
    assert calls["n"] == 2
    assert breaker.is_open() is False  # single timeout doesn't count as a failure


@pytest.mark.asyncio
async def test_guarded_ainvoke_second_timeout_records_failure():
    inner = AsyncMock()

    async def always_slow(*a, **kw):
        await asyncio.sleep(10)

    inner.ainvoke = always_slow
    breaker = CircuitBreaker(failure_threshold=1)
    guarded = GuardedChatModel(inner, breaker, timeout_s=0.02)

    with pytest.raises(asyncio.TimeoutError):
        await guarded.ainvoke(["msg"])
    assert breaker.is_open() is True


@pytest.mark.asyncio
async def test_guarded_ainvoke_non_timeout_error_records_failure_immediately():
    inner = AsyncMock()
    inner.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
    breaker = CircuitBreaker(failure_threshold=1)
    guarded = GuardedChatModel(inner, breaker, timeout_s=1)

    with pytest.raises(RuntimeError):
        await guarded.ainvoke(["msg"])
    assert breaker.is_open() is True
    inner.ainvoke.assert_awaited_once()  # no retry for non-timeout errors


@pytest.mark.asyncio
async def test_bind_tools_returns_guarded_wrapper_sharing_breaker():
    inner = AsyncMock()
    bound_inner = AsyncMock()
    bound_inner.ainvoke = AsyncMock(return_value="bound-ok")
    inner.bind_tools = lambda tools, **kw: bound_inner
    breaker = CircuitBreaker()
    guarded = GuardedChatModel(inner, breaker, timeout_s=1)

    bound = guarded.bind_tools(["fake_tool"])
    assert isinstance(bound, GuardedChatModel)
    assert bound._breaker is breaker
    result = await bound.ainvoke(["msg"])
    assert result == "bound-ok"
