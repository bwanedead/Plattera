# Engineering Brief — Transcript Loop Runway Gaps

Date: 2026-03-16
Status: Active — next implementation runway
Scope: `backend/agents/transcript_edit/`, `backend/harness/orchestration_kernel/`, `frontend/src/components/agent-viewer/`

---

## Goal

Address the remaining capability and observability gaps so transcript-edit can:

- Resolve more ambiguity without HITL by using T0 redundancy draft consensus
- Maintain explicit working-draft vs seed-source clarity across iterations
- Use image evidence more reliably without oscillation (agent-driven crop/zoom preserved)
- Surface agent-selected crop evidence to humans in the HITL feedback UI
- Emit structured, searchable "why" signals for focus, move, and progress decisions

**Non-goal:** Changing kernel phase grammar, domain-pack interface shape, or mission runtime transitions. This is "make the loop run right and diagnosable" — not more unification.

---

## Context

The kernel orchestration path (`harness/orchestration_kernel/`) and mission runtime unification are complete through Phase 7. The transcript-edit domain pack runs under the shared kernel. The following gaps are behavioral and observability deficits within the current architecture — none require structural changes.

CLI HITL injection is **already present** (`harness/mission_runtime/hitl_watch.py`, `harness/mission_runtime/hitl_inject.py`) and is not a gap.

---

## D1 — T0 Redundancy Draft Access (Consensus Evidence Lane)

### Problem

T0 produces `_v1`/`_v2`/`_v3` draft files per transcription run. The resolver focus packet is anchored to one `source_transcript_ref` and provides no "sibling drafts agree/disagree" signal. When the agent encounters a disputed PLSS value (range, township, section), it cannot cross-reference the raw redundancy drafts to determine whether 2-of-3 said "74 West." This forces HITL escalation for disputes that are mechanically resolvable from the stored data.

### Target

When a focus item is in `disputed` state for a mapping-blocking PLSS key, the focus packet includes a bounded `t0_consensus` lane:

- List of sibling draft refs found on disk
- Extracted candidate value(s) per draft for the current `decision_key` (bounded extraction, not full transcript blobs)
- Vote counts, dominant candidate, and a confidence label (`unanimous` / `majority` / `split`)

The resolver can then propose `apply_edit_plan` when consensus is strong without involving a human. Only a genuinely split or ambiguous consensus should escalate to HITL.

### Code Anchors

| What | Where |
|------|-------|
| T0 storage layout and draft naming | `docs/agent-testing/practice-deed-t0-setup.md` |
| Draft file naming convention (`_v1.json`, `_v2.json`) | `pipelines/image_to_text/pipeline.py` (`_resolve_post_t0_source_transcript_ref`, `_collect_post_t0_candidate_refs`) |
| Focus packet builder | `agents/transcript_edit/focus_packet.py` (`source_transcript_ref`, `source_transcript_hash` — no sibling lane today) |
| Candidate ref collector (already exists) | `pipelines/image_to_text/pipeline.py:_collect_post_t0_candidate_refs` |
| Decision key extraction from transcript text | `agents/transcript_edit/decision_ledger_state.py` (`_key_for_text`, `_extract_value_for_key`) |

### Acceptance

- For `practice_legaltext` range dispute, the focus packet contains a `t0_consensus` block that makes the 2/3-vote visible to the resolver.
- Resolver proposes `apply_edit_plan` (with `review_required` if warranted) without HITL when consensus is strong.
- When consensus is genuinely split the resolver correctly escalates to HITL or image verification.

---

## D2 — Explicit Working Draft vs Source + Edit Lineage in Focus Packet

### Problem

The loop tracks `current_transcript_ref` in `loop_state.py`, but the resolver focus packet does not explicitly tell the LLM:

- Which ref is the original T0 seed
- Which ref is the current working draft
- What edits have already been applied (iteration, key, plan summary, resulting ref)

This creates "forgetfulness" — the LLM may re-propose edits already applied, or propose an edit inconsistent with a prior one. The implicit `current_transcript_ref` shift (done in the refresh hook after `TX_APPLY_EDIT_PLAN`) is not visible to the resolver.

### Target

Add explicit structured fields to the focus packet:

