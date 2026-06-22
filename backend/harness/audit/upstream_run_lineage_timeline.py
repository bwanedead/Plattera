"""Human timeline projection for generic upstream run lineage."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def render_upstream_runs_section(
    upstream_run_lineage: Mapping[str, Any] | None,
    *,
    cli_runs_root: Path | None,
    downstream_timeline_path: Path,
) -> list[str]:
    """Render compact upstream-run identity near the top of the human timeline."""
    if not isinstance(upstream_run_lineage, Mapping):
        return []

    upstream_runs = upstream_run_lineage.get("upstream_runs")
    if not isinstance(upstream_runs, list) or not upstream_runs:
        return []

    lines: list[str] = ["## Upstream Runs", ""]
    for row in upstream_runs:
        if not isinstance(row, Mapping):
            continue
        run_id = row.get("run_id")
        domain_id = row.get("domain_id")
        relation = row.get("relation")
        if not isinstance(run_id, str) or not isinstance(domain_id, str) or not isinstance(relation, str):
            continue

        lines.append(
            f"- `{run_id}` · domain=`{domain_id}` · relation=`{relation}`"
        )
        refs = row.get("handoff_refs")
        if isinstance(refs, list) and refs:
            rendered_refs = ", ".join(f"`{ref}`" for ref in refs if isinstance(ref, str) and ref)
            if rendered_refs:
                lines.append(f"  - handoff refs: {rendered_refs}")

        if cli_runs_root is not None and run_id.strip():
            upstream_timeline = (
                cli_runs_root / run_id.strip() / "audit" / "human" / "timeline.md"
            )
            if upstream_timeline.is_file():
                rel = os.path.relpath(upstream_timeline, downstream_timeline_path.parent)
                rel = rel.replace("\\", "/")
                lines.append(f"  - [open upstream timeline]({rel})")
        lines.append("")

    if len(lines) <= 2:
        return []
    return lines
