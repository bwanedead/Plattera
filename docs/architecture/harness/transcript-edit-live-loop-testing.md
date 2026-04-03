# Transcript-Edit Live Loop Testing Guide

This is the single entrypoint doc for getting a fresh testing agent up to
speed on transcript-edit live-loop testing.

Read this doc first, then follow the links in sections 2 and 6.

---

## 1. What You Are Testing

You are testing whether the generic harness can run the
`mapping / transcript_edit` domain against a real practice dossier and whether
the model behaves like a useful transcript-edit agent.

Expected high-level loop behavior:

1. inspect the startup inventory of source image refs and peer T0 draft refs
2. hydrate one or more draft refs and source-image context as needed
3. maintain model-authored work state through `state_patch`
4. save transcript-edit working draft revisions when the model has authored a
   useful edit
5. publish transcript-edit output only when explicitly ready
6. surface contradictions or missing source content instead of silently guessing
7. request human input when a contradiction is genuinely blocked on HITL

For domain semantics and architecture boundaries, read
[`docs/architecture/harness/transcript-edit-domain.md`](./transcript-edit-domain.md).

For family-level mission intent, read
[`docs/architecture/mapping/mapping-family-intent.md`](../mapping/mapping-family-intent.md).

---

## 2. Non-Negotiable Standards

Before running or modifying anything, read:

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture/harness/harness-constitution.md`](./harness-constitution.md)
- [`docs/architecture/harness/domain-pack-constitution.md`](./domain-pack-constitution.md)
- [`docs/architecture/harness/domain-runtime-adapter-architecture.md`](./domain-runtime-adapter-architecture.md)
- [`docs/ethos/agent-engine-ergonomics-theory.md`](../../ethos/agent-engine-ergonomics-theory.md)
- [`docs/ethos/testing-ethos.md`](../../ethos/testing-ethos.md)

Tester rule of thumb:

- report whether failures are reasoning failures or seam/contract failures
- if the model repeatedly expresses a sane near-miss action shape, preserve that
  evidence because it may be an ergonomics signal
- do not “fix” behavior by introducing deterministic semantic scripting in the
  harness

---

## 3. Current Practice Dossier

The current app-generated right-of-way practice dossier is:

- `dossier_id = 9f5eecb6-cd7e-483c-b691-b76aa7132e8e`
- `transcription_id = draft_legal_text_image`
- source image:
  `backend/dossiers_data/images/original/draft_legal_text_image_original.jpg`
- T0 run folder:
  `backend/dossiers_data/views/transcriptions/9f5eecb6-cd7e-483c-b691-b76aa7132e8e/draft_legal_text_image/`

Read
[`practice_deeds/right_of_way_deed_cheatsheet.md`](../../../practice_deeds/right_of_way_deed_cheatsheet.md)
before judging whether behavior is good or bad.

Key expected practice-deed observations:

- the deed image is cut off at the bottom; Plot 2 is incomplete
- `Range 75` vs `Range 74` is an intrinsic source contradiction and should
  become a HITL/blocker, not a silent deterministic choice
- `1.4 acres` in one T0 draft should be corrected to `1.9 acres` from source
  evidence
- Plot 1 should remain forwardable to mapping once the range conflict is
  resolved; Plot 2 should be marked blocked/incomplete

---

## 4. How To Run the Loop from CLI

Use PowerShell from repo root and activate the repo venv first:

```powershell
cd C:\projects\Plattera
. .venv\scripts\activate.ps1
cd backend
```

Start a run:

```powershell
$ctx = '{"dossier_id":"9f5eecb6-cd7e-483c-b691-b76aa7132e8e","transcription_id":"draft_legal_text_image","workspace_id":"practice-right-of-way","run_id":"practice-right-of-way","model":"gpt-o4-mini","max_iterations":6}'
python -m harness.cli.start --run-id practice-right-of-way --loop-kind transcript_edit --python-module harness.runtime.runner.entrypoint --module-arg=--domain-id --module-arg=transcript_edit --module-arg=--launch-context-json --module-arg=$ctx
```

Check status:

```powershell
python -m harness.cli.status --run-id practice-right-of-way
```

Wait for either HITL or terminal completion:

```powershell
python -m harness.cli.watch --run-id practice-right-of-way --timeout 60
```

If `watch` returns a HITL prompt, answer it:

```powershell
python -m harness.cli.answer --run-id practice-right-of-way --prompt-id <prompt_id_from_watch> --choice "<your answer>" --note "<optional note>"
```

Then call `watch` again.

Restart-resume:

- on completion, `result.json` includes `kernel_resume_snapshot`
- to test resume in a fresh process, persist that snapshot and pass either
  `kernel_resume_snapshot_path` or `kernel_resume_snapshot` in the next
  launch-context JSON
- resume rehydrates loop continuity and execution-session state mechanically;
  it should restore model-authored `mission_state` / `resolution_state` without
  semantic re-authoring by the harness

---

## 5. Where To Inspect Artifacts

Harness CLI run-state and child logs:

```text
backend/dossiers_data/artifacts/harness/cli_runs/<run_id>/
  state.json
  stdout.log
  stderr.log
  result.json
  done.json
