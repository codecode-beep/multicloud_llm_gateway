import asyncio
import logging
import random
from typing import List

from app import mock_model
from app.config import (
    model_max_retries,
    model_timeout_seconds,
    retry_base_delay_seconds,
    retry_max_delay_seconds,
)
from app.metrics import MODEL_RETRIES
from app.schemas import Message

log = logging.getLogger("gateway.resilience")


class ModelTimeout(Exception):
    """The model took too long to answer."""


def backoff_delay(retry_number: int) -> float:
    """Exponential backoff with full jitter.

    retry 1 -> random wait between 0 and 0.1s
    retry 2 -> random wait between 0 and 0.2s
    retry 3 -> random wait between 0 and 0.4s ...
    """
    exp = retry_base_delay_seconds() * (2 ** (retry_number - 1))
    return random.uniform(0, min(retry_max_delay_seconds(), exp))


async def _call_once(messages: List[Message]) -> str:
    timeout = model_timeout_seconds()
    try:
        return await asyncio.wait_for(mock_model.generate(messages), timeout=timeout)
    except asyncio.TimeoutError:
        raise ModelTimeout(f"model did not answer within {timeout}s") from None


async def call_model(messages: List[Message]) -> str:
    max_retries = model_max_retries()

    for attempt in range(max_retries + 1):
        try:
            return await _call_once(messages)
        except (ModelTimeout, mock_model.ModelError) as exc:
            if attempt == max_retries:
                raise  # out of retries: let main.py turn it into 502/504

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