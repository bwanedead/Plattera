# tx_orient_and_baseline Schema v1

Date: March 2026
Status: Active
Owner surface: transcript-edit tx startup

## 1) Purpose
`TX_ORIENT_AND_BASELINE` is the startup semantic orientation action for transcript-edit loop.

It is:
- semantic evidence generation only
- text-only model call
- typed JSON contract with deterministic coercion

It is not:
- a planner
- an apply stage
- a branch/terminal decision authority

Deterministic code remains authoritative for closure gating, branch decisions, and terminalization.

## 2) Action Name
- `tx_orient_and_baseline`

## 3) Inputs (kernel action inputs)
Required:
- `source_transcript_ref` OR `source_text`

Optional:
- `dossier_id`: string
- `model`: string (default runtime model)
- `candidate_texts`: string[] (max 10)
- `max_attempts`: int (bounded retry for invalid model output)

## 4) Output (tool inline payload)
Primary artifact:
- `artifact_ref`: orient-baseline artifact ref (`tx_orient_baseline_ref` in kernel latest refs)

Inline fields:
- `tx_source_transcript_ref`: canonical source ref
- `tx_source_transcript_hash`: canonical source hash
- `tx_orient_items`: oriented decision items (coerced)
- `tx_orient_summary`:
  - `item_count`
  - `mapping_blocking_count`
  - `optional_count`
- `tx_span_seeds_ref`: persisted span-seed artifact
- `tx_orient_raw_output_ref`: raw model output artifact

Failure/refusal shape:
- `reason_codes`: includes `tx_orient_baseline_invalid_output` or service/source refusal code
- `kernel_refusal` may be present for deterministic degraded handling
- `tx_orient_raw_output_ref` is still persisted on invalid model output

## 5) Oriented Item Contract (`tx_orient_items[]`)
Each item:
- `key`: one of
  - `township`
  - `range`
  - `section`
  - `tie_distance`
  - `tie_bearing`
  - `acreage`
  - `closure_or_pob`
- `state`: one of
  - `unknown`
  - `candidate_found`
  - `verified`
  - `disputed`
  - `accepted_with_risk`
- `selected_value`: string|null
- `alternatives`: string[]
- `confidence`: `low|medium|high`
- `layer_tag`: one of
  - `layer1_canonical_recovery`
  - `layer2_canonical_sanity`
  - `layer3_dependency`
  - `layer4_transcript_quality_optional`
- `operational_impact`: `mapping_blocking|transcript_quality_only`
- `block_reason`: `ambiguity|contradiction|dependency`
- `required_information`: string
- `minimal_user_action`: string
- `resolution_options`: string[]
- `self_retrievable`: `yes|conditional`
- `retrieval_attempted`: boolean
- `retrieval_blocker`: string|null
- `verification_required`: boolean
- `attempt_summary`: string
- `evidence_refs`: string[]
- `provenance`: string (default coerced to `orient_llm`)
- `span_seed`: object|null

## 6) span_seed Contract (per item)
If present:
- `label`: one of
  - `pob`
  - `call_chain`
  - `plss`
  - `tie_to_corner`
  - `closure`
  - `exception`
  - `acreage`
  - `misc`
- `confidence`: `low|medium|high`
- `notes`: string|null
- `start_anchor`: string (min anchor quality threshold)
- `end_anchor`: string (min anchor quality threshold)
- `occurrence`: int (1..200)

These are transformed into persisted transcript span seed artifact entries.

## 7) Deterministic Coercion Rules
The action output is treated as provisional evidence and is deterministically coerced:

- Invalid keys are dropped.
- Invalid enum values are normalized to safe defaults.
- Duplicate keys are deduplicated (first valid accepted).
- String arrays are bounded and deduplicated.
- Missing/invalid span seeds are dropped.
- `provenance` defaults to `orient_llm`.
- `mapping_blocking_count` is computed deterministically from coerced items.

No model-provided branch status, closure state, or terminal state is trusted.

## 8) Ledger Commit Rules
`update_ledger_from_orient_baseline(...)` consumes coerced items and:
- updates per-decision item state/value/alternatives/confidence
- sets layer and operational-impact metadata
- sets/normalizes closure requirements
- preserves deterministic closure requirement shape and invariants

Branching and closure gates are computed from committed ledger only.

## 9) Retry / Repair Behavior
On invalid model JSON:
1. send deterministic repair message with error reason + clipped prior output
2. retry up to bounded `max_attempts`
3. if still invalid:
  - persist raw output artifact
  - return deterministic refusal path
  - controller degrades deterministically (no invariant bypass)

## 10) Observability
Artifacts produced:
- raw model output artifact (`tx_orient_raw_output_ref`)
- orient baseline artifact (`tx_orient_baseline_ref`)
- span seed artifact (`tx_span_seeds_ref`)

Startup baseline is emitted to viewer via `investigation_baseline_result` after deterministic ledger commit.

## 11) Non-Goals
`TX_ORIENT_AND_BASELINE` must not:
- produce edit plans
- apply edits
- emit HITL decisions
- set terminal status
- bypass deterministic ledger commit path

