# Raptor 3 Doctrine Pre-Refactor Snapshot

## Purpose

Human-readable reference snapshot of live harness and transcript-edit doctrine surfaces **before** the Raptor 3 subtractive/integrative doctrine refactor.

These files preserve the exact pre-refactor wording for comparison, review, and behavioral regression analysis. They are **not** runtime doctrine and must not be imported or wired into the harness.

**Use git for authoritative restoration; these files are human-readable comparison snapshots.**

## Snapshot metadata

| Field | Value |
|-------|-------|
| Date | 2026-05-26 |
| Git branch | `harness-efficiency-polish-and-sharpening` |
| Git commit | `d674c126a25a485e5a14af27a36ae70b5859eaee` |
| Backup directory | `docs/architecture/harness/doctrine-backups/raptor3-prepass-20260526/` |

## Source → backup mapping

| Source (live runtime) | Backup (reference only) |
|-----------------------|-------------------------|
| `backend/harness/runtime/orchestration/choose_action_instruction.py` | `choose_action_instruction.py.txt` |
| `backend/harness/runtime/prompting/surface.py` | `harness_surface.py.txt` |
| `backend/domains/mapping/transcript_edit/prompting/branch.py` | `transcript_edit_branch.py.txt` |
| `backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py` | `transcript_edit_procedural_guidance.py.txt` |
| `backend/domains/mapping/transcript_edit/prompting/surfaces/startup_context.py` | `transcript_edit_startup_context.py.txt` |
| `backend/domains/mapping/transcript_edit/execution/tool_specs.py` | `transcript_edit_tool_specs.py.txt` |

Backup files use the `.txt` extension so they cannot be imported or executed as Python modules.

## Size verification (snapshot creation)

All copies verified byte-identical (SHA-256 match) to source at snapshot time.

| Source file | Bytes | Lines | Backup file | Bytes | Lines | Match |
|-------------|------:|------:|-------------|------:|------:|-------|
| `choose_action_instruction.py` | 59,066 | 268 | `choose_action_instruction.py.txt` | 59,066 | 268 | yes |
| `surface.py` | 59,005 | 351 | `harness_surface.py.txt` | 59,005 | 351 | yes |
| `branch.py` | 30,842 | 192 | `transcript_edit_branch.py.txt` | 30,842 | 192 | yes |
| `procedural_guidance.py` | 17,681 | 103 | `transcript_edit_procedural_guidance.py.txt` | 17,681 | 103 | yes |
| `startup_context.py` | 5,442 | 115 | `transcript_edit_startup_context.py.txt` | 5,442 | 115 | yes |
| `tool_specs.py` | 27,193 | 421 | `transcript_edit_tool_specs.py.txt` | 27,193 | 421 | yes |

## What this snapshot captures

Pre-refactor doctrine overlap context:

- `choose_action_instruction.py` — action mechanics plus generic method doctrine
- `surface.py` — generic harness operating method
- `branch.py` — transcript-edit domain law plus procedural source-reading workflow
- `procedural_guidance.py` — transcript-edit working rhythm (pre point-crop packet workflow update)
- `startup_context.py` — startup capability awareness (pre point-crop capability wording update)
- `tool_specs.py` — mechanical tool contract including current point-crop mechanics

## Reminder

- Do not treat these backups as live doctrine surfaces.
- Do not copy from backups into runtime paths without an explicit refactor/review decision.
- Prefer git history for mechanical restore; use this directory for side-by-side human review.
