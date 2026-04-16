from __future__ import annotations

from harness.runtime.prompting.surface import build_harness_turn_surface


def test_harness_surface_teaches_work_universe_posture_and_audit_sweep() -> None:
    surface = build_harness_turn_surface()
    text = "\n".join(block.content for block in surface.blocks).lower()
    assert "work_universe_posture" in text
    assert "initial" in text
    assert "believed_adequate" in text
    assert "audited" in text
    assert "audit sweep" in text
    assert "if i had to defend every closed item one by one" in text
    assert "mechanically blocked until `mission.work_universe_posture` is `audited`" in text


def test_harness_surface_teaches_hitl_self_audit_and_async_default() -> None:
    surface = build_harness_turn_surface()
    text = "\n".join(block.content for block in surface.blocks).lower()
    assert "which remaining material unresolved issues have exhausted the strongest in-run check" in text
    assert "multiple hitls in one run are valid" in text
    assert "async hitl is the default" in text
    assert "blocking hitl is for true pause conditions only" in text
