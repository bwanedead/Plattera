# Phase 6 Experiment Report — delegate_subtask Visual Source Observation

Status: **mechanical prep only** (mechanical checks passed; live experiments require explicit human approval)

**Coding agents:** do not start, resume, watch, stop, or message live harness runs from this document unless the human explicitly asks for that specific action.

Related plan: [`delegate-subtask-implementation-plan.md`](./delegate-subtask-implementation-plan.md)

---

## Mechanical Checks (pre-live)

| Check | Result |
|-------|--------|
| Transcript-edit surface payload includes `subtask_profiles` | Pass |
| Composed registry contains `transcript_edit.visual_source_observation` | Pass |
| Schema-driven normalize + project preserves custom result fields | Pass |
| Timeline renderer supports `delegate_subtask` custom fields | Pass (harness tests) |
| Known localized crop file exists on disk | Pass — `backend/dossiers_data/images/original/draft_legal_text_image_original_derived_b2202a5a.png` |

Suggested pytest slice:

```powershell
. .venv\scripts\activate.ps1
pytest backend/domains/mapping/transcript_edit/test_delegate_subtask_phase6_mechanical.py backend/domains/mapping/transcript_edit/test_transcript_edit_pack.py -q -k "visual_source or subtask"
pytest backend/harness/runtime/orchestration/subtasks backend/harness/audit/test_delegate_subtask_timeline.py -q
```

---

## Baseline Run (no delegation) — `practice-row-live-20260521-40`

This run predates organic use of `delegate_subtask` but already exhibits the target failure mode.

### Run facts

- **Run id:** `practice-row-live-20260521-40`
- **Status at report time:** `paused` / resumable (`model_connection_interrupted` at iteration 15)
- **LLM turns completed:** 15
- **Localized parcel 1 tie-bearing crop ref:** `image:derived:5d79cd203e114c529042676fb06c217f`
- **Crop file:** `backend/dossiers_data/images/original/draft_legal_text_image_original_derived_b2202a5a.png`

### Parent-loop behavior (pre-experiment)

| Question | Baseline observation |
|----------|---------------------|
| Did parent choose `delegate_subtask`? | **No** — zero `delegate_subtask` actions in audit/timeline |
| Turn crop created | Turn 11 (`crop_p1_bearing: transform_artifact`) |
| Turn parent closed bearing | Turn 12 (`no_dispatch` + `state_patch`) after host hydration surfaced the crop |
| Parent determined value | **`N. 2° 00' W.`** on item `parcel-1-nw-corner-bearing` |
| Candidate pair in graph | `N. 2° 00' W.` vs `N. 4° 00' W.` |
| Parent verification_basis prose | "Focused crop visibly reads `N. 2° 00' W., 1638 feet distant` and resolves the 2° vs 4° peer disagreement from the source image." |
| Evidence ref used | `image:derived:5d79cd203e114c529042676fb06c217f` |

Interpretation: the parent had a good localized crop and still earned the disputed numeral from broad-turn context/candidate pressure rather than isolated child observation.

---

## Live Experiment Protocol

**Human-approval gate:** coding agents must not start, resume, watch, stop, or message live harness runs from this document unless the human explicitly asks for that specific run action. This report records the intended experiment shape; it is not standing authorization to operate `harness.cli.*`.

### Test A — Blind source observation (primary)

If the human approves a live test, the operator/tester can inject a correction or experiment request asking the parent agent to delegate a blind visual source observation over the localized crop. The message should ask the child to read only the source-visible bearing text without peer drafts or candidate values, then integrate the returned observation through normal graph/draft/evidence channels using the parent agent's own decision.

Expected parent action shape (Test A):

```json
{
  "profile": "transcript_edit.visual_source_observation",
  "task": "Read the bearing text visible in the supplied localized crop. Preserve the source-visible text as written. Do not infer from peer drafts or surrounding mission context.",
  "context_refs": ["image:derived:5d79cd203e114c529042676fb06c217f"],
  "isolation": {
    "omit_parent_graph": true,
    "omit_peer_candidates": true,
    "omit_parent_closure_ledger": true,
    "omit_broad_doctrine": true
  },
  "output_contract": {
    "kind": "visual_source_observation",
    "need": "source-visible reading and visual basis"
  }
}
```

### Test B — Discriminative follow-up (only if blind read ambiguous)

Narrow degree-numeral comparison task; still no confidence field.

---

## Observability Checklist (fill after live turns)

Record in this section after the resumed run produces `delegate_subtask` output:

- [ ] Turn parent delegated
- [ ] Child `status`
- [ ] `task_response`
- [ ] `source_visible_text`
- [ ] `visual_basis`
- [ ] `ambiguity` / `limits`
- [ ] `subtask_trace.prompt_char_count`
- [ ] Parent follow-up action (patch / save / HITL)
- [ ] Final `parcel-1-nw-corner-bearing` determined value
- [ ] Draft/output artifact change
- [ ] Turn-count delta vs baseline

Inspect:

- `backend/harness/cli_artifacts/cli_runs/<run_id>/audit/human/timeline.md`
- `result.json`, `done.json`
- `backend/dossiers_data/artifacts/transcript_edit/9f5eecb6-cd7e-483c-b691-b76aa7132e8e/draft_legal_text_image/<workspace>/`

---

## Follow-Up Decision Matrix (after live results)

1. **Continue hardening profile** — if delegation runs but child/parent integration is weak
2. **Add ergonomic helper** — if mechanics work but parent rarely chooses delegation
3. **Model visual limitation / HITL** — if child repeats parent misread without ambiguity signal
4. **Try alternate child model profile** — if isolation helps but default model still fails pixels
5. **Defer delegate_subtask for transcript-edit** — if turn cost rises without correctness gain

---

## Initial Hypothesis

Mechanical infrastructure is ready. The open question is behavioral: whether an isolated child read on the existing good crop produces a different (hopefully correct) source-visible numeral and whether the parent integrates that observation without treating it as automatic truth.
