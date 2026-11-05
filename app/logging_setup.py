import json
import logging
import re
import sys
from datetime import datetime, timezone

BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-~+/=]+")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if fields:
            entry.update(fields)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)

        line = json.dumps(entry)
        return BEARER_RE.sub("Bearer [REDACTED]", line)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # We write our own request log, so turn off uvicorn's plain-text one
    logging.getLogger("uvicorn.access").disabled = True