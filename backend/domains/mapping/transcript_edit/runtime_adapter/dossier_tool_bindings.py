"""Dossier-mode transcript-edit tool bindings (BR-002–BR-005 composition).

Assembles existing dossier handlers behind the five shared-capability action IDs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from harness.runtime.composition import ToolBinding
from tooling.mapping.transcript_edit.dossier_artifact_hydration import (
    hydrate_dossier_artifact_refs,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import DossierArtifactRefIndex
from tooling.mapping.transcript_edit.dossier_publication_persistence import (
    publish_dossier_transcript_edit_output,
)
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    DossierStartupInventoryBundle,
)
from tooling.mapping.transcript_edit.dossier_workspace_actions import (
    make_dossier_copy_forward_save_workspace_artifact_handler,
    make_dossier_save_workspace_artifact_handler,
    make_dossier_transform_artifact_handler,
)
from tooling.mapping.transcript_edit.draft_persistence import resolve_workspace_key

from ..execution.result_views import wrap_handler_with_result_view
from .tool_refusal_boundary import apply_tool_refusal_boundary

_MANIFEST_ACTION_IDS = (
    "hydrate_artifact_refs",
    "transform_artifact",
    "save_workspace_artifact",
    "copy_forward_save_workspace_artifact",
    "publish_workspace_artifact",
)
_PUBLISH_ALLOWED_KEYS = frozenset({"source_revision_refs"})


class DossierRuntimeBindingError(Exception):
    """Stable refusal while composing dossier runtime tool bindings."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail or "")
        message = self.code if not self.detail else f"{self.code}: {self.detail}"
        super().__init__(message)


def build_dossier_transcript_edit_tool_bindings(
    *,
    bundle: DossierStartupInventoryBundle,
) -> tuple[ToolBinding, ...]:
    """Compose BR-002–BR-005 dossier handlers behind the five TE action IDs."""
    dossier_id, workspace_key, ref_index = _validate_bundle(bundle)

    hydrate = wrap_handler_with_result_view(
        _make_hydrate_handler(
            dossier_id=dossier_id,
            ref_index=ref_index,
            workspace_key=workspace_key,
        ),
        action_id="hydrate_artifact_refs",
    )
    transform = wrap_handler_with_result_view(
        make_dossier_transform_artifact_handler(
            dossier_id=dossier_id,
            ref_index=ref_index,
            workspace_key=workspace_key,
        ),
        action_id="transform_artifact",
    )
    save = make_dossier_save_workspace_artifact_handler(
        dossier_id=dossier_id,
        ref_index=ref_index,
        workspace_key=workspace_key,
    )
    copy_forward = make_dossier_copy_forward_save_workspace_artifact_handler(
        dossier_id=dossier_id,
        ref_index=ref_index,
        workspace_key=workspace_key,
    )
    publish = _make_publish_handler(bundle=bundle, workspace_key=workspace_key)

    return tuple(
        ToolBinding(tool_id=tool_id, handler=_guard_transport(handler, action_id=tool_id))
        for tool_id, handler in zip(
            _MANIFEST_ACTION_IDS,
            (hydrate, transform, save, copy_forward, publish),
            strict=True,
        )
    )


def _validate_bundle(
    bundle: DossierStartupInventoryBundle,
) -> tuple[str, str, DossierArtifactRefIndex]:
    if not isinstance(bundle, DossierStartupInventoryBundle):
        raise DossierRuntimeBindingError("dossier_runtime_bundle_invalid")

    inventory = bundle.inventory
    ref_index = bundle.ref_index
    if not isinstance(ref_index, DossierArtifactRefIndex):
        raise DossierRuntimeBindingError("dossier_runtime_bundle_invalid")

    dossier_id = str(inventory.scope.dossier_id or "").strip()
    if not dossier_id:
        raise DossierRuntimeBindingError("dossier_runtime_bundle_invalid")

    workspace_key = resolve_workspace_key(
        workspace_id=inventory.scope.workspace_id,
        run_id=inventory.scope.run_id,
    )
    if not workspace_key:
        raise DossierRuntimeBindingError("dossier_runtime_workspace_required")

    if inventory.scope.dossier_id != ref_index.dossier_id:
        raise DossierRuntimeBindingError("dossier_runtime_dossier_mismatch")
    if inventory.topology_fingerprint != ref_index.topology_fingerprint:
        raise DossierRuntimeBindingError("dossier_runtime_topology_mismatch")

    inventory_runs: set[tuple[str, str]] = set()
    for segment in inventory.segments:
        segment_id = str(getattr(segment, "segment_id", "") or "").strip()
        if not segment_id:
            raise DossierRuntimeBindingError("dossier_runtime_run_binding_mismatch")
        for run in getattr(segment, "runs", ()) or ():
            transcription_id = str(getattr(run, "transcription_id", "") or "").strip()
            if not transcription_id:
                raise DossierRuntimeBindingError("dossier_runtime_run_binding_mismatch")
            inventory_runs.add((segment_id, transcription_id))

    for segment_id, transcription_id in inventory_runs:
        if not ref_index.has_run(segment_id, transcription_id):
            raise DossierRuntimeBindingError(
                "dossier_runtime_run_binding_mismatch",
                f"{segment_id}:{transcription_id}",
            )

    return dossier_id, workspace_key, ref_index


