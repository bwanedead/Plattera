"""Frozen practice handoff fixture and live-launch contract tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import harness.cli.run_state as cli_run_state
from domains.mapping.deed_to_ir.runtime_adapter import build_deed_to_ir_runtime_adapter
from harness.runtime.runner import RuntimeArtifactTargets, RuntimeRunner

_REPO_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE_ROOT = _REPO_ROOT / "practice_deeds" / "right_of_way" / "deed_to_ir"
_MANIFEST = _FIXTURE_ROOT / "fixture_manifest.json"
_TRANSCRIPT_OUTPUT = _FIXTURE_ROOT / "transcript_edit_output.json"
_RESOLUTION_STATE = _FIXTURE_ROOT / "resolution_state.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frozen_launch_context(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "dossier_id": "9f5eecb6-cd7e-483c-b691-b76aa7132e8e",
        "transcription_id": "draft_legal_text_image",
        "run_id": "deed-to-ir-frozen-test",
        "workspace_id": "deed-to-ir-frozen-test",
        "max_iterations": 3,
        "transcript_edit_output_path": str(_TRANSCRIPT_OUTPUT),
        "resolution_state_ref": "transcript_edit:resolution_state:practice-row-live-20260619-76",
        "resolution_state_snapshot_path": str(_RESOLUTION_STATE),
    }
    base.update(overrides)
    return base


def _compact_launch_context_json(run_id: str = "deed-to-ir-live-01") -> str:
    fixture_root = "..\\practice_deeds\\right_of_way\\deed_to_ir"
    ctx = {
        "dossier_id": "9f5eecb6-cd7e-483c-b691-b76aa7132e8e",
        "transcription_id": "draft_legal_text_image",
        "run_id": run_id,
        "workspace_id": run_id,
        "max_iterations": 100,
        "transcript_edit_output_path": f"{fixture_root}\\transcript_edit_output.json",
        "resolution_state_ref": "transcript_edit:resolution_state:practice-row-live-20260619-76",
        "resolution_state_snapshot_path": f"{fixture_root}\\resolution_state.json",
    }
    return json.dumps(ctx, separators=(",", ":"))


def test_frozen_fixture_manifest_hashes_and_counts_match_files() -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    files = manifest["files"]

    assert manifest["source_upstream_run_id"] == "practice-row-live-20260619-76"
    assert manifest["dossier_id"] == "9f5eecb6-cd7e-483c-b691-b76aa7132e8e"
    assert manifest["transcription_id"] == "draft_legal_text_image"
    assert manifest["resolution_state_ref"].startswith("transcript_edit:resolution_state:")

    transcript_meta = files["transcript_edit_output.json"]
    assert _sha256(_TRANSCRIPT_OUTPUT) == transcript_meta["sha256"]
    assert _TRANSCRIPT_OUTPUT.stat().st_size == transcript_meta["byte_length"]

    resolution_meta = files["resolution_state.json"]
    assert _sha256(_RESOLUTION_STATE) == resolution_meta["sha256"]
    assert _RESOLUTION_STATE.stat().st_size == resolution_meta["byte_length"]

    resolution = json.loads(_RESOLUTION_STATE.read_text(encoding="utf-8"))
    items = resolution.get("items") if isinstance(resolution.get("items"), list) else []
    relations = resolution.get("relations") if isinstance(resolution.get("relations"), list) else []
    covered_units = sum(
        len(item.get("covered_units"))
        for item in items
        if isinstance(item, dict) and isinstance(item.get("covered_units"), list)
    )
    assert len(items) == resolution_meta["item_count"]
    assert len(relations) == resolution_meta["relation_count"]
    assert covered_units == resolution_meta["covered_unit_count"]


def test_runtime_adapter_loads_frozen_handoff_via_snapshot_path() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_frozen_launch_context())

    handoff = surface.payload["deed_to_ir_startup_handoff"]
    assert handoff["resolution_state_ref"] == "transcript_edit:resolution_state:practice-row-live-20260619-76"
    assert handoff["resolution_state_counts"]["items"] == 5
    assert handoff["resolution_state_counts"]["relations"] == 4
    assert handoff["resolution_state_counts"]["covered_units"] == 15
    assert "resolution_state_snapshot" not in handoff


def test_frozen_handoff_startup_prompt_and_wire_payload_are_path_free() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_frozen_launch_context())

    prompt_text = "\n".join(block.content for block in surface.blocks)
    wire = json.dumps(surface.payload["deed_to_ir_startup_handoff"])
    for forbidden in (
        str(_TRANSCRIPT_OUTPUT),
        str(_RESOLUTION_STATE),
        "resolution_state_snapshot_path",
        "transcript_edit_output_path",
        "practice_deeds\\right_of_way\\deed_to_ir",
        "practice_deeds/right_of_way/deed_to_ir",
    ):
        assert forbidden not in prompt_text
        assert forbidden not in wire


def test_runtime_adapter_rejects_inline_and_path_snapshot_sources() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    inline = json.loads(_RESOLUTION_STATE.read_text(encoding="utf-8"))
    with pytest.raises(Exception, match="mutually_exclusive"):
        adapter.build_turn_surface(
            _frozen_launch_context(resolution_state_snapshot=inline),
        )


def test_runtime_adapter_requires_resolution_ref_when_snapshot_path_present() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    with pytest.raises(Exception, match="resolution_state_ref_and_snapshot_must_be_paired"):
        adapter.build_turn_surface(
            _frozen_launch_context(resolution_state_ref=None),
        )


def test_compact_cli_launch_context_contains_fixture_paths_not_resolution_graph() -> None:
    ctx_json = _compact_launch_context_json()
    ctx = json.loads(ctx_json)

    assert "resolution_state_snapshot_path" in ctx
    assert "transcript_edit_output_path" in ctx
    assert "resolution_state_snapshot" not in ctx
    assert len(ctx_json) < 2048
    assert '"items"' not in ctx_json
    assert '"relations"' not in ctx_json


def test_generic_runner_emits_audit_turn_and_timeline_for_frozen_handoff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from harness.cli import run_layout

    run_id = "deed-to-ir-frozen-runner"
    cli_runs = tmp_path / "cli_runs"
    monkeypatch.setenv("HARNESS_CLI_RUN_ID", run_id)
    monkeypatch.setattr(run_layout, "cli_runs_root", lambda: cli_runs)
    monkeypatch.setattr(cli_run_state, "cli_runs_root", lambda: cli_runs)
    run_dir_path = cli_runs / "by_loop_kind" / "deed_to_ir" / run_id
    cli_run_state.write_state(
        cli_run_state.new_run_state(
            run_id=run_id,
            pid=4242,
            loop_kind="deed_to_ir",
            mode="live",
            spawn_argv=["python", "-m", "harness.runtime.runner.entrypoint"],
            status="started",
            run_dir=run_dir_path,
        )
    )

    model_calls: list[tuple[str, str]] = []

    def model_caller(prompt: str, model: str, **_kwargs: object) -> str:
        model_calls.append((prompt, model))
        return json.dumps(
            {
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "plan-complete",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "frozen handoff smoke complete",
                "state_patch": {"mission": {"work_universe_posture": "audited"}},
                "continuity_journal_entry": {"runner_stub": True},
                "operator_progress_message": None,
            }
        )

    adapter = build_deed_to_ir_runtime_adapter()
    runner = RuntimeRunner(
        adapter=adapter,
        model_caller=model_caller,
        targets=RuntimeArtifactTargets(
            done_file=tmp_path / "done.json",
            result_file=tmp_path / "result.json",
        ),
    )

    result = runner.run(launch_context=_frozen_launch_context(run_id=run_id))

    assert result.status == "completed"
    assert len(model_calls) == 1
    assert "Deed-to-IR Startup Handoff" in model_calls[0][0]
    assert str(_RESOLUTION_STATE) not in model_calls[0][0]

    audit_dir = cli_run_state.run_dir(run_id) / "audit"
    assert (audit_dir / "turn_0001.json").is_file()
    assert (audit_dir / "human" / "timeline.md").is_file()
    assert not (audit_dir / "turns").exists()

    turn = json.loads((audit_dir / "turn_0001.json").read_text(encoding="utf-8"))
    assert isinstance(turn, dict)
    assert turn.get("terminal_decision") == "complete_run" or turn.get("iteration") == 1

    timeline = (audit_dir / "human" / "timeline.md").read_text(encoding="utf-8")
    assert "Run Timeline" in timeline
    assert "complete_run" in timeline
