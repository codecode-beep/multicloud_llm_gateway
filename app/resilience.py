import asyncio
from typing import List

from app import mock_model
from app.config import model_timeout_seconds
from app.schemas import Message


class ModelTimeout(Exception):
    """The model took too long to answer."""


async def call_model(messages: List[Message]) -> str:
    timeout = model_timeout_seconds()
    try:
        return await asyncio.wait_for(mock_model.generate(messages), timeout=timeout)
    except asyncio.TimeoutError:
        raise ModelTimeout(f"model did not answer within {timeout}s") from None