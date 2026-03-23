"""Tests for deterministic kernel state machine transitions."""

from pathlib import Path
import sys

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from backend.agent_kernel.models import KernelState
from backend.agent_kernel.state_machine import (
    KernelEvent,
    TransitionError,
    advance_state,
    can_transition,
)


def test_compile_then_judge_reaches_ready_to_map():
    state = advance_state(KernelState.INIT, KernelEvent.SOURCE_READY)
    state = advance_state(state, KernelEvent.ANALYSIS_COMPLETED)
    state = advance_state(state, KernelEvent.REVIEW_COMPLETED)

    assert state == KernelState.PACKAGE_READY


def test_judge_then_compile_reaches_ready_to_map():
    state = advance_state(KernelState.INIT, KernelEvent.SOURCE_READY)
    state = advance_state(state, KernelEvent.REVIEW_COMPLETED)
    state = advance_state(state, KernelEvent.ANALYSIS_COMPLETED)

    assert state == KernelState.PACKAGE_READY


def test_repair_and_mapping_path_reaches_done():
    state = advance_state(KernelState.INIT, KernelEvent.SOURCE_READY)
    state = advance_state(state, KernelEvent.REPAIR_REQUESTED)
    state = advance_state(state, KernelEvent.REPAIR_COMPLETED)
    state = advance_state(state, KernelEvent.ANALYSIS_COMPLETED)
    state = advance_state(state, KernelEvent.REVIEW_COMPLETED)
    state = advance_state(state, KernelEvent.PACKAGE_COMMITTED)
    state = advance_state(state, KernelEvent.FINISH)

    assert state == KernelState.DONE


def test_invalid_transition_raises_deterministic_error():
    with pytest.raises(TransitionError) as exc:
        advance_state(KernelState.INIT, KernelEvent.PACKAGE_COMMITTED)

    assert str(exc.value) == "Invalid transition: state=init, event=package_committed"


def test_can_transition_matches_transition_table():
    assert can_transition(KernelState.ANALYZED, KernelEvent.REVIEW_COMPLETED) is True
    assert can_transition(KernelState.ANALYZED, KernelEvent.PACKAGE_COMMITTED) is False


def test_legacy_state_aliases_still_resolve_to_generic_states():
    assert KernelState.HAVE_IR is KernelState.SOURCE_READY
    assert KernelState.HAVE_COMPILE is KernelState.ANALYZED
    assert KernelState.HAVE_JUDGE is KernelState.REVIEWED
