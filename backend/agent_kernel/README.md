# Agent Kernel v0

## What This Is
- Deterministic orchestration loop for request-driven deed-to-map kernel execution.
- Library-first package (`run_kernel`) with a thin JSON CLI wrapper (`python -m backend.agent_kernel.cli`).
- Primary interface is now step-driven via `KernelSessionManager.start_session()` and `KernelSessionManager.step()`.
- `run_kernel` remains as a legacy/autopilot harness for deterministic regression/smoke usage.

## Core Invariants
- Run artifacts store refs, not large blobs (`ArtifactRef` paths and compact inline payloads only).
- Request bootstrap is one-of friendly: runs may start from `initial_ir_ref` or `initial_graph_json`; neither yields `needs_upload`.
- Terminal metadata is split into:
- `terminal_outcome` (external taxonomy: `SUCCESS|PARTIAL|NEEDS_USER_CHOICE|NEEDS_UPLOAD|FAILED`)
- `stop_reason` (internal diagnosis: budget, validation, capability, worker, etc.)
- `SET_GRAPH_REQUIREMENTS` operates on a real IR graph loaded from `initial_ir_ref`; the kernel never fabricates `kernel://` IR refs.
- Global-placement runs can perform semantic retrieval and map stable worker-down codes to `StopReason.WORKER_UNAVAILABLE`.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/agent_kernel -q`
- CLI run: `.venv\scripts\activate.ps1; python -m backend.agent_kernel.cli path/to/request.json`

## Notes
- `KernelGoal` supports `requires_global_placement` and `render_required`.
- Missing both `initial_ir_ref` and `initial_graph_json` is classified as `needs_upload`.
- Prefer `INTERNAL_ERROR` for unexpected exceptions or invariant breaks; keep `ERROR` as legacy compatibility only.
