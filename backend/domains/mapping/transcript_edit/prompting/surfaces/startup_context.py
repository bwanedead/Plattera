"""Startup artifact context block for transcript-edit.

Formats the deterministic startup inventory into a prompt block that tells the LLM
what artifact refs are available without exposing storage internals.
"""

from __future__ import annotations

from domains.prompting import PromptBlock

from ...payloads import DossierTranscriptEditStartupInventory
from ..branch import TRANSCRIPT_EDIT_DOMAIN_ID

TRANSCRIPT_EDIT_STARTUP_CONTEXT_VERSION = "v5"
_STARTUP_CONTEXT_SOURCE_PATH = "backend/domains/mapping/transcript_edit/prompting/surfaces/startup_context.py"


def build_startup_context_block(inventory: object) -> PromptBlock:
    """Build a prompt-visible startup context block from the pre-assembled inventory."""
    text = _format_startup_context(inventory)
    return PromptBlock(
        block_id="transcript_edit_startup_context",
        layer="domain_startup_context",
        owner=TRANSCRIPT_EDIT_DOMAIN_ID,
        source_path=_STARTUP_CONTEXT_SOURCE_PATH,
        version=TRANSCRIPT_EDIT_STARTUP_CONTEXT_VERSION,
        text=text,
    )


def _format_startup_context(inventory: object) -> str:
    """Render the startup inventory as instructional prompt text for the LLM."""
    if isinstance(inventory, DossierTranscriptEditStartupInventory):
        return _format_dossier_startup_context(inventory)
    return _format_transcription_startup_context(inventory)


def _format_transcription_startup_context(inventory: object) -> str:
    """Render the established single-transcription startup inventory."""
    lines: list[str] = [
        "## Startup Artifact Context",
        "",
        "The following artifact refs are available for this run. "
        "Use `hydrate_artifact_refs` to load full content for any ref. "
        "The LLM owns comparison, reconciliation, and semantic verification — "
        "these are not tools. `transform_artifact` creates derived image refs you can hydrate and re-use.",
        "",
    ]

    # Source images
    source_images = getattr(inventory, "source_images", ()) or ()
    if source_images:
        lines.append("### Source Image Refs")
        for img in source_images:
            role = getattr(img, "role", "")
            ref_id = getattr(img, "ref_id", "")
            basename = getattr(img, "basename", None)
            label = f"`{ref_id}`"
            if basename:
                label += f" ({basename})"
            if role:
                label += f" — {role}"
            lines.append(f"- {label}")
        lines.append("")

    # T0 drafts
    t0_drafts = getattr(inventory, "t0_drafts", ()) or ()
    if t0_drafts:
        lines.append("### Peer T0 Draft Refs")
        lines.append(
            "T0 drafts are independent redundant machine passes over the source image. "
            "Each is a peer — none is pre-ranked. Reconciliation is your responsibility."
        )
        for draft in t0_drafts:
            ref_id = getattr(draft, "ref_id", "")
            label = getattr(draft, "variant_label", "")
            byte_len = getattr(draft, "byte_length", None)
            section_count = getattr(draft, "section_count", None)
            parts = [f"`{ref_id}`"]
            if label and label != ref_id:
                parts.append(f"variant: {label}")
            if byte_len is not None:
                parts.append(f"{byte_len:,} bytes")
            if section_count is not None:
                parts.append(f"{section_count} sections")
            lines.append(f"- {' | '.join(parts)}")
        lines.append("")

    # Transcript-edit workspace refs
    te = getattr(inventory, "transcript_edit_drafts", None)
    if te is not None:
        te_lines: list[str] = []
        wr = getattr(te, "working_draft_ref", None)
        if wr:
            rev = getattr(te, "working_latest_revision", None)
            saved = getattr(te, "working_saved_at", None)
            note = f"`{wr}`"
            if rev is not None:
                note += f" (latest revision: {rev:04d})"
            if saved:
                note += f" — saved at {saved}"
            te_lines.append(f"- Working draft: {note}")
        out_ref = getattr(te, "output_draft_ref", None)
        if out_ref:
            pub = getattr(te, "output_published_at", None)
            note = f"`{out_ref}`"
            if pub:
                note += f" — published at {pub}"
            te_lines.append(f"- Published output: {note}")
        if te_lines:
            lines.append("### Transcript-Edit Workspace Refs")
            lines.extend(te_lines)
            lines.append("")

    # Missing resources (surface as advisory only)
    missing = getattr(inventory, "missing_resources", ()) or ()
    if missing:
        lines.append("### Advisory: Missing or Incomplete Resources")
        for m in missing:
            code = getattr(m, "code", "")
            message = getattr(m, "message", "")
            lines.append(f"- `{code}`: {message}")
        lines.append("")

    lines.append(
        "**What each artifact kind returns when hydrated:**\n"
        "- `t0:raw:*` → full transcript text + metadata\n"
        "- `transcript_edit:*` → saved draft payload + bounded metadata\n"
        "- `image:assoc:*:original` → raw captured source image (model-visible pixels) + bounded metadata\n"
        "- `image:derived:*` → model-visible derived image evidence (actual pixels) + bounded provenance metadata\n\n"
        "**Capabilities:** `hydrate_artifact_refs` loads any of the above refs. "
        "`transform_artifact` creates reusable `image:derived:*` refs (model-visible evidence) via crop, expand, zoom, "
        "annotate, render_evidence_locators, point_crops_scaffold, point_crops, point_crops_adjust, and point_crops_view. "
        "Derived refs can be re-hydrated with `hydrate_artifact_refs`. "
        "`save_workspace_artifact` saves a working transcript revision. "
        "`publish_workspace_artifact` promotes a working revision to output."
    )

    return "\n".join(lines)


