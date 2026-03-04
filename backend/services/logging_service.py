import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from collections import deque
from typing import Deque, Dict, Any, Optional
from pathlib import Path

from config.paths import is_frozen


LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
RING_BUFFER_SIZE = int(os.getenv("RING_BUFFER_SIZE", "2000"))
LOG_FILE = os.path.join(LOG_DIR, "app.log")
ACTIVE_LOG_FILE = LOG_FILE
# Keep a strict fixed cap so session logs never grow unbounded.
MAX_SESSION_LOG_FILES = 5


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


def get_active_log_file() -> str:
    return ACTIVE_LOG_FILE


def init_logging():
    global ACTIVE_LOG_FILE
    os.makedirs(LOG_DIR, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    root = logging.getLogger()
    # Preserve any level previously set by the app; otherwise, apply env level
    if root.level == logging.NOTSET:
        root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    def _env_truthy(value: Optional[str], default: bool) -> bool:
        if value is None:
            return default
        return value.strip().lower() in ("1", "true", "yes", "on")

    # Per-launch log file in dev, stable file in frozen builds
    session_file_default = not is_frozen()
    use_session_file = _env_truthy(os.getenv("LOG_SESSION_FILE"), session_file_default)
    if use_session_file and not is_frozen():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(LOG_DIR, f"app_{stamp}.log")
    else:
        log_file = LOG_FILE
    ACTIVE_LOG_FILE = log_file
    _prune_session_logs(log_dir=LOG_DIR, active_log_file=ACTIVE_LOG_FILE, keep_count=MAX_SESSION_LOG_FILES)

    # Rotating file handler (append-only)
    file_handler = RotatingFileHandler(
        log_file,
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


def _prune_session_logs(*, log_dir: str, active_log_file: str, keep_count: int) -> None:
    """Retain only the newest per-session app_*.log files to cap disk growth."""
    keep = 5
    try:
        directory = Path(log_dir)
        if not directory.exists():
            return
        active_path = Path(active_log_file).resolve()
        session_logs = sorted(
            (p for p in directory.glob("app_*.log") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        kept = 0
        for path in session_logs:
            if path.resolve() == active_path:
                kept += 1
                continue
            if kept < keep:
                kept += 1
                continue
            try:
                path.unlink()
            except Exception:
                # Never fail startup due to log housekeeping.
                pass
    except Exception:
        pass
