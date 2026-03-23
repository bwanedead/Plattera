"""Compatibility shim for legacy imports of the feature-graph policy."""

from __future__ import annotations

from backend.feature_graph.kernel_policy import FeatureGraphDeedToMapPolicyV0

from .generic import KernelPolicy

__all__ = ["KernelPolicy", "FeatureGraphDeedToMapPolicyV0"]
