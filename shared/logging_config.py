"""
shared/logging_config.py — Structured JSON logging for all services.

Usage:
    from shared.logging_config import setup_logging
    setup_logging("gateway")
"""

import logging
import json
import sys
import os
import time
import traceback


class JSONFormatter(logging.Formatter):
    """Outputs log records as JSON lines (one JSON object per line)."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(record.created)),
            "level": record.levelname,
            "service": getattr(record, "service", os.environ.get("SERVICE_NAME", "unknown")),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from record
        for key in ("request_id", "job_id", "client_ip", "method", "path",
                     "status_code", "duration_ms", "user_agent"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class RequestIDFilter(logging.Filter):
    """Adds request_id to log records if available in context."""
    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = ""
        return True


def setup_logging(service_name: str, level: str = "INFO") -> None:
    """
    Configure structured JSON logging for a service.

    Args:
        service_name: name of the service (e.g. "gateway", "llm-service")
        level: log level (DEBUG, INFO, WARNING, ERROR)
    """
    os.environ["SERVICE_NAME"] = service_name

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # JSON handler to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    handler.addFilter(RequestIDFilter())
    root_logger.addHandler(handler)

    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)
