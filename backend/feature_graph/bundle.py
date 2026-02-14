"""
Feature Graph Bundle Operation
================================

Implements bundle/freeze operation for portability.
A bundle packages a target graph with its minimal dependency subgraph.

Design principles:
- Minimal dependencies: only include what is directly referenced
- Explicit reasons: record why each dependency was included
- Portable: bundles are self-contained and can be moved/shared
- Deterministic: same input graph always produces same bundle structure
"""

from __future__ import annotations

from typing import Any, List, Dict, Optional, Set, Tuple
from .models import FeatureGraph, FeatureNode, FeatureRef
from .artifacts import BundleArtifact, create_bundle_artifact


class BundleOperation:
    """
    Bundles a target feature graph with its minimal dependency subgraph.

    The bundler performs recursive dependency discovery:
    1. Start with target graph
    2. Find all external FeatureRefs in target graph nodes
    3. For each external ref, include the referenced graph
    4. Recursively process dependencies until closure is reached
    5. Record why each dependency was included (which node/edge referenced it)
    """

    def __init__(self):
        self.visited_graph_ids: Set[str] = set()
        self.dependency_graphs: List[FeatureGraph] = []
        self.dependency_reasons: Dict[str, str] = {}

    def bundle_graph(
        self,
        target_graph: FeatureGraph,
        available_graphs: Optional[Dict[str, FeatureGraph]] = None,
        bundle_id: Optional[str] = None,
        created_by: Optional[str] = None,
        bundle_purpose: Optional[str] = None
    ) -> BundleArtifact:
        """
        Bundle a target graph with its minimal dependency subgraph.

        Args:
            target_graph: The primary feature graph to bundle
            available_graphs: Dict of graph_id -> FeatureGraph for dependency resolution
                             If None, only target graph is bundled (no dependencies)
            bundle_id: Unique ID for this bundle artifact (auto-generated if None)
            created_by: Agent/tool creating this bundle
            bundle_purpose: Why this bundle was created

        Returns:
            BundleArtifact with target graph + minimal dependencies
        """
        # Reset state for this bundling operation
        self.visited_graph_ids.clear()
        self.dependency_graphs.clear()
        self.dependency_reasons.clear()

        # Discover dependencies recursively
        if available_graphs is not None:
            self._discover_dependencies(target_graph, available_graphs)

        # Generate bundle ID if not provided
        if bundle_id is None:
            bundle_id = f"bundle_{target_graph.graph_id}"

        # Create bundle artifact
        return create_bundle_artifact(
            artifact_id=bundle_id,
            target_graph=target_graph,
            dependency_graphs=self.dependency_graphs,
            dependency_reasons=self.dependency_reasons,
            created_by=created_by,
            bundle_purpose=bundle_purpose,
            parent_artifact_ids=[target_graph.graph_id]
        )

    def _discover_dependencies(
        self,
        graph: FeatureGraph,
        available_graphs: Dict[str, FeatureGraph]
    ) -> None:
        """
        Recursively discover and collect dependency graphs.

        Args:
            graph: Current graph to scan for dependencies
            available_graphs: Available graphs for resolution
        """
        # Mark this graph as visited
        self.visited_graph_ids.add(graph.graph_id)

        # Scan all nodes for external FeatureRefs
        for node in graph.nodes:
            if node.feature_ref and node.feature_ref.is_external:
                ref = node.feature_ref
                ref_graph_id = ref.graph_id

                # Skip if already visited
                if ref_graph_id in self.visited_graph_ids:
                    continue

                # Skip if graph not available
                if ref_graph_id not in available_graphs:
                    # Record missing dependency in reasons
                    self.dependency_reasons[ref_graph_id] = (
                        f"Referenced by node '{node.id}' in graph '{graph.graph_id}' "
                        f"but graph not available"
                    )
                    continue

                # Include dependency graph
                dep_graph = available_graphs[ref_graph_id]
                self.dependency_graphs.append(dep_graph)

                # Record reason for inclusion
                reason_parts = [
                    f"Referenced by node '{node.id}'",
                ]
                if node.label:
                    reason_parts.append(f"(label: '{node.label}')")
                reason_parts.append(f"in graph '{graph.graph_id}'")
                if ref.label:
                    reason_parts.append(f"as '{ref.label}'")

                self.dependency_reasons[ref_graph_id] = " ".join(reason_parts)

                # Recursively process this dependency
                self._discover_dependencies(dep_graph, available_graphs)

            # Policy A invariant: external dependencies must be explicit FeatureRef nodes.
            # If we detect external-ref-like payloads inside OpExpr, record a reason so the
            # omission is explicit and testable.
            if node.op_expr:
                op_expr_refs = self._scan_op_expr_for_refs(node.op_expr)
                for ref_graph_id, ref_path in op_expr_refs:
                    self.dependency_reasons[ref_graph_id] = (
                        f"Referenced via {ref_path} in node '{node.id}' in graph "
                        f"'{graph.graph_id}', but ignored by bundle policy. "
                        "Declare external dependencies as node.feature_ref with "
                        "is_external=true."
                    )

    def _scan_op_expr_for_refs(self, op_expr: Any) -> List[Tuple[str, str]]:
        """
        Scan an OpExpr for external-reference-like payloads.

        Bundle Policy A: dependencies are discovered only from explicit FeatureRef nodes.
        This scanner intentionally does not include dependencies, it only surfaces policy
        violations so they are not silently ignored.

        Args:
            op_expr: OpExpr to scan

        Returns:
            List of (ref_graph_id, path) markers that looked like external refs.
        """
        refs: List[Tuple[str, str]] = []

        def walk(value: Any, path: str) -> None:
            if isinstance(value, dict):
                graph_id = value.get("graph_id")
                is_external = value.get("is_external")
                if is_external is True and isinstance(graph_id, str) and graph_id:
                    refs.append((graph_id, path))
                for key, nested in value.items():
                    walk(nested, f"{path}.{key}")
                return

            if isinstance(value, list):
                for idx, nested in enumerate(value):
                    walk(nested, f"{path}[{idx}]")
                return

            if hasattr(value, "model_dump"):
                walk(value.model_dump(mode="python"), path)

        walk(op_expr, "op_expr")
        return refs


