"""Qualify leaf action result refs for dossier-scoped transcript-edit missions.

Owns mechanical remapping of leaf transform/save/copy-forward results onto
dossier-qualified refs. Does not dispatch handlers or perform persistence.
"""

from __future__ import annotations

import re
from typing import Any

from tooling.mapping.transcript_edit.dossier_artifact_refs import (
    DossierArtifactRefError,
    DossierArtifactRefIndex,
    DossierArtifactRefTarget,
    parse_dossier_qualified_ref,
    qualify_leaf_ref,
)

# Explicit artifact-ref field vocabulary — do not rewrite every ``*_ref`` string.
_SINGLE_REF_KEYS = frozenset(
    {
        "ref_id",
        "derived_ref_id",
        "parent_ref_id",
        "root_source_ref",
        "source_ref",
        "working_draft_ref",
        "aggregate_working_ref",
        "base_revision_ref",
        "source_revision_ref",
        "previous_crop_set_overlay_ref",
        "view_of_crop_set_overlay_ref",
        "adjustment_source_ref",
        "crop_set_overlay_ref",
        "master_overlay_ref",
        "crop_ref",
        "local_source_ref",
        "placement_surface_ref",
        "source_unwrapped_from_ref",
        "rendered_ref",
    }
)
_COLLECTION_REF_KEYS = frozenset(
    {
        "artifact_refs",
        "evidence_refs",
    }
)
_HOST_OR_BINARY_KEYS = frozenset(
    {
        "absolute_path",
        "path",
        "b64",
        "image_b64",
        "base64",
        "bytes",
        "crop_img",
        "image",
        "image_obj",
        "workspace_root",
        "revision_relative_path",
        "output_relative_path",
    }
)
_PATHISH_RE = re.compile(
    r"(?:[A-Za-z]:\\|\\\\|/Users/|/home/|AppData|LOCALAPPDATA|/tmp/|\\Users\\)",
    re.IGNORECASE,
)
_SAFE_GENERIC_MESSAGES = {
    "transform_failed": "Leaf transform failed.",
    "source_image_missing": "Source image is missing or unreadable.",
    "derived_ref_not_found": "Derived image ref was not found.",
    "derived_persist_failed": "Derived image could not be persisted.",
    "unsupported_ref_kind": "Unsupported artifact ref kind for this action.",
}


