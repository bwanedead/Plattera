# Closure Policy Action Ownership Brief

This brief defines the first bounded cleanup leg from the harness polish backlog:

- remove transcript-edit save/publish action-id knowledge from shared harness code
- move action-role ownership into the existing domain-owned closure-policy contract
- preserve current runtime behavior while making the ownership boundary honest

This is a **boundary-correction** brief, not a feature brief.

---

## 1. Why this change matters

The current harness is architecturally close to the right shape, but one clear leak remains:

- shared harness code still knows transcript-edit tool ids for `save` and `publish`

That conflicts with the current domain-pack architecture:

- harness owns generic loop mechanics and enforcement rails
- domains own semantic tool declarations and closure meaning

If shared harness code knows that `publish_workspace_artifact` is "the publish action,"
then the harness is carrying domain vocabulary that should belong to the domain pack.

This is not a theoretical purity issue.
It matters because:

- it teaches the wrong ownership boundary
- it makes the harness less generic than it claims to be
- it encourages more future policy leakage into shared orchestration

---

## 2. Repo reality today

### 2.1 Where the leak lives

Shared harness code currently hard-codes transcript-edit action ids in:

- `backend/harness/runtime/orchestration/orchestrator_policy.py`
- `backend/harness/runtime/orchestration/orchestrator.py`

Specifically, the harness currently carries:

- `_PUBLISH_ACTION_IDS = {"publish_workspace_artifact"}`
- `_SAVE_ACTION_IDS = {"save_workspace_artifact"}`

Those ids are then used to decide:

- whether resolution-item minimums apply to `save` or `publish`
- whether audited-work-universe and closure gating apply to `publish`

### 2.2 Where the ownership should already live

The domain layer already owns the closure-policy contract:

- `backend/domains/closure_policy.py`

Transcript-edit already owns the concrete closure-policy instance:

- `backend/domains/mapping/transcript_edit/semantics/closure.py`

The runner already injects that policy into orchestration context:

- `backend/harness/runtime/runner/runner.py`

So the missing piece is not a new transport.
The missing piece is to let the domain-owned policy also declare which action ids count as `save` and `publish`.

---

## 3. The real problem

The problem is **not** that the harness is enforcing closure mechanically.
That is correct.

The problem is that the harness is deciding which opaque action ids map to semantic closure targets:

- "this action id means save"
- "this action id means publish"

That mapping is domain knowledge.

The shared harness should be able to ask only:

- is this action in the domain's declared `save` set?
- is this action in the domain's declared `publish` set?

It should not know the transcript-edit strings directly.

---

## 4. Non-negotiable rules

### 4.1 Keep the harness generic

After this change, shared harness code must no longer hard-code transcript-edit action ids.

### 4.2 Reuse the existing policy seam

Do not invent a second side channel for action-role ownership.

Use the existing domain-owned `DomainClosurePolicy` contract unless a stronger reason appears.

### 4.3 Keep prompt-visible closure policy slim

The model-facing prompt should continue to see only the currently whitelisted closure-policy requirement fields.

Do not expose the new action-id fields in the prompt by accident.

### 4.4 No behavior broadening through fallback guesswork

If a domain does not declare `save_action_ids` or `publish_action_ids`, the harness should not guess.

Use explicit declarations, not inferred name matching.

---

## 5. Target shape

### 5.1 DomainClosurePolicy grows two action-role fields

Add to `backend/domains/closure_policy.py`:

- `save_action_ids: tuple[str, ...] = ()`
- `publish_action_ids: tuple[str, ...] = ()`

These fields are generic because they express action-role ownership, not transcript-edit semantics.

### 5.2 Transcript-edit declares its own action roles

In `backend/domains/mapping/transcript_edit/semantics/closure.py`, transcript-edit should set:

- `save_action_ids=("save_workspace_artifact",)`
- `publish_action_ids=("publish_workspace_artifact",)`

This keeps ownership where it belongs: the transcript-edit domain pack.

### 5.3 The runner transport stays the same

`backend/harness/runtime/runner/runner.py` already injects the domain closure policy into `opaque_run_context`.

That should remain the transport path.

### 5.4 Harness enforcement reads the declared ids from policy

`backend/harness/runtime/orchestration/orchestrator_policy.py` should:

- remove the hard-coded `_SAVE_ACTION_IDS`
- remove the hard-coded `_PUBLISH_ACTION_IDS`
- read the action-role sets from `domain_closure_policy`

This should drive:

- `minimum_resolution_items_required(...)`
- `closure_enforcement_failure(...)`

### 5.5 The main orchestrator should not carry dead copies

`backend/harness/runtime/orchestration/orchestrator.py` should not retain duplicate action-id constants if they are no longer used.

---

## 6. File-by-file responsibilities

### 6.1 `backend/domains/closure_policy.py`

Own the generic policy contract fields only.

Add:

