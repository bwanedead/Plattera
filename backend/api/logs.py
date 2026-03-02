from collections import deque
from pathlib import Path

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field
from services.logging_service import get_ring_handler, LOG_FILE, LOG_DIR, get_active_log_file
import os
import io
import zipfile
import json


router = APIRouter(prefix="/logs", tags=["logs"])
_frontend_log_buffer: deque[dict[str, object]] = deque(maxlen=5000)


class FrontendLogEntry(BaseModel):
    level: str = Field(default="INFO", min_length=1, max_length=20)
    message: str = Field(default="", min_length=0, max_length=4000)
    source: str | None = Field(default=None, max_length=200)
    ts: float | None = None
    meta: dict[str, object] | None = None


@router.get("/recent")
def get_recent_logs(limit: int = Query(500, ge=1, le=5000)):
    ring = get_ring_handler()
    return {"logs": ring.get_recent(limit)}


@router.post("/frontend")
def ingest_frontend_log(entry: FrontendLogEntry):
    payload = {
        "ts": entry.ts,
        "level": str(entry.level or "INFO").upper(),
        "message": str(entry.message or ""),
        "source": entry.source,
        "meta": entry.meta or {},
    }
    _frontend_log_buffer.append(payload)
    return {"ok": True, "count": len(_frontend_log_buffer)}


@router.get("/frontend/recent")
def recent_frontend_logs(
    limit: int = Query(default=300, ge=1, le=5000),
    level: str | None = Query(default=None),
    contains: str | None = Query(default=None),
):
    level_filter = str(level or "").strip().upper()
    contains_filter = str(contains or "").strip()
    out: list[dict[str, object]] = []
    for item in reversed(_frontend_log_buffer):
        if level_filter and str(item.get("level") or "").upper() != level_filter:
            continue
        if contains_filter and contains_filter not in str(item.get("message") or ""):
            continue
        out.append(item)
        if len(out) >= limit:
            break
    return {"count": len(out), "logs": out}


def _resolve_log_path(source: str) -> Path:
    normalized = str(source or "active").strip().lower()
    if normalized == "app":
        return Path(LOG_FILE)
    if normalized == "latest_session":
        log_dir = Path(LOG_DIR)
        if log_dir.exists():
            candidates = sorted(log_dir.glob("app_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
            if candidates:
                return candidates[0]
        return Path(get_active_log_file())
    return Path(get_active_log_file())


@router.get("/tail")
def tail_logs(
    limit_lines: int = Query(default=300, ge=1, le=5000),
    source: str = Query(default="active", description="active | latest_session | app"),
    run_id: str | None = Query(default=None),
    contains: str | None = Query(default=None),
    exclude: str | None = Query(default=None),
    level: str | None = Query(default=None, description="INFO | WARNING | ERROR | DEBUG | CRITICAL"),
    newest_first: bool = Query(default=False),
):
    path = _resolve_log_path(source)
    if not path.exists():
        return {
            "source": source,
            "path": str(path),
            "exists": False,
            "count": 0,
            "lines": [],
        }

    run_filter = str(run_id or "").strip()
    contains_filter = str(contains or "").strip()
    exclude_filter = str(exclude or "").strip()
    level_filter = str(level or "").strip().upper()
    if level_filter and level_filter not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level_filter = ""

    window: deque[str] = deque(maxlen=limit_lines)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            if run_filter and run_filter not in line:
                continue
            if contains_filter and contains_filter not in line:
                continue
            if exclude_filter and exclude_filter in line:
                continue
            if level_filter and f" {level_filter} " not in line:
                continue
            window.append(line)

    lines = list(window)
    if newest_first:
        lines.reverse()
    return {
        "source": source,
        "path": str(path),
        "exists": True,
        "count": len(lines),
        "filters": {
            "run_id": run_filter or None,
            "contains": contains_filter or None,
            "exclude": exclude_filter or None,
            "level": level_filter or None,
            "newest_first": newest_first,
        },
        "lines": lines,
    }


@router.get("/tail/run/{run_id}")
def tail_logs_for_run(
    run_id: str,
    limit_lines: int = Query(default=400, ge=1, le=5000),
    source: str = Query(default="active", description="active | latest_session | app"),
    contains: str | None = Query(default=None),
    exclude: str | None = Query(default=None),
    level: str | None = Query(default=None, description="INFO | WARNING | ERROR | DEBUG | CRITICAL"),
    newest_first: bool = Query(default=False),
):
    return tail_logs(
        limit_lines=limit_lines,
        source=source,
        run_id=run_id,
        contains=contains,
        exclude=exclude,
        level=level,
        newest_first=newest_first,
    )


@router.get("/download")
def download_logs():
    buf = io.BytesIO()
    base = os.path.basename(LOG_FILE)
    directory = os.path.dirname(LOG_FILE)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Include rotating files app.log, app.log.1, ...
        try:
            for name in os.listdir(directory):
                if name.startswith(os.path.splitext(base)[0]):
                    path = os.path.join(directory, name)
                    if os.path.isfile(path):
                        zf.write(path, arcname=name)
        except Exception:
            # If log dir not present yet, continue gracefully
            pass

        # Also include recent ring buffer as JSON
        try:
            ring_json = json.dumps({"logs": get_ring_handler().get_recent(2000)}, indent=2).encode("utf-8")
            zf.writestr("recent_ring_buffer.json", ring_json)
        except Exception:
            pass

    headers = {"Content-Disposition": 'attachment; filename="plattera-logs.zip"'}
    return Response(content=buf.getvalue(), media_type="application/zip", headers=headers)


