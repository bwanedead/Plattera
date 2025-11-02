import logging
import os
from logging.handlers import RotatingFileHandler
from collections import deque
from typing import Deque, Dict, Any


LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
RING_BUFFER_SIZE = int(os.getenv("RING_BUFFER_SIZE", "2000"))
LOG_FILE = os.path.join(LOG_DIR, "app.log")


class RingBufferHandler(logging.Handler):
    def __init__(self, maxlen: int = 2000):
        super().__init__()
        self.buffer: Deque[Dict[str, Any]] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buffer.append({
                "ts": record.created,
                "level": record.levelname,
                "name": record.name,
                "message": record.getMessage(),
                "pathname": record.pathname,
                "lineno": record.lineno,
            })
        except Exception:
            # Never raise from logging handler
            pass

    def get_recent(self, limit: int = 500):
        if limit <= 0:
            return list(self.buffer)
        return list(self.buffer)[-limit:]


_ring_handler: RingBufferHandler | None = None


def get_ring_handler() -> RingBufferHandler:
    global _ring_handler
    if _ring_handler is None:
        _ring_handler = RingBufferHandler(maxlen=RING_BUFFER_SIZE)
    return _ring_handler


def init_logging():
    os.makedirs(LOG_DIR, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    root = logging.getLogger()
    # Preserve any level previously set by the app; otherwise, apply env level
    if root.level == logging.NOTSET:
        root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Rotating file handler (append-only)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # In-memory ring buffer (default WARNING+)
    ring = get_ring_handler()
    ring.setFormatter(fmt)
    try:
        # Capture INFO+ by default; can be overridden via RING_BUFFER_MIN_LEVEL
        min_level_name = os.getenv("RING_BUFFER_MIN_LEVEL", "INFO").upper()
        ring.setLevel(getattr(logging, min_level_name, logging.WARNING))
    except Exception:
        ring.setLevel(logging.WARNING)
    root.addHandler(ring)

    # Quiet very noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # Keep uvicorn.error at INFO to see startup/errors
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


