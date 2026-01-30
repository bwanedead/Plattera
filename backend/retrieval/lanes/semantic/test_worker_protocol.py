from __future__ import annotations

import numpy as np

from .manifest import SemanticIndexManifest
from .worker.protocol import decode_vector_from_b64, encode_vector_to_b64, manifest_fingerprint


def test_vector_roundtrip_b64() -> None:
    vector = [0.1, -0.2, 0.3]
    encoded = encode_vector_to_b64(vector)
    decoded = decode_vector_from_b64(encoded, expected_dim=3)
    assert decoded.dtype == np.float32
    assert decoded.shape == (3,)
    assert np.allclose(decoded, np.asarray(vector, dtype=np.float32))


def test_manifest_fingerprint_includes_policy() -> None:
    manifest = SemanticIndexManifest(
        schema_version="v1",
        pool_identifier="FINAL_SEGMENTS",
        embedding_dim=384,
        embedding_model_id="model-x",
        embedding_model_fingerprint="fp123",
        chunking_policy_id="policy-a",
        created_at="now",
        updated_at="now",
    )
    fingerprint = manifest_fingerprint(manifest)
    assert fingerprint == "fp123:policy-a:384"
