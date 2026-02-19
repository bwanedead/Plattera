from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import config.paths as legacy_paths
from backend.agents.controller.bootstrap import persist_deed_text_artifact


def test_persist_deed_text_artifact_writes_full_text_and_excerpt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            text = "A" * 1500
            out = persist_deed_text_artifact(request_id="req1", deed_text=text, dossier_id="D1")
            payload = json.loads(Path(out.artifact_path).read_text(encoding="utf-8"))
            assert payload["artifact_type"] == "deed_text"
            assert payload["text"] == text
            assert len(out.excerpt) == 1000
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]

