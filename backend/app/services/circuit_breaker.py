"""Generic per-(module:action) circuit breaker — in-process only.

NOTE: This is a process-local implementation (asyncio.Lock + in-memory dict).
Multi-worker deployments will have independent circuit-breaker states per
worker process.  Cross-worker consistency requires a DB-backed variant
(挂点 for future).

States: CLOSED → OPEN (on N consecutive failures) → HALF_OPEN (after recovery_timeout) → CLOSED or OPEN
"""

import time
import asyncio
import logging
from typing import Literal

from app.core.exceptions import AppException

logger = logging.getLogger("v2.circuit_breaker")

CircuitState = Literal["CLOSED", "OPEN", "HALF_OPEN"]


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state: CircuitState = "CLOSED"
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, fn, *args, **kwargs):
        async with self._lock:
            self._maybe_half_open()
            if self._state == "OPEN":
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN — request fast-rejected"
                )

        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:
            await self._record_failure()
            raise
        else:
            await self._record_success()
            return result

    def _maybe_half_open(self):
        if self._state == "OPEN" and (time.monotonic() - self._last_failure_time) >= self.recovery_timeout:
            logger.info("Circuit breaker '%s' → HALF_OPEN (recovery timeout elapsed)", self.name)
            self._state = "HALF_OPEN"

    async def _record_failure(self):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = "OPEN"
                logger.warning(
                    "Circuit breaker '%s' → OPEN (%d consecutive failures)",
                    self.name, self._failure_count,
                )

    async def _record_success(self):
        async with self._lock:
            if self._state == "HALF_OPEN":
                logger.info("Circuit breaker '%s' → CLOSED (probe succeeded)", self.name)
                self._state = "CLOSED"
            self._failure_count = 0


class CircuitBreakerOpenError(AppException):
    def __init__(self, message: str = "Circuit breaker is OPEN"):
        super().__init__(message, code="CIRCUIT_OPEN", status_code=503)


# Global registry: { "module:action" -> CircuitBreaker }
_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = asyncio.Lock()


async def get_circuit_breaker(key: str, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> CircuitBreaker:
    async with _breakers_lock:
        if key not in _breakers:
            _breakers[key] = CircuitBreaker(
                name=key,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return _breakers[key]
