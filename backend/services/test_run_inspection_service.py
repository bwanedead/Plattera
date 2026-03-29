from __future__ import annotations

import json
import tempfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.run_inspection_service import RunInspectionMirror
from backend.services.workflows.mapping.transcription_edit.run_reporting import human_feedback_needed_payload


def test_run_inspection_mirrors_image_artifacts_and_marks_reuse() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifacts = root / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        region = artifacts / "region.jpg"
        context = artifacts / "context.jpg"
        region.write_bytes(b"region-bytes")
        context.write_bytes(b"context-bytes")

        mirror = RunInspectionMirror(run_id="tx_agent_test_1", max_runs=5, base_dir=root / "run_inspection")
        mirror.capture_event(
            event={
                "iteration": 2,
                "phase": "image_verify",
                "detail": {
                    "decision_key": "range",
                    "evidence_kind": "image_evidence",
                    "mode": "locate",
                    "tx_image_evidence_region_ref": {"artifact_path": str(region)},
                    "tx_image_evidence_context_ref": {"artifact_path": str(context)},
                },
            }
        )
        mirror.capture_event(
            event={
                "iteration": 3,
                "phase": "image_verify",
                "detail": {
                    "decision_key": "range",
                    "evidence_kind": "image_evidence",
                    "mode": "verify",
                    "tx_image_evidence_region_ref": {"artifact_path": str(region)},
                },
            }
        )
        mirror.finalize(status="needs_review", reason_code="test")

        manifest = json.loads((root / "run_inspection" / "tx_agent_test_1" / "run_manifest.json").read_text(encoding="utf-8"))
        rows = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
        assert len(rows) >= 3
        created_rows = [r for r in rows if str(r.get("created_or_reused") or "") == "created"]
        reused_rows = [r for r in rows if str(r.get("created_or_reused") or "") == "reused"]
        assert created_rows
        assert reused_rows
        for row in rows:
            mirrored = Path(str(row.get("mirrored_path") or ""))
            assert mirrored.exists()


def test_run_inspection_prunes_to_latest_five_runs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "run_inspection"
        for i in range(7):
            mirror = RunInspectionMirror(run_id=f"tx_agent_test_{i}", max_runs=5, base_dir=root)
            mirror.finalize(status="needs_review", reason_code=None)
        dirs = [p for p in root.iterdir() if p.is_dir()]
        assert len(dirs) <= 5


def test_run_inspection_reads_focused_refs_from_flattened_human_feedback_needed_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifacts = root / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        region = artifacts / "hitl_region.jpg"
        region.write_bytes(b"hitl-region")

        event = human_feedback_needed_payload(
            iteration=4,
            latest_refs={},
            feedback_prompt={
                "prompt_id": "hitl_range_4_test",
                "line1": "Confirm range token",
                "line2": "Pick value",
                "choices": ["Range 75 West", "Range 74 West"],
                "default_choice": "Range 75 West",
                "context": {
                    "decision_key": "range",
                    "focused_image_evidence": {
                        "selector_type": "normalized_box",
                        "source_image_path": "in-memory://source-image.jpg",
                        "region_lineage": {
                            "parent_region_ref": {"artifact_path": "in-memory://parent-region.jpg"},
                        },
                        "tx_image_evidence_region_ref": {"artifact_path": str(region)},
                    },
                },
            },
            evidence_attempts={"open_spans_count": 1, "image_verify_count": 1, "retrieval_count": 0},
        )
        mirror = RunInspectionMirror(run_id="tx_agent_test_hitl", max_runs=5, base_dir=root / "run_inspection")
        mirror.capture_event(event=event)
        mirror.finalize(status="waiting_feedback", reason_code=None)

        manifest = json.loads((root / "run_inspection" / "tx_agent_test_hitl" / "run_manifest.json").read_text(encoding="utf-8"))
        rows = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
        hitl_rows = [r for r in rows if str(r.get("ref_kind") or "").startswith("hitl_")]
        assert hitl_rows
        assert any(str(r.get("source_artifact_path") or "") == str(region) for r in hitl_rows)
        assert any(str(r.get("selector_type") or "") == "normalized_box" for r in hitl_rows)
        assert any(str(r.get("source_image_path") or "") == "in-memory://source-image.jpg" for r in hitl_rows)


