"""Phase 19: canonical agent_kernel exports stay primary; compatibility remains available."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import backend.agent_kernel as ak


def test_kernel_session_manager_is_public_canonical_export() -> None:
    assert hasattr(ak, "KernelSessionManager")
    assert "KernelSessionManager" in ak.__all__


def test_run_kernel_remains_compatibility_export() -> None:
    assert hasattr(ak, "run_kernel")
    assert "run_kernel" in ak.__all__


def test_canonical_export_precedes_compatibility_in_all_ordering() -> None:
    """Light guard: ``KernelSessionManager`` should appear before ``run_kernel`` in ``__all__``."""
    names = list(ak.__all__)
    if "KernelSessionManager" in names and "run_kernel" in names:
        assert names.index("KernelSessionManager") < names.index("run_kernel")
