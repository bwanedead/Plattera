"""Closure-policy action roles for artifact-progress observability.

Domains declare which actions write the working artifact and which publish it.
This module resolves those declarations into one immutable role object.
It does not decide whether a state change is ready to write.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class ArtifactActionRoleConfigError(ValueError):
    """A present closure-policy role lane is not a list or tuple of action ids."""


_DEFAULT_WORKING_WRITE_ACTION_IDS: frozenset[str] = frozenset(
    {
        "save_workspace_artifact",
        "copy_forward_save_workspace_artifact",
    }
)
_DEFAULT_PUBLISH_ACTION_IDS: frozenset[str] = frozenset(
    {
        "publish_workspace_artifact",
    }
)


@dataclass(frozen=True)
class ArtifactActionRoles:
    working_write_action_ids: frozenset[str]
    publish_action_ids: frozenset[str]

    @property
    def materialize_action_ids(self) -> frozenset[str]:
        return self.working_write_action_ids | self.publish_action_ids


def resolve_artifact_action_roles(
    closure_policy: Mapping[str, Any] | None,
) -> ArtifactActionRoles:
    """Resolve working-write and publish action ids from a closure policy.

    A missing policy or a missing role field keeps the generic default for that
    lane. A present role field must be a list or tuple of nonblank strings.
    A malformed present lane raises; it is not replaced with the default.
    """
    if closure_policy is None:
        return ArtifactActionRoles(
            working_write_action_ids=_DEFAULT_WORKING_WRITE_ACTION_IDS,
            publish_action_ids=_DEFAULT_PUBLISH_ACTION_IDS,
        )
    if not isinstance(closure_policy, Mapping):
        raise ArtifactActionRoleConfigError("closure_policy must be a mapping when provided")
    return ArtifactActionRoles(
        working_write_action_ids=_resolve_role_lane(
            closure_policy,
            "save_action_ids",
            _DEFAULT_WORKING_WRITE_ACTION_IDS,
        ),
        publish_action_ids=_resolve_role_lane(
            closure_policy,
            "publish_action_ids",
            _DEFAULT_PUBLISH_ACTION_IDS,
        ),
    )


def _resolve_role_lane(
    closure_policy: Mapping[str, Any],
    key: str,
    default: frozenset[str],
) -> frozenset[str]:
    if key not in closure_policy or closure_policy.get(key) is None:
        return default
    raw = closure_policy.get(key)
    if not isinstance(raw, (list, tuple)):
        raise ArtifactActionRoleConfigError(f"{key} must be a list or tuple when present")
    action_ids: list[str] = []
    for item in raw:
        if type(item) is not str:
            raise ArtifactActionRoleConfigError(
                f"{key} members must be nonblank strings; rejected {type(item).__name__}"
            )
        text = item.strip()
        if not text:
            raise ArtifactActionRoleConfigError(f"{key} members must be nonblank strings")
        action_ids.append(text)
    return frozenset(action_ids)
