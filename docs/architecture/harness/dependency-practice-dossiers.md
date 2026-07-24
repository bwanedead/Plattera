# Dependency Practice Dossiers (T0 Fixture Packets)

This document describes the **immutable local T0 practice packets** for multi-segment
(dependency-chain) deed work. It establishes **test inputs only**.

It does **not** implement multi-page transcript editing, dependency discovery,
dependency linking, scheduling, or deed-to-IR changes.

---

## 1. Product model

Hierarchy:

```
One deed
└── One dossier
    ├── Segment/page 1 → T0 transcription runs/drafts
    ├── Segment/page 2 → T0 transcription runs/drafts
    └── ...
```

Cross-deed relationships remain separate:

```
Child deed dossier ──dependency pointer──> Parent deed dossier
```

A dossier is already the deed boundary. Do **not** search for a boundary between
different deeds inside one dossier. Continuity represented by these fixtures is
**across pages/segments of the same deed only**.

---

## 2. Canonical fixture coordinates

Packets live under (local, ignored practice data):

`practice_deeds/dependency_chain/`

| Fixture ID | Dossier ID | Segment order (transcription IDs) |
|---|---|---|
| `curve_station_chain` | `892abc34-ed4d-4e85-a0cb-9a5ddc133f31` | `draft_curve_deed_part1`, `draft_curve_deed_part2` |
| `new_deed` | `64b66561-6c0a-4702-a6b6-b8b5c076d891` | `draft_newdeedleft`, `draft_newdeedright` |

Source SHA-256 (inputs to freeze validation):

| Segment | SHA-256 |
|---|---|
| Curve part 1 | `2d6deec12e52e1ca65caaf52a2da36d9aaa2ab09c548f1d531c876f51a9e11f9` |
| Curve part 2 | `9e6fe2a6921d34922e641c2754f4ce5dd6950e0225e71893f2a2ec87f8e64e6b` |
| New deed left | `f80337db9fc9c496692be36ecb3d0a3beb16d6da4fd4d0ca62ab4a7bf41aa462` |
| New deed right | `3f0652d41f8993d22bc270bd4ba06bca1688bec67f138844b966979baf56da67` |

Do **not** use dossier `14f31a30-4f84-430c-93b4-fc1984e653ac` (older mismatched
curve-deed attempt).

`fixture_set_manifest.json` lists the two fixture manifests. It does **not**
assert that one deed depends on the other. Cross-dossier dependency linking is
intentionally outside this brief and belongs to later **agent-authored** work.

---

## 3. What is frozen

Allowlisted post-T0 baseline only:

- source image for each segment
- T0 `run.json`
- T0 `head.json` when it actually exists (never synthesized)
- JSON files under that transcription’s T0 `raw/` directory

Excluded (must not contaminate the packet):

- consensus / alignment results
- transcript-edit workspaces
- final registries / dossier-final outputs
- deed-to-IR outputs
- live-run histories
- dependency decisions
- any later-phase results outside the T0 baseline

Each fixture represents **one deed with multiple pages**.

---

## 4. Operational rules for future work

- **Do not rerun T0** for these fixtures.
- **Do not use init-run** to recreate their associations.
- Future transcript-edit / deed-to-IR runs should create **unique workspace
  coordinates** while reusing this immutable T0 baseline.
- Do **not** clean up old dossier clutter as part of consuming these packets.
- Do **not** treat this doc as a launch checklist for a live test.

Freeze tooling (generic; no hardcoded curve/new-deed IDs in the core module):

- Module: `backend/harness/fixtures/dossier_t0_fixture.py` (public freeze orchestration)
- Manifest/integrity: `backend/harness/fixtures/dossier_t0_fixture_manifest.py`
- CLI: `python -m harness.cli.freeze_dossier_t0_fixture` (from `backend/`)

Freezing into a nonexistent destination creates the packet. Freezing the same
validated inputs again is an **idempotent replay** (validate only; no rewrite).
Conflicts refuse with `dossier_t0_fixture_conflict`. There is no `--force`.

---

## 5. Related

- Practice folder notes: `practice_deeds/agents.md`
- Ignore policy: `practice_deeds/*` remains local (same pattern as other practice
  packets; do not change ignore rules merely to commit source images or T0 data)
