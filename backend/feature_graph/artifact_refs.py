"""Canonical feature-graph artifact ref vocabulary (no filesystem resolution)."""

from __future__ import annotations

import re
from typing import Literal

FeatureGraphArtifactType = Literal["ir", "compile", "judge", "bundle"]

ARTIFACT_REF_PREFIXES: dict[str, str] = {
    "ir": "feature_graph:ir:",
    "compile": "feature_graph:compile:",
    "judge": "feature_graph:judge:",
    "bundle": "feature_graph:bundle:",
}

SUPPORTED_ARTIFACT_TYPES = frozenset(ARTIFACT_REF_PREFIXES.keys())

ARTIFACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
MAX_ARTIFACT_ID_LEN = 128


class FeatureGraphArtifactRefError(ValueError):
    """Raised when artifact ref/type/id validation fails mechanically."""


def validate_artifact_id(artifact_id: str) -> str:
    text = str(artifact_id or "").strip()
    if not text or len(text) > MAX_ARTIFACT_ID_LEN or not ARTIFACT_ID_PATTERN.fullmatch(text):
        raise FeatureGraphArtifactRefError("feature_graph_artifact_id_invalid")
    return text


def build_feature_graph_artifact_ref(artifact_type: str, artifact_id: str) -> str:
    kind = str(artifact_type or "").strip().lower()
    if kind not in SUPPORTED_ARTIFACT_TYPES:
        raise FeatureGraphArtifactRefError("feature_graph_artifact_type_unsupported")
    validated_id = validate_artifact_id(artifact_id)
    return f"{ARTIFACT_REF_PREFIXES[kind]}{validated_id}"


def parse_feature_graph_artifact_ref(ref: str) -> tuple[str, str]:
    text = str(ref or "").strip()
    if not text:
        raise FeatureGraphArtifactRefError("feature_graph_artifact_ref_invalid")
    for artifact_type, prefix in ARTIFACT_REF_PREFIXES.items():
        if text.startswith(prefix):
            artifact_id = text[len(prefix) :]
            return artifact_type, validate_artifact_id(artifact_id)
    raise FeatureGraphArtifactRefError("feature_graph_artifact_ref_invalid")
