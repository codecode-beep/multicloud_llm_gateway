import asyncio
from typing import List,AsyncIterator

from app.schemas import Message



async def generate(messages: List[Message]) -> str:
    last = messages[-1].content
    await asyncio.sleep(0.2)  # pretend the model is thinking
    return f"Mock reply to: {last}"


async def stream(messages: List[Message]) -> AsyncIterator[str]:
    text = f"Mock reply to: {messages[-1].content}"
    words = text.split(" ")
    for i, word in enumerate(words):
        await asyncio.sleep(0.05)  # pretend each word takes time to generate
        yield word if i == 0 else " " + word