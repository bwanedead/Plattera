"""Mechanical deed-to-IR to harness composition translation."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import is_dataclass
from typing import Any

from harness.runtime.composition import ToolBinding, TurnBlock, TurnSurface
from tooling.artifact_capability import HYDRATE_ARTIFACT_REFS
from tooling.mapping.deed_to_ir.artifact_hydration import (
    list_feature_graph_artifacts,
    make_hydrate_artifact_refs_handler,
)
from tooling.mapping.deed_to_ir.feature_graph_capabilities import describe_feature_graph_capabilities
from tooling.mapping.deed_to_ir.input_hydration import make_hydrate_deed_to_ir_input_handler
from tooling.mapping.deed_to_ir.ir_draft_patch import patch_ir_draft
from tooling.mapping.deed_to_ir.ir_mapping_submission import submit_ir_for_mapping
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.output_persistence import publish_deed_to_ir_output

from ..domain_pack import DeedToIrDomainPack
from ..payloads import DeedToIrStartupHandoff
from ..prompting import PromptBlock

DEED_TO_IR_RUNTIME_SURFACE_ID = "deed_to_ir"
_PROMPT_BLOCK_NAMESPACE = "deed_to_ir.prompt_block"
_PAYLOAD_NAMESPACE = "deed_to_ir"
logger = logging.getLogger(__name__)

_WIN_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\s\"']+")
_UNIX_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9:/.-])/(?:[^\s\"']+)")
_SAFE_ERROR_CODE_PATTERN = re.compile(r"^[a-z0-9_]+$")


def build_deed_to_ir_tool_bindings(
    *,
    dossier_id: str,
    handoff: DeedToIrStartupHandoff,
) -> tuple[ToolBinding, ...]:
    entries = _tool_handler_entries(dossier_id=dossier_id, handoff=handoff)
    return tuple(ToolBinding(tool_id=tool_id, handler=handler) for tool_id, handler in entries)


def build_deed_to_ir_turn_surface(
    *,
    domain_pack: DeedToIrDomainPack,
    startup_handoff: DeedToIrStartupHandoff,
) -> TurnSurface:
    payload = domain_pack.build_surface_payload()
    tool_bindings = build_deed_to_ir_tool_bindings(
        dossier_id=startup_handoff.scope.dossier_id,
        handoff=startup_handoff,
    )
    bound_tool_ids = [binding.tool_id for binding in tool_bindings]
    if bound_tool_ids != payload["tool_ids"]:
        raise ValueError("deed_to_ir_runtime_tool_binding_mismatch")

    all_blocks = _build_turn_blocks(
        domain_pack.build_runtime_prompt_blocks(startup_handoff=startup_handoff)
    )
    surface_payload = {
        _PAYLOAD_NAMESPACE: _jsonable(payload),
        f"{_PAYLOAD_NAMESPACE}_startup_handoff": _jsonable(_handoff_wire(startup_handoff)),
    }
    return TurnSurface(
        surface_id=DEED_TO_IR_RUNTIME_SURFACE_ID,
        blocks=all_blocks,
        payload=surface_payload,
        tool_bindings=tool_bindings,
    )


def _tool_handler_entries(
    *,
    dossier_id: str,
    handoff: DeedToIrStartupHandoff,
) -> tuple[tuple[str, Callable[[Any], Any]], ...]:
    handoff_context = _handoff_tool_context(handoff)
    return (
        (
            "hydrate_deed_to_ir_input",
            make_hydrate_deed_to_ir_input_handler(handoff_context=handoff_context),
        ),
        (
            "describe_feature_graph_capabilities",
            _make_capabilities_handler(),
        ),
        (
            "save_ir_artifact",
            _make_save_ir_handler(
                dossier_id=dossier_id,
                draft_workspace_id=handoff.scope.workspace_id,
                draft_run_id=handoff.scope.run_id,
            ),
        ),
        (
            "patch_ir_draft",
            _make_patch_ir_draft_handler(
                dossier_id=dossier_id,
                draft_workspace_id=handoff.scope.workspace_id,
                draft_run_id=handoff.scope.run_id,
            ),
        ),
        (
            "submit_ir_for_mapping",
            _make_submit_ir_handler(dossier_id=dossier_id),
        ),
        (
            "publish_deed_to_ir_output",
            _make_publish_output_handler(dossier_id=dossier_id, handoff=handoff),
        ),
        (
            HYDRATE_ARTIFACT_REFS,
            make_hydrate_artifact_refs_handler(
                dossier_id=dossier_id,
                transcription_id=handoff.scope.transcription_id,
                workspace_id=handoff.scope.workspace_id,
                run_id=handoff.scope.run_id,
                handoff_context=handoff_context,
            ),
        ),
        (
            "list_feature_graph_artifacts",
            _make_list_fg_artifacts_handler(dossier_id=dossier_id),
        ),
    )


def _make_capabilities_handler() -> Callable[[Any], Any]:
    def handler(request: Any) -> dict[str, Any]:
        inputs = _extract_inputs(request)
        sections = inputs.get("sections")
        operation_names = inputs.get("operation_names")
        if sections is not None and not isinstance(sections, list):
            return _error_refusal("invalid_capability_sections", "sections must be an array when provided.")
        if operation_names is not None and not isinstance(operation_names, list):
            return _error_refusal("invalid_operation_names", "operation_names must be an array when provided.")
        try:
            outputs = describe_feature_graph_capabilities(
                sections=sections,
                operation_names=operation_names,
            )
        except ValueError as exc:
            code = _error_code_for_exception(exc)
            return _error_refusal(code, code)
        return {"executed": True, "outputs": outputs}

    return handler


def _make_save_ir_handler(
    *,
    dossier_id: str,
    draft_workspace_id: str | None = None,
    draft_run_id: str | None = None,
) -> Callable[[Any], Any]:
    def handler(request: Any) -> dict[str, Any]:
        inputs = _extract_inputs(request)
        graph = inputs.get("feature_graph")
        try:
            return save_ir_artifact(
                dossier_id=dossier_id,
                feature_graph=graph if isinstance(graph, dict) else {},
                artifact_id=_optional_str(inputs.get("artifact_id")),
                base_draft_ref=_optional_str(inputs.get("base_draft_ref")),
                source_document_id=_optional_str(inputs.get("source_document_id")),
                created_by=_optional_str(inputs.get("created_by")),
                draft_workspace_id=draft_workspace_id,
                draft_run_id=draft_run_id,
            )
        except Exception as exc:
            return _exception_refusal(exc)

    return handler


def _make_patch_ir_draft_handler(
    *,
    dossier_id: str,
    draft_workspace_id: str | None = None,
    draft_run_id: str | None = None,
) -> Callable[[Any], Any]:
    def handler(request: Any) -> dict[str, Any]:
        inputs = _extract_inputs(request)
        base_draft_ref = _optional_str(inputs.get("base_draft_ref"))
        if not base_draft_ref:
            return _error_refusal("base_draft_ref_required", "base_draft_ref is required.")
        node_upserts = inputs.get("node_upserts") if isinstance(inputs.get("node_upserts"), list) else []
        edge_upserts = inputs.get("edge_upserts") if isinstance(inputs.get("edge_upserts"), list) else []
        node_removals = inputs.get("node_removals") if isinstance(inputs.get("node_removals"), list) else []
        edge_removals = inputs.get("edge_removals") if isinstance(inputs.get("edge_removals"), list) else []
        try:
            return patch_ir_draft(
                dossier_id=dossier_id,
                base_draft_ref=base_draft_ref,
                node_upserts=node_upserts,
                edge_upserts=edge_upserts,
                node_removals=node_removals,
                edge_removals=edge_removals,
                graph_id=_optional_str(inputs.get("graph_id")),
                draft_workspace_id=draft_workspace_id,
                draft_run_id=draft_run_id,
            )
        except Exception as exc:
            return _exception_refusal(exc)

    return handler


def _make_submit_ir_handler(*, dossier_id: str) -> Callable[[Any], Any]:
    def handler(request: Any) -> dict[str, Any]:
        inputs = _extract_inputs(request)
        ir_artifact_ref = _optional_str(inputs.get("ir_artifact_ref"))
        if not ir_artifact_ref:
            return _error_refusal("ir_artifact_ref_required", "ir_artifact_ref is required.")
        try:
            return submit_ir_for_mapping(
                dossier_id=dossier_id,
                ir_artifact_ref=ir_artifact_ref,
            )
        except Exception as exc:
            return _exception_refusal(exc)

    return handler


def _make_publish_output_handler(
    *,
    dossier_id: str,
    handoff: DeedToIrStartupHandoff,
) -> Callable[[Any], Any]:
    def handler(request: Any) -> dict[str, Any]:
        inputs = _extract_inputs(request)
        try:
            return publish_deed_to_ir_output(
                dossier_id=dossier_id,
                transcription_id=handoff.scope.transcription_id,
                workspace_id=handoff.scope.workspace_id,
                run_id=handoff.scope.run_id,
                transcript_edit_source_revision_ref=handoff.source.source_revision_ref,
                resolution_state_ref=handoff.resolution_state_ref,
                mapping_artifact_ref=_optional_str(inputs.get("mapping_artifact_ref")) or "",
                scope_results=inputs.get("scope_results"),
                external_dependencies=inputs.get("external_dependencies"),
                closure_dimensions=inputs.get("closure_dimensions"),
                notes=inputs.get("notes"),
                expected_ir_artifact_ref=_optional_str(inputs.get("expected_ir_artifact_ref")),
            )
        except Exception as exc:
            return _exception_refusal(exc)

    return handler


def _make_list_fg_artifacts_handler(*, dossier_id: str) -> Callable[[Any], Any]:
    def handler(request: Any) -> dict[str, Any]:
        inputs = _extract_inputs(request)
        try:
            return list_feature_graph_artifacts(
                dossier_id=dossier_id,
                artifact_type=_optional_str(inputs.get("artifact_type")),
                limit=inputs.get("limit") or 32,
            )
        except Exception as exc:
            return _exception_refusal(exc)

    return handler


def _handoff_tool_context(handoff: DeedToIrStartupHandoff) -> dict[str, Any]:
    return {
        "scope": {
            "dossier_id": handoff.scope.dossier_id,
            "run_id": handoff.scope.run_id,
            "workspace_id": handoff.scope.workspace_id,
            "transcription_id": handoff.scope.transcription_id,
        },
        "source": {
            "loaded_source_label": handoff.source.loaded_source_label,
            "source_revision_ref": handoff.source.source_revision_ref,
            "published_at": handoff.source.published_at,
        },
        "normalized_or_mapping_transcript": handoff.normalized_or_mapping_transcript,
        "source_transcript_verbatim": handoff.source_transcript_verbatim,
        "issues": list(handoff.issues),
        "hitl_decisions": list(handoff.hitl_decisions),
        "parcel_metadata": dict(handoff.parcel_metadata),
        "evidence_refs": list(handoff.evidence_refs),
        "excerpts": dict(handoff.excerpts),
        "resolution_state_ref": handoff.resolution_state_ref,
        "resolution_state_snapshot": handoff.resolution_state_snapshot,
        "operand_suite_ref": handoff.operand_suite_ref,
        "inherited_handoff_conditions": dict(handoff.inherited_handoff_conditions),
    }


def _handoff_wire(handoff: DeedToIrStartupHandoff) -> dict[str, Any]:
    return {
        "scope": {
            "dossier_id": handoff.scope.dossier_id,
            "run_id": handoff.scope.run_id,
            "workspace_id": handoff.scope.workspace_id,
            "transcription_id": handoff.scope.transcription_id,
        },
        "source": {
            "loaded_source_label": handoff.source.loaded_source_label,
            "source_revision_ref": handoff.source.source_revision_ref,
            "published_at": handoff.source.published_at,
        },
        "normalized_or_mapping_transcript": handoff.normalized_or_mapping_transcript,
        "source_transcript_verbatim": handoff.source_transcript_verbatim,
        "issues": list(handoff.issues),
        "hitl_decisions": list(handoff.hitl_decisions),
        "parcel_metadata": dict(handoff.parcel_metadata),
        "evidence_refs": list(handoff.evidence_refs),
        "counts": dict(handoff.counts),
        "excerpts": dict(handoff.excerpts),
        "resolution_state_ref": handoff.resolution_state_ref,
        "resolution_state_counts": dict(handoff.resolution_state_counts),
        "resolution_state_summary": list(handoff.resolution_state_summary),
        "operand_suite_ref": handoff.operand_suite_ref,
        "inherited_handoff_conditions": dict(handoff.inherited_handoff_conditions),
    }


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


def _extract_inputs(request: Any) -> dict[str, Any]:
    if hasattr(request, "inputs"):
        raw = request.inputs
        return dict(raw) if isinstance(raw, Mapping) else {}
    if isinstance(request, Mapping):
        return dict(request)
    return {}


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _exception_refusal(exc: Exception) -> dict[str, Any]:
    logger.exception("deed_to_ir_tool_error")
    code = _error_code_for_exception(exc)
    return {
        "executed": False,
        "refusal": {"reason_code": code, "retryable": False},
        "outputs": {"error": {"code": code, "message": _sanitize_error_detail(str(exc))}},
    }


def _error_code_for_exception(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        message = str(exc).strip()
        if message:
            candidate = message.split(":", 1)[0].strip()
            if _SAFE_ERROR_CODE_PATTERN.fullmatch(candidate):
                return candidate
    return "deed_to_ir_tool_error"


def _sanitize_error_detail(text: str) -> str:
    cleaned = _WIN_PATH_PATTERN.sub("<path>", text)
    cleaned = _UNIX_PATH_PATTERN.sub("<path>", cleaned)
    if len(cleaned) > 400:
        return cleaned[:399].rstrip() + "…"
    return cleaned


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
    if is_dataclass(value):
        from dataclasses import asdict

        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
