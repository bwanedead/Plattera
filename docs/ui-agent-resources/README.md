# Agent Viewer UI Resources

This folder contains lightweight, git-safe replay bundles for building and
testing a universal agent-process viewer without requiring a live model run.

## Cloud Agent Start

Start with
[`cloud-agent-initiation-brief.md`](./cloud-agent-initiation-brief.md). It
defines the base/working branches, required reading, hard no-harness-edit scope,
long-running product goal, and autonomy expected for cloud UI development.

Before implementation, read:

1. `docs/architecture/agent-viewer-product-vision.md` for the product and UX
   north star.
2. `docs/architecture/agent-viewer-v1.md` for architecture and ownership
   boundaries.
3. `docs/ui-agent-resources/platform-viewer-contract.md` for the generic replay
   lanes and extension contract.

Cloud UI work must treat `backend/harness/`, active domain packs, and domain
tooling as read-only. Use this replay and viewer-owned adapters to develop the
experience. Document missing upstream contracts rather than patching producers
from the UI branch.

The viewer is a platform surface. It must render generic harness concepts first:

- run identity, status, progress, and terminal outcome
- chronological turns and agent-authored rationale/progress text
- action batches, tool requests, results, refusals, and repairs
- mission, resolution, stable-context, pin, and continuity state
- model timing, token usage, streaming, and delegate activity
- user/HITL messages and pending interaction
- artifact refs, artifact lineage, media, and final outputs

Domain payloads are opaque extensions. Transcript-edit, deed-to-IR, and future
domains may register richer renderers, but the core viewer must remain useful
when it has never seen a domain or tool ID before.

## Included Replay

`fixtures/practice-row-live-20260619-76/` is a sanitized replay of a complete
29-turn transcript-edit run. It preserves real harness structures and artifact
relationships while replacing all source/derived images with one placeholder.

Start with:

1. `replay_manifest.json`
2. `replay/turn_index.json`
3. `replay/events.jsonl`
4. `replay/turns/turn_NNNN.json`
5. `artifacts/artifact_catalog.json`
6. `artifacts/media_catalog.json`
7. `replay/final_state.json`

## Regeneration

From the repository root with the repository venv active:

```powershell
python docs/ui-agent-resources/scripts/build_transcript_edit_replay.py
```

The generator sanitizes local paths, drops raw prompts and binary payloads,
copies persisted JSON artifacts, builds generic indexes, and validates the
result before replacing the checked-in fixture.
