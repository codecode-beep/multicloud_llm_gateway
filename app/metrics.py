from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

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


def render_metrics():
    return generate_latest(), CONTENT_TYPE_LATEST