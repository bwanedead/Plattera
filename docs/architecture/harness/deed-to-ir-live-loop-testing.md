# Deed-to-IR Live Loop Testing Guide

This is the entrypoint doc for running **deed-to-IR** live-loop tests against the
frozen practice handoff from completed transcript-edit run
`practice-row-live-20260619-76`.

Read this doc first, then follow the linked harness standards in section 2.

---

## 1. What You Are Testing

You are testing whether the generic harness can run the `mapping / deed_to_ir`
domain against the practice ROW dossier using a **stable frozen handoff fixture**,
not live CLI upstream state and not transcript-edit mission state.

Expected high-level loop behavior:

1. hydrate deed-to-IR startup input from the frozen transcript-edit output
2. inspect feature-graph capabilities and author IR with provenance links
3. save IR, submit for mapping, inspect compile/judge/render feedback
4. publish deed-to-IR output when explicitly ready
5. surface blocked scopes and external dependencies honestly

For practice-deed expectations, read
[`practice_deeds/right_of_way_deed_cheatsheet.md`](../../../practice_deeds/right_of_way_deed_cheatsheet.md).

For upstream transcript-edit context, read
[`docs/architecture/harness/transcript-edit-live-loop-testing.md`](./transcript-edit-live-loop-testing.md).

For repair-behavior testing, use the **Corrupted Handoff Repair Test** section below.

---

## 2. Non-Negotiable Standards

Before running or modifying anything, read:

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture/harness/harness-constitution.md`](./harness-constitution.md)
- [`docs/architecture/harness/cli-constitution.md`](./cli-constitution.md)
- [`docs/architecture/harness/domain-runtime-adapter-architecture.md`](./domain-runtime-adapter-architecture.md)

Tester rule of thumb:

- the frozen fixture is **inherited upstream handoff**, not deed-to-IR mission state
- audit/timeline files are produced by the **generic harness runner**, not deed-to-IR tooling
- report whether failures are reasoning failures or seam/contract failures

---

## 3. Frozen Practice Handoff

Fixture root:

```text
practice_deeds/right_of_way/deed_to_ir/
  fixture_manifest.json
  transcript_edit_output.json
  resolution_state.json
```

Manifest records:

- source upstream run `practice-row-live-20260619-76`
- dossier / transcription IDs
- handoff refs
- file hashes and resolution item counts

Practice identities:

- `dossier_id = 9f5eecb6-cd7e-483c-b691-b76aa7132e8e`
- `transcription_id = draft_legal_text_image`
- `resolution_state_ref = transcript_edit:resolution_state:practice-row-live-20260619-76`

There is **no automatic latest-run selection** and **no live CLI upstream read**
during deed-to-IR startup.

### Normal practice test (default)

Use this frozen handoff when running the standard deed-to-IR live loop. Expected
behavior: efficient publish/complete against a clean inherited handoff.

### Corrupted handoff repair test (secondary)

Use only when explicitly asked to run the **corrupted handoff repair test**. Fixture:

```text
practice_deeds/right_of_way/deed_to_ir/variants/corrupted_handoff_call_distance/
  fixture_manifest.json
  transcript_edit_output.json
  resolution_state.json
