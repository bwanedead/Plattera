"""Append-only JSONL audit event log.

``AuditEventLog`` writes one JSON line per event immediately, with fsync, so every
recorded event survives a later crash.  This is the durable source-of-truth backbone;
``turn_NNNN.json`` / ``index.json`` / ``review.md`` are derived views.

Usage::

    log = AuditEventLog(run_dir)
    log.append("llm_io", payload, turn_index=1)
    log.append("turn_completed", payload, turn_index=1)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from .normalize import audit_jsonable

_LOG = logging.getLogger(__name__)


class AuditEventLog:
    """Per-run append-only event log written to ``<run_dir>/audit/events.jsonl``.

    Pass ``run_dir=None`` for a no-op instance (test/stub contexts).
    Each ``append()`` call normalises the payload, writes one line, flushes, and fsyncs.
    Exceptions are logged and suppressed so the event log never blocks run progress.
    """

    def __init__(self, run_dir: Path | str | None) -> None:
        self._path: Path | None = (
            Path(run_dir) / "audit" / "events.jsonl" if run_dir is not None else None
        )

    def append(self, kind: str, payload: dict[str, Any], **meta: Any) -> None:
        """Append one event line.  ``kind`` is a short snake_case label; ``meta`` are
        scalar top-level fields (e.g. ``turn_index=1``).  ``payload`` is normalised
        through ``audit_jsonable`` before serialisation.
        """
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            record: dict[str, Any] = {
                "ts": int(time.time()),
                "kind": kind,
            }
            for k, v in meta.items():
                record[k] = audit_jsonable(v)
            record["payload"] = audit_jsonable(payload)
            line = json.dumps(record, ensure_ascii=False) + "\n"
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass  # fsync not available on all platforms/fd types; flush is sufficient
        except Exception:
            _LOG.warning("AuditEventLog.append failed kind=%s", kind, exc_info=True)
