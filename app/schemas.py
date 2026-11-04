from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model: str = "mock-1"
    messages: List[Message] = Field(min_length=1)
    stream: bool = False
    max_tokens: Optional[int] = Field(default=None, ge=1, le=4096)