```

This variant is derived from the normal frozen handoff. It deliberately corrupts
one mapping-critical resolution operand (`p1_call2_distance`) while transcript
lanes preserve the source-supported value. The manifest labels it as a test
fixture variant — not real transcript-edit output.

Expected behavior: publish/complete with at least one `upstream_corrections` row
when the agent confirms repair from source/verbatim evidence.

---

## 4. Inherited Handoff vs Fresh Deed-to-IR Mission State

The launch context supplies:

- frozen transcript-edit published output (loader input only)
- frozen resolution-state snapshot via `resolution_state_snapshot_path`
- explicit `resolution_state_ref`

It does **not** inherit transcript-edit continuity journal, mission state, or
closure posture. Deed-to-IR mission state starts fresh under the generic harness.

---

## 5. How To Run from CLI

Use PowerShell from repo root and activate the repo venv first:

```powershell
cd C:\projects\Plattera
. .venv\scripts\activate.ps1
cd backend
```

Start a run with the **generic harness runtime entrypoint**. The CLI allocates a
sortable run id automatically when `--run-id` is omitted.

### 5a. Normal practice test

```powershell
$fixtureRoot = (Resolve-Path "..\practice_deeds\right_of_way\deed_to_ir").Path
$contextObject = @{
  dossier_id = "9f5eecb6-cd7e-483c-b691-b76aa7132e8e"
  transcription_id = "draft_legal_text_image"
  max_iterations = 100
  transcript_edit_output_path = Join-Path $fixtureRoot "transcript_edit_output.json"
  resolution_state_ref = "transcript_edit:resolution_state:practice-row-live-20260619-76"
  resolution_state_snapshot_path = Join-Path $fixtureRoot "resolution_state.json"
  upstream_run_lineage = @{
    schema_version = "upstream_run_lineage.v1"
    upstream_runs = @(
      @{
        run_id = "practice-row-live-20260619-76"
        domain_id = "transcript_edit"
        relation = "input_handoff"
        handoff_refs = @(
          "transcript_edit:output"
          "transcript_edit:resolution_state:practice-row-live-20260619-76"
        )
      }
    )
  }
}
$ctx = $contextObject | ConvertTo-Json -Depth 6 -Compress

$startResult = python -m harness.cli.start `
  --loop-kind deed_to_ir `
  --python-module harness.runtime.runner.entrypoint `
  --module-arg=--domain-id `
  --module-arg=deed_to_ir `
  --module-arg=--launch-context-json `
  --module-arg=$ctx | ConvertFrom-Json

$runId = $startResult.run_id
$startResult.run_collection
$startResult.human_timeline_path
```

Guidance:

- capture `$runId` from `$startResult.run_id`; do not author timestamp-based ids
- keep the launch and foreground watch loop in one persistent PowerShell / PTY
  session so `$runId` remains available
- do **not** create repo-root scratch files such as `deed_to_ir_run_id.txt` to
  carry the ID between shell calls; run identity already lives in the CLI run
  directory and `state.json`, and scratch pointers leave the worktree dirty
- omit `run_id` and `workspace_id` from launch context unless you need an explicit
  override; the CLI injects both from the generated id when absent
- the compact launch context contains **fixture paths only** and authored
  `upstream_run_lineage`; the resolution graph is loaded mechanically inside the
  child process from `resolution_state_snapshot_path`
- prefer `max_iterations: 100` for roomier live testing
- automatic ids look like `deed-to-ir-live-r00000001` and increase per collection

### 5b. Corrupted handoff repair test

Use this block **only** when explicitly running the corrupted handoff repair test.
The launch flow is identical; only fixture paths change:

```powershell
$fixtureRoot = (Resolve-Path "..\practice_deeds\right_of_way\deed_to_ir\variants\corrupted_handoff_call_distance").Path
$contextObject = @{
  dossier_id = "9f5eecb6-cd7e-483c-b691-b76aa7132e8e"
  transcription_id = "draft_legal_text_image"
  max_iterations = 100
  transcript_edit_output_path = Join-Path $fixtureRoot "transcript_edit_output.json"
  resolution_state_ref = "transcript_edit:resolution_state:practice-row-live-20260619-76"
  resolution_state_snapshot_path = Join-Path $fixtureRoot "resolution_state.json"
  upstream_run_lineage = @{
    schema_version = "upstream_run_lineage.v1"
    upstream_runs = @(
      @{
        run_id = "practice-row-live-20260619-76"
        domain_id = "transcript_edit"
        relation = "input_handoff"
        handoff_refs = @(
          "transcript_edit:output"
          "transcript_edit:resolution_state:practice-row-live-20260619-76"
        )
      }
    )
  }
}
$ctx = $contextObject | ConvertTo-Json -Depth 6 -Compress

$startResult = python -m harness.cli.start `
  --loop-kind deed_to_ir `
  --python-module harness.runtime.runner.entrypoint `
  --module-arg=--domain-id `
  --module-arg=deed_to_ir `
  --module-arg=--launch-context-json `
  --module-arg=$ctx | ConvertFrom-Json