def _format_dossier_startup_context(
    inventory: DossierTranscriptEditStartupInventory,
) -> str:
    """Render the complete ordered dossier inventory without storage internals."""
    scope = inventory.scope
    lines: list[str] = [
        "## Dossier Startup Artifact Context",
        "",
        f"Dossier: `{scope.dossier_id}`",
        f"Topology fingerprint: `{inventory.topology_fingerprint}`",
        f"Ordered segment count: {inventory.segment_count}",
        "",
        "All refs below are bound to this dossier topology. Use the qualified refs exactly as shown. "
        "Hydration, transformation, saving, and publication remain agent-directed; the inventory "
        "does not rank transcription runs or choose a final revision.",
        "",
    ]

    for segment in inventory.segments:
        neighbors: list[str] = []
        if segment.previous_segment_id is not None:
            neighbors.append(f"previous `{segment.previous_segment_id}`")
        if segment.next_segment_id is not None:
            neighbors.append(f"next `{segment.next_segment_id}`")
        neighbor_text = f" ({'; '.join(neighbors)})" if neighbors else ""
        lines.append(
            f"### Segment {segment.position}: `{segment.segment_id}`{neighbor_text}"
        )
        if not segment.runs:
            lines.append("- No transcription runs are currently bound to this segment.")
            lines.append("")
            continue
        lines.append(
            "The runs below are peers. Select and reconcile them from source evidence; "
            "their ordering is identity, not quality."
        )
        for run in segment.runs:
            run_position = (
                f", run position {run.position}" if run.position is not None else ""
            )
            lines.append(
                f"- Run `{run.transcription_id}`{run_position}"
            )
            _append_ref_group(lines, "Source images", run.source_image_refs)
            _append_ref_group(lines, "T0 drafts", run.t0_draft_refs)
            if run.working_draft_ref:
                lines.append(f"  - Working aggregate: `{run.working_draft_ref}`")
            if run.working_latest_revision_ref:
                lines.append(
                    f"  - Latest exact working revision: `{run.working_latest_revision_ref}`"
                )
            if run.output_draft_ref:
                lines.append(f"  - Existing output: `{run.output_draft_ref}`")
            for missing in run.missing_resources:
                lines.append(
                    f"  - Advisory `{missing.code}`: {missing.message}"
                )
        lines.append("")

    if inventory.topology_diagnostics:
        lines.append("### Topology Diagnostics")
        for diagnostic in inventory.topology_diagnostics:
            identity = ":".join(
                value
                for value in (
                    diagnostic.segment_id,
                    diagnostic.transcription_id,
                )
                if value
            )
            suffix = f" ({identity})" if identity else ""
            lines.append(f"- `{diagnostic.code}`{suffix}")
        lines.append("")

    lines.append(
        "**Dossier-qualified ref shape:** "
        "`dossier_segment:<segment_id>:run:<transcription_id>:<leaf_ref>`.\n"
        "- qualified `t0:raw:*` → full peer transcript text + bounded metadata\n"
        "- qualified `transcript_edit:*` → saved segment draft payload + bounded metadata\n"
        "- qualified `image:assoc:*:original` → model-visible source pixels + bounded metadata\n"
        "- qualified `image:derived:*` → model-visible derived pixels + bounded provenance metadata\n\n"
        "**Capabilities:** hydrate and transform use dossier-qualified refs. "
        "`save_workspace_artifact` writes only the segment/run lineage named by `target_ref` "
        "or `base_revision_ref`. `copy_forward_save_workspace_artifact` continues an exact "
        "qualified working revision. `publish_workspace_artifact` requires "
        "`source_revision_refs`: one chosen exact qualified working revision per topology segment."
    )
    return "\n".join(lines)


def _append_ref_group(lines: list[str], label: str, refs: tuple[str, ...]) -> None:
    if refs:
        lines.append(f"  - {label}: " + ", ".join(f"`{ref}`" for ref in refs))
