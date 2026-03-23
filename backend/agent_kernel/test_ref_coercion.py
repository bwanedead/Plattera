from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.ref_coercion import flatten_latest_refs_payload, latest_ref_artifact_path


def test_flatten_latest_refs_payload_prefers_canonical_artifact_refs() -> None:
    latest_refs = {
        "artifact_refs": {
            "ir_ref": {"artifact_path": "artifacts/ir/canonical.json"},
            "compile_ref": {"artifact_path": "artifacts/compile/canonical.json"},
        },
        "ir_ref": {"artifact_path": "artifacts/ir/legacy.json"},
        "provider_artifact_refs": {
            "compile_ref": {"artifact_path": "artifacts/compile/provider.json"},
            "judge_ref": {"artifact_path": "artifacts/judge/provider.json"},
        },
    }

    flat = flatten_latest_refs_payload(latest_refs)

    assert flat["ir_ref"]["artifact_path"] == "artifacts/ir/canonical.json"
    assert flat["compile_ref"]["artifact_path"] == "artifacts/compile/canonical.json"
    assert flat["judge_ref"]["artifact_path"] == "artifacts/judge/provider.json"
    assert latest_ref_artifact_path(latest_refs, "ir_ref") == "artifacts/ir/canonical.json"
    assert latest_ref_artifact_path(latest_refs, "compile_ref") == "artifacts/compile/canonical.json"
    assert latest_ref_artifact_path(latest_refs, "judge_ref") == "artifacts/judge/provider.json"

