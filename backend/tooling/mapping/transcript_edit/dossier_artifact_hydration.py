"""Read-only dossier-qualified artifact hydration router.

Accepts dossier-qualified refs, resolves them through a validated index, and
dispatches leaf refs to the existing per-transcription hydrator.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

from tooling.mapping.transcript_edit.artifact_hydration import (
    make_hydrate_artifact_refs_handler,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import (
    DossierArtifactRefError,
    DossierArtifactRefIndex,
)

HydrateHandler = Callable[[Any], Any]
HandlerFactory = Callable[..., HydrateHandler]

_DEFAULT_MAX_REFS = 8
_HARD_MAX_REFS = 32
_LEAF_ERROR_MESSAGE = "Leaf hydrator reported an error for this ref."
_LEAF_REFUSAL_MESSAGE = "Leaf hydrator refused the request."
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
    }
)


def hydrate_dossier_artifact_refs(
    *,
    dossier_id: str,
    ref_index: DossierArtifactRefIndex,
    ref_ids: Sequence[str],
    workspace_key: str | None = None,
    max_refs: int | None = None,
    handler_factory: HandlerFactory | None = None,
) -> dict[str, Any]:
    """Hydrate dossier-qualified refs; preserve request order and partial success."""
    did = str(dossier_id or "").strip()
    if not did:
        return _error_result("dossier_id_required", "dossier_id is required.")

    if not isinstance(ref_index, DossierArtifactRefIndex):
        return _error_result("ref_index_invalid", "ref_index must be a DossierArtifactRefIndex.")
    if ref_index.dossier_id != did:
        return _error_result(
            "index_dossier_mismatch",
            "Requested dossier_id does not match the bound ref index dossier.",
        )

    # JSON array/list shape only — refuse tuples and other sequences.
    if type(ref_ids) is not list:
        return _error_result("ref_ids_invalid_type", "ref_ids must be a JSON array of strings.")

    all_ids: list[str] = []
    for item in ref_ids:
        if not isinstance(item, str) or not item.strip():
            return _error_result("ref_id_invalid_type", "Each ref_id must be a non-empty string.")
        all_ids.append(item.strip())
    if not all_ids:
        return _error_result("ref_ids_empty", "ref_ids must contain at least one ref.")

    if max_refs is None:
        cap = _DEFAULT_MAX_REFS
    elif type(max_refs) is not int:
        return _error_result("max_refs_invalid", "max_refs must be an integer.")
    else:
        cap = max(1, min(max_refs, _HARD_MAX_REFS))

    cap_exceeded = len(all_ids) > cap
    omitted = all_ids[cap:] if cap_exceeded else []
    to_process = all_ids[:cap]

    # (qualified, segment_id, transcription_id, leaf_ref) or None when unknown
    resolved: list[tuple[str, str, str, str] | None] = []
    errors: list[dict[str, Any]] = []
    if cap_exceeded:
        errors.append(
            {
                "code": "cap_exceeded",
                "message": f"Requested {len(all_ids)} refs; capped at {cap}. First {cap} were hydrated.",
                "omitted_ref_ids": omitted,
            }
        )

    by_transcription: dict[str, list[str]] = defaultdict(list)
    leaf_to_qualified: dict[tuple[str, str], list[str]] = defaultdict(list)
    qualified_meta: dict[str, tuple[str, str, str]] = {}

    for qualified in to_process:
        try:
            target = ref_index.resolve(qualified)
        except DossierArtifactRefError as exc:
            resolved.append(None)
            errors.append(
                {
                    "ref_id": qualified,
                    "code": exc.code,
                    "message": exc.detail or exc.code,
                }
            )
            continue
        resolved.append(
            (qualified, target.segment_id, target.transcription_id, target.leaf_ref)
        )
        qualified_meta[qualified] = (
            target.segment_id,
            target.transcription_id,
            target.leaf_ref,
        )
        by_transcription[target.transcription_id].append(target.leaf_ref)
        leaf_to_qualified[(target.transcription_id, target.leaf_ref)].append(qualified)

    factory = handler_factory or make_hydrate_artifact_refs_handler
    leaf_results_by_qualified: dict[str, dict[str, Any]] = {}
    leaf_errors_by_qualified: dict[str, dict[str, Any]] = {}
    batch_errors: list[dict[str, Any]] = []
    image_evidence: list[dict[str, Any]] = []

    for transcription_id, leaf_refs in by_transcription.items():
        unique_leaves: list[str] = []
        seen_leaves: set[str] = set()
        for leaf in leaf_refs:
            if leaf in seen_leaves:
                continue
            seen_leaves.add(leaf)
            unique_leaves.append(leaf)

        handler = factory(
            dossier_id=did,
            transcription_id=transcription_id,
            workspace_key=workspace_key,
        )
        try:
            raw = handler({"ref_ids": unique_leaves, "max_refs": len(unique_leaves)})
        except Exception:  # noqa: BLE001 — localize; never leak host paths via str(exc)
            for leaf in unique_leaves:
                for qualified in leaf_to_qualified[(transcription_id, leaf)]:
                    segment_id, _, _ = qualified_meta[qualified]
                    leaf_errors_by_qualified[qualified] = {
                        "ref_id": qualified,
                        "segment_id": segment_id,
                        "transcription_id": transcription_id,
                        "leaf_ref_id": leaf,
                        "code": "transcription_hydration_error",
                        "message": "Leaf hydrator raised an unexpected error.",
                    }
            continue

        if not isinstance(raw, dict):
            for leaf in unique_leaves:
                for qualified in leaf_to_qualified[(transcription_id, leaf)]:
                    segment_id, _, _ = qualified_meta[qualified]
                    leaf_errors_by_qualified[qualified] = {
                        "ref_id": qualified,
                        "segment_id": segment_id,
                        "transcription_id": transcription_id,
                        "leaf_ref_id": leaf,
                        "code": "hydration_invalid_result",
                        "message": "Leaf hydrator returned a non-object result.",
                    }
            continue

        if raw.get("executed") is False:
            err = ((raw.get("outputs") or {}) if isinstance(raw.get("outputs"), dict) else {}).get(
                "error"
            )
            code = "hydration_refused"
            if isinstance(err, dict) and err.get("code"):
                code = str(err.get("code"))
            for leaf in unique_leaves:
                for qualified in leaf_to_qualified[(transcription_id, leaf)]:
                    segment_id, _, _ = qualified_meta[qualified]
                    leaf_errors_by_qualified[qualified] = {
                        "ref_id": qualified,
                        "segment_id": segment_id,
                        "transcription_id": transcription_id,
                        "leaf_ref_id": leaf,
                        "code": code,
                        "message": _LEAF_REFUSAL_MESSAGE,
                    }
            continue

        outputs = raw.get("outputs") if isinstance(raw.get("outputs"), dict) else {}
        results_raw = outputs.get("results")
        errors_raw = outputs.get("errors")
        if results_raw is None:
            results_raw = []
        if errors_raw is None:
            errors_raw = []
        if type(results_raw) is not list:
            for leaf in unique_leaves:
                for qualified in leaf_to_qualified[(transcription_id, leaf)]:
                    segment_id, _, _ = qualified_meta[qualified]
                    leaf_errors_by_qualified[qualified] = {
                        "ref_id": qualified,
                        "segment_id": segment_id,
                        "transcription_id": transcription_id,
                        "leaf_ref_id": leaf,
                        "code": "hydration_invalid_leaf_results",
                        "message": "Leaf hydrator returned a non-list results collection.",
                    }
            continue
        if type(errors_raw) is not list:
            for leaf in unique_leaves:
                for qualified in leaf_to_qualified[(transcription_id, leaf)]:
                    segment_id, _, _ = qualified_meta[qualified]
                    leaf_errors_by_qualified[qualified] = {
                        "ref_id": qualified,
                        "segment_id": segment_id,
                        "transcription_id": transcription_id,
                        "leaf_ref_id": leaf,
                        "code": "hydration_invalid_leaf_errors",
                        "message": "Leaf hydrator returned a non-list errors collection.",
                    }
            continue

        for item in results_raw:
            if not isinstance(item, dict):
                continue
            leaf_ref = str(item.get("ref_id") or "").strip()
            if not leaf_ref:
                continue
            for qualified in leaf_to_qualified.get((transcription_id, leaf_ref), ()):
                segment_id, _, _ = qualified_meta[qualified]
                remapped = _project_dossier_result_row(item)
                remapped["ref_id"] = qualified
                remapped["leaf_ref_id"] = leaf_ref
                remapped["segment_id"] = segment_id
                remapped["transcription_id"] = transcription_id
                leaf_results_by_qualified[qualified] = remapped

        for err in errors_raw:
            if not isinstance(err, dict):
                continue
            leaf_ref = str(err.get("ref_id") or "").strip()
            if leaf_ref and (transcription_id, leaf_ref) in leaf_to_qualified:
                for qualified in leaf_to_qualified[(transcription_id, leaf_ref)]:
                    segment_id, _, _ = qualified_meta[qualified]
                    leaf_errors_by_qualified[qualified] = {
                        "ref_id": qualified,
                        "leaf_ref_id": leaf_ref,
                        "segment_id": segment_id,
                        "transcription_id": transcription_id,
                        "code": str(err.get("code") or "leaf_hydration_error"),
                        "message": _LEAF_ERROR_MESSAGE,
                    }
            else:
                batch_errors.append(
                    {
                        "transcription_id": transcription_id,
                        "code": str(err.get("code") or "leaf_hydration_error"),
                        "message": _LEAF_ERROR_MESSAGE,
                    }
                )

        evidence_raw = raw.get("image_evidence")
        if evidence_raw is None:
            evidence_raw = []
        if type(evidence_raw) is not list:
            batch_errors.append(
                {
                    "transcription_id": transcription_id,
                    "code": "hydration_invalid_image_evidence",
                    "message": "Leaf hydrator returned a non-list image_evidence collection.",
                }
            )
        else:
            for evidence in evidence_raw:
                if not isinstance(evidence, dict):
                    continue
                leaf_ref = str(evidence.get("ref_id") or "").strip()
                if not leaf_ref:
                    continue
                for qualified in leaf_to_qualified.get((transcription_id, leaf_ref), ()):
                    segment_id, _, _ = qualified_meta[qualified]
                    # Preserve image_evidence transport (including bytes); remap identity only.
                    remapped_ev = dict(evidence)
                    remapped_ev["ref_id"] = qualified
                    remapped_ev["leaf_ref_id"] = leaf_ref
                    remapped_ev["segment_id"] = segment_id
                    remapped_ev["transcription_id"] = transcription_id
                    image_evidence.append(remapped_ev)

    results: list[dict[str, Any]] = []
    for item in resolved:
        if item is None:
            continue
        qualified, segment_id, transcription_id, leaf_ref = item
        hit = leaf_results_by_qualified.get(qualified)
        if hit is not None:
            results.append(hit)
            continue
        err = leaf_errors_by_qualified.get(qualified)
        if err is not None:
            errors.append(err)
            continue
        errors.append(
            {
                "ref_id": qualified,
                "segment_id": segment_id,
                "transcription_id": transcription_id,
                "leaf_ref_id": leaf_ref,
                "code": "hydration_silent_omission",
                "message": "Leaf hydrator omitted a requested ref without an explicit result or error.",
            }
        )

    errors.extend(batch_errors)
    result: dict[str, Any] = {
        "executed": True,
        "outputs": {
            "results": results,
            "errors": errors,
            "cap_exceeded": cap_exceeded,
            "hydrated_count": len(results),
        },
    }
    if image_evidence:
        result["image_evidence"] = image_evidence
    return result


def _project_dossier_result_row(item: dict[str, Any]) -> dict[str, Any]:
    """Copy a leaf result row without mutating it; strip host/binary fields recursively."""
    projected = _strip_host_or_binary_fields(item)
    if not isinstance(projected, dict):
        return {}
    return projected


def _strip_host_or_binary_fields(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, nested in value.items():
            if key in _HOST_OR_BINARY_KEYS:
                continue
            out[key] = _strip_host_or_binary_fields(nested)
        return out
    if isinstance(value, list):
        return [_strip_host_or_binary_fields(item) for item in value]
    if isinstance(value, tuple):
        return [_strip_host_or_binary_fields(item) for item in value]
    return value


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
