"""Generic domain-owned closure policy contracts.

The harness may enforce these mechanically, but domains define the dimensions,
questions, and when enforcement should be active.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClosureDimensionStandard:
    dimension_id: str
    title: str
    question: str
    guidance: str | None = None


@dataclass(frozen=True)
class CompletionAnchorPolicy:
    """Declarative completion-anchor rules owned by the domain closure policy."""

    enabled: bool = False
    publish_action_ids: tuple[str, ...] = ()
    publish_lineage_ref_fields: tuple[str, ...] = ()
    published_preview_ref_field: str | None = None
    require_published_preview_ref: bool = False
    publish_ready_container: str = "final_output_summary"
    publish_ready_field: str = "ready_for_completion_candidate"
    posture_mirror_blocker_exact: tuple[str, ...] = ()
    posture_mirror_blocker_prefixes: tuple[str, ...] = ()
    preview_ready_publish_bypass: bool = False
    preview_prepare_action_ids: tuple[str, ...] = ()
    preview_ready_field: str = "publish_ready_candidate"
    publish_posture_mirror_blocker_exact: tuple[str, ...] = ()
    publish_posture_mirror_blocker_prefixes: tuple[str, ...] = ()
    expected_next: str | None = None
    suppressed_flag_reason: str = "local posture mismatch after published output"


@dataclass(frozen=True)
class DomainClosurePolicy:
    hard_enforced: bool = False
    enforce_on_publish: bool = False
    enforce_on_complete: bool = False
    save_action_ids: tuple[str, ...] = ()
    publish_action_ids: tuple[str, ...] = ()
    minimum_resolution_items_for_save: int = 0
    minimum_resolution_items_for_wait: int = 0
    minimum_resolution_items_for_publish: int = 0
    minimum_resolution_items_for_complete: int = 0
    required_dimension_ids: tuple[str, ...] = ()
    standards: tuple[ClosureDimensionStandard, ...] = ()
    # Optional output-tier ref key/value required in latest_refs before complete_run.
    required_output_ref_for_complete: str | None = None
    completion_anchor: CompletionAnchorPolicy | None = None
