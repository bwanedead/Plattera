"""Phase 35: shared session stays generic; product composition lives outside agent_kernel."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel import session as kernel_session_module
from backend.agent_kernel.harness_action_ids import ActionType
from backend.feature_graph.kernel_executor_composition import (
    build_plattera_default_action_executor,
    build_plattera_default_kernel_session_manager,
)


def test_session_py_has_no_feature_graph_default_imports_or_pointer_persistence() -> None:
    text = Path(kernel_session_module.__file__).read_text(encoding="utf-8")
    assert "build_plattera_default_action_executor" not in text
    assert "FeatureGraphPersistenceService" not in text
    assert "mark_final_pointers_from_paths" not in text


def test_plain_kernel_session_manager_uses_generic_executor_by_default() -> None:
    manager = kernel_session_module.KernelSessionManager()
    assert manager._action_executor.available_actions() == ("set_graph_requirements",)


def test_plattera_composition_injects_product_executor_outside_agent_kernel() -> None:
    manager = build_plattera_default_kernel_session_manager()
    assert ActionType.COMPILE_ARTIFACT.value in manager._action_executor.available_actions()
    assert manager._action_executor.deps.terminal_success_hooks


def test_product_default_action_executor_registers_terminal_hooks() -> None:
    executor = build_plattera_default_action_executor()
    assert executor.deps.terminal_success_hooks
