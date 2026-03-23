"""Phase 34: deed/FG projection lives in domain projectors; shared session stays neutral."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel import session as kernel_session_module
from backend.feature_graph.kernel_step_projections import build_feature_graph_provider_step_projectors


def test_update_latest_refs_has_no_harness_domain_action_branches() -> None:
    """Session must only dispatch ``provider_step_projectors`` — no deed/FG semantics."""
    src = Path(kernel_session_module.__file__).read_text(encoding="utf-8")
    start = src.index("def _update_latest_refs")
    end = src.index("def _latest_validate_ref", start)
    body = src[start:end]
    assert "ActionType" not in body
    assert "COMPILE" not in body
    assert "DRAFT_IR" not in body


def test_feature_graph_projector_registry_is_non_empty() -> None:
    fg = build_feature_graph_provider_step_projectors()
    assert "compile_artifact" in fg
    assert "draft_artifact" in fg
