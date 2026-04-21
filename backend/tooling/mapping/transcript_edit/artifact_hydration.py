"""Unified ``hydrate_artifact_refs`` capability for transcript-edit.

Dispatches to the correct underlying hydrator based on ref prefix.
The handler factory closes over the launch scope so the LLM request only carries ref_ids.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .draft_loading import hydrate_t0_draft_refs, hydrate_transcript_edit_working_draft
from .image_loading import hydrate_source_image_context, image_evidence_from_path
from .paths import (
    UnsafeArtifactPathSegmentError,
    transcript_edit_derived_images_dir,
)

_T0_PREFIX = "t0:raw:"
_IMAGE_ASSOC_PREFIX = "image:assoc:"
_IMAGE_DERIVED_PREFIX = "image:derived:"
_TE_PREFIX = "transcript_edit:"

_DEFAULT_MAX_REFS = 8
_HARD_MAX_REFS = 32


def make_hydrate_artifact_refs_handler(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str | None,
) -> Callable[[Any], Any]:
    """Return a handler for ``hydrate_artifact_refs`` closed over the run scope."""

    def handler(request: Any) -> Any:
        inputs: dict[str, Any] = dict(request.inputs) if hasattr(request, "inputs") else dict(request) if isinstance(request, dict) else {}
        ref_ids_raw = inputs.get("ref_ids")
        if ref_ids_raw is None:
            return _error_result("ref_ids_required", "ref_ids is required and must be a non-empty array.")
        if not isinstance(ref_ids_raw, (list, tuple)):
            return _error_result("ref_ids_invalid_type", "ref_ids must be a JSON array of strings.")
        max_refs_raw = inputs.get("max_refs")
        cap = _DEFAULT_MAX_REFS
        if max_refs_raw is not None:
            try:
                cap = max(1, min(int(max_refs_raw), _HARD_MAX_REFS))
            except (TypeError, ValueError):
                return _error_result("max_refs_invalid", "max_refs must be an integer.")

        all_ids: list[str] = []
        for item in ref_ids_raw:
            if not isinstance(item, str) or not item.strip():
                return _error_result("ref_id_invalid_type", "Each ref_id must be a non-empty string.")
            all_ids.append(item.strip())

        if not all_ids:
            return _error_result("ref_ids_empty", "ref_ids must contain at least one ref.")

        cap_exceeded = len(all_ids) > cap
        omitted = all_ids[cap:] if cap_exceeded else []
        to_process = all_ids[:cap]

        # Partition by kind
        t0_refs: list[str] = []
        te_refs: list[str] = []
        image_assoc_refs: list[str] = []
        image_derived_refs: list[str] = []
        unknown_refs: list[str] = []

        for rid in to_process:
            if rid.startswith(_T0_PREFIX):
                t0_refs.append(rid)
            elif rid.startswith(_IMAGE_ASSOC_PREFIX):
                image_assoc_refs.append(rid)
            elif rid.startswith(_IMAGE_DERIVED_PREFIX):
                image_derived_refs.append(rid)
            elif rid.startswith(_TE_PREFIX):
                te_refs.append(rid)
            else:
                unknown_refs.append(rid)

        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        image_evidence_collected: list[dict[str, Any]] = []

        if cap_exceeded:
            errors.append({
                "code": "cap_exceeded",
                "message": f"Requested {len(all_ids)} refs; capped at {cap}. First {cap} were hydrated.",
                "omitted_ref_ids": omitted,
            })

        # T0 batch
        if t0_refs:
            try:
                t0_result = hydrate_t0_draft_refs(
                    dossier_id=dossier_id,
                    transcription_id=transcription_id,
                    ref_ids=t0_refs,
                    max_refs=len(t0_refs),
                )
                for draft in t0_result.drafts:
                    results.append({
                        "ref_id": draft.ref_id,
                        "kind": "t0_draft",
                        "text": draft.text,
                        "metadata": draft.metadata,
                    })
                errors.extend(t0_result.errors)
            except Exception as exc:
                errors.append({"code": "t0_hydration_error", "message": str(exc)})

        # Transcript-edit workspace refs (one at a time — different workspace semantics)
        for rid in te_refs:
            if not workspace_key:
                errors.append({
                    "ref_id": rid,
                    "code": "workspace_required",
                    "message": "workspace_id or run_id is required to hydrate transcript_edit refs.",
                })
                continue
            try:
                raw = hydrate_transcript_edit_working_draft(
                    dossier_id=dossier_id,
                    transcription_id=transcription_id,
                    ref_id=rid,
                    workspace_id=workspace_key,
                )
                if raw.get("status") == "ok":
                    results.append({
                        "ref_id": rid,
                        "kind": "transcript_edit_draft",
                        "payload": raw.get("payload"),
                        "path": raw.get("path"),
                    })
                else:
                    errors.append({"ref_id": rid, "code": raw.get("code", "hydration_error"), "message": raw.get("message", "")})
            except Exception as exc:
                errors.append({"ref_id": rid, "code": "te_hydration_error", "message": str(exc)})

        # Source image refs
        for rid in image_assoc_refs:
            try:
                raw = hydrate_source_image_context(
                    dossier_id=dossier_id,
                    transcription_id=transcription_id,
                    ref_id=rid,
                )
                if raw.get("status") == "ok":
                    results.append({
                        "ref_id": rid,
                        "kind": "source_image",
                        "absolute_path": raw.get("absolute_path"),
                        "exists": raw.get("exists"),
                        "size_bytes": raw.get("size_bytes"),
                        "width_height": raw.get("width_height"),
                        "basename": raw.get("basename"),
                        "role": raw.get("role"),
                    })
                    b64 = raw.get("image_b64")
                    if b64:
                        image_evidence_collected.append({
                            "ref_id": rid,
                            "b64": b64,
                            "media_type": raw.get("image_media_type", "image/jpeg"),
                        })
                else:
                    errors.append({"ref_id": rid, "code": raw.get("code", "hydration_error"), "message": raw.get("message", "")})
            except Exception as exc:
                errors.append({"ref_id": rid, "code": "image_hydration_error", "message": str(exc)})

        # Derived image refs
        for rid in image_derived_refs:
            if not workspace_key:
                errors.append({
                    "ref_id": rid,
                    "code": "workspace_required",
                    "message": "workspace_id or run_id is required to hydrate image:derived refs.",
                })
                continue
            desc = _load_derived_image_descriptor(dossier_id, transcription_id, workspace_key, rid)
            if desc is None:
                errors.append({"ref_id": rid, "code": "not_found", "message": "Derived image ref not found."})
            else:
                results.append({"ref_id": rid, "kind": "derived_image", **desc})
                abs_path = desc.get("absolute_path")
                if abs_path:
                    from pathlib import Path as _Path
                    dp = _Path(str(abs_path))
                    if dp.is_file():
                        evidence = image_evidence_from_path(rid, dp)
                        if evidence:
                            image_evidence_collected.append(evidence)

        for rid in unknown_refs:
            errors.append({"ref_id": rid, "code": "unknown_ref_kind", "message": "Ref prefix not recognized."})

        result: dict[str, Any] = {
            "executed": True,
            "outputs": {
                "results": results,
                "errors": errors,
                "cap_exceeded": cap_exceeded,
                "hydrated_count": len(results),
            },
        }
        if image_evidence_collected:
            result["image_evidence"] = image_evidence_collected
        return result

    return handler


def _load_derived_image_descriptor(
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
    ref_id: str,
) -> dict[str, Any] | None:
    uuid = ref_id[len(_IMAGE_DERIVED_PREFIX):]
    if not uuid or "/" in uuid or "\\" in uuid or ".." in uuid:
        return None
    try:
        derived_dir = transcript_edit_derived_images_dir(dossier_id, transcription_id, workspace_key)
    except UnsafeArtifactPathSegmentError:
        return None
    desc_path = derived_dir / f"{uuid}.json"
    if not desc_path.is_file():
        return None
    try:
        data = json.loads(desc_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _error_result(code: str, message: str) -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {
            "reason_code": code,
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"error": {"code": code, "message": message}},
    }
