import asyncio
import random
from typing import AsyncIterator, List

from app.config import mock_failure_rate, mock_latency_seconds
from app.schemas import Message


class ModelError(Exception):
    """The model backend failed, like a 500 error from a real AI provider."""


async def generate(messages: List[Message]) -> str:
    await asyncio.sleep(mock_latency_seconds())
    if random.random() < mock_failure_rate():
        raise ModelError("mock model failure")
    return f"Mock reply to: {messages[-1].content}"


async def stream(messages: List[Message]) -> AsyncIterator[str]:
    text = f"Mock reply to: {messages[-1].content}"
    words = text.split(" ")
    for i, word in enumerate(words):
        await asyncio.sleep(0.05)
        yield word if i == 0 else " " + word