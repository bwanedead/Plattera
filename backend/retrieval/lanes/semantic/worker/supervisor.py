from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

from .client import SemanticWorkerClient, WorkerResponse


DEFAULT_PORTS = {
    "FINAL_SEGMENTS": 9351,
    "EVERYTHING": 9352,
}


def _resolve_port(pool_identifier: str) -> int:
    key = f"HNSW_WORKER_PORT_{pool_identifier}"
    raw = os.getenv(key)
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_PORTS[pool_identifier]


def _resolve_host() -> str:
    return os.getenv("HNSW_WORKER_HOST", "127.0.0.1")


@dataclass
class WorkerHealth:
    status: str
    reason_code: Optional[str] = None
    worker_stats: Optional[Dict] = None


@dataclass
class SemanticWorkerSupervisor:
    pool_identifier: str
    host: str
    port: int
    process: Optional[subprocess.Popen] = None
    restart_count: int = 0
    last_crash_ts: Optional[float] = None
    backoff_seconds: float = 0.0
    last_start_ts: Optional[float] = None
    log_path: Optional[Path] = None
    _log_handle: Optional[object] = field(default=None, repr=False)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _client(self, timeout: Optional[float] = None) -> SemanticWorkerClient:
        if timeout is None:
            timeout = float(os.getenv("HNSW_WORKER_CLIENT_TIMEOUT_SEC", "3"))
        return SemanticWorkerClient(
            host=self.host,
            port=self.port,
            pool_identifier=self.pool_identifier,
            timeout=timeout,
        )

    def _in_backoff(self) -> bool:
        if self.backoff_seconds <= 0:
            return False
        if self.last_crash_ts is None:
            return False
        return (time.monotonic() - self.last_crash_ts) < self.backoff_seconds

    def _update_backoff(self) -> None:
        base = 1.0
        if self.backoff_seconds <= 0:
            self.backoff_seconds = base
        else:
            self.backoff_seconds = min(self.backoff_seconds * 2, 60.0)
        self.last_crash_ts = time.monotonic()

    def _reset_backoff(self) -> None:
        self.backoff_seconds = 0.0

    def _spawn_worker(self) -> None:
        log_path = self.log_path or self._default_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._close_log_handle()
        self._log_handle = open(log_path, "a", encoding="utf-8", buffering=1)
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "retrieval.lanes.semantic.worker.main",
                "--pool",
                self.pool_identifier,
                "--host",
                self.host,
                "--port",
                str(self.port),
            ],
            stdout=self._log_handle,
            stderr=self._log_handle,
            creationflags=creationflags,
        )
        self.last_start_ts = time.monotonic()
        self.restart_count += 1

    def _ensure_running(self) -> Optional[str]:
        if self._in_backoff():
            return "semantic_worker_in_backoff"
        if self.process is not None and self.process.poll() is None:
            return None

        probe = self._probe_existing_worker()
        if probe == "ok":
            self._reset_backoff()
            return None
        if probe == "port_in_use":
            self._update_backoff()
            return "semantic_worker_port_in_use"

        self._spawn_worker()
        return None

    def _probe_existing_worker(self) -> str:
        response = self._client(timeout=0.5).stats()
        if response.status == "ok" and response.worker_stats:
            pool = response.worker_stats.get("pool_identifier")
            if pool == self.pool_identifier:
                return "ok"
            return "port_in_use"
        if response.reason_code == "semantic_worker_port_in_use":
            return "port_in_use"
        return "unavailable"

    def restart(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.process = None
        self._spawn_worker()

    def stats(self) -> WorkerHealth:
        with self.lock:
            reason = self._ensure_running()
            if reason:
                return WorkerHealth(status="error", reason_code=reason)
            response = self._client().stats()
            if response.status != "ok":
                self._mark_failure(response)
                return WorkerHealth(status="error", reason_code=response.reason_code)
            self._reset_backoff()
            return WorkerHealth(status="ok", worker_stats=response.worker_stats)

    def query(
        self,
        *,
        vector: list[float],
        k: int,
        embedding_dim: int,
        manifest_fingerprint: Optional[str],
        ef: Optional[int] = None,
    ) -> Tuple[WorkerResponse, Optional[str]]:
        with self.lock:
            reason = self._ensure_running()
            if reason:
                return WorkerResponse(status="error", reason_code=reason, results=[]), reason

            budget_ms = int(os.getenv("HNSW_WORKER_QUERY_BUDGET_MS", "1500"))
            start = time.monotonic()
            timeout = max(0.1, budget_ms / 1000.0)
            response = self._client(timeout=timeout).knn_query(
                vector=vector,
                k=k,
                embedding_dim=embedding_dim,
                manifest_fingerprint=manifest_fingerprint,
                ef=ef,
            )

            if response.status == "ok":
                self._reset_backoff()
                return response, None

            if response.reason_code in ("semantic_worker_manifest_mismatch", "semantic_worker_busy"):
                return response, response.reason_code

            self._mark_failure(response)
            self.restart()
            elapsed = time.monotonic() - start
            remaining = max(0.0, (budget_ms / 1000.0) - elapsed)
            if remaining <= 0.0:
                return WorkerResponse(status="error", reason_code="semantic_worker_timeout", results=[]), "semantic_worker_timeout"
            retry = self._client(timeout=remaining).knn_query(
                vector=vector,
                k=k,
                embedding_dim=embedding_dim,
                manifest_fingerprint=manifest_fingerprint,
                ef=ef,
            )
            if retry.status == "ok":
                self._reset_backoff()
                return retry, None

            if retry.reason_code in ("semantic_worker_manifest_mismatch", "semantic_worker_busy"):
                return retry, retry.reason_code

            self._mark_failure(retry)
            return retry, retry.reason_code

    def _mark_failure(self, response: WorkerResponse) -> None:
        if response.reason_code == "semantic_worker_busy":
            return
        self._update_backoff()

    def _default_log_path(self) -> Path:
        backend_root = Path(__file__).resolve().parents[4]
        return backend_root / "logs" / f"hnsw_worker_{self.pool_identifier.lower()}.log"

    def _close_log_handle(self) -> None:
        handle = self._log_handle
        if handle is None:
            return
        try:
            handle.flush()
        except Exception:
            pass
        try:
            handle.close()
        except Exception:
            pass
        self._log_handle = None


_SUPERVISORS: Dict[str, SemanticWorkerSupervisor] = {}


def get_supervisor(pool_identifier: str) -> SemanticWorkerSupervisor:
    pool_identifier = pool_identifier.strip().upper()
    if pool_identifier not in DEFAULT_PORTS:
        raise ValueError(f"Unsupported pool_identifier: {pool_identifier}")
    if pool_identifier not in _SUPERVISORS:
        _SUPERVISORS[pool_identifier] = SemanticWorkerSupervisor(
            pool_identifier=pool_identifier,
            host=_resolve_host(),
            port=_resolve_port(pool_identifier),
        )
    return _SUPERVISORS[pool_identifier]
