import json
import logging

from app import rate_limit
from app.logging_setup import JsonFormatter

URL = "/v1/chat/completions"
BODY = {"messages": [{"role": "user", "content": "hello"}]}


# ---------- Health ----------

def test_healthz_needs_no_key(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------- Auth ----------

def test_missing_key_rejected(client):
    r = client.post(URL, json=BODY)
    assert r.status_code == 401


def test_wrong_key_rejected(client):
    r = client.post(URL, json=BODY, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid API key"


# ---------- Chat completions ----------

def test_valid_key_returns_openai_format(client, auth):
    r = client.post(URL, json=BODY, headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "hello" in data["choices"][0]["message"]["content"]
    usage = data["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_invalid_role_returns_422(client, auth):
    bad = {"messages": [{"role": "hacker", "content": "hi"}]}
    r = client.post(URL, json=bad, headers=auth)
    assert r.status_code == 422


def test_streaming_returns_sse_chunks(client, auth):
    with client.stream("POST", URL, json={**BODY, "stream": True}, headers=auth) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in r.iter_lines() if line.startswith("data: ")]

    assert lines[-1] == "data: [DONE]"
    chunks = [json.loads(line[len("data: "):]) for line in lines[:-1]]
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert text == "Mock reply to: hello"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"


# ---------- Rate limiting ----------

def test_rate_limit_returns_429_with_retry_after(client, auth, monkeypatch):
    monkeypatch.setattr(
        rate_limit, "limiter",
        rate_limit.TokenBucketLimiter(rate_per_sec=0.001, burst=3),
    )
    responses = [client.post(URL, json=BODY, headers=auth) for _ in range(5)]
    codes = [r.status_code for r in responses]
    assert codes == [200, 200, 200, 429, 429]
    assert "retry-after" in responses[-1].headers


# ---------- Observability ----------

def test_request_id_is_echoed(client):
    r = client.get("/healthz", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"


def test_metrics_endpoint_exposes_counters(client):
    client.get("/healthz")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "gateway_requests_total" in r.text


def test_log_formatter_redacts_bearer_tokens():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="header was Bearer super-secret-key", args=None, exc_info=None,
    )
    out = JsonFormatter().format(record)
    assert "super-secret-key" not in out
    assert "Bearer [REDACTED]" in out