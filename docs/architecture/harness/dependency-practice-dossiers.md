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

Source review status:

- `curve_station_chain` is a coherent two-segment instrument and is the
  approved first dossier-scale transcript-edit test. Its first segment ends
  mid-description and the second segment continues it.
- `new_deed` contains valid transcript source for two instruments. Its left
  page and the top of its right page finish a town-lot deed; the lower right
  page begins a Lake Hattie right-of-way deed and cuts off. All visible text is
  usable. A live dossier-scale test waits only on logical instrument-span setup
  so the two deeds can publish separately without duplicating or dropping the
  shared physical page.

Semantic inventory:

| Source packet | Physical pages | Legal meaning represented |
|---|---:|---|
| `curve_station_chain` | 2 | A Lake Hattie irrigation-system property description: a 200-foot canal strip through Section 36, T14N R77W, followed across the page boundary by station/headworks/dam and additional canal-strip descriptions. It is a likely reference/base alignment candidate, but the packet begins and ends as an excerpt. |
| `new_deed` — town-lot instrument | 1 full page + top of shared page | Conveyance of Lot 775, Block 22, Town of Wyoming, with warranties, existing-easement exceptions, corporate execution, and notarial acknowledgment. This appears unrelated to the canal dependency chain. |
| `new_deed` — Lake Hattie instrument | bottom of shared page | A separate deed from George H. Nutting and wife to the Lake Hattie Reservoir & Irrigation Company for a 100-foot strip, fifty feet on each side of a middle line. The available source cuts off before the middle-line description continues. It is processable as partial source, but the visible excerpt alone does not establish the expected station-chain dependency. |

Local `deed_dump` audit:

- `curve_deed_part1.jpg`, `curve_deed_part2.jpg`, `newdeedleft.png`,
  `newdeedright.png`, and `legal_text_image.jpg` are byte-identical to the
  existing practice sources.
- `curve_deed_full.jpg` is also already present in `practice_deeds/`; it is the
  combined pages 498–499 spread represented by the two curve page images. It
  supplies wider visual context, but not the missing continuation of the new
  Lake Hattie deed.
- The stored curve T0 drafts cover the highlighted canal descriptions but omit
  substantial unhighlighted page context. That context includes references to
  Lake Hattie/Pioneer Canal interests acquired under separately recorded
  Pioneer Canal Company lease instruments. A full-instrument test must account
  for that T0 incompleteness rather than treating the existing drafts as full
  page transcriptions.
- The only newly supplied instrument is a 1937 William I. and Ellen Jensen to
  Pioneer Canal Company quit-claim text pair. It is a self-contained canal
  strip description with raw/edited geometry disagreements and no supplied
  source image. It does not show a dependency on the Lake Hattie station chain.

Dependency conclusion:

- `curve_station_chain` contains a real external-dependency signal: the source
  refers to separately recorded Pioneer Canal Company lease instruments that
  are not present in the current corpus. It can therefore test honest
  dependency discovery and unmatched/pending behavior.
- The partial George H. Nutting Lake Hattie deed remains the likely dependent
  instrument, but its available page stops before the middle-line language
  that would prove or identify the dependency.
- No file currently in `deed_dump` supplies either the referenced Pioneer Canal
  lease or the continuation of the George H. Nutting deed. Successful
  dependency matching cannot yet be proven with two authentic in-corpus deeds.
  The real curve instrument should cover the unmatched path; a clearly labeled
  synthetic instrument may later reproduce the referenced identity to exercise
  successful matching without falsifying the authentic corpus.

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

The frozen packet faithfully preserves historical source/T0 state; it does not
certify that physical page grouping equals legal-instrument grouping.
`curve_station_chain` is immediately usable as a canonical one-instrument,
multi-segment test. `new_deed` becomes equally usable once the shared page is
represented by two non-overlapping logical instrument spans.

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
