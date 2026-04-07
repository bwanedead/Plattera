"""Shared artifact capability layer.

Defines canonical shared tool IDs and generic artifact-ref contracts.
Domain-specific implementations live in their respective tooling packages.
Harness core must not depend on this package.
"""

from __future__ import annotations

# Canonical shared tool IDs — domain handlers are registered under these names.
HYDRATE_ARTIFACT_REFS = "hydrate_artifact_refs"
TRANSFORM_ARTIFACT = "transform_artifact"
SAVE_WORKSPACE_ARTIFACT = "save_workspace_artifact"
PUBLISH_WORKSPACE_ARTIFACT = "publish_workspace_artifact"

SHARED_TOOL_IDS: tuple[str, ...] = (
    HYDRATE_ARTIFACT_REFS,
    TRANSFORM_ARTIFACT,
    SAVE_WORKSPACE_ARTIFACT,
    PUBLISH_WORKSPACE_ARTIFACT,
)
