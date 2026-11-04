import time
import uuid

from fastapi import FastAPI

from app import mock_model
from app.schemas import ChatRequest

app = FastAPI(title="Multicloud LLM Gateway", version="0.1.0")


@app.get("/healthz")
def healthz():
    """Liveness: is the process running at all?"""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness: is it ready to accept traffic?"""
    return {"status": "ready"}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    text = await mock_model.generate(req.messages)

    prompt_tokens = sum(len(m.content.split()) for m in req.messages)
    completion_tokens = len(text.split())

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }