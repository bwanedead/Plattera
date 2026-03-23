"""Generic artifact ref extraction / slot updates (no mission semantics).

Used by harness session updates and by domain-owned step projection modules.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping

from .run_artifact import ArtifactRef, RunArtifact


def extract_output_ref(outputs: dict[str, object], key: str) -> ArtifactRef | None:
    raw = outputs.get(key)
    if isinstance(raw, dict):
        return ArtifactRef.model_validate(raw)
    if isinstance(raw, str) and raw:
        return ArtifactRef(artifact_path=raw)
    return None


def extract_inline_ref(outputs_inline: dict[str, object] | None, key: str) -> ArtifactRef | None:
    if not isinstance(outputs_inline, dict):
        return None
    raw = outputs_inline.get(key)
    if isinstance(raw, dict):
        try:
            return ArtifactRef.model_validate(raw)
        except Exception:
            path = raw.get("artifact_path")
            if isinstance(path, str) and path:
                return ArtifactRef(artifact_path=path)
            return None
    if isinstance(raw, str) and raw:
        return ArtifactRef(artifact_path=raw)
    return None


def put_artifact_ref(run_artifact: RunArtifact, key: str, ref: ArtifactRef | None) -> None:
    if ref is None:
        return
    run_artifact.artifact_refs[key] = ref


def flatten_latest_refs_payload(latest_refs: Mapping[str, object]) -> dict[str, object]:
    """Flatten dashboard latest-ref compatibility payloads with canonical ``artifact_refs`` precedence."""
    inner = latest_refs.get("artifact_refs")
    if isinstance(inner, Mapping):
        out = dict(inner)
        for key, value in latest_refs.items():
            if key in {"provider_artifact_refs", "artifact_refs"}:
                continue
            if key not in out:
                out[key] = value
        provider_refs = latest_refs.get("provider_artifact_refs")
        if isinstance(provider_refs, Mapping):
            for key, value in provider_refs.items():
                if key not in out:
                    out[key] = value
        return out

    out: dict[str, object] = {
        key: value for key, value in latest_refs.items() if key not in {"provider_artifact_refs", "artifact_refs"}
    }
    provider_refs = latest_refs.get("provider_artifact_refs")
    if isinstance(provider_refs, Mapping):
        out.update(provider_refs)
    return out


def latest_ref_artifact_path(latest_refs: Mapping[str, object], key: str) -> str | None:
    flat = flatten_latest_refs_payload(latest_refs)
    row = flat.get(key)
    if isinstance(row, Mapping):
        path = row.get("artifact_path")
        if isinstance(path, str):
            path = path.strip()
            if path:
                return path
    if isinstance(row, str):
        path = row.strip()
        if path:
            return path
    return None