class DossierActionResultRefError(Exception):
    """Mechanical refusal while remapping leaf action result refs."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail or "")
        message = self.code if not self.detail else f"{self.code}: {self.detail}"
        super().__init__(message)


def remap_dossier_action_result(
    *,
    result: Any,
    ref_index: DossierArtifactRefIndex,
    target: DossierArtifactRefTarget,
) -> Any:
    """Return a dossier-qualified projection of a leaf action result.

    Does not mutate ``result``. Preserves top-level ``image_evidence`` transport
    (including image bytes) while remapping its ``ref_id`` identity fields.
    Ordinary rows retain host/binary containment.
    """
    if not isinstance(result, dict):
        return result
    try:
        projected = _remap_value(
            result,
            ref_index=ref_index,
            target=target,
            preserve_binary=False,
            at_root=True,
        )
    except DossierArtifactRefError as exc:
        raise DossierActionResultRefError(
            "dossier_result_ref_remap_failed",
            exc.code,
        ) from exc
    if not isinstance(projected, dict):
        raise DossierActionResultRefError("dossier_result_ref_remap_failed", "non_object")
    projected["segment_id"] = target.segment_id
    projected["transcription_id"] = target.transcription_id
    return projected


def project_dossier_leaf_failure(
    *,
    result: Any,
    ref_index: DossierArtifactRefIndex,
    target: DossierArtifactRefTarget,
) -> dict[str, Any]:
    """Project a failed leaf action through the dossier containment boundary."""
    if not isinstance(result, dict):
        return {
            "executed": False,
            "refusal": {
                "reason_code": "leaf_action_failed",
                "retryable": False,
                "blocked_by_invariant": True,
                "blocked_by_budget": False,
                "missing_inputs": [],
            },
            "outputs": {
                "error": {
                    "code": "leaf_action_failed",
                    "message": "Leaf action failed.",
                }
            },
            "segment_id": target.segment_id,
            "transcription_id": target.transcription_id,
        }

    refusal_in = result.get("refusal") if isinstance(result.get("refusal"), dict) else {}
    reason_code = str(refusal_in.get("reason_code") or "leaf_action_failed")
    retryable = bool(refusal_in.get("retryable")) if "retryable" in refusal_in else False
    blocked_by_invariant = (
        bool(refusal_in.get("blocked_by_invariant"))
        if "blocked_by_invariant" in refusal_in
        else True
    )
    blocked_by_budget = (
        bool(refusal_in.get("blocked_by_budget"))
        if "blocked_by_budget" in refusal_in
        else False
    )
    missing_inputs = refusal_in.get("missing_inputs")
    if not isinstance(missing_inputs, list):
        missing_inputs = []

    try:
        projected_body = _remap_value(
            {k: v for k, v in result.items() if k not in {"executed", "refusal"}},
            ref_index=ref_index,
            target=target,
            preserve_binary=False,
            at_root=True,
        )
    except DossierArtifactRefError as exc:
        raise DossierActionResultRefError(
            "dossier_result_ref_remap_failed",
            exc.code,
        ) from exc

    if not isinstance(projected_body, dict):
        projected_body = {}

    outputs = projected_body.get("outputs")
    if not isinstance(outputs, dict):
        outputs = {}
    outputs = dict(outputs)
    outputs["error"] = _project_error_payload(
        outputs.get("error"),
        reason_code=reason_code,
        retryable=retryable,
    )
    projected_body["outputs"] = outputs

    out: dict[str, Any] = {
        "executed": False,
        "refusal": {
            "reason_code": reason_code,
            "retryable": retryable,
            "blocked_by_invariant": blocked_by_invariant,
            "blocked_by_budget": blocked_by_budget,
            "missing_inputs": missing_inputs,
        },
        "segment_id": target.segment_id,
        "transcription_id": target.transcription_id,
    }
    for key, value in projected_body.items():
        if key in {"executed", "refusal", "segment_id", "transcription_id"}:
            continue
        out[key] = value
    return out


def _project_error_payload(
    error: Any,
    *,
    reason_code: str,
    retryable: bool,
) -> dict[str, Any]:
    code = reason_code
    message = _SAFE_GENERIC_MESSAGES.get(reason_code, "Leaf action failed.")
    repair_hint: str | None = None

    if isinstance(error, dict):
        code = str(error.get("code") or code)
        raw_message = str(error.get("message") or "").strip()
        if raw_message and not _is_path_bearing_text(raw_message):
            message = raw_message
        elif code in _SAFE_GENERIC_MESSAGES:
            message = _SAFE_GENERIC_MESSAGES[code]
        raw_hint = error.get("repair_hint")
        if isinstance(raw_hint, str) and raw_hint.strip() and not _is_path_bearing_text(raw_hint):
            repair_hint = raw_hint.strip()
    elif isinstance(error, str) and error.strip() and not _is_path_bearing_text(error):
        message = error.strip()

    # Parameter-repair guidance is only retained when the refusal is retryable and safe.
    payload: dict[str, Any] = {"code": code, "message": message}
    if retryable and repair_hint:
        payload["repair_hint"] = repair_hint
    return payload


def _is_path_bearing_text(text: str) -> bool:
    return bool(_PATHISH_RE.search(text))


def _remap_value(
    value: Any,
    *,
    ref_index: DossierArtifactRefIndex,
    target: DossierArtifactRefTarget,
    preserve_binary: bool,
    at_root: bool,
) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, nested in value.items():
            if at_root and key == "image_evidence":
                out[key] = _remap_image_evidence(
                    nested,
                    ref_index=ref_index,
                    target=target,
                )
                continue
            if not preserve_binary and key in _HOST_OR_BINARY_KEYS:
                continue
            if key in _SINGLE_REF_KEYS and isinstance(nested, str):
                out[key] = _remap_ref_string(
                    nested,
                    ref_index=ref_index,
                    target=target,
                )
                continue
            if key in _COLLECTION_REF_KEYS:
                out[key] = _remap_ref_collection(
                    nested,
                    ref_index=ref_index,
                    target=target,
                )
                continue
            out[key] = _remap_value(
                nested,
                ref_index=ref_index,
                target=target,
                preserve_binary=preserve_binary,
                at_root=False,
            )
        return out
    if isinstance(value, list):
        return [
            _remap_value(
                item,
                ref_index=ref_index,
                target=target,
                preserve_binary=preserve_binary,
                at_root=False,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _remap_value(
                item,
                ref_index=ref_index,
                target=target,
                preserve_binary=preserve_binary,
                at_root=False,
            )
            for item in value
        )
    return value


def _remap_image_evidence(
    value: Any,
    *,
    ref_index: DossierArtifactRefIndex,
    target: DossierArtifactRefTarget,
) -> Any:
    if not isinstance(value, list):
        return value
    out: list[Any] = []
    for item in value:
        if not isinstance(item, dict):
            out.append(item)
            continue
        remapped = dict(item)
        leaf_ref = str(item.get("ref_id") or "").strip()
        if leaf_ref:
            remapped["ref_id"] = _remap_ref_string(
                leaf_ref,
                ref_index=ref_index,
                target=target,
            )
            resolved = ref_index.resolve(remapped["ref_id"])
            remapped["leaf_ref_id"] = resolved.leaf_ref
            remapped["segment_id"] = resolved.segment_id
            remapped["transcription_id"] = resolved.transcription_id
        out.append(remapped)
    return out


def _remap_ref_collection(
    value: Any,
    *,
    ref_index: DossierArtifactRefIndex,
    target: DossierArtifactRefTarget,
) -> Any:
    if isinstance(value, list):
        return [
            _remap_ref_string(item, ref_index=ref_index, target=target)
            if isinstance(item, str)
            else item
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _remap_ref_string(item, ref_index=ref_index, target=target)
            if isinstance(item, str)
            else item
            for item in value
        )
    return value


def _remap_ref_string(
    value: str,
    *,
    ref_index: DossierArtifactRefIndex,
    target: DossierArtifactRefTarget,
) -> str:
    text = value.strip()
    if not text:
        return value
    if text.startswith("dossier_segment:"):
        # Full resolve: startup index hit OR supported runtime kind; else raise.
        ref_index.resolve(text)
        return text
    if text.startswith("image:assoc:"):
        owner = _assoc_owner(text, ref_index=ref_index)
        if owner is None:
            raise DossierArtifactRefError("dossier_ref_run_not_in_topology", text)
        segment_id, transcription_id = owner
        qualified = qualify_leaf_ref(
            segment_id=segment_id,
            transcription_id=transcription_id,
            leaf_ref=text,
        )
        ref_index.resolve(qualified)
        return qualified
    if not _looks_like_leaf_artifact_ref(text):
        return value
    qualified = qualify_leaf_ref(
        segment_id=target.segment_id,
        transcription_id=target.transcription_id,
        leaf_ref=text,
    )
    ref_index.resolve(qualified)
    return qualified


def _assoc_owner(
    leaf_ref: str,
    *,
    ref_index: DossierArtifactRefIndex,
) -> tuple[str, str] | None:
    """Return the unique topology owner for an ``image:assoc:<tid>:...`` leaf ref."""
    parts = leaf_ref.split(":")
    if len(parts) < 4:
        return None
    assoc_tid = parts[2].strip()
    if not assoc_tid:
        return None
    owners = [
        (segment_id, transcription_id)
        for segment_id, transcription_id in ref_index.run_bindings
        if transcription_id == assoc_tid
    ]
    if len(owners) != 1:
        return None
    return owners[0]


def _looks_like_leaf_artifact_ref(text: str) -> bool:
    return (
        text.startswith("transcript_edit:")
        or text.startswith("image:assoc:")
        or text.startswith("image:derived:")
        or text.startswith("t0:raw:")
    )
