import pytest
from fastapi.testclient import TestClient

from app import rate_limit
from app.main import app

TEST_KEY = "test-key-123"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GATEWAY_API_KEYS", TEST_KEY)

    for var in [
        "MOCK_FAILURE_RATE", "MOCK_LATENCY_SECONDS", "MODEL_TIMEOUT_SECONDS",
        "MODEL_MAX_RETRIES", "RETRY_BASE_DELAY_SECONDS",
    ]:
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setattr(
        rate_limit, "limiter",
        rate_limit.TokenBucketLimiter(rate_per_sec=0.001, burst=100),
    )
    return TestClient(app)


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {TEST_KEY}"}