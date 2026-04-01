"""Harness orchestration package.

Keep package imports intentionally minimal so runtime orchestration modules can
depend on observability/read-model modules without circular package init
coupling. Import concrete modules directly, for example:
- ``harness.runtime.orchestration.orchestrator``
- ``harness.runtime.orchestration.mission_orchestrator``
- ``harness.runtime.orchestration.mission_contracts``
"""

__all__: list[str] = []
