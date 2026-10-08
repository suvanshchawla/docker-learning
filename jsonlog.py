"""JSON logging: one JSON object per line on stdout, tagged with the request ID."""

import json
import logging
import sys
from datetime import datetime, timezone

from flask import g, has_request_context


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
