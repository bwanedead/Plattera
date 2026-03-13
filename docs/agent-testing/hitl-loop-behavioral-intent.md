# HITL Loop — Behavioral Intent

**Purpose of this doc:** Preserve the intended behavior of the transcript-edit loop's HITL
(human-in-the-loop) mechanism so that any agent debugging or modifying this system can
re-anchor to the design intent without needing to reconstruct it from conversation.

---

## The Core Idea

The loop should never feel like it is waiting on a human. From the outside, it should appear
to be a continuous, self-directed process that surfaces decisions it cannot make alone, keeps
working on everything else, and seamlessly absorbs feedback whenever it arrives — then
continues without interruption.

The human (or testing agent) is not a gatekeeper that the loop must stop and wait for. They
are an asynchronous contributor whose input gets woven in at the next available moment.

---

## Intended Behavior, Step by Step

1. **The loop runs.** It audits, identifies issues, and repairs what it can.

2. **When it hits a blocker requiring human judgment**, it:
   - Records the blocker internally (blocker_registry)
   - Surfaces it to the outside world (HITL event via `progress_cb`, written to a pending file)
   - Keeps working on everything else it can — other findings, other repairs, other tickets
   - Does NOT stop or pause

3. **If feedback arrives while the loop is still iterating:**
   - At the start of the next iteration, the loop checks for feedback (`drain_pending_feedback`)
   - It finds the injected response, integrates it, and applies the repair
   - The loop continues as if there was no interruption

4. **If the loop exhausts its work before feedback arrives:**
   - It has genuinely run out of things it can do right now
   - It enters a "pending" state — it is not done, it is waiting
   - Externally, the process appears to be sitting idle
   - As soon as feedback is injected, the loop resumes where it left off and continues

5. **After feedback is consumed and acted upon:**
   - The loop continues its normal cycle
   - If more blockers are encountered, the same pattern repeats
   - The loop only truly completes when there is nothing left to do

---

## What "Pending" Means

Pending is not done. Pending is not failed. Pending means:
> "I have done everything I can do without this one piece of information.
> Give it to me and I will keep going."

The loop should never be in a state where it has consumed feedback and then has nothing to do.
If feedback is provided and acted on, there should always be follow-on work (verifying the
repair, checking for downstream effects, attempting promotion, etc.).

---

## What Should NOT Happen

- The loop should NOT terminate permanently just because feedback has not arrived yet.
- The loop should NOT require a full restart after feedback is injected. It resumes.
- The loop should NOT re-do work it already completed before the feedback arrived.
- The tester/user should NOT need to know whether feedback arrived mid-run or post-exhaustion.
  The observable outcome should be the same either way.

---

## Mechanical Implementation (for debugging reference)

The intent above is realized through two distinct paths depending on timing:

**Fast path (feedback arrives mid-run):**
- Controller loop polls `drain_pending_feedback` at the start of each iteration
- Feedback injected into the feedback store is consumed and applied inline
- Runner is never involved in the feedback cycle

**Slow path (loop exhausts before feedback arrives):**
- Controller returns `waiting_feedback` status to the runner
- Runner enters a block-poll on the feedback store (2-second interval, 10-minute timeout)
- When feedback lands, runner calls the controller again with resume parameters:
  `resume_pending_feedback_prompt_id`, `resume_pending_feedback_decision_key`,
  `resume_blocker_registry`
- Controller starts a new iteration cycle with the blocker state and feedback pre-loaded
- From the outside, this is indistinguishable from the fast path

**If the mechanical behavior ever diverges from the intent above**, the intent above is
authoritative. Fix the implementation to match, not the other way around.

---

## Links

- CLI testing guide: `docs/agent-testing/transcript-edit-loop-cli-testing.md`
- Runner implementation: `backend/harness/mission_runtime/cli_support.py`
- Feedback polling (mid-run): `backend/agents/transcript_edit/iteration_repair_runtime.py` (~line 627)
- Feedback store: `backend/services/agent_viewer/feedback_store.py`
- Blocker lifecycle: `backend/agents/transcript_edit/blocker_registry_lifecycle.py`
