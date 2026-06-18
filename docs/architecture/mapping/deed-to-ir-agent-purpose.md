# Deed-to-IR Agent Purpose

This document preserves the working intent for the `mapping / deed_to_ir` domain. It is reference guidance, not a runtime contract and not deterministic parsing policy.

The short version: deed-to-IR consumes a transcript-edit handoff and produces feature-graph IR that can be compiled, judged, rendered, inspected, repaired, and handed downstream as the programmatic mapping representation of the deed.

---

## 1. Core Mission

The deed-to-IR agent turns transcript text and upstream mapping notes into a durable intermediate representation.

It should:

- consume the transcript-edit output lanes and parcel forwardability metadata
- author feature-graph IR for the forwardable deed scope
- preserve blocked or partial scopes instead of silently mapping them
- compile and judge the IR through deterministic tools when available
- inspect the resulting geometry or map preview for sanity
- repair the IR when compile, judge, or visual review exposes a problem
- produce final IR/compile/judge/bundle artifacts for downstream mapping use

The output is not just a prose summary. The output is the schema-level object the system can programmatically compile and render.

---

## 2. Source Lanes

Transcript-edit hands deed-to-IR several lanes with different authority.

- `normalized_or_mapping_transcript` is the primary machine-parameter lane.
- `source_transcript_verbatim` is audit and contradiction context.
- `parcel_metadata` carries upstream forwardable/blocked scope.
- `issues`, `hitl_decisions`, and `evidence_refs` preserve why upstream made the handoff it made.

The normalized lane is allowed to be the working lane for IR. The verbatim lane still matters when there is a contradiction, a source quotation need, or a reason to audit what was normalized.

Do not collapse those lanes. The difference is part of the handoff.

---

## 3. Agent vs Tool Responsibilities

The agent authors meaning.

Deterministic tools provide rails:

- validate feature-graph schema
- persist artifacts
- compile IR into best-effort geometry
- judge missing operands, missing parameters, unsupported operations, and related gaps
- render map or geometry previews when available
- return explicit refs and compact summaries

Tools must not parse the deed into IR by themselves, choose semantic blockers, invent forwardability, or declare closure from a scripted category. Those are agent-authored decisions.

---

## 4. Normal Working Loop

The local deed-to-IR loop should be:

1. Orient on transcript-edit handoff and inherited parcel scope.
2. Inventory the IR work by forwardable vs blocked scope.
3. Author an initial feature graph for the forwardable scope.
4. Save the IR artifact.
5. Compile the IR artifact.
6. Judge the IR artifact.
7. Review deterministic gaps and rendered/compiled geometry.
8. Repair the IR if the compiled or visual result does not match the deed meaning.
9. Repeat until the remaining gaps are honest and the final artifact package is ready.

This is not a one-shot text-to-schema parse. It is an artifact loop: author, compile, judge, inspect, repair.

---

## 5. Visual Sanity

The map or geometry preview is not decorative. It is a practical sanity check.

The agent should compare the rendered result against:

- the IR it authored
- the normalized/mapping transcript
- inherited blocked/forwardable scope
- general geometric common sense
- explicit compile and judge gaps

If the map looks wrong, the next question is why. The problem may be bad IR, a missing dependency, an unsupported operation, an upstream transcript issue, or a renderer/compiler limitation. The agent should investigate and repair the correct layer instead of forcing the final output to look complete.

---

## 6. Upstream Diagnostic Access

Most deed-to-IR work should not reopen transcript-edit. The handoff exists to prevent constant backtracking.

But if mapping exposes a real upstream issue, the agent should be able to inspect upstream context:

- transcript-edit final output
- relevant evidence refs
- upstream resolution graph or state, if exposed
- source imagery or crops, when the map failure depends on source interpretation

This is diagnostic fallback, not the normal path. The normal path is: trust the transcript-edit handoff enough to build IR, then use compile/judge/render results to find real problems.

---

## 7. Closure Layers

Deed-to-IR closure is different from transcript-edit closure.

Useful closure layers:

1. **Scope closure**: forwardable vs blocked scopes from transcript-edit are preserved.
2. **IR representability**: forwardable deed meaning is represented in feature graph IR, or the gap is explicit.
3. **Compile closure**: compile was attempted where possible and compile gaps are explicit.
4. **Judge closure**: judge was attempted and judge gaps are explicit.
5. **Visual sanity closure**: rendered/compiled output was inspected against deed meaning and obvious mismatches were repaired or explained.
6. **Handoff closure**: final artifact refs are produced for downstream use.

An honest partial result is acceptable. A silent fake-complete map is not.

---

## 8. First Implementation Target

The first real implementation target is a local loop for one transcript-edit handoff:

- save IR
- compile IR
- judge IR
- inspect summaries and future map previews
- repair IR
- publish the artifact package

External dependency retrieval, folder-level deed scheduling, and cross-deed dependency resolution are later orchestration layers. Deed-to-IR should emit dependency needs cleanly, but it should not own the whole multi-deed scheduler.

