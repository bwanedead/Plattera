from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from .feedback_shape import normalize_hitl_feedback

HitlState = Literal[
    "no_prompt",
    "async_prompts_pending",
    "waiting",
    "answered_unintegrated",
    "consumed",
]

_MAX_PENDING_REQUESTS = 32
_MAX_ANSWERED_RESPONSES = 32


@dataclass
class HitlTransportPosture:
    """Human-in-the-loop transport lifecycle for the bounded orchestrator loop.

    ``wait_for_human`` on the action plan is the canonical blocking flag; this object only stores
    mechanical request/response carriage. ``blocking_prompt_id`` is set when the loop is paused
    until that prompt is answered.
    """

    hitl_state: HitlState = "no_prompt"
    blocking_prompt_id: str | None = None
    pending_hitl_requests: list[dict[str, Any]] = field(default_factory=list)
    answered_hitl_responses: list[dict[str, Any]] = field(default_factory=list)
    # Back-compat: same value as ``blocking_prompt_id`` when waiting (kernel_resume.v1).
    pending_feedback_prompt_id: str | None = None
    pending_feedback_response: dict[str, Any] | None = None


def hitl_refresh_derived_state(posture: HitlTransportPosture) -> None:
    """Recompute ``hitl_state`` from mechanical fields (no semantic inference)."""
    has_p = bool(posture.pending_hitl_requests)
    has_a = bool(posture.answered_hitl_responses) or posture.pending_feedback_response is not None
    blk = str(posture.blocking_prompt_id or "").strip()
    if blk and not hitl_has_answer_for_prompt(posture, blk):
        posture.hitl_state = "waiting"
        posture.pending_feedback_prompt_id = blk
        return
    if blk and hitl_has_answer_for_prompt(posture, blk):
        posture.hitl_state = "answered_unintegrated"
        posture.pending_feedback_prompt_id = blk
        return
    if has_p and has_a:
        posture.hitl_state = "async_prompts_pending"
    elif has_a:
        posture.hitl_state = "answered_unintegrated"
    elif has_p:
        posture.hitl_state = "async_prompts_pending"
    else:
        posture.hitl_state = "no_prompt"
    if not blk:
        posture.pending_feedback_prompt_id = None


def hitl_has_answer_for_prompt(posture: HitlTransportPosture, prompt_id: str) -> bool:
    pid = str(prompt_id or "").strip()
    if not pid:
        return False
    for row in posture.answered_hitl_responses:
        if str(row.get("prompt_id") or "").strip() == pid:
            return True
    if posture.pending_feedback_response and str(posture.pending_feedback_prompt_id or "").strip() == pid:
        return True
    return False


def hitl_prompt_visible_slice(
    posture: HitlTransportPosture,
    *,
    max_pending: int = 16,
    max_answered: int = 16,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Bounded copies for LLM envelope (no mutation)."""
    pend = list(posture.pending_hitl_requests)[-max_pending:]
    ans = list(posture.answered_hitl_responses)[-max_answered:]
    return pend, ans, posture.hitl_state


def clamp_hitl_lists(posture: HitlTransportPosture) -> None:
    if len(posture.pending_hitl_requests) > _MAX_PENDING_REQUESTS:
        posture.pending_hitl_requests[:] = posture.pending_hitl_requests[-_MAX_PENDING_REQUESTS:]
    if len(posture.answered_hitl_responses) > _MAX_ANSWERED_RESPONSES:
        posture.answered_hitl_responses[:] = posture.answered_hitl_responses[-_MAX_ANSWERED_RESPONSES:]


def apply_hitl_consumed_prompt_ids(posture: HitlTransportPosture, consumed: tuple[str, ...]) -> None:
    """Mechanically drop answered rows (and legacy single-slot) for listed prompt ids."""
    if not consumed:
        return
    want = {str(x).strip() for x in consumed if str(x).strip()}
    posture.answered_hitl_responses[:] = [
        r for r in posture.answered_hitl_responses if str(r.get("prompt_id") or "").strip() not in want
    ]
    pid_fb = str(posture.pending_feedback_prompt_id or "").strip()
    if pid_fb and pid_fb in want:
        posture.pending_feedback_response = None
        posture.pending_feedback_prompt_id = None
    if posture.blocking_prompt_id and posture.blocking_prompt_id in want:
        posture.blocking_prompt_id = None
    hitl_refresh_derived_state(posture)


def hitl_poll_feedback_store(
    *,
    posture: HitlTransportPosture,
    loop_kind: str,
    run_id: str,
    on_inbound: Callable[[str, dict[str, Any]], None] | None = None,
) -> None:
    """Merge new feedback_store entries for this run (mechanical prompt_id match only).

    ``on_inbound``, when supplied, is invoked once per newly merged response with
    ``(prompt_id, feedback_dict)``.  The transport stays mechanical; the caller
    uses the callback to update the durable HITL exchange ledger or emit traces.
    """
    rid = str(run_id or "").strip()
    lk = str(loop_kind or "").strip()
    if not rid or not lk:
        return
    try:
        from services.agent_viewer import feedback_store
    except Exception:
        return

    entries = feedback_store.list_entries(loop_kind=lk, run_id=rid)
    if not entries:
        return

    pending_ids = {str(r.get("prompt_id") or "").strip() for r in posture.pending_hitl_requests}
    if posture.blocking_prompt_id:
        pending_ids.add(str(posture.blocking_prompt_id).strip())
    if posture.pending_feedback_prompt_id:
        pending_ids.add(str(posture.pending_feedback_prompt_id).strip())

    seen: set[tuple[str, str]] = set()
    for row in posture.answered_hitl_responses:
        fb = row.get("feedback") if isinstance(row.get("feedback"), dict) else {}
        pid = str(row.get("prompt_id") or "").strip()
        ts = str((fb or {}).get("submitted_at_epoch_seconds") or "")
        seen.add((pid, ts))

    for ent in entries:
        if not isinstance(ent, dict):
            continue
        pid = str(ent.get("prompt_id") or "").strip()
        if not pid or pid not in pending_ids:
            continue
        ts = str(ent.get("submitted_at_epoch_seconds") or "")
        if (pid, ts) in seen:
            continue
        # Bound inbound feedback once at admission; downstream consumers
        # (answered list, pending_feedback_response, ledger callback, trace)
        # all see the same normalized payload.  Truncation flags are surfaced
        # via the ``_bounds`` block on the normalized dict.
        normalized = normalize_hitl_feedback({**ent, "prompt_id": pid})
        posture.answered_hitl_responses.append({"prompt_id": pid, "feedback": dict(normalized)})
        seen.add((pid, ts))
        posture.pending_hitl_requests[:] = [r for r in posture.pending_hitl_requests if str(r.get("prompt_id") or "").strip() != pid]
        if posture.blocking_prompt_id == pid:
            posture.pending_feedback_response = dict(normalized)
        if str(posture.pending_feedback_prompt_id or "").strip() == pid:
            posture.pending_feedback_response = dict(normalized)
        if on_inbound is not None:
            try:
                on_inbound(pid, dict(normalized))
            except Exception:  # pragma: no cover — never let observer errors break transport
                pass
    clamp_hitl_lists(posture)
    hitl_refresh_derived_state(posture)
