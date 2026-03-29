"""Phase 19: wrapper reduction + canonical transcript-edit / ledger rails."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def test_standalone_planner_helper_lives_on_iteration_repair_runtime() -> None:
    from backend.domains.mapping.transcript_edit import iteration_repair_runtime as irr

    assert callable(getattr(irr, "run_standalone_edit_planner_for_focus_packet", None))


def test_iteration_pipeline_does_not_import_removed_clean_flow_module() -> None:
    root = Path(__file__).resolve().parents[3]
    path = root / "backend" / "agents" / "transcript_edit" / "iteration_pipeline.py"
    text = path.read_text(encoding="utf-8")
    assert "iteration_clean_flow" not in text
    assert "iteration_repair_runtime" in text


def test_removed_bridge_modules_not_present() -> None:
    root = Path(__file__).resolve().parents[3] / "backend" / "agents" / "transcript_edit"
    assert not (root / "iteration_clean_flow.py").exists()
    assert not (root / "planner_runtime_bridge.py").exists()


def test_iteration_pipeline_uses_package_kernel_session_manager_import() -> None:
    root = Path(__file__).resolve().parents[3]
    path = root / "backend" / "agents" / "transcript_edit" / "iteration_pipeline.py"
    text = path.read_text(encoding="utf-8")
    assert "from agent_kernel import KernelSessionManager" in text


def test_ledger_snapshot_docstring_marks_wire_only() -> None:
    path = Path(__file__).resolve().parents[3] / "backend" / "agents" / "transcript_edit" / "decision_ledger_state.py"
    text = path.read_text(encoding="utf-8")
    assert "def ledger_snapshot_for_payload" in text
    assert "API/wire" in text or "wire" in text
    assert "unified" in text.lower() and "closure" in text.lower()

