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
    state = advance_state(KernelState.INIT, KernelEvent.IR_READY)
    state = advance_state(state, KernelEvent.COMPILE_COMPLETED)
    state = advance_state(state, KernelEvent.JUDGE_COMPLETED)

    assert state == KernelState.READY_TO_MAP


def test_judge_then_compile_reaches_ready_to_map():
    state = advance_state(KernelState.INIT, KernelEvent.IR_READY)
    state = advance_state(state, KernelEvent.JUDGE_COMPLETED)
    state = advance_state(state, KernelEvent.COMPILE_COMPLETED)

    assert state == KernelState.READY_TO_MAP


def test_repair_and_mapping_path_reaches_done():
    state = advance_state(KernelState.INIT, KernelEvent.IR_READY)
    state = advance_state(state, KernelEvent.REPAIR_REQUESTED)
    state = advance_state(state, KernelEvent.REPAIR_COMPLETED)
    state = advance_state(state, KernelEvent.COMPILE_COMPLETED)
    state = advance_state(state, KernelEvent.JUDGE_COMPLETED)
    state = advance_state(state, KernelEvent.MAP_COMPLETED)
    state = advance_state(state, KernelEvent.FINISH)

    assert state == KernelState.DONE


def test_invalid_transition_raises_deterministic_error():
    with pytest.raises(TransitionError) as exc:
        advance_state(KernelState.INIT, KernelEvent.MAP_COMPLETED)

    assert str(exc.value) == "Invalid transition: state=init, event=map_completed"


def test_can_transition_matches_transition_table():
    assert can_transition(KernelState.HAVE_COMPILE, KernelEvent.JUDGE_COMPLETED) is True
    assert can_transition(KernelState.HAVE_COMPILE, KernelEvent.MAP_COMPLETED) is False
