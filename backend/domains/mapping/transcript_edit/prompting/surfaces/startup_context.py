"""Startup artifact context block for transcript-edit.

Formats the deterministic startup inventory into a prompt block that tells the LLM
what artifact refs are available without exposing storage internals.
"""

from __future__ import annotations

from ..branch import TRANSCRIPT_EDIT_DOMAIN_ID, PromptBlock

TRANSCRIPT_EDIT_STARTUP_CONTEXT_VERSION = "v3"
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
        "- `transcript_edit:*` → saved draft payload + path/metadata\n"
        "- `image:assoc:*:original` → raw captured source image (model-visible pixels) + metadata\n"
        "- `image:derived:*` → model-visible derived image evidence (actual pixels) + provenance/metadata\n\n"
        "**Capabilities:** `hydrate_artifact_refs` loads any of the above refs. "
        "`transform_artifact` applies crop/expand/zoom/annotate to image refs and returns a new `image:derived:*` ref "
        "that can itself be re-hydrated as model-visible evidence. "
        "`save_workspace_artifact` saves a working transcript revision. "
        "`publish_workspace_artifact` promotes a working revision to output."
    )

    return "\n".join(lines)
