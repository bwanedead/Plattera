"""Phase 43: shared package facade stays canonical-first."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import backend.agent_kernel as kernel_pkg
import backend.agent_kernel.kernel as kernel_mod


def test_agent_kernel_facade_exposes_core_canonical_surface() -> None:
    assert kernel_pkg.KernelSessionManager is not None
    assert kernel_pkg.KernelPolicy is not None
    assert kernel_pkg.KernelState is not None
    assert kernel_mod.run_kernel is not None


def test_agent_kernel_facade_does_not_reexport_product_tooling_aliases() -> None:
    assert not hasattr(kernel_pkg, "CorpusDeedHydrator")
    assert not hasattr(kernel_pkg, "DraftIRFilesystemProposer")
    assert not hasattr(kernel_pkg, "FeatureGraphBundlerTool")
    assert not hasattr(kernel_pkg, "FeatureGraphCompilerTool")
    assert not hasattr(kernel_pkg, "FeatureGraphJudgeTool")
    assert not hasattr(kernel_pkg, "RetrievalEvidenceTool")
    assert not hasattr(kernel_pkg, "run_kernel")
    assert not hasattr(kernel_pkg, "DefaultKernelPolicy")
