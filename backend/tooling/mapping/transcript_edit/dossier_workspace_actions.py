"""Dossier-scoped transform/save/copy-forward routing over leaf TE primitives.

Resolves dossier-qualified targets, delegates to existing per-transcription
handlers/functions, and requalifies returned artifact refs. Not wired into the
production runtime adapter by this brief.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler
from tooling.mapping.transcript_edit.dossier_action_result_refs import (
    DossierActionResultRefError,
    project_dossier_leaf_failure,
    remap_dossier_action_result,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import (
    DossierArtifactRefError,
    DossierArtifactRefIndex,
    DossierArtifactRefTarget,
    qualify_leaf_ref,
)
from tooling.mapping.transcript_edit.draft_persistence import (
    copy_forward_save,
    parse_working_revision_ref,
    save_transcript_edit,
    working_revision_exists,
)

HydrateHandler = Callable[[Any], Any]


def make_dossier_transform_artifact_handler(
    *,
    dossier_id: str,
    ref_index: DossierArtifactRefIndex,
    workspace_key: str | None,
) -> Callable[[Any], Any]:
    """Route transform_artifact across dossier-qualified image refs."""

    def handler(request: Any) -> Any:
        guarded = _guard_index(dossier_id=dossier_id, ref_index=ref_index)
        if isinstance(guarded, dict):
            return guarded
        did, index = guarded
        inputs = _request_inputs(request)
        ref_id = str(inputs.get("ref_id") or "").strip()
        if not ref_id:
            return _refuse("dossier_ref_required", "ref_id must be a dossier-qualified artifact ref.")
        try:
            target = _resolve_target(index, ref_id)
        except DossierArtifactRefError as exc:
            return _refuse(exc.code, _safe_detail(exc))

        leaf_inputs = dict(inputs)
        leaf_inputs["ref_id"] = target.leaf_ref
        leaf_handler = make_transform_artifact_handler(
            dossier_id=did,
            transcription_id=target.transcription_id,
            workspace_key=workspace_key,
        )
        leaf_result = leaf_handler(leaf_inputs)
        return _project_result(leaf_result, ref_index=index, target=target)

    return handler


def make_dossier_save_workspace_artifact_handler(
    *,
    dossier_id: str,
    ref_index: DossierArtifactRefIndex,
    workspace_key: str | None,
) -> Callable[[Any], Any]:
    """Route save_workspace_artifact to a topology run via target/base refs."""

    def handler(request: Any) -> Any:
        guarded = _guard_index(dossier_id=dossier_id, ref_index=ref_index)
        if isinstance(guarded, dict):
            return guarded
        did, index = guarded
        inputs = _request_inputs(request)
        try:
            target = _resolve_save_target(index, inputs)
        except DossierArtifactRefError as exc:
            return _refuse(exc.code, _safe_detail(exc))

        base_leaf = None
        base_raw = inputs.get("base_revision_ref")
        if base_raw is not None and str(base_raw).strip():
            try:
                base_target = _resolve_exact_working_revision(index, str(base_raw).strip())
                base_leaf = base_target.leaf_ref
                if not working_revision_exists(
                    dossier_id=did,
                    transcription_id=base_target.transcription_id,
                    revision_ref=base_leaf,
                    workspace_id=workspace_key,
                ):
                    return _refuse(
                        "dossier_base_revision_not_found",
                        "The named base working revision does not exist in this workspace.",
                    )
            except DossierArtifactRefError as exc:
                return _refuse(exc.code, _safe_detail(exc))

        evidence_refs = inputs.get("evidence_refs") or []
        if evidence_refs is None:
            evidence_refs = []
        if not isinstance(evidence_refs, list):
            return _refuse("invalid_request", "evidence_refs must be a list when provided.")
        try:
            evidence_refs = _validate_evidence_refs(evidence_refs, ref_index=index)
        except DossierArtifactRefError as exc:
            return _refuse(exc.code, _safe_detail(exc))

        leaf_result = save_transcript_edit(
            dossier_id=did,
            transcription_id=target.transcription_id,
            workspace_id=workspace_key,
            transcript_text=inputs.get("transcript_text"),
            draft_payload=inputs.get("draft_payload"),
            base_revision_ref=base_leaf,
            evidence_refs=list(evidence_refs),
            rationale=inputs.get("rationale"),
        )
        return _project_result(leaf_result, ref_index=index, target=target)

    return handler


def make_dossier_copy_forward_save_workspace_artifact_handler(
    *,
    dossier_id: str,
    ref_index: DossierArtifactRefIndex,
    workspace_key: str | None,
) -> Callable[[Any], Any]:
    """Route copy-forward saves using a dossier-qualified exact working revision base."""

    def handler(request: Any) -> Any:
        guarded = _guard_index(dossier_id=dossier_id, ref_index=ref_index)
        if isinstance(guarded, dict):
            return guarded
        did, index = guarded
        inputs = _request_inputs(request)
        base_ref = str(inputs.get("base_ref") or "").strip()
        if not base_ref:
            return _refuse(
                "dossier_base_revision_required",
                "base_ref must be a dossier-qualified exact working revision.",
            )
        try:
            target = _resolve_exact_working_revision(index, base_ref)
        except DossierArtifactRefError as exc:
            return _refuse(exc.code, _safe_detail(exc))

        if not working_revision_exists(
            dossier_id=did,
            transcription_id=target.transcription_id,
            revision_ref=target.leaf_ref,
            workspace_id=workspace_key,
        ):
            return _refuse(
                "dossier_base_revision_not_found",
                "The named base working revision does not exist in this workspace.",
            )

        # Optional explicit target must match the base lineage.
        target_ref = str(inputs.get("target_ref") or "").strip()
        if target_ref:
            try:
                explicit = _resolve_target(index, target_ref)
            except DossierArtifactRefError as exc:
                return _refuse(exc.code, _safe_detail(exc))
            if (
                explicit.segment_id != target.segment_id
                or explicit.transcription_id != target.transcription_id
            ):
                return _refuse(
                    "dossier_target_lineage_mismatch",
                    "target_ref and base_ref resolve to different segment/transcription runs.",
                )

        copy_forward_paths = inputs.get("copy_forward_paths")
        if not isinstance(copy_forward_paths, list) or not copy_forward_paths:
            return _refuse(
                "copy_forward_paths_required",
                "copy_forward_paths must be a non-empty list of dot-notation path strings.",
            )
        set_paths = inputs.get("set_paths")
        if not isinstance(set_paths, dict):
            return _refuse(
                "set_paths_required",
                "set_paths must be an object mapping dot-notation paths to authored values.",
            )

        evidence_refs = inputs.get("evidence_refs") or []
        if not isinstance(evidence_refs, list):
            return _refuse("invalid_request", "evidence_refs must be a list when provided.")
        try:
            evidence_refs = _validate_evidence_refs(evidence_refs, ref_index=index)
        except DossierArtifactRefError as exc:
            return _refuse(exc.code, _safe_detail(exc))

        leaf_result = copy_forward_save(
            dossier_id=did,
            transcription_id=target.transcription_id,
            workspace_id=workspace_key,
            base_ref=target.leaf_ref,
            copy_forward_paths=copy_forward_paths,
            set_paths=set_paths,
            evidence_refs=list(evidence_refs),
            rationale=inputs.get("rationale"),
        )
        return _project_result(leaf_result, ref_index=index, target=target)

    return handler


def _guard_index(
    *,
    dossier_id: str,
    ref_index: DossierArtifactRefIndex,
) -> tuple[str, DossierArtifactRefIndex] | dict[str, Any]:
    did = str(dossier_id or "").strip()
    if not did:
        return _refuse("dossier_id_required", "dossier_id is required.")
    if not isinstance(ref_index, DossierArtifactRefIndex):
        return _refuse("dossier_index_mismatch", "ref_index must be a DossierArtifactRefIndex.")
    if ref_index.dossier_id != did:
        return _refuse(
            "dossier_index_mismatch",
            "Requested dossier_id does not match the bound ref index.",
        )
    return did, ref_index


def _resolve_save_target(
    ref_index: DossierArtifactRefIndex,
    inputs: dict[str, Any],
) -> DossierArtifactRefTarget:
    target_raw = str(inputs.get("target_ref") or "").strip()
    base_raw = str(inputs.get("base_revision_ref") or "").strip()
    if not target_raw and not base_raw:
        raise DossierArtifactRefError(
            "dossier_target_required",
            "Provide target_ref and/or base_revision_ref.",
        )
    target_from_target: DossierArtifactRefTarget | None = None
    target_from_base: DossierArtifactRefTarget | None = None
    if target_raw:
        target_from_target = _resolve_target(ref_index, target_raw)
    if base_raw:
        target_from_base = _resolve_exact_working_revision(ref_index, base_raw)
    if target_from_target and target_from_base:
        if (
            target_from_target.segment_id != target_from_base.segment_id
            or target_from_target.transcription_id != target_from_base.transcription_id
        ):
            raise DossierArtifactRefError("dossier_target_lineage_mismatch")
        return target_from_base
    return target_from_base or target_from_target  # type: ignore[return-value]


def _resolve_exact_working_revision(
    ref_index: DossierArtifactRefIndex,
    qualified_ref: str,
) -> DossierArtifactRefTarget:
    target = _resolve_target(ref_index, qualified_ref)
    if parse_working_revision_ref(target.leaf_ref) is None:
        raise DossierArtifactRefError("dossier_base_revision_invalid", target.leaf_ref)
    return target


def _validate_evidence_refs(
    evidence_refs: list[Any],
    *,
    ref_index: DossierArtifactRefIndex,
) -> list[str]:
    """Accept validated dossier-qualified refs or uniquely owned assoc refs only."""
    out: list[str] = []
    for raw in evidence_refs:
        text = str(raw or "").strip()
        if not text:
            continue
        if text.startswith("dossier_segment:"):
            # Full resolve — rejects unsupported/malformed/unknown qualified refs.
            ref_index.resolve(text)
            out.append(text)
            continue
        if text.startswith("image:assoc:"):
            parts = text.split(":")
            if len(parts) < 4 or not parts[2].strip():
                raise DossierArtifactRefError("dossier_ref_invalid", text)
            assoc_tid = parts[2].strip()
            owners = [
                (sid, tid)
                for sid, tid in ref_index.run_bindings
                if tid == assoc_tid
            ]
            if len(owners) != 1:
                raise DossierArtifactRefError(
                    "dossier_ref_run_not_in_topology",
                    assoc_tid,
                )
            segment_id, transcription_id = owners[0]
            qualified = qualify_leaf_ref(
                segment_id=segment_id,
                transcription_id=transcription_id,
                leaf_ref=text,
            )
            # Same strength as result remapping: unique owner is not enough.
            ref_index.resolve(qualified)
            out.append(qualified)
            continue
        if (
            text.startswith("transcript_edit:")
            or text.startswith("image:derived:")
            or text.startswith("t0:raw:")
        ):
            raise DossierArtifactRefError(
                "dossier_ref_required",
                "Opaque transcript/t0/derived evidence refs must be dossier-qualified.",
            )
        raise DossierArtifactRefError("dossier_ref_invalid", text)
    return out


def _resolve_target(
    ref_index: DossierArtifactRefIndex,
    qualified_ref: str,
) -> DossierArtifactRefTarget:
    text = str(qualified_ref or "").strip()
    if not text:
        raise DossierArtifactRefError("dossier_ref_required")
    if not text.startswith("dossier_segment:"):
        raise DossierArtifactRefError("dossier_ref_required", text)
    return ref_index.resolve(text)


def _project_result(
    leaf_result: Any,
    *,
    ref_index: DossierArtifactRefIndex,
    target: DossierArtifactRefTarget,
) -> Any:
    if not isinstance(leaf_result, dict):
        return leaf_result
    if leaf_result.get("executed") is False:
        try:
            return project_dossier_leaf_failure(
                result=leaf_result,
                ref_index=ref_index,
                target=target,
            )
        except DossierActionResultRefError as exc:
            return _refuse(exc.code, "Failed to project leaf action refusal.")
    try:
        return remap_dossier_action_result(
            result=leaf_result,
            ref_index=ref_index,
            target=target,
        )
    except DossierActionResultRefError as exc:
        return _refuse(exc.code, "Failed to qualify leaf action result refs.")


def _request_inputs(request: Any) -> dict[str, Any]:
    if hasattr(request, "inputs"):
        return dict(request.inputs or {})
    if isinstance(request, dict):
        return dict(request)
    return {}


def _refuse(code: str, message: str) -> dict[str, Any]:
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


def _safe_detail(exc: DossierArtifactRefError) -> str:
    # Prefer stable code-facing messages; never forward host paths.
    mapping = {
        "dossier_ref_required": "A dossier-qualified artifact ref is required.",
        "dossier_ref_invalid": "The dossier-qualified artifact ref is malformed.",
        "dossier_ref_kind_not_runtime_resolvable": (
            "The leaf ref kind is not runtime-resolvable for dossier actions."
        ),
        "dossier_ref_run_not_in_topology": (
            "The segment/transcription pair is not present in the dossier topology."
        ),
        "dossier_target_required": "A dossier target_ref or base_revision_ref is required.",
        "dossier_target_lineage_mismatch": (
            "Target refs resolve to different segment/transcription runs."
        ),
        "dossier_base_revision_required": "A dossier-qualified exact working revision is required.",
        "dossier_base_revision_invalid": (
            "base revision must match transcript_edit:working:rev:NNNN."
        ),
        "dossier_base_revision_not_found": (
            "The named base working revision does not exist in this workspace."
        ),
        "dossier_index_mismatch": "Requested dossier_id does not match the bound ref index.",
        "dossier_result_ref_remap_failed": "Failed to qualify leaf action result refs.",
    }
    return mapping.get(exc.code, exc.code)
