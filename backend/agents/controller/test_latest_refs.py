from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agent_kernel.ref_coercion import latest_ref_artifact_path
from backend.agents.controller.controller_guardrails import _latest_refs_summary
from backend.api.endpoints.transcript_edit_agent import _extract_resume_source_ref


def test_controller_and_api_use_shared_latest_ref_flattening_rules() -> None:
    latest_refs = {
        "artifact_refs": {
            "ir_ref": {"artifact_path": "artifacts/ir/canonical.json"},
            "compile_ref": {"artifact_path": "artifacts/compile/canonical.json"},
        },
        "ir_ref": {"artifact_path": "artifacts/ir/legacy.json"},
        "provider_artifact_refs": {
            "judge_ref": {"artifact_path": "artifacts/judge/provider.json"},
        },
    }

    summary = _latest_refs_summary({"latest_refs": latest_refs})

    assert summary == {
        "ir_ref": "artifacts/ir/canonical.json",
        "compile_ref": "artifacts/compile/canonical.json",
        "judge_ref": "artifacts/judge/provider.json",
    }
    assert latest_ref_artifact_path(latest_refs, "ir_ref") == "artifacts/ir/canonical.json"
    assert latest_ref_artifact_path(latest_refs, "compile_ref") == "artifacts/compile/canonical.json"
    assert latest_ref_artifact_path(latest_refs, "judge_ref") == "artifacts/judge/provider.json"


def test_transcript_endpoint_resume_source_uses_shared_latest_ref_helper() -> None:
    run = {
        "snapshot": {
            "latest_refs": {
                "artifact_refs": {
                    "tx_edited_transcript_ref": {"artifact_path": "artifacts/tx/edited.json"},
                    "tx_source_transcript_ref": {"artifact_path": "artifacts/tx/source.json"},
                },
                "tx_source_transcript_ref": {"artifact_path": "artifacts/tx/legacy-source.json"},
                "provider_artifact_refs": {
                    "tx_edited_transcript_ref": {"artifact_path": "artifacts/tx/provider-edited.json"},
                },
            }
        }
    }

    assert _extract_resume_source_ref(run=run) == "artifacts/tx/edited.json"
