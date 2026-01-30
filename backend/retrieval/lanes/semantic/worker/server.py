from __future__ import annotations

import json
import logging
import os
import queue
import socketserver
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ..hnsw_store import load_hnsw_store
from ..manifest import hnsw_index_path, read_manifest
from .protocol import decode_vector_from_b64, manifest_fingerprint


logger = logging.getLogger(__name__)


@dataclass
class WorkerState:
    pool_identifier: str
    embedding_dim: int
    fingerprint: Optional[str]
    hnsw_store: object
    started_at: float


def _load_state(pool_identifier: str) -> WorkerState:
    manifest = read_manifest(pool_identifier)
    if manifest is None:
        raise RuntimeError(f"Missing manifest for pool={pool_identifier}")
    store = load_hnsw_store(
        path=hnsw_index_path(pool_identifier),
        embedding_dim=manifest.embedding_dim,
    )
    return WorkerState(
        pool_identifier=pool_identifier,
        embedding_dim=manifest.embedding_dim,
        fingerprint=manifest_fingerprint(manifest),
        hnsw_store=store,
        started_at=time.monotonic(),
    )


def _error_response(request_id: str, reason_code: str) -> Dict[str, Any]:
    return {
        "request_id": request_id,
        "status": "error",
        "reason_code": reason_code,
    }


class SemanticWorkerTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, server_address: Tuple[str, int], handler_class, *, pool_identifier: str):
        super().__init__(server_address, handler_class)
        self.pool_identifier = pool_identifier
        self.request_queue: queue.Queue = queue.Queue(maxsize=int(os.getenv("HNSW_WORKER_QUEUE_SIZE", "64")))
        self.request_timeout = float(os.getenv("HNSW_WORKER_REQUEST_TIMEOUT_SEC", "10"))
        self.state = _load_state(pool_identifier)
        logger.info(
            "Semantic worker ready pool=%s vectors=%s dim=%s fp=%s",
            self.pool_identifier,
            self.state.hnsw_store.get_current_count(),
            self.state.embedding_dim,
            self.state.fingerprint,
        )
        self.shutdown_flag = threading.Event()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _worker_loop(self) -> None:
        while not self.shutdown_flag.is_set():
            try:
                request, response_queue = self.request_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                response = self._handle_request(request)
            except Exception:
                logger.exception("Worker request failed")
                response = _error_response(request.get("request_id", "unknown"), "semantic_worker_malformed_request")
            response_queue.put(response)

    def _handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        request_id = request.get("request_id", "unknown")
        op = request.get("op")
        if request.get("pool_identifier") != self.pool_identifier:
            return _error_response(request_id, "semantic_worker_malformed_request")

        if op == "ping":
            return {"request_id": request_id, "status": "ok", "reason_code": None}
        if op == "stats":
            return {
                "request_id": request_id,
                "status": "ok",
                "reason_code": None,
                "worker_stats": {
                    "pool_identifier": self.pool_identifier,
                    "total_vectors": self.state.hnsw_store.get_current_count(),
                    "embedding_dim": self.state.embedding_dim,
                    "manifest_fingerprint": self.state.fingerprint,
                    "uptime_s": time.monotonic() - self.state.started_at,
                },
            }
        if op == "reload":
            try:
                self.state = _load_state(self.pool_identifier)
            except Exception:
                logger.exception("Worker reload failed")
                return _error_response(request_id, "semantic_worker_reload_failed")
            return {"request_id": request_id, "status": "ok", "reason_code": None}
        if op == "shutdown":
            self.shutdown_flag.set()
            threading.Thread(target=self.shutdown, daemon=True).start()
            return {"request_id": request_id, "status": "ok", "reason_code": None}
        if op != "knn":
            return _error_response(request_id, "semantic_worker_malformed_request")

        expected_fp = request.get("manifest_fingerprint")
        if expected_fp is not None and self.state.fingerprint != expected_fp:
            return _error_response(request_id, "semantic_worker_manifest_mismatch")

        try:
            vector_b64 = request["vector_b64"]
            embedding_dim = int(request["embedding_dim"])
            query_vector = decode_vector_from_b64(vector_b64, expected_dim=embedding_dim)
        except Exception:
            logger.exception("Worker decode failed")
            return _error_response(request_id, "semantic_worker_malformed_request")

        if embedding_dim != self.state.embedding_dim:
            return _error_response(request_id, "semantic_worker_manifest_mismatch")

        k = int(request.get("k", 10))
        ef = request.get("ef")
        results = self.state.hnsw_store.knn_query(query_vector, k=k, ef=ef)
        return {
            "request_id": request_id,
            "status": "ok",
            "reason_code": None,
            "results": results,
        }


class SemanticWorkerRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline()
        if not raw:
            return
        try:
            request = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            response = _error_response("unknown", "semantic_worker_malformed_request")
            self._send_response(response)
            return

        response_queue: queue.Queue = queue.Queue(maxsize=1)
        try:
            self.server.request_queue.put_nowait((request, response_queue))
        except queue.Full:
            response = _error_response(request.get("request_id", "unknown"), "semantic_worker_busy")
            response["status"] = "busy"
            self._send_response(response)
            return

        try:
            response = response_queue.get(timeout=self.server.request_timeout)
        except queue.Empty:
            response = _error_response(request.get("request_id", "unknown"), "semantic_worker_timeout")
        self._send_response(response)

    def _send_response(self, response: Dict[str, Any]) -> None:
        payload = json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
        self.wfile.write(payload)
        self.wfile.flush()
