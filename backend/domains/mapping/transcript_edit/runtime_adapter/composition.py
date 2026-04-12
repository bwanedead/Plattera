"""Mechanical transcript-edit to harness composition translation.

Handlers close over the launch scope (dossier_id, transcription_id, workspace_key)
so the LLM request only carries capability-level inputs — no storage bookkeeping IDs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

from harness.runtime.composition import ToolBinding, TurnBlock, TurnSurface
from tooling.mapping.transcript_edit import (
    publish_transcript_edit_output,
    save_transcript_edit,
)
from tooling.mapping.transcript_edit.artifact_hydration import make_hydrate_artifact_refs_handler
from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler
from tooling.mapping.transcript_edit.draft_persistence import resolve_workspace_key

from ..domain_pack import TranscriptEditDomainPack
from ..payloads import TranscriptEditStartupInventory
from ..prompting import PromptBlock

TRANSCRIPT_EDIT_RUNTIME_SURFACE_ID = "transcript_edit"
_PROMPT_BLOCK_NAMESPACE = "transcript_edit.prompt_block"
_PAYLOAD_NAMESPACE = "transcript_edit"


def build_transcript_edit_tool_bindings(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str | None,
) -> tuple[ToolBinding, ...]:
    """Build shared-capability tool bindings closed over the run scope."""
    entries = _tool_handler_entries(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_key=workspace_key,
    )
    return tuple(ToolBinding(tool_id=tool_id, handler=handler) for tool_id, handler in entries)


def build_transcript_edit_turn_surface(
    *,
    domain_pack: TranscriptEditDomainPack,
    startup_inventory: TranscriptEditStartupInventory,
) -> TurnSurface:
    """Package transcript-edit prompt blocks (including startup context) and tool bindings."""
    scope = startup_inventory.scope
    workspace_key = resolve_workspace_key(
        workspace_id=scope.workspace_id,
        run_id=scope.run_id,
    )
    tool_bindings = build_transcript_edit_tool_bindings(
        dossier_id=scope.dossier_id,
        transcription_id=scope.transcription_id,
        workspace_key=workspace_key,
    )
    payload = domain_pack.build_surface_payload()
    bound_tool_ids = [binding.tool_id for binding in tool_bindings]
    if bound_tool_ids != payload["tool_ids"]:
        raise ValueError("transcript_edit_runtime_tool_binding_mismatch")
    all_blocks = _build_turn_blocks(
        domain_pack.build_runtime_prompt_blocks(startup_inventory=startup_inventory)
    )
    return TurnSurface(
        surface_id=TRANSCRIPT_EDIT_RUNTIME_SURFACE_ID,
        blocks=all_blocks,
        payload={_PAYLOAD_NAMESPACE: _jsonable(payload)},
        tool_bindings=tool_bindings,
    )


# ---------------------------------------------------------------------------
# Handler wiring
# ---------------------------------------------------------------------------


def _tool_handler_entries(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str | None,
) -> tuple[tuple[str, Callable[[Any], Any]], ...]:
    return (
        (
            "hydrate_artifact_refs",
            make_hydrate_artifact_refs_handler(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
            ),
        ),
        (
            "transform_artifact",
            make_transform_artifact_handler(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
            ),
        ),
        (
            "save_workspace_artifact",
            _make_save_handler(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
            ),
        ),
        (
            "publish_workspace_artifact",
            _make_publish_handler(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
            ),
        ),
    )


def _make_save_handler(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str | None,
) -> Callable[[Any], Any]:
    def handler(request: Any) -> Any:
        inputs = dict(request.inputs) if hasattr(request, "inputs") else dict(request) if isinstance(request, dict) else {}
        try:
            raw_result = save_transcript_edit(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=workspace_key,
                transcript_text=inputs.get("transcript_text"),
                draft_payload=inputs.get("draft_payload"),
                base_revision_ref=inputs.get("base_revision_ref"),
                evidence_refs=inputs.get("evidence_refs") or [],
                rationale=inputs.get("rationale"),
            )
        except Exception as exc:
            return _exception_refusal(exc)
        return _normalize_tool_result(raw_result)

    return handler


def _make_publish_handler(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str | None,
) -> Callable[[Any], Any]:
    def handler(request: Any) -> Any:
        inputs = dict(request.inputs) if hasattr(request, "inputs") else dict(request) if isinstance(request, dict) else {}
        source_ref = str(inputs.get("source_revision_ref") or "").strip()
        if not source_ref:
            return _error_refusal("source_revision_ref_required", "source_revision_ref is required.")
        try:
            raw_result = publish_transcript_edit_output(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                source_revision_ref=source_ref,
                workspace_id=workspace_key,
            )
        except Exception as exc:
            return _exception_refusal(exc)
        return _normalize_tool_result(raw_result)

    return handler


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _build_turn_blocks(prompt_blocks: Sequence[PromptBlock]) -> tuple[TurnBlock, ...]:
    return tuple(
        TurnBlock(
            content=block.text,
            metadata={
                _PROMPT_BLOCK_NAMESPACE: {
                    "block_id": block.block_id,
                    "layer": block.layer,
                    "owner": block.owner,
                    "source_path": block.source_path,
                    "version": block.version,
                }
            },
        )
        for block in prompt_blocks
    )


def _normalize_tool_result(raw_result: Any) -> Any:
    if isinstance(raw_result, Mapping):
        if _looks_like_action_result(raw_result):
            return dict(raw_result)
        return {"executed": True, "outputs": {"result": _jsonable(raw_result)}}
    if is_dataclass(raw_result):
        return {"executed": True, "outputs": {"result": _jsonable(asdict(raw_result))}}
    if hasattr(raw_result, "model_dump"):
        return {"executed": True, "outputs": {"result": _jsonable(raw_result.model_dump(mode="python"))}}  # type: ignore[call-arg]
    return {"executed": True, "outputs": {"result": _jsonable(raw_result)}}


def _looks_like_action_result(value: Mapping[str, Any]) -> bool:
    return any(key in value for key in ("executed", "outputs", "refusal", "reason_codes", "artifact_refs"))


def _exception_refusal(exc: Exception) -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {"reason_code": "transcript_edit_tool_error", "retryable": False},
        "outputs": {"error": str(exc)},
    }


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


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="python"))  # type: ignore[call-arg]
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=str)]
    return value
