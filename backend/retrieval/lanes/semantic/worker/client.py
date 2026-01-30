from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .protocol import build_request, encode_vector_to_b64


@dataclass
class WorkerResponse:
    status: str
    reason_code: Optional[str]
    results: List[Tuple[int, float]]
    worker_stats: Optional[Dict[str, Any]] = None


class SemanticWorkerClient:
    def __init__(self, *, host: str, port: int, pool_identifier: str, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.pool_identifier = pool_identifier
        self.timeout = timeout

    def request(self, payload: Dict[str, Any]) -> WorkerResponse:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.settimeout(self.timeout)
                message = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
                sock.sendall(message)
                response_line = self._readline(sock)
        except (OSError, socket.timeout):
            return WorkerResponse(status="error", reason_code="semantic_worker_unavailable", results=[])

        if not response_line:
            return WorkerResponse(status="error", reason_code="semantic_worker_port_in_use", results=[])

        try:
            response = json.loads(response_line.decode("utf-8"))
        except json.JSONDecodeError:
            return WorkerResponse(status="error", reason_code="semantic_worker_port_in_use", results=[])

        status = response.get("status", "error")
        reason_code = response.get("reason_code")
        results = response.get("results") or []
        worker_stats = response.get("worker_stats")
        parsed_results = [(int(label), float(distance)) for label, distance in results]
        return WorkerResponse(status=status, reason_code=reason_code, results=parsed_results, worker_stats=worker_stats)

    def knn_query(
        self,
        *,
        vector: List[float],
        k: int,
        embedding_dim: int,
        manifest_fingerprint: Optional[str],
        ef: Optional[int] = None,
    ) -> WorkerResponse:
        payload = build_request(
            "knn",
            pool_identifier=self.pool_identifier,
            k=k,
            ef=ef,
            embedding_dim=embedding_dim,
            vector_b64=encode_vector_to_b64(vector),
            manifest_fingerprint_value=manifest_fingerprint,
        )
        return self.request(payload)

    def ping(self) -> WorkerResponse:
        payload = build_request("ping", pool_identifier=self.pool_identifier)
        return self.request(payload)

    def stats(self) -> WorkerResponse:
        payload = build_request("stats", pool_identifier=self.pool_identifier)
        return self.request(payload)

    def reload(self) -> WorkerResponse:
        payload = build_request("reload", pool_identifier=self.pool_identifier)
        return self.request(payload)

    @staticmethod
    def _readline(sock: socket.socket) -> bytes:
        with sock.makefile("rb") as stream:
            return stream.readline()
