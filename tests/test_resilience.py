import time

import pytest

from app import main, mock_model, resilience

URL = "/v1/chat/completions"
BODY = {"messages": [{"role": "user", "content": "hello"}]}


class FakeModel:
    """Stand-in model: fails a set number of times, then succeeds."""

    def __init__(self, failures_before_success):
        self.calls = 0
        self.failures_before_success = failures_before_success

    async def __call__(self, messages):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise mock_model.ModelError("fake failure")
        return "fake reply"


ALWAYS_FAIL = float("inf")


@pytest.fixture
def make_breaker(monkeypatch):
    def make(threshold=100, recovery=10.0):
        b = resilience.CircuitBreaker(threshold, recovery)
        monkeypatch.setattr(resilience, "breaker", b)
        monkeypatch.setattr(main, "breaker", b)
        return b
    return make


@pytest.fixture(autouse=True)
def isolated(monkeypatch, make_breaker):
    """Every test gets a fresh breaker and near-instant retry waits."""
    make_breaker()
    monkeypatch.setenv("RETRY_BASE_DELAY_SECONDS", "0.001")


# ---------- Timeout ----------

def test_slow_model_returns_504(client, auth, monkeypatch):
    monkeypatch.setenv("MOCK_LATENCY_SECONDS", "0.5")
    monkeypatch.setenv("MODEL_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setenv("MODEL_MAX_RETRIES", "0")
    r = client.post(URL, json=BODY, headers=auth)
    assert r.status_code == 504


# ---------- Errors and retries ----------

def test_model_error_returns_502(client, auth, monkeypatch):
    monkeypatch.setenv("MODEL_MAX_RETRIES", "0")
    monkeypatch.setattr(mock_model, "generate", FakeModel(ALWAYS_FAIL))
    r = client.post(URL, json=BODY, headers=auth)
    assert r.status_code == 502


def test_retry_hides_temporary_failures(client, auth, monkeypatch):
    monkeypatch.setenv("MODEL_MAX_RETRIES", "2")
    fake = FakeModel(failures_before_success=2)
    monkeypatch.setattr(mock_model, "generate", fake)
    r = client.post(URL, json=BODY, headers=auth)
    assert r.status_code == 200
    assert fake.calls == 3  # failed, failed, succeeded


def test_gives_up_after_max_retries(client, auth, monkeypatch):
    monkeypatch.setenv("MODEL_MAX_RETRIES", "2")
    fake = FakeModel(ALWAYS_FAIL)
    monkeypatch.setattr(mock_model, "generate", fake)
    r = client.post(URL, json=BODY, headers=auth)
    assert r.status_code == 502
    assert fake.calls == 3  # 1 try + 2 retries, then stop


# ---------- Circuit breaker ----------

def test_breaker_opens_and_fails_fast(client, auth, monkeypatch, make_breaker):
    monkeypatch.setenv("MODEL_MAX_RETRIES", "0")
    breaker = make_breaker(threshold=3, recovery=10)
    fake = FakeModel(ALWAYS_FAIL)
    monkeypatch.setattr(mock_model, "generate", fake)

    codes = [client.post(URL, json=BODY, headers=auth).status_code for _ in range(3)]
    assert codes == [502, 502, 502]
    assert breaker.state == "open"

    r = client.post(URL, json=BODY, headers=auth)
    assert r.status_code == 503
    assert "retry-after" in r.headers
    assert fake.calls == 3  # the 4th request never reached the model

    assert client.get("/readyz").json()["model_circuit"] == "open"


def test_breaker_recovers_when_model_is_healthy(client, auth, monkeypatch, make_breaker):
    monkeypatch.setenv("MODEL_MAX_RETRIES", "0")
    breaker = make_breaker(threshold=2, recovery=0.2)
    monkeypatch.setattr(mock_model, "generate", FakeModel(ALWAYS_FAIL))

    for _ in range(2):
        client.post(URL, json=BODY, headers=auth)
    assert breaker.state == "open"

    time.sleep(0.25)  # wait out the recovery time
    monkeypatch.setattr(mock_model, "generate", FakeModel(0))  # model is fixed

    r = client.post(URL, json=BODY, headers=auth)
    assert r.status_code == 200
    assert breaker.state == "closed"


def test_failed_test_request_reopens_breaker():
    b = resilience.CircuitBreaker(failure_threshold=1, recovery_seconds=0)
    b.record_failure()
    assert b.state == "open"

    assert b.allow_request() is True  # recovery time is 0, so it tests right away
    assert b.state == "half_open"

    b.record_failure()  # the test request failed
    assert b.state == "open"