```

This `cli_runs/` folder is operator control-plane metadata. The transcript-edit
domain data path itself is app-native backend plumbing, not a CLI-only sandbox:
the CLI invokes the real `transcript_edit` domain adapter, loads dossier/T0
inputs from `dossiers_data`, and writes transcript-edit working/output artifacts
to the normal `artifacts/transcript_edit/...` tree below.

Generic harness run/session artifacts:

```text
backend/dossiers_data/artifacts/harness/
```

Transcript-edit working/output draft artifacts:

```text
backend/dossiers_data/artifacts/transcript_edit/<dossier_id>/<transcription_id>/<workspace_id>/
  working/rev_0001.json
  working/latest.json
  output/output.json
  manifest.json
```

T0 source draft inputs remain under:

```text
backend/dossiers_data/views/transcriptions/<dossier_id>/<transcription_id>/raw/
```

Do not treat the legacy pointer alias `raw/<transcription_id>.json` as an
independent peer T0 draft. The startup inventory should expose only real peer
T0 draft refs from `run.json.completed_drafts`.

---

## 6. What To Read If Something Looks Wrong

Current domain + harness docs:

- [`docs/architecture/mapping/mapping-family-intent.md`](../mapping/mapping-family-intent.md)
- [`docs/architecture/harness/transcript-edit-domain.md`](./transcript-edit-domain.md)
- [`docs/architecture/harness/harness-constitution.md`](./harness-constitution.md)
- [`docs/architecture/harness/domain-pack-constitution.md`](./domain-pack-constitution.md)
- [`docs/ethos/agent-engine-ergonomics-theory.md`](../../ethos/agent-engine-ergonomics-theory.md)

Current code entrypoints:

- [`backend/harness/cli/`](../../../backend/harness/cli)
- [`backend/harness/runtime/runner/`](../../../backend/harness/runtime/runner)
- [`backend/harness/runtime/orchestration/`](../../../backend/harness/runtime/orchestration)
- [`backend/domains/mapping/transcript_edit/runtime_adapter/`](../../../backend/domains/mapping/transcript_edit/runtime_adapter)
- [`backend/tooling/mapping/transcript_edit/`](../../../backend/tooling/mapping/transcript_edit)

Practice deed interpretation:

- [`practice_deeds/right_of_way_deed_cheatsheet.md`](../../../practice_deeds/right_of_way_deed_cheatsheet.md)

## 7. What To Report After a Test Run

Always report:

- run id and launch context
- terminal status/reason
- which tools the model called and in what order
- whether `state_patch` was applied/rejected/not_applied and why
- what transcript-edit working/output refs were produced
- whether HITL was requested and whether that request was warranted
- whether the model caught the known practice-deed quirks from the cheat sheet
- whether a failure was a model reasoning failure or a system/contract seam
  failure

If behavior reveals a repeated sane near-miss action shape, preserve the raw
payload and cite
[`docs/ethos/agent-engine-ergonomics-theory.md`](../../ethos/agent-engine-ergonomics-theory.md)
when recommending contract changes.
