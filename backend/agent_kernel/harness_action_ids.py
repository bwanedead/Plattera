"""Harness-reserved execution action ids.

Generic member names are primary. Legacy product-shaped strings remain accepted as transitional
compatibility aliases, but they are no longer the canonical harness vocabulary.
Product composition may register additional opaque string ids via ``ActionExecutorDeps.provider_actions``.
"""

from __future__ import annotations

from enum import Enum


class HarnessAction(str, Enum):
    """Built-in harness execution actions for the generic host."""

    SET_GRAPH_REQUIREMENTS = "set_graph_requirements"
    HYDRATE_ARTIFACT = "hydrate_artifact"
    OPEN_ARTIFACT = "open_artifact"
    OPEN_TEXT_SPANS = "open_text_spans"
    DRAFT_ARTIFACT = "draft_artifact"
    DECLARE_DONE = "declare_done"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    COMPILE_ARTIFACT = "compile_artifact"
    JUDGE_ARTIFACT = "judge_artifact"
    BUNDLE_ARTIFACT = "bundle_artifact"
    GEOREFERENCE_ARTIFACT = "georeference_artifact"
    VALIDATE_ARTIFACT = "validate_artifact"
    RENDER_ARTIFACT = "render_artifact"
    PROPOSE_PATCH = "propose_patch"
    SUMMARIZE_STATUS = "summarize_status"
    UPSERT_ARTIFACT_SPAN_INDEX = "upsert_artifact_span_index"

    # Transitional aliases retained for compatibility with older call sites.
    HYDRATE_DEED = HYDRATE_ARTIFACT
    DRAFT_IR = DRAFT_ARTIFACT
    COMPILE = COMPILE_ARTIFACT
    JUDGE = JUDGE_ARTIFACT
    BUNDLE = BUNDLE_ARTIFACT
    GEOREFERENCE = GEOREFERENCE_ARTIFACT
    VALIDATE = VALIDATE_ARTIFACT
    RENDER = RENDER_ARTIFACT
    UPSERT_DEED_SPAN_INDEX = UPSERT_ARTIFACT_SPAN_INDEX

# Backward-compatible alias for call sites still named ActionType (harness-only members).
ActionType = HarnessAction


LEGACY_ACTION_VALUE_ALIASES: dict[str, str] = {
    "hydrate_deed": HarnessAction.HYDRATE_ARTIFACT.value,
    "draft_ir": HarnessAction.DRAFT_ARTIFACT.value,
    "compile": HarnessAction.COMPILE_ARTIFACT.value,
    "judge": HarnessAction.JUDGE_ARTIFACT.value,
    "bundle": HarnessAction.BUNDLE_ARTIFACT.value,
    "georeference": HarnessAction.GEOREFERENCE_ARTIFACT.value,
    "validate": HarnessAction.VALIDATE_ARTIFACT.value,
    "render": HarnessAction.RENDER_ARTIFACT.value,
    "upsert_deed_span_index": HarnessAction.UPSERT_ARTIFACT_SPAN_INDEX.value,
}


def canonical_action_id(action: ActionType | str) -> str:
    """Return the canonical generic action id for built-ins and legacy compatibility strings."""

    if isinstance(action, HarnessAction):
        return action.value
    action_str = str(action)
    return LEGACY_ACTION_VALUE_ALIASES.get(action_str, action_str)