$runId = $startResult.run_id
$startResult.run_collection
$startResult.human_timeline_path
```

Corrupted-run guidance for the testing agent:

- use the corrupted fixture **only** when explicitly asked for the corrupted
  handoff repair test; do not substitute it for normal practice runs
- do **not** create scratch `run_id` files; let the CLI auto-allocate the id
- watch the normal deed-to-IR timeline path under
  `backend/harness/cli_artifacts/cli_runs/by_loop_kind/deed_to_ir/<runId>/audit/human/timeline.md`
- stop and review if the run appears to spin (repeated reads without drafting,
  mapping, or publication progress)
- do **not** mutate the normal frozen fixture at
  `practice_deeds/right_of_way/deed_to_ir/`

Success signals for the corrupted repair test:

- saves/patches IR
- submits mapping
- prepares final package
- publishes output
- completes the run
- includes `upstream_corrections` documenting the upstream delta when repair was
  needed and confirmed from source/verbatim/evidence basis

Failure signals:

- blindly publishes the corrupted resolution operand with no correction
- repeatedly rereads transcript lanes without drafting/patching IR
- emits `upstream_corrections` rows without source/verbatim/evidence basis
- spawns or requests transcript-edit repair during drafting (out of scope)
- mutates the normal frozen fixture

After launch, use the same `status`, `watch`, `answer`, `pause`, `stop`, and
`resume` commands from section 5a with the allocated `$runId`.

Check status:

```powershell
python -m harness.cli.status --run-id $runId
```

Watch the run in the foreground:

```powershell
while ($true) {
  $watchEvent = python -m harness.cli.watch --run-id $runId --timeout 7200 --poll-interval 3 | ConvertFrom-Json

  if ($watchEvent.event -eq "timeout") {
    continue
  }

  if ($watchEvent.event -eq "hitl") {
    # Inspect the returned prompt and choices. Use prompt_id exactly as returned.
    python -m harness.cli.answer --run-id $runId --prompt-id $watchEvent.prompt_id --choice "<operator answer>" --note "<optional note>"
    continue
  }

  if ($watchEvent.event -eq "loop_done") {
    break
  }

  # event=error or an unknown event: inspect status and logs before continuing.
  break
}
```

`watch` is a blocking poll that returns one JSON event and exits. The loop above
keeps monitoring the same run until terminal completion or an explicit operator
decision. Do not detach or background the watcher: the testing agent needs the
foreground event so it can answer HITL promptly and continue observing the same
run.

Watch events:

- `hitl`: inspect the prompt and any choices, answer the exact returned
  `prompt_id`, then continue watching
- `loop_done`: the run reached a terminal state; exit the watch loop and review
  final artifacts
- `timeout`: no event arrived during that watch window; continue watching
- `error`: inspect `status`, `stdout.log`, `stderr.log`, and the human timeline

When `watch` returns a HITL event, it consumes the operator-side pending prompt
sidecar so the same prompt is not shown repeatedly. The prompt remains answerable
with the returned `prompt_id`; do not expect a later `status` call to rediscover it.

Use graceful operator controls when needed:

```powershell
python -m harness.cli.pause --run-id $runId
python -m harness.cli.stop --run-id $runId
```

Pause and stop are honored at safe runtime boundaries. They do not kill a model or
tool call in progress. Once the run reaches `paused` or `stopped`, it remains
resumable when `kernel_resume.json` exists:

```powershell
python -m harness.cli.status --run-id $runId
python -m harness.cli.resume --run-id $runId
```

If the provider disconnects, the child process exits, or another resumable failure
occurs, inspect status before starting over. Resume the same logical run when status
reports an interrupted resumable checkpoint:

```powershell
python -m harness.cli.status --run-id $runId
python -m harness.cli.resume --run-id $runId
```

Resume restores the last completed-turn checkpoint. It does not replay a partially
failed model call or infer domain meaning. Completed runs are not reopened by the
current resume path.

### Tester-to-agent corrections

HITL is agent-initiated. To give a tester-initiated correction or missing context,
send an exact message for the next turn:

```powershell
python -m harness.cli.message --run-id $runId --text "Correction: <specific IR, source, mapping, or artifact issue and the requested repair>." --source tester
```

Name the affected source unit, IR entity, mapping feature, or artifact ref when
possible. State what appears wrong and what should be rechecked; do not replace
normal evidence and repair work with broad critique. If the run is interrupted,
send the message first, resume, then return to the foreground watch loop.

---

## 6. Artifact and Timeline Locations

New runs are stored under a namespaced collection derived from `--loop-kind`:

```text
backend/harness/cli_artifacts/cli_runs/by_loop_kind/deed_to_ir/<runId>/
  state.json
  kernel_resume.json
  done.json
  result.json
  stdout.log
  stderr.log
  audit/
    index.json
    human/timeline.md
    turn_0001.json
    turn_0002.json
