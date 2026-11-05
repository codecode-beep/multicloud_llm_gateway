import hashlib
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app import mock_model
from app.logging_setup import setup_logging
from app.rate_limit import enforce_rate_limit
from app.schemas import ChatRequest
from app.metrics import LATENCY, REQUESTS, render_metrics
from app.resilience import CircuitOpen, ModelTimeout, breaker, call_model

setup_logging()
log = logging.getLogger("gateway")

app = FastAPI(title="Multicloud LLM Gateway", version="0.1.0")


def key_fingerprint(auth_header: Optional[str]) -> Optional[str]:
    """Short, non-reversible ID for an API key, safe to log."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[len("Bearer "):].strip()
    return hashlib.sha256(token.encode()).hexdigest()[:8]


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = (request.headers.get("x-request-id") or uuid.uuid4().hex)[:64]
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        elapsed = time.perf_counter() - start

        route = request.scope.get("route")
        route_label = route.path if route else "unmatched"
        REQUESTS.labels(request.method, route_label, str(status_code)).inc()
        LATENCY.labels(request.method, route_label).observe(elapsed)

        log.info(
            "request",
            extra={
                "fields": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "latency_ms": round(elapsed * 1000, 1),
                    "key_id": key_fingerprint(request.headers.get("authorization")),
                    "client": request.client.host if request.client else None,
                }
            },
        )


@app.get("/healthz")
def healthz():
    """Liveness: is the process running at all?"""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness: is it ready to accept traffic?"""
    return {"status": "ready", "model_circuit": breaker.state}

@app.get("/metrics")
def metrics():
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)

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

    try:
        text = await call_model(req.messages)
    except CircuitOpen as exc:
        raise HTTPException(
            status_code=503,
            detail="Model backend unavailable, circuit open",
            headers={"Retry-After": str(max(1, int(exc.retry_after) + 1))},
        )
    except ModelTimeout:
        raise HTTPException(status_code=504, detail="Model backend timed out")
    except mock_model.ModelError:
        raise HTTPException(status_code=502, detail="Model backend error")
    
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