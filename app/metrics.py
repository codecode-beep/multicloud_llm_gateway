from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


REQUESTS = Counter(
    "gateway_requests_total",
    "Total HTTP requests",
    ["method", "route", "status"],
)

LATENCY = Histogram(
    "gateway_request_duration_seconds",
    "Request latency in seconds",
    ["method", "route"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

MODEL_RETRIES = Counter(
    "gateway_model_retries_total",
    "Model calls that failed and were retried",
    ["reason"],
)

CIRCUIT_STATE = Gauge(
    "gateway_circuit_state",
    "Model circuit breaker state: 0=closed, 1=half_open, 2=open",
)

def render_metrics():
    return generate_latest(), CONTENT_TYPE_LATEST