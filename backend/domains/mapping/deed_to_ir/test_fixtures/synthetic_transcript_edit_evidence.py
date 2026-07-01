"""Shared test helpers for synthetic transcript-edit derived image fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tooling.mapping.transcript_edit import paths as transcript_edit_paths

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


def install_synthetic_transcript_edit_derived_image(
    *,
    monkeypatch: Any,
    tmp_path: Path,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    ref_id: str,
    absolute_path_override: str | Path | None = None,
) -> Path:
    """Monkeypatch transcript-edit derived-image root to tmp_path; write descriptor + PNG."""
    uuid = ref_id.split(":", 2)[2]
    derived_dir = (
        tmp_path
        / "transcript_edit"
        / dossier_id
        / transcription_id
        / workspace_id
        / "derived_images"
    )
    derived_dir.mkdir(parents=True, exist_ok=True)
    png_path = derived_dir / f"{uuid}.png"
    png_path.write_bytes(_TINY_PNG)

    descriptor_absolute_path = (
        Path(absolute_path_override) if absolute_path_override is not None else png_path
    )
    (derived_dir / f"{uuid}.json").write_text(
        json.dumps(
            {
                "ref_id": ref_id,
                "parent_ref_id": f"image:assoc:{transcription_id}:original",
                "absolute_path": str(descriptor_absolute_path),
                "basename": f"{uuid}.png",
                "size_bytes": png_path.stat().st_size,
                "width_height": [1, 1],
            }
        ),
        encoding="utf-8",
    )

    def _derived_dir(d_id: str, t_id: str, w_id: str) -> Path:
        return (
            tmp_path
            / "transcript_edit"
            / d_id
            / t_id
            / w_id
            / "derived_images"
        )

    monkeypatch.setattr(transcript_edit_paths, "transcript_edit_derived_images_dir", _derived_dir)
    return derived_dir
