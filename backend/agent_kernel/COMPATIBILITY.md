# Agent Kernel — compatibility surface classification

Phase 18–19: **canonical vs compatibility** must stay obvious so new work does not accidentally build on JSON loop seams. Phase 19 adds tests and tightens package-level import guidance (`KernelSessionManager` from `agent_kernel`); compatibility exports stay available and non-primary.

This document records **explicit** classification so legacy code is not deleted by mistake.

| Surface | Class | Rationale |
|--------|--------|-----------|
| `kernel.run_kernel` | **Active compatibility** | Exported from `__init__.py`, used by `cli.py`, README documents legacy/autopilot regression usage. **Not vestigial.** |
| `python -m backend.agent_kernel.cli` | **Active compatibility** | Low-level JSON-in/JSON-out debug CLI; not the canonical mission runtime. |
| `KernelSessionManager` | **Active canonical** | Preferred step-driven harness integration. |

**Rule:** Remove a legacy surface only when this file and `README.md` are updated **and** callers/tests are migrated intentionally.

**Import guidance:** Prefer `from backend.agent_kernel import KernelSessionManager, ...` for session/step APIs. Treat `run_kernel` as a labeled compatibility export (see `kernel.py` module docstring).