| Field | Content |
|-------|---------|
| `seed_transcript_ref` | The original T0 ref the loop started from |
| `working_transcript_ref` | The current edited ref (same as `current_transcript_ref`) |
| `edit_lineage_summary` | Bounded list: `{iteration, decision_key, plan_id, short_summary, resulting_ref}` |
| `last_edit_summary` | Optional shorthand: what the most recent edit changed |

### Code Anchors

| What | Where |
|------|-------|
| Loop state fields | `agents/transcript_edit/loop_state.py` (`current_transcript_ref`, `latest_refs`, `apply_reaudit_baseline_*`) |
| Focus packet builder | `agents/transcript_edit/focus_packet.py` |
| Edit result output key | `agent_kernel/actions.py` (`TX_APPLY_EDIT_PLAN` → `tx_edited_transcript_ref`) |
| Where edit is applied and ref updated | `agents/transcript_edit/domain_pack.py:refresh` (reads `loop_memory.latest_refs`) |

### Acceptance

- In trace and in resolver input, it is unambiguous which draft is the working edit and what the original seed was.
- Edit lineage is visible in the focus packet so the LLM cannot redundantly re-apply the same edit.
- Seed ref is set once at loop start and never overwritten.

---

## D3 — Image Evidence Policy (Reduce Oscillation; Preserve Agent Crop/Zoom Control)

### Problem

The agent controls crop/zoom (correct — agent specifies `crop_box_normalized` + `zoom_factor` in `evidence_request`; runtime applies it). However, behavior can oscillate:

- Repeated `image_evidence` attempts on the same focus key without resolution
- Escalating to HITL without attempting a single targeted crop first
- Evidence kind vocabulary inconsistency (`image_check` is not a valid kind; valid kinds are `open_spans`, `image_verify`, `image_evidence`, `retrieve_dependency_evidence`)

### Target

Define and enforce a consistent image-evidence policy in prompting and domain-pack move compilation:

- For mapping-blocking disputed PLSS items: allow at most **N image-evidence attempts** per focus key per session (suggest N=2), then HITL.
- In `live_hitl` mode: one targeted image-evidence pass is permitted; if still disputed after that, prefer HITL.
- Evidence kind vocabulary corrected and enforced in prompting guidance.
- Attempt counter tracked per focus key (can live in domain-local state alongside `focus_stagnation_streak`).

### Code Anchors

| What | Where |
|------|-------|
| Evidence request vocabulary and guidance | `agents/transcript_edit/prompting.py:128-129` |
| Valid evidence kinds | `agents/transcript_edit/prompting.py` (inline allowed-kinds list) |
| Visual evidence already in focus packet | `agents/transcript_edit/focus_packet.py:287-320` (`crop_box`, `zoom_factor`, `tx_image_evidence_*_ref`) |
| Move compilation for evidence | `agents/transcript_edit/domain_pack.py:606-637` (compile_move evidence branch) |
| Focus stagnation tracking | `harness/orchestration_kernel/kernel.py` (`focus_stagnation_streak`) |

### Acceptance

- No run exhibits infinite "image evidence thrash" on a single `decision_key`.
- A trace from any run shows at most N image-evidence executions per focus key before HITL or resolution.
- Policy is visible in the trace (see D5 — progress path + attempt count logged).

---

## D4 — HITL UI: Render Agent-Selected Crop/Zoom Evidence

### Problem

The backend payload correctly populates focused image evidence into the HITL feedback prompt:
- `crop_box`, `zoom_factor`, `selector_type` in `focused_image_evidence`
- `tx_image_evidence_region_ref` and `tx_image_evidence_context_ref` as artifact paths

Frontend rendering of this data is **unconfirmed**. During a `practice_legaltext` HITL prompt today, it is unknown whether the user sees the cropped image region or just raw text fields.

### Target

In the Agent Viewer feedback UI, when a HITL prompt's `focused_image_evidence` is populated:

- Render the region image (from `tx_image_evidence_region_ref`) inline or as a prominent preview
- Render the context image (from `tx_image_evidence_context_ref`) as secondary reference
- Show crop metadata (zoom factor, selector type) as a readable label
- Keep the display bounded and clearly scoped to the `prompt_id` / `decision_key`

