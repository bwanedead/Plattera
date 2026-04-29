# Generic Harness Hardening — Current Experiment

## Status
Active experiment. Do not add domain-specific doctrine without explicit user authorization.

## What this experiment is testing
Whether the **generic harness** can produce sane, outcome-driven, evidence-backed behavior across
domains — without baking deed-specific, transcript-edit-specific, or mapping-specific solutions
into prompt doctrine or code.

## Allowed generic pressure areas (harness may teach these)
- Work graph completeness: broad items must eventually decompose into independently-resolvable units.
- Source fact vs downstream decision separation: verifying a conflict exists is not the same as resolving the governing value; represent each as a separate work unit.
- Readiness and dependency consistency: a readiness, handoff, or output claim must not close while an unresolved blocker, prerequisite, or governing decision remains open in its dependency graph.
- Exact-claim evidence pressure: claims that carry specific values should have evidence refs that let a human audit the value directly.
- HITL as last-resort blocker resolution: when a mission-critical decision cannot be resolved from available evidence and tools, surface a focused HITL question rather than closing around it.
- Non-blocking consequence rationale: before marking an unresolved issue non-blocking, state what goes wrong downstream if the value is incorrect and why it is genuinely non-blocking despite those consequences.
- Atomicity of independently-wrong units: a unit is too broad if it bundles multiple exact claims or decisions that could be independently verified, independently wrong, or independently blocked.

## Forbidden during this experiment
- Deed-specific examples (Range 75/74, PLSS calls, bearings, distances) in harness or domain doctrine.
- Transcript-edit-specific decomposition lists (bearing, distance, PLSS, acreage, cutoff).
- Mapping-specific output contract fields (downstream_decisions, governing range structures).
- Readiness vocabulary tiers added only to address a specific run's failure mode.
- Dangerous-mistake entries that encode this deed's observed behavior pattern.
- Any generic harness change that is only useful for the current practice deed.

## If a behavior gap seems domain-specific
Write it as a **pending domain note** (a markdown file in `docs/architecture/harness/` or the
relevant domain directory) and flag it for a future domain-hardening pass. Do not ship it as
prompt doctrine or code during the current generic-only experiment.

## Currently active generic harness changes (kept from recent hardening pass)
These are in harness files only and are domain-neutral:

### `surface.py` (v15)
- `## Source fact vs downstream decision` — generic doctrine: verified conflict ≠ resolved governing value; represent each as a separate unit.
- `## Covered unit splitting rule` — generic doctrine: a unit with multiple independently-wrong exact values must be split.

### `choose_action_instruction.py`
- Guidance for `closed_item_with_open_dependency` flag: reopen or verify the dependency was resolved.
- Guidance for `explicit_non_blocking_without_notes` flag: add consequence rationale or reconsider.

### `loop_health_summary.py`
- `closed_items_with_open_dependencies_count` — checks both `dependencies` list and
  `resolution.relations` (open item with `blocks`/`prerequisite_of` → closed item).
- `explicit_non_blocking_without_notes_count` — items with `blocking=False` and no rationale text.
- Flag cap raised from 16 → 24.

### `models.py` / `prompt_observability.py`
- New count fields wired through the observability path.

## Related files (do not edit during this experiment without re-reading this doc)
- `backend/harness/runtime/prompting/surface.py`
- `backend/harness/runtime/orchestration/choose_action_instruction.py`
- `backend/harness/runtime/orchestration/loop_health_summary.py`
- `backend/harness/observability/summary/models.py`
- `backend/harness/observability/summary/prompt_observability.py`