- `save_action_ids`
- `publish_action_ids`

Do not add harness-specific enforcement logic here.

### 6.2 `backend/domains/mapping/transcript_edit/semantics/closure.py`

Own the transcript-edit declaration of which action ids count as `save` and `publish`.

This file is the correct semantic home because it already owns transcript-edit closure policy.

### 6.3 `backend/harness/runtime/orchestration/orchestrator_policy.py`

Own the mechanical enforcement logic only.

It should:

- normalize action ids from policy
- decide whether the current action belongs to the declared `save` or `publish` role
- keep all enforcement behavior generic once that role is known

### 6.4 `backend/harness/runtime/orchestration/orchestrator.py`

Own loop mechanics only.

Remove dead constants if they become obsolete after the policy change.

### 6.5 Tests

The test work should be concentrated in:

- `backend/domains/mapping/transcript_edit/test_transcript_edit_pack.py`
- `backend/harness/runtime/orchestration/test_orchestrator_policy.py`
- `backend/harness/runtime/orchestration/test_orchestrator.py`
- `backend/harness/runtime/runner/test_runner.py`
- optionally `backend/harness/runtime/orchestration/test_llm_turn_adapter.py`

---

## 7. Implementation sequence

Recommended order:

1. Extend `DomainClosurePolicy` with `save_action_ids` and `publish_action_ids`.
2. Update transcript-edit closure semantics to declare those ids.
3. Refactor `orchestrator_policy.py` to read action-role sets from the injected policy dict.
4. Remove obsolete hard-coded constants from `orchestrator.py`.
5. Update unit tests that build raw `domain_closure_policy` dicts by hand.
6. Update transcript-edit pack tests to assert the new contract fields.
7. Add a prompt-visibility regression test if needed to ensure the new fields remain hidden from the model.
8. Run the targeted verification suite.

---

## 8. Implementation notes

### 8.1 Matching logic

Use exact normalized string membership against the declared policy sets.

Do not:

- regex-match action names
- infer role from substrings like `publish`
- add fallback guesses

### 8.2 Policy defaults

Empty tuples are acceptable defaults for generic domains that do not use those roles.

That keeps the shared contract generic and non-prescriptive.

### 8.3 Prompt visibility

`backend/harness/runtime/orchestration/prompt_packet_builder.py` currently exposes only a small whitelist of closure-policy keys to the model.

Do not add the new action-id fields to that whitelist.

The model does not need those ids from closure policy because tool ids already arrive through the normal prompt surface.

### 8.4 Compatibility of test helpers

Many harness tests build `domain_closure_policy` as a plain dict instead of using the dataclass.

Those helpers will need to include the new fields where `publish` or `save` semantics are under test.

This is expected and should be treated as part of the change, not as incidental fallout.

---

## 9. Risks and edge cases

### 9.1 Biggest regression risk: incomplete test fixtures

The most likely failure mode is not production behavior.
It is tests that manually construct partial `domain_closure_policy` dicts and no longer reflect the new contract shape.

### 9.2 Prompt-surface regression

If the new fields accidentally become prompt-visible, the prompt contract will silently widen.

That is avoidable by leaving the whitelist unchanged and, ideally, adding a regression assertion.

### 9.3 Silent behavior change when policy omits action ids

If a future domain turns on minimum resolution-item requirements for `save` or `publish` but forgets to declare the corresponding action-id sets, the harness will no longer know which actions those policies apply to.

That is acceptable because explicit declaration is the point of this change.
The fix in that case is to correct the domain policy, not to add shared fallback guessing.

---

## 10. Verification plan

Run these targeted checks after implementation:

1. `.\.venv\scripts\activate.ps1; pytest backend/domains/mapping/transcript_edit/test_transcript_edit_pack.py -q`
2. `.\.venv\scripts\activate.ps1; pytest backend/harness/runtime/orchestration/test_orchestrator_policy.py -q`
3. `.\.venv\scripts\activate.ps1; pytest backend/harness/runtime/orchestration/test_orchestrator.py -q -k "publish or closure or resolution"`
4. `.\.venv\scripts\activate.ps1; pytest backend/harness/runtime/runner/test_runner.py -q -k closure_policy`
5. If prompt-visibility coverage is added: `.\.venv\scripts\activate.ps1; pytest backend/harness/runtime/orchestration/test_llm_turn_adapter.py -q -k domain_closure_policy`

---

## 11. Definition of done

This brief is complete when:

1. shared harness code no longer hard-codes transcript-edit `save` / `publish` action ids
2. transcript-edit declares those action-role ids through the domain-owned closure policy
3. enforcement behavior remains the same from the operator's perspective
4. the new action-id fields stay out of the prompt-visible closure-policy slice
5. targeted tests pass

---

## 12. One-line operating rule

Let the domain declare which action ids count as `save` and `publish`; let the harness enforce mechanically once those roles are declared, and nothing more.

