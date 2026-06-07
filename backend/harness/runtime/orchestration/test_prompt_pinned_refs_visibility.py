from __future__ import annotations

from harness.execution.session import ExecutionSessionManager
from harness.runtime.composition.contracts import ComposedTurnInput
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.contracts import OrchestratorContext
from harness.runtime.orchestration.llm_prompt_builder import build_choose_action_prompt_document


def test_choose_action_prompt_body_includes_pinned_refs_lane() -> None:
    loop_memory = LoopMemoryState()
    loop_memory.iterations = 4
    loop_memory.continuity.pinned_refs = [
        {
            "ref": "artifact://pinned-evidence",
            "pinned_at_turn": 2,
            "last_refreshed_turn": 4,
            "ttl_turns": 8,
        }
    ]
    loop_memory.continuity.pinned_refs_hydration = {
        "refs": ["artifact://pinned-evidence"],
        "status": "completed",
        "hydrated_results": [{"ref": "artifact://pinned-evidence", "kind": "text"}],
    }
    context = OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-pin",
        loop_memory=loop_memory,
        request_id_prefix="req-pin",
    )
    doc = build_choose_action_prompt_document(
        composed_input=ComposedTurnInput(blocks=()),
        opaque_launch_context={},
        context=context,
        projection=None,
        journal_verbatim_keep_n=2,
    )
    structured = doc.prompt_body["structured_state"]
    assert "pinned_refs" in structured
    active_row = structured["pinned_refs"]["active"][0]
    assert active_row["ref"] == "artifact://pinned-evidence"
    assert active_row["expires_in_turns"] == 8
    assert "pinned_refs_hydration" in structured
    assert structured["pinned_refs_hydration"]["status"] == "completed"