### Code Anchors

| What | Where |
|------|-------|
| Backend payload constructor | `agents/transcript_edit/hitl_feedback.py` (`crop_box`, `zoom_factor`, `tx_image_evidence_region_ref`, `tx_image_evidence_context_ref`) |
| Feedback UI component | `frontend/src/components/agent-viewer/FeedbackComposer.tsx` |
| Feedback hook | `frontend/src/components/agent-viewer/hooks/useAgentViewerFeedback.ts` |
| Stream hook (data delivery) | `frontend/src/components/agent-viewer/hooks/useAgentViewerStream.ts` |
| Utility helpers | `frontend/src/components/agent-viewer/agentViewerUtils.ts` |

### Acceptance

- During `practice_legaltext` with `live_hitl`, a HITL prompt for a range dispute shows the agent-cropped image region the LLM was examining.
- If no image evidence was collected for a given prompt, the section is absent (not shown as empty).

---

## D5 — Structured "Why" Observability (Trace-First)

### Problem

The kernel trace correctly records **what** happened per iteration. The **why** is still mostly freeform (`reason`, `iteration_summary` strings) and requires manual reconstruction from blocking signature diffs and rationale strings. This makes diagnosing hung, stalled, or suboptimal runs expensive.

### Target

Add structured fields to trace events — not replacing freeform strings, but alongside them:

**Focus selection event:**
- Top-K ranked candidates with per-item `rank_reason` (priority tag, scope status, stagnation count)
- The domain pack's `ranked_work_item_list` is already produced in Phase 3/4 but currently discarded by the kernel before trace emission

**Move decision event:**
- Explicit decision factors alongside freeform rationale:
  - `used_hitl_feedback: bool`
  - `consensus_votes: int | null` (from D1)
  - `image_evidence_attempt_count: int`
  - `safety_gate_triggered: bool`
  - `move_type_alternatives_considered: list[str]` (if LLM surfaced them)

**Progress evaluation event:**
- Numeric comparisons used: `baseline_blocking_count`, `current_blocking_count`, `signature_changed: bool`
- The progress path label (`refresh_improved`, `refresh_pending_reaudit_grace`, `no_progress`, etc.) is already emitted — add the inputs that drove it

### Code Anchors

| What | Where |
|------|-------|
| Kernel trace emission hooks | `harness/orchestration_kernel/kernel.py` (`emit_focus_selected`, `emit_move_resolved`, `emit_progress_delta`) |
| Ranked work item list (currently ephemeral) | `harness/orchestration_kernel/contracts.py` (`WorkStateProjection.ranked_work_item_list`) |
| Progress metrics struct | `harness/orchestration_kernel/contracts.py` (`ProgressMetrics`) |
| Progress evaluation paths | `harness/orchestration_kernel/progress.py` |
| Domain pack progress supply | `agents/transcript_edit/domain_pack.py:supply_progress_metrics` (Hook 7) |

### Acceptance

- A `_trace.json` from any run contains enough structured data to answer: "why was range selected over township?", "why did the progress evaluator fire grace?", "why did the loop terminate when it did?"
- No manual signature diffing or string parsing required to reconstruct a run's decision logic.

---

## Implementation Order

These are independent — no hard sequencing — but the following order minimizes wasted work:

1. **D5 first**: structured observability makes every subsequent gap easier to diagnose and verify. Cheapest to add (kernel trace hooks already exist).
2. **D2**: edit lineage in focus packet. Self-contained, backend only, directly reduces forgetfulness.
3. **D1**: T0 consensus lane. Requires candidate ref collector plumbing into focus packet builder. Highest loop quality impact.
4. **D3**: image evidence policy. Depends on D5 (need observability to verify the policy holds) and benefits from D1 (less image verification needed when consensus resolves first).
5. **D4**: frontend crop rendering. Depends on D3 being stable (need the backend evidence to be reliably populated before the UI work is meaningful).

---

## Managerial Note

Same operating approach as prior convergence work:
- Define contracts in docs before implementation where non-trivial
- One gap at a time
- Do not claim a gap closed until a concrete artifact or trace proves it
- D1/D2/D3 are backend-only; D4 is frontend; D5 spans kernel + domain pack
