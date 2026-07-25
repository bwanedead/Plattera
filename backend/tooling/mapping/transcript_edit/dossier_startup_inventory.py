"""Build dossier-scoped transcript-edit startup inventory from leaf inventories.

Aggregates compact segment/run descriptors and dossier-qualified refs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass

from domains.mapping.transcript_edit.payloads.dossier_startup_inventory import (
    DossierTopologyDiagnostic,
    DossierTranscriptEditScope,
    DossierTranscriptEditStartupInventory,
    DossierTranscriptRunInventory,
    DossierTranscriptSegmentInventory,
)
from domains.mapping.transcript_edit.payloads.startup_inventory import (
    MissingResource,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)
from services.dossier.segment_topology import (
    DossierSegmentTopology,
    DossierSegmentTopologyError,
    TopologySegmentInput,
    build_dossier_segment_topology,
    load_dossier_segment_topology,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import (
    DossierArtifactRefError,
    DossierArtifactRefIndex,
    DossierArtifactRefTarget,
    build_dossier_artifact_ref_index,
    qualify_leaf_ref,
)
from tooling.mapping.transcript_edit.startup_inventory import (
    build_transcript_edit_startup_inventory,
)

_MAX_SAFE_MESSAGE_CHARS = 240


class DossierStartupInventoryError(Exception):
    """Mechanical refusal while building a dossier startup inventory."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail or "")
        message = self.code if not self.detail else f"{self.code}: {self.detail}"
        super().__init__(message)


@dataclass(frozen=True)
class DossierStartupInventoryBundle:
    """Inventory plus the mechanical ref index required for hydration."""

    inventory: DossierTranscriptEditStartupInventory
    ref_index: DossierArtifactRefIndex


def build_dossier_transcript_edit_startup_inventory(
    *,
    dossier_id: str,
    run_id: str | None = None,
    workspace_id: str | None = None,
    topology: DossierSegmentTopology | None = None,
    leaf_inventory_builder: Callable[..., TranscriptEditStartupInventory] | None = None,
) -> DossierStartupInventoryBundle:
    """Aggregate leaf inventories into a compact dossier-scoped startup inventory."""
    did = str(dossier_id or "").strip()
    if not did:
        raise DossierStartupInventoryError("dossier_id_required")

    topo = topology
    if topo is None:
        try:
            topo = load_dossier_segment_topology(did)
        except DossierSegmentTopologyError as exc:
            raise DossierStartupInventoryError(exc.code, exc.detail) from exc
    elif not isinstance(topo, DossierSegmentTopology):
        raise DossierStartupInventoryError("invalid_topology", repr(topo))
    elif topo.dossier_id != did:
        raise DossierStartupInventoryError(
            "topology_dossier_mismatch",
            f"requested={did} topology={topo.dossier_id}",
        )

    leaf_builder = leaf_inventory_builder or build_transcript_edit_startup_inventory
    segment_inventories: list[DossierTranscriptSegmentInventory] = []
    index_entries: list[tuple[str, DossierArtifactRefTarget]] = []
    seen_qualified: set[str] = set()

    ordered_segments = list(topo.segments)
    run_bindings: list[tuple[str, str]] = []
    for segment in ordered_segments:
        for run in segment.runs:
            run_bindings.append((segment.segment_id, run.transcription_id))

    for idx, segment in enumerate(ordered_segments):
        previous_segment_id = ordered_segments[idx - 1].segment_id if idx > 0 else None
        next_segment_id = (
            ordered_segments[idx + 1].segment_id
            if idx + 1 < len(ordered_segments)
            else None
        )
        run_inventories: list[DossierTranscriptRunInventory] = []
        for run in segment.runs:
            try:
                leaf = leaf_builder(
                    dossier_id=did,
                    transcription_id=run.transcription_id,
                    segment_id=segment.segment_id,
                    run_id=run_id,
                    workspace_id=workspace_id,
                )
            except Exception:  # noqa: BLE001 — localize leaf failure; never leak exc text
                leaf = TranscriptEditStartupInventory(
                    scope=TranscriptEditScope(
                        dossier_id=did,
                        transcription_id=run.transcription_id,
                        segment_id=segment.segment_id,
                        run_id=run_id,
                        workspace_id=workspace_id,
                    ),
                    missing_resources=(
                        MissingResource(
                            code="leaf_inventory_build_failed",
                            message="Per-transcription startup inventory builder failed.",
                        ),
                    ),
                )

            run_inv, run_entries = _compact_run_inventory(
                segment_id=segment.segment_id,
                transcription_id=run.transcription_id,
                position=run.position,
                leaf=leaf,
            )
            for qualified, target in run_entries:
                if qualified in seen_qualified:
                    raise DossierStartupInventoryError(
                        "duplicate_qualified_ref",
                        qualified,
                    )
                seen_qualified.add(qualified)
                index_entries.append((qualified, target))
            run_inventories.append(run_inv)

        segment_inventories.append(
            DossierTranscriptSegmentInventory(
                segment_id=segment.segment_id,
                position=segment.position,
                previous_segment_id=previous_segment_id,
                next_segment_id=next_segment_id,
                runs=tuple(run_inventories),
            )
        )

    try:
        ref_index = build_dossier_artifact_ref_index(
            dossier_id=did,
            topology_fingerprint=topo.topology_fingerprint,
            entries=index_entries,
            run_bindings=run_bindings,
        )
    except DossierArtifactRefError as exc:
        raise DossierStartupInventoryError(exc.code, exc.detail) from exc

    inventory = DossierTranscriptEditStartupInventory(
        scope=DossierTranscriptEditScope(
            dossier_id=did,
            run_id=run_id,
            workspace_id=workspace_id,
        ),
        topology_fingerprint=topo.topology_fingerprint,
        segment_count=len(segment_inventories),
        segments=tuple(segment_inventories),
        topology_diagnostics=tuple(
            DossierTopologyDiagnostic(
                code=d.code,
                segment_id=d.segment_id,
                transcription_id=d.transcription_id,
                detail=d.detail,
            )
            for d in topo.diagnostics
        ),
    )
    _assert_agent_facing_refs_are_hydratable(inventory, ref_index)
    return DossierStartupInventoryBundle(inventory=inventory, ref_index=ref_index)


