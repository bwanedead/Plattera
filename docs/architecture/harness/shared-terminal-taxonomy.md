# Shared Terminal Taxonomy

Date: 2026-03-11
Status: Phase 2 shared contract (definition only)
Program references:
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/harness/target-harness-v1.md`

## Why Harness-Level Terminal Taxonomy

Loop-family local statuses are useful, but harness convergence needs one shared terminal vocabulary for:
- cross-loop comparability
- trace analytics and failure clustering
- consistent resumability/escalation handling

This taxonomy is a harness classification layer. It does not replace local reason codes or domain closure semantics.

## Shared Terminal Classes

Harness terminal classes:
- `completed`: run objective reached under harness/domain closure gates.
- `blocked`: run cannot safely progress without a new capability/input/decision.
- `waiting_human`: blocked specifically on human response or integration of human response.
- `waiting_evidence`: blocked specifically on missing evidence/dependency inputs.
- `exhausted`: run stopped due to bounded budgets/iterations/no-progress ceilings.
- `failed`: run stopped due to execution/runtime/internal error conditions.

## Mapping Rules

## Controller/kernel family

Primary source signals:
- `TerminalOutcome.terminal_outcome`
- `TerminalOutcome.stop_reason`
- `TerminalOutcome.reason_code`

Recommended mapping:
- `stop_reason=completed` and success -> `completed`
- `stop_reason=needs_user_choice` -> `waiting_human`
- `stop_reason=needs_upload` -> `waiting_evidence`
- `stop_reason=needs_capability` -> `blocked` (capability gap; may carry blocker class `capability`)
- `stop_reason=budget_exceeded` -> `exhausted`
- `stop_reason=no_progress` -> `exhausted`
- `stop_reason=worker_unavailable` -> `blocked` (or `failed` if runtime outage semantics are explicit)
- `stop_reason=validation_failed` -> `blocked`
- `stop_reason=internal_error|error|cancelled` -> `failed` (pending future cancel-policy refinement)

## Transcript-edit family

Primary source signals:
- run result `status` (`completed`, `needs_review`, `waiting_feedback`, `failed`)
- `reason_code`
- terminal summary (`terminal_classification`, `human_feedback_pending`, unresolved closure fields)

Recommended mapping:
- `status=completed` -> `completed`
- `status=waiting_feedback` -> `waiting_human`
- `status=needs_review` + human feedback pending / waiting classifications -> `waiting_human`
- `status=needs_review` + dependency-evidence missing classifications -> `waiting_evidence`
- `status=needs_review` + no-safe-move / unresolved ambiguity without active waiting state -> `blocked`
- max-iteration/no-progress style terminal reasons -> `exhausted`
- `status=failed` -> `failed` (except explicit waiting-feedback timeout conversion cases already represented as waiting_human)

## Relationship to Reason Codes and Domain Closure

Contract split:
- terminal taxonomy answers: "How did this run end at harness level?"
- reason codes answer: "Why specifically did it end?"
- domain closure logic answers: "Was domain-specific correctness satisfied?"

Do not collapse reason codes into taxonomy classes. Keep reason codes as the granular analytics surface.

## Shared vs Domain Responsibilities

Shared harness semantics:
- terminal class definitions
- mapping requirements from loop-local outcomes
- minimum terminal record fields in canonical trace

Domain policy remains local:
- transcript-edit layer statuses and scope closure semantics
- feature-graph/mapping-specific acceptability criteria
- reason-code generation logic

## Explicit Non-Goal

This taxonomy does not erase transcript-edit's stronger closure semantics (layer statuses, scope closure, unresolved requirement structure). It only provides a shared harness-level terminal classification above them.

## Open Questions

- Should `cancelled` eventually be a distinct harness class instead of mapping to `failed`?
- Should worker availability failures split into `blocked` vs `failed` by policy id/runtime context?
- Do we need a small `partial_success` annotation field while keeping the top-level class set minimal?

