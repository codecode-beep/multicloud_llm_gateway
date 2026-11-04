from fastapi import FastAPI

app = FastAPI(title="Multicloud LLM Gateway", version="0.1.0")


@app.get("/healthz")
def healthz():
    """Liveness: is the process running at all?"""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness: is it ready to accept traffic?"""
    return {"status": "ready"}