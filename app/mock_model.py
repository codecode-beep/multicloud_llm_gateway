import asyncio
from typing import List

from app.schemas import Message


async def generate(messages: List[Message]) -> str:
    last = messages[-1].content
    await asyncio.sleep(0.2)  # pretend the model is thinking
    return f"Mock reply to: {last}"