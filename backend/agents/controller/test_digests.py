from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import config.paths as legacy_paths
from backend.agents.controller.digests import build_fallback_iteration_digest, persist_iteration_digest


def test_digest_persistence_is_bounded_and_persists_under_agent_kernel_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            digest = build_fallback_iteration_digest(
                seed={
                    "iter": 1,
                    "phase_hint": "bootstrap",
                    "context_inputs": {
                        "deed_text_full": "x" * 10000,
                        "deed_text_artifact_ref": "artifacts/deed/d1.json",
                        "dossier_id": "D1",
                    },
                    "proposal": {"action_type": "open_artifact", "args": {}, "why": "open"},
                    "outcome": {
                        "kind": "controller_refusal",
                        "reason_code": "open_artifact_requires_artifact_or_corpus_ref",
                        "missing_inputs": ["artifact_ref | artifact_path | corpus_entry_ref"],
                    },
                    "progress": {"latest_refs": {}},
                }
            )
            ref, excerpt = persist_iteration_digest(
                request_id="req1",
                session_id="s1",
                iteration=1,
                digest=digest,
            )
            path = Path(ref)
            assert path.exists()
            assert "iteration_digests" in str(path)
            assert len(excerpt) <= 220
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert payload["iter"] == 1
            assert payload["result"] == "controller_refusal"
            assert len(json.dumps(payload, ensure_ascii=True).encode("utf-8")) <= 2600
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]
