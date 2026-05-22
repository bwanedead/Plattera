"""Profile registry for generic delegated subtasks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from .contracts import (
    DEFAULT_MAX_CONTEXT_REFS,
    DEFAULT_MAX_RESULT_CHARS,
    DEFAULT_MAX_TASK_CHARS,
    SubtaskBatchingMetadata,
    SubtaskModelPolicy,
    SubtaskProfile,
)
from .errors import SubtaskRegistryError


class SubtaskProfileRegistry:
    """In-memory registry for profile metadata.

    The registry is intentionally small and explicit.  Domain packs can register
    opaque profile ids later without changing the shared action contract.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, SubtaskProfile] = {}

    def register(self, profile: SubtaskProfile) -> None:
        profile_id = str(profile.profile_id or "").strip()
        if not profile_id:
            raise ValueError("subtask profile_id is required")
        if int(profile.max_turns) != 1:
            raise ValueError("delegate_subtask v1 profiles must have max_turns=1")
        self._profiles[profile_id] = replace(profile, profile_id=profile_id)

    def get(self, profile_id: str) -> SubtaskProfile | None:
        normalized = str(profile_id or "").strip()
        if not normalized:
            return None
        return self._profiles.get(normalized)

    def require(self, profile_id: str) -> SubtaskProfile:
        profile = self.get(profile_id)
        if profile is None:
            raise SubtaskRegistryError(str(profile_id or "").strip())
        return profile

    def list_profile_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._profiles))

    def clone(self) -> SubtaskProfileRegistry:
        registry = SubtaskProfileRegistry()
        for profile_id in self.list_profile_ids():
            registry.register(self.require(profile_id))
        return registry


_OBSERVATION_SCHEMA = {
    "status": ["completed", "ambiguous", "insufficient_input", "failed"],
    "result": {
        "reading": "string|null",
        "ambiguity": "string",
        "observations": ["string"],
        "limits": ["string"],
    },
}


def build_default_subtask_registry() -> SubtaskProfileRegistry:
    registry = SubtaskProfileRegistry()
    registry.register(
        SubtaskProfile(
            profile_id="harness.observation",
            owner="harness",
            description="Generic observation profile for isolated harness subtasks.",
            allowed_ref_kinds=("artifact", "image", "text"),
            prompt_preamble=(
                "You are a narrow observation subagent. Answer only the supplied local task. "
                "Use only supplied refs and media. Report ambiguity and limits directly."
            ),
            result_schema=_OBSERVATION_SCHEMA,
            model_policy=SubtaskModelPolicy(),
            max_context_refs=DEFAULT_MAX_CONTEXT_REFS,
            max_task_chars=DEFAULT_MAX_TASK_CHARS,
            max_result_chars=DEFAULT_MAX_RESULT_CHARS,
            max_turns=1,
            batching=SubtaskBatchingMetadata(supported=False, max_batch_size=1),
        )
    )
    return registry


DEFAULT_SUBTASK_REGISTRY = build_default_subtask_registry()


def build_composed_subtask_registry(
    *,
    surface_payloads: Mapping[str, Mapping[str, Any]] | None = None,
    opaque_run_context: Mapping[str, Any] | None = None,
    base_registry: SubtaskProfileRegistry = DEFAULT_SUBTASK_REGISTRY,
) -> SubtaskProfileRegistry:
    """Build the runtime registry from harness defaults plus domain/profile specs.

    Domain packs can contribute profile specs through a surface payload or launch
    context under ``subtask_profiles``.  This keeps profile ownership explicit
    without requiring mutation of the default singleton.
    """

    registry = base_registry.clone()
    for spec in _iter_profile_specs(surface_payloads=surface_payloads, opaque_run_context=opaque_run_context):
        registry.register(profile_from_mapping(spec))
    return registry


def profile_from_mapping(raw: Mapping[str, Any]) -> SubtaskProfile:
    profile_id = str(raw.get("profile_id") or raw.get("id") or "").strip()
    owner = str(raw.get("owner") or "").strip() or "external"
    description = str(raw.get("description") or "").strip()
    allowed = raw.get("allowed_ref_kinds")
    if not isinstance(allowed, (list, tuple)):
        allowed = ()
    prompt_preamble = str(raw.get("prompt_preamble") or "").strip()
    if not prompt_preamble:
        prompt_preamble = "You are a narrow observation subagent. Use only supplied inputs."
    result_schema = raw.get("result_schema")
    model_policy_raw = raw.get("model_policy")
    model_name = None
    phase = "delegate_subtask"
    if isinstance(model_policy_raw, Mapping):
        if isinstance(model_policy_raw.get("model_name"), str):
            model_name = model_policy_raw["model_name"].strip() or None
        if isinstance(model_policy_raw.get("phase"), str) and model_policy_raw["phase"].strip():
            phase = model_policy_raw["phase"].strip()
    batching_raw = raw.get("batching")
    batching_supported = False
    batching_max = 1
    if isinstance(batching_raw, Mapping):
        batching_supported = bool(batching_raw.get("supported"))
        try:
            batching_max = max(1, int(batching_raw.get("max_batch_size", 1)))
        except (TypeError, ValueError):
            batching_max = 1
    return SubtaskProfile(
        profile_id=profile_id,
        owner=owner,
        description=description,
        allowed_ref_kinds=tuple(str(kind).strip() for kind in allowed if str(kind).strip()),
        prompt_preamble=prompt_preamble,
        result_schema=dict(result_schema) if isinstance(result_schema, Mapping) else _OBSERVATION_SCHEMA,
        model_policy=SubtaskModelPolicy(model_name=model_name, phase=phase),
        max_context_refs=_positive_int(raw.get("max_context_refs"), DEFAULT_MAX_CONTEXT_REFS),
        max_task_chars=_positive_int(raw.get("max_task_chars"), DEFAULT_MAX_TASK_CHARS),
        max_result_chars=_positive_int(raw.get("max_result_chars"), DEFAULT_MAX_RESULT_CHARS),
        max_turns=_positive_int(raw.get("max_turns"), 1),
        batching=SubtaskBatchingMetadata(supported=batching_supported, max_batch_size=batching_max),
    )


def _iter_profile_specs(
    *,
    surface_payloads: Mapping[str, Mapping[str, Any]] | None,
    opaque_run_context: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any], ...]:
    specs: list[Mapping[str, Any]] = []
    if isinstance(opaque_run_context, Mapping):
        raw = opaque_run_context.get("subtask_profiles")
        if isinstance(raw, (list, tuple)):
            specs.extend(item for item in raw if isinstance(item, Mapping))
    if isinstance(surface_payloads, Mapping):
        for payload in surface_payloads.values():
            if not isinstance(payload, Mapping):
                continue
            raw = payload.get("subtask_profiles")
            if isinstance(raw, (list, tuple)):
                specs.extend(item for item in raw if isinstance(item, Mapping))
    return tuple(specs)


def _positive_int(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return int(default)
