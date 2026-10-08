"""JSON logging: one JSON object per line on stdout, tagged with the request ID."""

import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

from flask import g, has_request_context, request


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if has_request_context() and "request_id" in g:
            entry["request_id"] = g.request_id
        entry.update(getattr(record, "fields", {}))  # logger.info("...", extra={"fields": {...}})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logger(logger, level):
    """Replace the logger's handlers with a single JSON handler on stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.handlers[:] = [handler]
    logger.setLevel(level.upper())
    logger.propagate = False  # otherwise pytest/gunicorn root handlers would log it twice


def register_request_logging(app):
    """Tag every request with an ID and log one `request` line when it finishes."""

    @app.before_request
    def start_request():
        # Reuse the caller's ID (e.g. from a proxy) so one request can be traced across services.
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        g.start_time = time.perf_counter()

    @app.after_request
    def log_request(response):
        response.headers["X-Request-ID"] = g.request_id
        # /health is polled by the Compose healthcheck every few seconds, so keep it out of INFO.
        level = logging.DEBUG if request.path == "/health" else logging.INFO
        app.logger.log(level, "request", extra={"fields": {
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - g.start_time) * 1000, 2),
        }})
        return response
