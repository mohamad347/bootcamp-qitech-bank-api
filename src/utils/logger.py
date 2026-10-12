import json
import logging
import sys
from datetime import datetime, timezone

from constants import APP_ENV, SERVICE_NAME
from utils.request_context import get_request_id


STRUCTURED_FIELDS = (
    "event",
    "request_id",
    "method",
    "route",
    "status_code",
    "duration_ms",
    "error_code",
    "exception_type",
    "timeout_type",
    "sqlstate",
    "operation",
    "reason_type",
)


class RequestIdFilter(logging.Filter):
    """Attach the current request identifier without filtering records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JSONLogFormatter(logging.Formatter):
    """Serialize a deliberately small allowlist as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
        }

        for field in STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        payload.setdefault("event", "application.log")
        payload.setdefault("request_id", get_request_id())
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def setup_logging() -> None:
    """Configure application logs as JSON Lines on stdout."""
    level = logging.INFO
    if APP_ENV.upper() in ("LOCAL", "TEST"):
        level = logging.DEBUG

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONLogFormatter())
    handler.addFilter(RequestIdFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [handler]

    logging.getLogger("urllib3").setLevel(logging.CRITICAL)


def get_logger(class_name: str) -> logging.Logger:
    return logging.getLogger(f"{SERVICE_NAME}.{class_name}")
