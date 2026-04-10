from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Generic, TypeVar
import asyncio
import random
import time

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RetryPolicy:
    max_retries: int = 3
    initial_backoff_ms: int = 100
    max_backoff_ms: int = 5000
    backoff_multiplier: float = 2.0
    jitter_factor: float = 0.1

    def backoff_duration(self, attempt: int) -> float:
        """Calculate backoff duration in seconds for given attempt number."""
        base_ms = min(
            self.initial_backoff_ms * (self.backoff_multiplier ** attempt),
            self.max_backoff_ms,
        )
        jitter = base_ms * self.jitter_factor * random.uniform(-1, 1)
        return (base_ms + jitter) / 1000.0


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout_s: int = 60
    success_threshold_half_open: int = 2


@dataclass
class CircuitBreakerMetrics:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count_half_open: int = 0
    last_failure_at: str | None = None
    last_state_change_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_requests: int = 0
    total_failures: int = 0


class CircuitBreaker(Generic[T]):
    """Circuit breaker for protecting against cascading failures."""

    def __init__(self, name: str, config: CircuitBreakerConfig) -> None:
        self.name = name
        self.config = config
        self.metrics = CircuitBreakerMetrics()

    def record_success(self) -> None:
        self.metrics.total_requests += 1
        if self.metrics.state == CircuitState.CLOSED:
            self.metrics.failure_count = 0
        elif self.metrics.state == CircuitState.HALF_OPEN:
            self.metrics.success_count_half_open += 1
            if self.metrics.success_count_half_open >= self.config.success_threshold_half_open:
                self._transition_to(CircuitState.CLOSED)
                self.metrics.failure_count = 0
                self.metrics.success_count_half_open = 0

    def record_failure(self) -> None:
        self.metrics.total_requests += 1
        self.metrics.total_failures += 1
        self.metrics.failure_count += 1
        self.metrics.last_failure_at = datetime.now(timezone.utc).isoformat()

        if self.metrics.state == CircuitState.CLOSED:
            if self.metrics.failure_count >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)
        elif self.metrics.state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)

    def can_execute(self) -> bool:
        if self.metrics.state == CircuitState.CLOSED:
            return True
        elif self.metrics.state == CircuitState.HALF_OPEN:
            return True
        elif self.metrics.state == CircuitState.OPEN:
            last_change = datetime.fromisoformat(self.metrics.last_state_change_at)
            elapsed = (datetime.now(timezone.utc) - last_change).total_seconds()
            if elapsed >= self.config.recovery_timeout_s:
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            return False
        return False

    def _transition_to(self, new_state: CircuitState) -> None:
        old_state = self.metrics.state
        self.metrics.state = new_state
        self.metrics.last_state_change_at = datetime.now(timezone.utc).isoformat()
        if new_state == CircuitState.HALF_OPEN:
            self.metrics.success_count_half_open = 0


class ResilienceContext:
    """Container for retry and circuit breaker logic."""

    def __init__(self) -> None:
        self.circuit_breakers: dict[str, CircuitBreaker] = {}
        self.retry_policy = RetryPolicy()

    def get_breaker(self, name: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(
                name, config or CircuitBreakerConfig()
            )
        return self.circuit_breakers[name]

    async def execute_with_resilience(
        self,
        call_name: str,
        coro_fn: Callable[[], Any],
        timeout_s: float = 10.0,
        on_retry: Callable[[int, Exception], None] | None = None,
        on_failure: Callable[[Exception], None] | None = None,
    ) -> str:
        """Execute an async call with retry and circuit breaker protection."""
        breaker = self.get_breaker(call_name)

        if not breaker.can_execute():
            raise RuntimeError(
                f"Circuit breaker {call_name} is {breaker.metrics.state.value}"
            )

        last_error = None
        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                result = await asyncio.wait_for(coro_fn(), timeout=timeout_s)
                breaker.record_success()
                return result
            except asyncio.TimeoutError as e:
                last_error = e
                if on_retry:
                    on_retry(attempt, e)
            except Exception as e:
                last_error = e
                if on_retry:
                    on_retry(attempt, e)

            breaker.record_failure()

            if attempt < self.retry_policy.max_retries:
                backoff = self.retry_policy.backoff_duration(attempt)
                await asyncio.sleep(backoff)

        if on_failure:
            on_failure(last_error or RuntimeError("Unknown error"))

        raise last_error or RuntimeError(
            f"{call_name} failed after {self.retry_policy.max_retries + 1} attempts"
        )
