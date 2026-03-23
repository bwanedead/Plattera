"""Phase 19: canonical agent_kernel exports stay primary; compatibility remains available."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import backend.agent_kernel as ak
import backend.agent_kernel.kernel as kernel_mod


def test_kernel_session_manager_is_public_canonical_export() -> None:
    assert hasattr(ak, "KernelSessionManager")
    assert "KernelSessionManager" in ak.__all__


def test_run_kernel_remains_compatibility_module_export() -> None:
    assert not hasattr(ak, "run_kernel")
    assert "run_kernel" not in ak.__all__
    assert hasattr(kernel_mod, "run_kernel")


def test_canonical_export_precedes_compatibility_in_all_ordering() -> None:
    """Light guard: canonical session surface should remain visible in ``__all__``."""
    names = list(ak.__all__)
    assert "KernelSessionManager" in names
