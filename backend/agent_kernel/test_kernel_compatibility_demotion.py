"""Phase 42: shared kernel delegates legacy workflow grammar out of agent_kernel."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel import kernel as kernel_module
from backend.feature_graph import kernel_compatibility as fg_kernel_compatibility


def test_kernel_py_is_compatibility_shell_only() -> None:
    body = Path(kernel_module.__file__).read_text(encoding="utf-8")
    assert "KernelEvent.ANALYSIS_COMPLETED" not in body
    assert "ActionType.COMPILE_ARTIFACT" not in body
    assert "ActionType.JUDGE_ARTIFACT" not in body
    assert "ActionType.BUNDLE_ARTIFACT" not in body
    assert "ActionType.GEOREFERENCE_ARTIFACT" not in body
    assert "ActionType.VALIDATE_ARTIFACT" not in body


def test_feature_graph_compatibility_loop_keeps_legacy_progression_doctrine() -> None:
    body = Path(fg_kernel_compatibility.__file__).read_text(encoding="utf-8")
    assert "KernelEvent.ANALYSIS_COMPLETED" in body
    assert "ActionType.COMPILE_ARTIFACT" in body
    assert "ActionType.JUDGE_ARTIFACT" in body
    assert "ActionType.BUNDLE_ARTIFACT" in body
    assert "ActionType.GEOREFERENCE_ARTIFACT" in body
    assert "ActionType.VALIDATE_ARTIFACT" in body