```

Example deed-to-IR timeline path:

```text
C:\projects\Plattera\backend\harness\cli_artifacts\cli_runs\by_loop_kind\deed_to_ir\<runId>\audit\human\timeline.md
```

Legacy flat runs (pre-partition) remain readable in place, for example upstream run
`practice-row-live-20260619-76`:

```text
backend/harness/cli_artifacts/cli_runs/practice-row-live-20260619-76/
  audit/human/timeline.md
```

Retention keeps the latest **5 unpinned runs per collection** independently:
`transcript_edit`, `deed_to_ir`, and legacy flat runs each have their own queue.
A sixth deed-to-IR run removes only the oldest unpinned deed-to-IR run; it does
not evict transcript-edit runs.

Keep `audit/human/timeline.md` open while the foreground watcher runs. The file is
created after the first audited turn and rewritten as later turns complete. Use it
to inspect orientation, state changes, tool calls, IR revisions, mapping submission,
render inspection, repairs, publication, and upstream-run lineage while the run is
still active.

Domain artifacts (outside harness CLI dir):

- feature-graph IR / compile / judge / mapping under
  `backend/dossiers_data/artifacts/feature_graphs/<dossier_id>/`
- mapping sidecars under
  `backend/dossiers_data/artifacts/feature_graphs/<dossier_id>/mappings/`
- published deed-to-IR output under
  `backend/dossiers_data/artifacts/deed_to_ir/<dossier_id>/<transcription_id>/<workspace_id>/output/`

---

## 7. Expected Outputs

During a healthy deed-to-IR live run you should eventually see:

- saved IR artifact(s)
- compile and judge artifacts from mapping submission
- mapping artifact plus clean/control render sidecars
- published deed-to-IR output revision (`deed_to_ir:output`, `deed_to_ir:output:rev:NNNN`)
- audit timeline entries for tool calls and publish outputs

For the **corrupted handoff repair test**, also confirm published output (or final
package preview) includes at least one `upstream_corrections` row when the agent
relied on a corrected value instead of the corrupted resolution operand.

Absence of publish output alone does not mean the harness failed; it may mean the
agent has not yet earned publication.

---

## 8. Run Review Checklist

After a live run, inspect:

1. `audit/human/timeline.md` — upstream run lineage section (when authored), turn sequence, tool calls, publish section if present
2. `audit/turn_NNNN.json` — per-turn mechanical records
3. `result.json` / `done.json` — terminal class and reason code
4. feature-graph artifacts for the dossier — IR, mapping, sidecars
5. deed-to-IR published output revision if publish ran
6. whether failures look like agent reasoning vs harness seam/contract breakage

---

## 9. Related Code

- Frozen fixture (normal): `practice_deeds/right_of_way/deed_to_ir/`
- Corrupted fixture variant: `practice_deeds/right_of_way/deed_to_ir/variants/corrupted_handoff_call_distance/`
- Fixture integrity tests: `backend/domains/mapping/deed_to_ir/test_corrupted_handoff_fixture.py`
- Resolution path loader: `backend/tooling/mapping/deed_to_ir/resolution_state_loading.py`
- Generic runtime entrypoint: `backend/harness/runtime/runner/entrypoint.py`
- Upstream run lineage: `backend/harness/runtime/upstream_run_lineage.py`
- Deed-to-IR runtime adapter: `backend/domains/mapping/deed_to_ir/runtime_adapter/`
