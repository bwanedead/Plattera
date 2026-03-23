"""Generic closure-policy seam for DECLARE_DONE readiness."""

from __future__ import annotations

from typing import Protocol

from .run_artifact import RunArtifact

CLAIMABILITY_POLICY_NOT_CONFIGURED = "claimability_policy_not_configured"


class ClaimabilityPolicy(Protocol):
    """Contract for deciding whether declare_done can be accepted."""

    def evaluate(self, run_artifact: RunArtifact) -> tuple[bool, list[str]]: ...


def evaluate_claimability(
    policy: ClaimabilityPolicy | None,
    run_artifact: RunArtifact,
) -> tuple[bool, list[str]]:
    """Return claimability from the injected policy, or a neutral refusal when none is configured."""
    if policy is None:
        return False, [CLAIMABILITY_POLICY_NOT_CONFIGURED]
    return policy.evaluate(run_artifact)
