"""
Resilience patterns for robust operation

This module implements circuit breakers, rate limiting, and retry logic
to ensure kubectl-smart operates reliably even when facing API issues.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

import structlog

logger = structlog.get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout_seconds: float = 60.0  # Time before trying half-open
    window_seconds: float = 10.0  # Sliding window for failure counting


class CircuitBreaker:
    """Circuit breaker pattern implementation

    Prevents cascading failures by stopping calls to failing services.
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change = time.time()

    def record_success(self) -> None:
        """Record a successful operation"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0  # Reset failures on success

    def record_failure(self) -> None:
        """Record a failed operation"""
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self._transition_to_open()
        elif self.state == CircuitState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.config.failure_threshold:
                self._transition_to_open()

    def can_proceed(self) -> bool:
        """Check if operation can proceed

        Returns:
            True if operation should proceed, False if rejected
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed
            if self.last_failure_time:
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.config.timeout_seconds:
                    self._transition_to_half_open()
                    return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return True

        return False

    def _transition_to_open(self) -> None:
        """Transition to OPEN state"""
        logger.warning(
            "Circuit breaker opened",
            name=self.name,
            failure_count=self.failure_count
        )
        self.state = CircuitState.OPEN
        self.last_state_change = time.time()

    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state"""
        logger.info("Circuit breaker half-open, testing recovery", name=self.name)
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        self.last_state_change = time.time()

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state"""
        logger.info("Circuit breaker closed, service recovered", name=self.name)
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change = time.time()


class RateLimiter:
    """Token bucket rate limiter

    Limits the rate of operations to prevent overwhelming the API.
    """

    def __init__(
        self,
        max_calls: int = 100,  # Max calls per period
        period_seconds: float = 60.0,  # Time period
    ):
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self.calls: deque = deque()

    async def acquire(self) -> None:
        """Acquire permission to make a call (blocks if rate exceeded)"""
        now = time.time()

        # Remove old calls outside the window
        while self.calls and self.calls[0] < now - self.period_seconds:
            self.calls.popleft()

        # Check if we're at the limit
        if len(self.calls) >= self.max_calls:
            # Calculate how long to wait
            oldest_call = self.calls[0]
            wait_time = (oldest_call + self.period_seconds) - now

            if wait_time > 0:
                logger.debug(
                    "Rate limit reached, waiting",
                    wait_seconds=wait_time,
                    calls_in_window=len(self.calls)
                )
                await asyncio.sleep(wait_time)

                # Try again after waiting
                await self.acquire()
                return

        # Record this call
        self.calls.append(time.time())

    def get_stats(self) -> dict:
        """Get rate limiter statistics"""
        now = time.time()
        recent_calls = sum(1 for t in self.calls if t > now - self.period_seconds)

        return {
            'recent_calls': recent_calls,
            'max_calls': self.max_calls,
            'period_seconds': self.period_seconds,
            'utilization': recent_calls / self.max_calls if self.max_calls > 0 else 0
        }


class RetryStrategy:
    """Exponential backoff retry strategy"""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 10.0,
        exponential_base: float = 2.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number

        Args:
            attempt: Attempt number (0-based)

        Returns:
            Delay in seconds
        """
        delay = self.base_delay * (self.exponential_base ** attempt)
        return min(delay, self.max_delay)

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> any:
        """Execute function with retry logic

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func

        Raises:
            Last exception if all retries exhausted
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if attempt < self.max_retries:
                    delay = self.get_delay(attempt)
                    logger.debug(
                        "Retry attempt failed, backing off",
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        delay=delay,
                        error=str(e)
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "All retry attempts exhausted",
                        attempts=attempt + 1,
                        error=str(e)
                    )

        raise last_exception


# Global instances for common use
default_circuit_breaker = CircuitBreaker("default")
default_rate_limiter = RateLimiter(max_calls=100, period_seconds=60)
default_retry_strategy = RetryStrategy(max_retries=3)


async def with_resilience(
    func: Callable,
    *args,
    circuit_breaker: Optional[CircuitBreaker] = None,
    rate_limiter: Optional[RateLimiter] = None,
    retry_strategy: Optional[RetryStrategy] = None,
    **kwargs
) -> any:
    """Execute function with full resilience patterns

    Args:
        func: Async function to execute
        *args: Positional arguments
        circuit_breaker: Optional circuit breaker (uses default if None)
        rate_limiter: Optional rate limiter (uses default if None)
        retry_strategy: Optional retry strategy (uses default if None)
        **kwargs: Keyword arguments

    Returns:
        Result of func

    Raises:
        Exception if circuit is open or retries exhausted
    """
    cb = circuit_breaker or default_circuit_breaker
    rl = rate_limiter or default_rate_limiter
    rs = retry_strategy or default_retry_strategy

    # Check circuit breaker
    if not cb.can_proceed():
        raise Exception(f"Circuit breaker {cb.name} is open, rejecting request")

    # Rate limiting
    await rl.acquire()

    # Execute with retry
    try:
        result = await rs.execute(func, *args, **kwargs)
        cb.record_success()
        return result
    except Exception as e:
        cb.record_failure()
        raise
