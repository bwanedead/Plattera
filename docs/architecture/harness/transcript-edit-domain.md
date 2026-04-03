# Transcript-Edit Domain

This document is the current tester/developer-facing description of the
`mapping / transcript_edit` domain pack.

For family-level intent, read
[`docs/architecture/mapping/mapping-family-intent.md`](../mapping/mapping-family-intent.md)
first.

For live CLI testing instructions, read
[`docs/architecture/harness/transcript-edit-live-loop-testing.md`](./transcript-edit-live-loop-testing.md).

---

## 1. Mission Intent

Transcript edit exists to establish a source-grounded transcript artifact that
is trustworthy enough to hand forward to mapping work.

The domain starts from a dossier/transcription scope, a source image (or source
image set), and one or more peer T0 raw draft refs. The agent’s job is to author
a **separate transcript-edit working draft** and eventually publish an explicit
transcript-edit output artifact when it judges that doing so is warranted.

This domain is not “pick the best T0 head.”
T0 drafts are peer evidence inputs. The transcript-edit output is a distinct
agent-authored artifact.

---

## 2. Current Input/Output Model

### Inputs

The first-contact startup surface is refs-first:

- dossier/transcription/workspace scope
- source image refs from dossier associations
- peer T0 raw draft refs from the transcription run folder
- latest transcript-edit working/output refs if they exist for the workspace
- lightweight metadata only

Full draft text and source-image path details are hydrated only if the model
chooses to call a tool.

### Outputs

The domain currently supports domain-owned transcript-edit persistence under:

```text
backend/dossiers_data/artifacts/transcript_edit/<dossier_id>/<transcription_id>/<workspace_id>/
  working/rev_0001.json
  working/rev_0002.json
  working/latest.json
  output/output.json
  manifest.json
```

`workspace_id` is preferred when provided; otherwise `run_id` is used as the
workspace key. This keeps working drafts resumable without placing in-progress
agent-authored text inside T0 raw draft storage.

---

## 3. Current Tool Surface

Implemented and bound in the transcript-edit runtime adapter:

- `load_transcript_edit_startup_inventory`
- `hydrate_t0_draft_refs`
- `hydrate_transcript_edit_working_draft`
- `load_source_image_context`
- `save_transcript_edit`
- `publish_transcript_edit_output`

Declared but not yet implemented in this slice:

- `image_verify`
- `image_crop_refine`
- `compare_transcript_variants`
- `compare_transcript_to_image`
- `request_alignment_refresh`
- `request_consensus_refresh`
- `request_human_verification`

The model may still see the declared semantic tool specs for those deferred
actions, but only the implemented tool IDs above are currently executable.

---

## 4. State Model

The transcript-edit agent can now maintain a generic model-authored
`state_patch` alongside each action. That patch is merged into carried
mission/resolution state by harness code only if the mechanical gate allows it.

Important consequences:

- the model can persist an evolving work list, active focus, relations, and
  mission summaries across turns in one uninterrupted run
- state patches are mechanically validated and bounded by the harness
- host-owned mission summaries such as `latest_refs_summary`,
  `terminal_summary`, and `prompt_observability_summary` are not writable from
  model patches

Current caveat:

- this state survives **within one running process**, but restart-resume
  rehydration for model-authored mission/resolution state is not yet wired

---

## 5. Semantics and Closure Doctrine

Transcript edit should reason in terms of four practical closure concerns:

- source-vs-transcript delta recovery
- intrinsic source contradictions
- external missing dependencies or missing source content
- downstream mapping relevance of unresolved issues

That doctrine lives in domain-owned prompt and semantics files, not in harness
runtime logic. The harness may store and validate generic state containers, but
the model remains the author of work meaning, focus, blockers, and closure
posture.

---

## 6. Architecture Boundaries

Read these before editing domain/runtime seams:

- [`docs/architecture/harness/harness-constitution.md`](./harness-constitution.md)
- [`docs/architecture/harness/domain-pack-constitution.md`](./domain-pack-constitution.md)
- [`docs/architecture/harness/domain-runtime-adapter-architecture.md`](./domain-runtime-adapter-architecture.md)
- [`docs/ethos/agent-engine-ergonomics-theory.md`](../../ethos/agent-engine-ergonomics-theory.md)

Boundary rules:

- harness owns orchestration, execution mechanics, traces, and generic loop
  persistence
- transcript-edit domain owns doctrine, semantic tool declarations, state
  meaning, closure/handoff semantics, and its thin runtime adapter
- transcript-edit tooling owns dossier reads, image/artifact hydration, and
  transcript-edit draft persistence
- harness must not import transcript-edit internals
- domain must not implement its own runner/process lifecycle

---

## 7. Canonical Code Map

- Domain pack:
  [`backend/domains/mapping/transcript_edit/`](../../../backend/domains/mapping/transcript_edit)
- Domain runtime adapter:
  [`backend/domains/mapping/transcript_edit/runtime_adapter/`](../../../backend/domains/mapping/transcript_edit/runtime_adapter)
- Domain tooling:
  [`backend/tooling/mapping/transcript_edit/`](../../../backend/tooling/mapping/transcript_edit)
- Generic harness runner:
  [`backend/harness/runtime/runner/`](../../../backend/harness/runtime/runner)
- Generic harness orchestration:
  [`backend/harness/runtime/orchestration/`](../../../backend/harness/runtime/orchestration)
- Generic harness execution:
  [`backend/harness/execution/`](../../../backend/harness/execution)

---

## 8. Known Gaps Before Stronger Live Evaluation

- restart-resume rehydration for model-authored mission/resolution state is not
  wired yet
- HITL prompt emission and answer continuation still need to be validated in a
  full transcript-edit run
- image verification / comparison tools are declared but not yet concretely
  implemented in this slice
- frontend Agent Viewer integration is not built yet, though persisted refs,
  traces, and transcript-edit workspace artifacts are shaped to support it