def build_dossier_transcript_edit_startup_inventory_from_segments(
    *,
    dossier_id: str,
    segments: Sequence[TopologySegmentInput],
    association_positions: Mapping[str, int] | None = None,
    run_id: str | None = None,
    workspace_id: str | None = None,
    leaf_inventory_builder: Callable[..., TranscriptEditStartupInventory] | None = None,
) -> DossierStartupInventoryBundle:
    """Test/helper entry that builds topology from explicit segment inputs."""
    topology = build_dossier_segment_topology(
        dossier_id=dossier_id,
        segments=segments,
        association_positions=association_positions,
    )
    return build_dossier_transcript_edit_startup_inventory(
        dossier_id=dossier_id,
        run_id=run_id,
        workspace_id=workspace_id,
        topology=topology,
        leaf_inventory_builder=leaf_inventory_builder,
    )


def _compact_run_inventory(
    *,
    segment_id: str,
    transcription_id: str,
    position: int | None,
    leaf: TranscriptEditStartupInventory,
) -> tuple[DossierTranscriptRunInventory, list[tuple[str, DossierArtifactRefTarget]]]:
    entries: list[tuple[str, DossierArtifactRefTarget]] = []

    def _qualify(leaf_ref: str | None) -> str | None:
        if not leaf_ref:
            return None
        qualified = qualify_leaf_ref(
            segment_id=segment_id,
            transcription_id=transcription_id,
            leaf_ref=leaf_ref,
        )
        entries.append(
            (
                qualified,
                DossierArtifactRefTarget(
                    segment_id=segment_id,
                    transcription_id=transcription_id,
                    leaf_ref=leaf_ref,
                ),
            )
        )
        return qualified

    source_image_refs = tuple(
        qualified
        for img in leaf.source_images
        if img.ref_id
        for qualified in [_qualify(img.ref_id)]
        if qualified
    )
    t0_draft_refs = tuple(
        qualified
        for draft in leaf.t0_drafts
        if draft.ref_id
        for qualified in [_qualify(draft.ref_id)]
        if qualified
    )
    working = _qualify(leaf.transcript_edit_drafts.working_draft_ref)
    output = _qualify(leaf.transcript_edit_drafts.output_draft_ref)

    missing = [
        _project_safe_missing_resource(item) for item in leaf.missing_resources
    ]
    working_latest_revision_ref: str | None = None
    latest_rev = leaf.transcript_edit_drafts.working_latest_revision
    working_exists = bool(leaf.transcript_edit_drafts.working_draft_exists)
    if working_exists:
        if type(latest_rev) is int and latest_rev > 0:
            leaf_rev_ref = f"transcript_edit:working:rev:{latest_rev:04d}"
            working_latest_revision_ref = _qualify(leaf_rev_ref)
        else:
            missing.append(
                MissingResource(
                    code="working_latest_revision_unavailable",
                    message="Working draft exists but latest revision is missing or incoherent.",
                )
            )

    return (
        DossierTranscriptRunInventory(
            transcription_id=transcription_id,
            position=position,
            source_image_refs=source_image_refs,
            t0_draft_refs=t0_draft_refs,
            working_draft_ref=working,
            working_latest_revision_ref=working_latest_revision_ref,
            output_draft_ref=output,
            artifact_fingerprint=leaf.artifact_fingerprint,
            missing_resources=tuple(missing),
        ),
        entries,
    )


def _project_safe_missing_resource(item: MissingResource) -> MissingResource:
    """Keep mechanical code + bounded message; omit path-bearing leaf detail."""
    code = str(getattr(item, "code", "") or "").strip() or "missing_resource"
    message = str(getattr(item, "message", "") or "").strip()
    if not message:
        message = "Resource unavailable."
    if len(message) > _MAX_SAFE_MESSAGE_CHARS:
        message = message[:_MAX_SAFE_MESSAGE_CHARS]
    return MissingResource(code=code, message=message)


def _assert_agent_facing_refs_are_hydratable(
    inventory: DossierTranscriptEditStartupInventory,
    ref_index: DossierArtifactRefIndex,
) -> None:
    """Every agent-facing ``*_ref`` / ``*_refs`` value must resolve through the index."""
    for value in _iter_agent_facing_ref_values(inventory):
        if value not in ref_index.by_ref:
            raise DossierStartupInventoryError("non_hydratable_ref_exposed", value)


def _iter_agent_facing_ref_values(obj: object) -> list[str]:
    out: list[str] = []
    if is_dataclass(obj) and not isinstance(obj, type):
        for field in fields(obj):
            name = field.name
            value = getattr(obj, name)
            if name.endswith("_ref") and isinstance(value, str) and value:
                out.append(value)
            elif name.endswith("_refs") and isinstance(value, tuple):
                out.extend(item for item in value if isinstance(item, str) and item)
            else:
                out.extend(_iter_agent_facing_ref_values(value))
    elif isinstance(obj, tuple):
        for item in obj:
            out.extend(_iter_agent_facing_ref_values(item))
    return out