def _make_hydrate_handler(
    *,
    dossier_id: str,
    ref_index: DossierArtifactRefIndex,
    workspace_key: str,
) -> Callable[[Any], Any]:
    def handler(request: Any) -> Any:
        # Transport already validated by `_guard_transport`.
        inputs = _request_inputs(request) or {}
        return hydrate_dossier_artifact_refs(
            dossier_id=dossier_id,
            ref_index=ref_index,
            ref_ids=inputs.get("ref_ids"),
            workspace_key=workspace_key,
            max_refs=inputs.get("max_refs"),
        )

    return handler


def _make_publish_handler(
    *,
    bundle: DossierStartupInventoryBundle,
    workspace_key: str,
) -> Callable[[Any], Any]:
    def handler(request: Any) -> Any:
        # Transport already validated by `_guard_transport`.
        inputs = _request_inputs(request) or {}
        # Exact request shape: only source_revision_refs. Key presence matters;
        # do not coerce retired singular values.
        if "source_revision_ref" in inputs:
            return _error_refusal(
                "source_revision_refs_required",
                "Dossier publish requires source_revision_refs (plural); "
                "source_revision_ref is not accepted.",
            )
        if set(inputs.keys()) != _PUBLISH_ALLOWED_KEYS:
            if "source_revision_refs" not in inputs:
                return _error_refusal(
                    "source_revision_refs_required",
                    "source_revision_refs must be a JSON array of dossier-qualified exact revisions.",
                )
            return _error_refusal(
                "invalid_publish_request",
                "Dossier publish accepts only source_revision_refs.",
            )
        refs = inputs.get("source_revision_refs")
        if type(refs) is not list:
            return _error_refusal(
                "source_revision_refs_required",
                "source_revision_refs must be a JSON array of dossier-qualified exact revisions.",
            )
        return publish_dossier_transcript_edit_output(
            bundle=bundle,
            workspace_key=workspace_key,
            source_revision_refs=refs,
        )

    return handler


def _guard_transport(handler: Callable[[Any], Any], *, action_id: str) -> Callable[[Any], Any]:
    def wrapped(request: Any) -> Any:
        if not _is_valid_transport(request):
            return apply_tool_refusal_boundary(
                action_id,
                _error_refusal(
                    "invalid_request_transport",
                    "Request must be a mapping or typed request with mapping inputs.",
                ),
            )
        try:
            raw = handler(request)
        except Exception:
            return apply_tool_refusal_boundary(action_id, _exception_refusal())
        normalized = _normalize_tool_result(raw)
        return apply_tool_refusal_boundary(action_id, normalized)

    return wrapped


def _is_valid_transport(request: Any) -> bool:
    if isinstance(request, dict):
        return True
    if hasattr(request, "inputs"):
        return isinstance(getattr(request, "inputs"), Mapping)
    return False


def _request_inputs(request: Any) -> dict[str, Any] | None:
    if hasattr(request, "inputs"):
        inputs = getattr(request, "inputs")
        if isinstance(inputs, Mapping):
            return dict(inputs)
        return None
    if isinstance(request, dict):
        return dict(request)
    return None


def _normalize_tool_result(raw_result: Any) -> Any:
    if isinstance(raw_result, Mapping):
        if any(
            key in raw_result
            for key in ("executed", "outputs", "refusal", "reason_codes", "artifact_refs")
        ):
            return dict(raw_result)
        return {"executed": True, "outputs": {"result": raw_result}}
    return {"executed": True, "outputs": {"result": raw_result}}


def _error_refusal(code: str, message: str) -> dict[str, Any]:
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


def _exception_refusal() -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {"reason_code": "transcript_edit_tool_error", "retryable": False},
        "outputs": {
            "error": {
                "code": "transcript_edit_tool_error",
                "message": "Tool execution failed.",
            }
        },
    }
