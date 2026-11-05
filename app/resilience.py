import asyncio
import logging
import random
import time
from typing import List

from app import mock_model
from app.config import (
    cb_failure_threshold,
    cb_recovery_seconds,
    model_max_retries,
    model_timeout_seconds,
    retry_base_delay_seconds,
    retry_max_delay_seconds,
)
from app.metrics import CIRCUIT_STATE, MODEL_RETRIES
from app.schemas import Message

log = logging.getLogger("gateway.resilience")


class ModelTimeout(Exception):
    """The model took too long to answer."""


class CircuitOpen(Exception):
    """The breaker is open: we are not calling the model right now."""

    def __init__(self, retry_after: float):
        super().__init__("circuit breaker is open")
        self.retry_after = retry_after


# ---------- Circuit breaker ----------

STATE_VALUES = {"closed": 0, "half_open": 1, "open": 2}


class CircuitBreaker:
    def __init__(self, failure_threshold: int, recovery_seconds: float):
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self.state = "closed"
        self.failures = 0
        self.opened_at = 0.0
        CIRCUIT_STATE.set(STATE_VALUES["closed"])

    def _set_state(self, new_state: str) -> None:
        if new_state != self.state:
            log.warning(
                "circuit breaker state change",
                extra={"fields": {"from": self.state, "to": new_state}},
            )
            self.state = new_state
            CIRCUIT_STATE.set(STATE_VALUES[new_state])

    def retry_after(self) -> float:
        waited = time.monotonic() - self.opened_at
        return max(0.0, self.recovery_seconds - waited)

    def allow_request(self) -> bool:
        if self.state == "open":
            if self.retry_after() == 0:
                self._set_state("half_open")  # time to test the model again
                return True
            return False
        return True  # closed or half_open

    def record_success(self) -> None:
        self.failures = 0
        self._set_state("closed")

    def record_failure(self) -> None:
        self.failures += 1
        if self.state == "half_open" or self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()
            self._set_state("open")


breaker = CircuitBreaker(cb_failure_threshold(), cb_recovery_seconds())


# ---------- Timeout + retries ----------

def backoff_delay(retry_number: int) -> float:
    """Exponential backoff with full jitter."""
    exp = retry_base_delay_seconds() * (2 ** (retry_number - 1))
    return random.uniform(0, min(retry_max_delay_seconds(), exp))


async def _call_once(messages: List[Message]) -> str:
    timeout = model_timeout_seconds()
    try:
        return await asyncio.wait_for(mock_model.generate(messages), timeout=timeout)
    except asyncio.TimeoutError:
        raise ModelTimeout(f"model did not answer within {timeout}s") from None


async def _call_with_retries(messages: List[Message]) -> str:
    max_retries = model_max_retries()
    for attempt in range(max_retries + 1):
        try:
            return await _call_once(messages)
        except (ModelTimeout, mock_model.ModelError) as exc:
            if attempt == max_retries:
                raise
            reason = "timeout" if isinstance(exc, ModelTimeout) else "error"
            delay = backoff_delay(attempt + 1)
            MODEL_RETRIES.labels(reason).inc()
            log.warning(
                "model call failed, retrying",
                extra={"fields": {
                    "attempt": attempt + 1,
                    "reason": reason,
                    "retry_in_s": round(delay, 3),
                }},
            )
            await asyncio.sleep(delay)


# ---------- What the endpoint calls ----------

async def call_model(messages: List[Message]) -> str:
    if not breaker.allow_request():
        raise CircuitOpen(breaker.retry_after())

    try:
        result = await _call_with_retries(messages)
    except (ModelTimeout, mock_model.ModelError):
        breaker.record_failure()
        raise

    breaker.record_success()
    return result