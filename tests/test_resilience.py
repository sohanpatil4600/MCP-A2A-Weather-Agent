import asyncio
import unittest

from server.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    ResilienceContext,
    RetryPolicy,
)


class RetryPolicyTests(unittest.TestCase):
    def test_backoff_duration_increases_with_exponential_base(self) -> None:
        policy = RetryPolicy(
            initial_backoff_ms=100,
            backoff_multiplier=2.0,
            jitter_factor=0.0,
        )

        duration_0 = policy.backoff_duration(0)
        duration_1 = policy.backoff_duration(1)
        duration_2 = policy.backoff_duration(2)

        self.assertAlmostEqual(duration_0, 0.1, places=2)
        self.assertAlmostEqual(duration_1, 0.2, places=2)
        self.assertAlmostEqual(duration_2, 0.4, places=2)

    def test_backoff_duration_capped_at_max(self) -> None:
        policy = RetryPolicy(
            initial_backoff_ms=100,
            max_backoff_ms=500,
            backoff_multiplier=10.0,
            jitter_factor=0.0,
        )

        duration_0 = policy.backoff_duration(0)
        duration_10 = policy.backoff_duration(10)

        self.assertAlmostEqual(duration_0, 0.1, places=2)
        self.assertLessEqual(duration_10, 0.5)


class CircuitBreakerTests(unittest.TestCase):
    def test_circuit_breaker_starts_closed(self) -> None:
        cb = CircuitBreaker("test", CircuitBreakerConfig())
        self.assertEqual(cb.metrics.state, CircuitState.CLOSED)
        self.assertTrue(cb.can_execute())

    def test_circuit_breaker_opens_after_threshold_failures(self) -> None:
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", config)

        for _ in range(3):
            cb.record_failure()

        self.assertEqual(cb.metrics.state, CircuitState.OPEN)
        self.assertFalse(cb.can_execute())

    def test_circuit_breaker_half_opens_after_recovery_timeout(self) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout_s=1,
        )
        cb = CircuitBreaker("test", config)

        cb.record_failure()
        self.assertEqual(cb.metrics.state, CircuitState.OPEN)

        asyncio.run(asyncio.sleep(1.1))

        self.assertTrue(cb.can_execute())
        self.assertEqual(cb.metrics.state, CircuitState.HALF_OPEN)

    def test_circuit_breaker_recovers_to_closed_on_success_in_half_open(self) -> None:
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold_half_open=2,
        )
        cb = CircuitBreaker("test", config)

        cb.record_failure()
        cb.metrics.state = CircuitState.HALF_OPEN
        cb.metrics.success_count_half_open = 0

        cb.record_success()
        cb.record_success()

        self.assertEqual(cb.metrics.state, CircuitState.CLOSED)

    def test_circuit_breaker_tracks_metrics(self) -> None:
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=5))

        cb.record_success()
        self.assertEqual(cb.metrics.total_requests, 1)
        self.assertEqual(cb.metrics.total_failures, 0)

        for _ in range(3):
            cb.record_failure()

        self.assertEqual(cb.metrics.total_requests, 4)
        self.assertEqual(cb.metrics.total_failures, 3)


class ResilienceContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_with_resilience_succeeds_on_first_attempt(self) -> None:
        ctx = ResilienceContext()

        result = await ctx.execute_with_resilience(
            call_name="test",
            coro_fn=lambda: asyncio.sleep(0),
        )

        self.assertIsNone(result)

    async def test_execute_with_resilience_retries_on_exception(self) -> None:
        ctx = ResilienceContext()
        attempt_count = 0

        async def failing_call() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ValueError("transient error")
            return "success"

        result = await ctx.execute_with_resilience(
            call_name="test",
            coro_fn=failing_call,
            timeout_s=5.0,
        )

        self.assertEqual(result, "success")
        self.assertEqual(attempt_count, 2)

    async def test_execute_with_resilience_opens_breaker_on_persistent_failure(self) -> None:
        ctx = ResilienceContext()

        async def always_fails() -> None:
            raise RuntimeError("persistent error")

        breaker = ctx.get_breaker("test", CircuitBreakerConfig(failure_threshold=2))

        for i in range(2):
            try:
                await ctx.execute_with_resilience(
                    call_name="test",
                    coro_fn=always_fails,
                    timeout_s=0.1,
                )
            except RuntimeError:
                pass

        self.assertEqual(breaker.metrics.state, CircuitState.OPEN)
        self.assertFalse(breaker.can_execute())

    async def test_execute_with_resilience_enforces_timeout(self) -> None:
        ctx = ResilienceContext()

        async def slow_call() -> None:
            await asyncio.sleep(10)

        with self.assertRaises((RuntimeError, asyncio.TimeoutError)):
            await ctx.execute_with_resilience(
                call_name="test",
                coro_fn=slow_call,
                timeout_s=0.1,
            )

    async def test_execute_with_resilience_calls_retry_callback(self) -> None:
        ctx = ResilienceContext()
        retry_events = []

        async def failing_call() -> str:
            raise ValueError("test error")

        def on_retry_capture(attempt: int, exc: Exception) -> None:
            retry_events.append((attempt, type(exc).__name__))

        with self.assertRaises((RuntimeError, ValueError)):
            await ctx.execute_with_resilience(
                call_name="test",
                coro_fn=failing_call,
                timeout_s=5.0,
                on_retry=on_retry_capture,
            )

        self.assertGreater(len(retry_events), 0)


if __name__ == "__main__":
    unittest.main()
