# Doctrine Surface Backup — 2026-05-18 Pre-Prune

This folder is a verbatim backup of the doctrine/prompt surfaces before the efficiency-pruning pass on branch `harness-efficiency-polish-and-sharpening`.

Source commit at snapshot time: `cd3f386` (`enforce transcript edit output handoff`).

## Files

- `harness_runtime_prompting_surface.py` ← `backend/harness/runtime/prompting/surface.py`
- `harness_runtime_orchestration_choose_action_instruction.py` ← `backend/harness/runtime/orchestration/choose_action_instruction.py`
- `domains_mapping_prompting_family_branch.py` ← `backend/domains/mapping/prompting/family_branch.py`
- `domains_mapping_transcript_edit_prompting_branch.py` ← `backend/domains/mapping/transcript_edit/prompting/branch.py`
- `domains_mapping_transcript_edit_prompting_surfaces_procedural_guidance.py` ← `backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py`
- `domains_mapping_transcript_edit_execution_tool_specs.py` ← `backend/domains/mapping/transcript_edit/execution/tool_specs.py`

## Purpose

Use this only as a recovery/reference snapshot while editing live doctrine. Do not import from these files or treat them as active runtime surfaces.
