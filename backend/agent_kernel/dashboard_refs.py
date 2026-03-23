"""Legacy dashboard ref projection helpers for Agent Kernel v0."""

from __future__ import annotations

from .run_artifact import ArtifactRef, RunArtifact

_LEGACY_DASHBOARD_ARTIFACT_REF_FIELDS: tuple[tuple[str, str], ...] = (
    ("ir_artifact_ref", "ir_ref"),
    ("compile_artifact_ref", "compile_ref"),
    ("judge_artifact_ref", "judge_ref"),
    ("bundle_artifact_ref", "bundle_ref"),
    ("georeference_artifact_ref", "georef_ref"),
    ("render_artifact_ref", "render_ref"),
    ("retrieval_artifact_ref", "retrieval_ref"),
    ("deed_span_index_artifact_ref", "deed_span_index_ref"),
)


def build_latest_refs_map(run_artifact: RunArtifact) -> dict[str, dict[str, object]]:
    """Flatten run-level refs into one opaque-key map.

    ``artifact_refs`` is canonical. Legacy named slots are only surfaced here for dashboard
    compatibility and can be removed once callers fully converge.
    """

    merged: dict[str, dict[str, object]] = {}
    for attr_name, key in _LEGACY_DASHBOARD_ARTIFACT_REF_FIELDS:
        ref = getattr(run_artifact, attr_name)
        dumped = _dump_ref(ref)
        if dumped is not None:
            merged[key] = dumped
    validate_payload = build_latest_validate_ref(run_artifact)
    if validate_payload is not None:
        merged["validate_ref"] = validate_payload
    for slot_key, ref in (run_artifact.artifact_refs or {}).items():
        dumped = _dump_ref(ref)
        if dumped is not None:
            merged[str(slot_key)] = dumped
    return merged


def build_latest_validate_ref(run_artifact: RunArtifact) -> dict[str, object] | None:
    if run_artifact.validate_artifact_ref is not None:
        return _dump_ref(run_artifact.validate_artifact_ref)
    for step in reversed(run_artifact.steps):
        if step.action != "validate_artifact":
            continue
        return {"artifact_path": "inline://validation", "reason_codes": step.reason_codes}
    return None


def _dump_ref(ref: ArtifactRef | None) -> dict[str, object] | None:
    if ref is None:
        return None
    return ref.model_dump(mode="json")