# Public API

def bundle_feature_graph(
    target_graph: FeatureGraph,
    available_graphs: Optional[Dict[str, FeatureGraph]] = None,
    bundle_id: Optional[str] = None,
    created_by: Optional[str] = None,
    bundle_purpose: Optional[str] = None
) -> BundleArtifact:
    """
    Bundle a feature graph with its minimal dependency subgraph.

    This is the main entry point for the bundle operation.

    Args:
        target_graph: The primary feature graph to bundle
        available_graphs: Dict of graph_id -> FeatureGraph for dependency resolution
        bundle_id: Unique ID for this bundle (auto-generated if None)
        created_by: Agent/tool creating this bundle
        bundle_purpose: Why this bundle was created

    Returns:
        BundleArtifact containing target + minimal dependencies with reasons

    Example:
        >>> target = FeatureGraph(graph_id="parcel_a", nodes=[...])
        >>> deps = {"section_1": section_graph, "parcel_b": parcel_b_graph}
        >>> bundle = bundle_feature_graph(target, deps, bundle_purpose="Export for review")
        >>> bundle.dependency_reasons
        {'section_1': "Referenced by node 'origin' in graph 'parcel_a' as 'NE Corner Section 1'"}
    """
    bundler = BundleOperation()
    return bundler.bundle_graph(
        target_graph=target_graph,
        available_graphs=available_graphs,
        bundle_id=bundle_id,
        created_by=created_by,
        bundle_purpose=bundle_purpose
    )
