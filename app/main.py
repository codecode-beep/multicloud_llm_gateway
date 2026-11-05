import json
import time
import uuid

from fastapi import FastAPI, Depends
from fastapi.responses import StreamingResponse

from app import mock_model
from app.schemas import ChatRequest
from app.auth import require_api_key
from app.rate_limit import enforce_rate_limit

app = FastAPI(title="Multicloud LLM Gateway", version="0.1.0")


@app.get("/healthz")
def healthz():
    """Liveness: is the process running at all?"""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness: is it ready to accept traffic?"""
    return {"status": "ready"}


def new_chat_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


async def sse_stream(req: ChatRequest):
    chat_id = new_chat_id()
    created = int(time.time())

    def chunk(delta: dict, finish_reason=None) -> str:
        payload = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": req.model,
            "choices": [
                {"index": 0, "delta": delta, "finish_reason": finish_reason}
            ],
        }
        return f"data: {json.dumps(payload)}\n\n"

    yield chunk({"role": "assistant"})
    async for piece in mock_model.stream(req.messages):
        yield chunk({"content": piece})
    yield chunk({}, finish_reason="stop")
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest, api_key: str = Depends(enforce_rate_limit)):
    if req.stream:
        return StreamingResponse(sse_stream(req), media_type="text/event-stream")

    text = await mock_model.generate(req.messages)
    prompt_tokens = sum(len(m.content.split()) for m in req.messages)
    completion_tokens = len(text.split())

    return {
        "id": new_chat_id(),
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