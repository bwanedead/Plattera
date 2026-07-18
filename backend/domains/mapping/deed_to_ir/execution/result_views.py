"""Public attachment surface for deed-to-IR AgentResultView providers.

Routes action results to focused builders. Contains no detailed projection logic.
Does not admit pending deliveries or alter prompt composition.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from harness.execution.agent_result_view import (
    agent_result_view_omission_to_wire,
    agent_result_view_to_wire,
)

from .draft_result_views import (
    SCHEMA_PATCH_IR_DRAFT,
    SCHEMA_SAVE_IR_ARTIFACT,
    build_patch_ir_draft_view,
    build_save_ir_artifact_view,
)
from .finalization_result_views import (
    SCHEMA_FINALIZE_CURRENT_OUTPUT,
    build_finalize_current_output_view,
)
from .mapping_result_views import (
    SCHEMA_SUBMIT_IR_FOR_MAPPING,
    build_submit_ir_for_mapping_view,
)
from .result_view_common import build_working_head_continuity_key

_SUCCESS_ONLY_ACTIONS = frozenset(
    {
        "save_ir_artifact",
        "patch_ir_draft",
        "submit_ir_for_mapping",
    }
)
_FINALIZER_ACTION = "finalize_current_deed_to_ir_output"
_WRAPPED_ACTIONS = frozenset({*_SUCCESS_ONLY_ACTIONS, _FINALIZER_ACTION})


def attach_deed_to_ir_result_view(
    result: Mapping[str, Any],
    *,
    action_id: str,
    dossier_id: str | None,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
) -> dict[str, Any]:
    """Attach a provider view/omission without mutating nested outputs."""
    out = dict(result)
    if action_id not in _WRAPPED_ACTIONS:
        return out

    continuity_key = build_working_head_continuity_key(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
    )

    if action_id in _SUCCESS_ONLY_ACTIONS:
        if not _is_successful(out):
            return out
        outputs = out.get("outputs")
        if not isinstance(outputs, Mapping):
            return out
        if action_id == "save_ir_artifact":
            view, omission = build_save_ir_artifact_view(
                outputs, continuity_key=continuity_key
            )
        elif action_id == "patch_ir_draft":
            view, omission = build_patch_ir_draft_view(
                outputs, continuity_key=continuity_key
            )
        else:
            view, omission = build_submit_ir_for_mapping_view(
                outputs, continuity_key=continuity_key
            )
    else:
        # Finalizer: attach for success and normalized refusals.
        view, omission = build_finalize_current_output_view(
            out, continuity_key=continuity_key
        )

    if view is not None:
        out["agent_result_view"] = agent_result_view_to_wire(view)
        out.pop("agent_result_view_omitted", None)
    elif omission is not None:
        out["agent_result_view_omitted"] = agent_result_view_omission_to_wire(omission)
        out.pop("agent_result_view", None)
    return out


def wrap_handler_with_result_view(
    handler: Callable[[Any], Any],
    *,
    action_id: str,
    dossier_id: str | None,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
) -> Callable[[Any], Any]:
    def wrapped(request: Any) -> Any:
        raw = handler(request)
        if not isinstance(raw, Mapping):
            return raw
        return attach_deed_to_ir_result_view(
            raw,
            action_id=action_id,
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            run_id=run_id,
        )

    return wrapped


def _is_successful(result: Mapping[str, Any]) -> bool:
    return result.get("executed") is True and result.get("refusal") is None


__all__ = [
    "SCHEMA_FINALIZE_CURRENT_OUTPUT",
    "SCHEMA_PATCH_IR_DRAFT",
    "SCHEMA_SAVE_IR_ARTIFACT",
    "SCHEMA_SUBMIT_IR_FOR_MAPPING",
    "attach_deed_to_ir_result_view",
    "build_working_head_continuity_key",
    "wrap_handler_with_result_view",
]
