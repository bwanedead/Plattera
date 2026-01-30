from __future__ import annotations

import base64
import uuid
from typing import Any, Dict, Iterable, Optional

import numpy as np

from ..manifest import SemanticIndexManifest


def encode_vector_to_b64(vector: Iterable[float]) -> str:
    arr = np.asarray(list(vector), dtype=np.float32)
    raw = arr.tobytes()
    return base64.b64encode(raw).decode("ascii")


def decode_vector_from_b64(payload: str, expected_dim: Optional[int] = None) -> np.ndarray:
    raw = base64.b64decode(payload.encode("ascii"))
    arr = np.frombuffer(raw, dtype=np.float32)
    if expected_dim is not None and arr.size != expected_dim:
        raise ValueError(f"vector_dim_mismatch: expected={expected_dim}, got={arr.size}")
    return np.ascontiguousarray(arr)


def new_request_id() -> str:
    return uuid.uuid4().hex


def manifest_fingerprint(manifest: Optional[SemanticIndexManifest]) -> Optional[str]:
    if manifest is None:
        return None
    model_token = manifest.embedding_model_fingerprint or manifest.embedding_model_id
    return f"{model_token}:{manifest.chunking_policy_id}:{manifest.embedding_dim}"


def build_request(
    op: str,
    *,
    pool_identifier: str,
    k: Optional[int] = None,
    ef: Optional[int] = None,
    embedding_dim: Optional[int] = None,
    vector_b64: Optional[str] = None,
    manifest_fingerprint_value: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "request_id": new_request_id(),
        "op": op,
        "pool_identifier": pool_identifier,
    }
    if k is not None:
        payload["k"] = int(k)
    if ef is not None:
        payload["ef"] = int(ef)
    if embedding_dim is not None:
        payload["embedding_dim"] = int(embedding_dim)
    if vector_b64 is not None:
        payload["vector_b64"] = vector_b64
    if manifest_fingerprint_value is not None:
        payload["manifest_fingerprint"] = manifest_fingerprint_value
    return payload
