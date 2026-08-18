"""LLM circuit breaker (Feature ORCH-1, BR-ORCH-03/04).

Wraps a constructed LangChain chat model so every orchestrator node gets the
same protection without changing call sites (nodes.py keeps calling
``ctx.llm.ainvoke(...)`` / ``ctx.llm.bind_tools(tools).ainvoke(...)``).

Deliberately NOT wired into build_llm() itself: build_llm() is a pure
provider factory (its own docstring: "no provider-specific code outside
this module") and is unit-tested against raw ChatAnthropic/ChatOpenAI
instances. The breaker is a separate concern layered on top by the caller
(runner.py) that actually drives the agent loop.
"""
import asyncio
import threading
import time


class LLMUnavailableError(Exception):
    """Raised when the circuit breaker is open (BR-ORCH-03)."""


class CircuitBreaker:
    """Sliding-window failure counter with a cooldown (BR-ORCH-03):
    3 failures in 60 seconds opens the circuit; it stays open for a
    30-second cooldown before allowing calls again."""

    def __init__(self, failure_threshold: int = 3, window_s: float = 60.0,
                 cooldown_s: float = 30.0):
        self._threshold = failure_threshold
        self._window_s = window_s
        self._cooldown_s = cooldown_s
        self._failures: list[float] = []
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if time.monotonic() - self._opened_at >= self._cooldown_s:
                # Cooldown elapsed: close the circuit and start fresh.
                self._opened_at = None
                self._failures.clear()
                return False
            return True

    def record_failure(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._failures.append(now)
            self._failures = [t for t in self._failures if now - t <= self._window_s]
            if len(self._failures) >= self._threshold:
                self._opened_at = now

    def record_success(self) -> None:
        with self._lock:
            self._failures.clear()


_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_circuit_breaker(key: str) -> CircuitBreaker:
    """One breaker per (provider, model) so an outage on one provider
    (e.g. an org's Groq override) doesn't trip the breaker for another
    org running on the default Anthropic config."""
    with _breakers_lock:
        breaker = _breakers.get(key)
        if breaker is None:
            breaker = CircuitBreaker()
            _breakers[key] = breaker
        return breaker


class GuardedChatModel:
    """Duck-typed wrapper exposing the same .ainvoke()/.bind_tools()
    surface LangChain BaseChatModel exposes, so it's a drop-in for
    RunContext.llm (typed `Any` — see orchestrator/nodes.py)."""

    def __init__(self, inner, breaker: CircuitBreaker, timeout_s: int = 120):
        self._inner = inner
        self._breaker = breaker
        self._timeout_s = timeout_s

    def bind_tools(self, tools, **kwargs):
        bound = self._inner.bind_tools(tools, **kwargs)
        return GuardedChatModel(bound, self._breaker, self._timeout_s)

    async def ainvoke(self, *args, **kwargs):
        if self._breaker.is_open():
            raise LLMUnavailableError(
                "LLM circuit breaker open — provider unavailable "
                f"(>= {self._breaker._threshold} failures in the last "
                f"{self._breaker._window_s:.0f}s)"
            )

        # BR-ORCH-04: on timeout, retry once; only a second timeout counts
        # as a failure. Any non-timeout error counts immediately.
        for attempt in (1, 2):
            try:
                result = await asyncio.wait_for(
                    self._inner.ainvoke(*args, **kwargs), timeout=self._timeout_s
                )
                self._breaker.record_success()
                return result
            except asyncio.TimeoutError:
                if attempt == 2:
                    self._breaker.record_failure()
                    raise
                continue
            except Exception:
                self._breaker.record_failure()
                raise
