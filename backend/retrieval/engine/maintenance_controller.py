from __future__ import annotations

"""
Retrieval Maintenance Controller
=================================

Explicit orchestration for index maintenance actions (build, rebuild, compact).

Design principles:
- Never called from RetrievalEngine.search() (query paths must remain fast)
- Explicit dry_run mode for safety (reports actions without executing)
- Uses existing primitives (SemanticIndexBuilder, etc.)
- Deterministic decision outputs for testing

Usage:
    controller = MaintenanceController()
    report = controller.diagnose(dry_run=True)
    # Review report.actions
    controller.execute_actions(report.actions, dry_run=False)
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from ..lanes.semantic.manifest import (
    SemanticIndexManifest,
    hnsw_index_path,
    manifest_path,
    metadata_db_path,
    read_manifest,
)
from ..lanes.semantic.persistent_store import load_persistent_store


class ActionKind(str, Enum):
    """Types of maintenance actions."""

    BUILD_MISSING = "build_missing"
    REBUILD_STALE = "rebuild_stale"
    COMPACT = "compact"


@dataclass
class MaintenanceAction:
    """A single maintenance action recommendation."""

    kind: ActionKind
    pool_identifier: str
    reason: str
    priority: int = 0  # Higher is more urgent


@dataclass
class MaintenanceReport:
    """Report of maintenance diagnosis and actions."""

    actions: List[MaintenanceAction] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def has_actions(self) -> bool:
        """Returns True if there are any actions to take."""
        return len(self.actions) > 0


@dataclass(frozen=True)
class RuntimeIndexIdentity:
    """Runtime identity for comparing against a persisted manifest."""

    embedding_dim: int
    embedding_model_id: Optional[str]
    chunking_policy_id: Optional[str]
    embedding_model_fingerprint: Optional[str] = None

    def is_complete(self) -> bool:
        return self.embedding_model_id is not None and self.chunking_policy_id is not None


@dataclass
class MaintenanceController:
    """
    Controller for retrieval system maintenance.

    Orchestrates index build/rebuild/compact operations explicitly,
    never invoked from query paths.
    """

    def diagnose(
        self,
        *,
        pool_identifier: str = "FINAL_SEGMENTS",
        runtime_identity: Optional[RuntimeIndexIdentity] = None,
        compaction_threshold: float = 0.3,
        dry_run: bool = True,
    ) -> MaintenanceReport:
        """
        Diagnose maintenance needs for a given pool.

        Args:
            pool_identifier: Which corpus pool to check (default: FINAL_SEGMENTS)
            dry_run: If True, only report actions without executing

        Returns:
            MaintenanceReport with recommended actions
        """
        report = MaintenanceReport()
        report.metadata["pool_identifier"] = pool_identifier
        report.metadata["dry_run"] = dry_run
        report.metadata["compaction_threshold"] = compaction_threshold

        manifest_file = manifest_path(pool_identifier)
        hnsw_path = hnsw_index_path(pool_identifier)
        metadata_path = metadata_db_path(pool_identifier)

        missing_files = [
            name
            for name, path in (
                ("manifest.json", manifest_file),
                ("hnsw.bin", hnsw_path),
                ("metadata.db", metadata_path),
            )
            if not path.exists()
        ]
        if missing_files:
            report.actions.append(
                MaintenanceAction(
                    kind=ActionKind.BUILD_MISSING,
                    pool_identifier=pool_identifier,
                    reason=f"Index files missing: {', '.join(missing_files)}",
                    priority=10,
                )
            )
            return report

        manifest = read_manifest(pool_identifier)
        if manifest is None:
            report.warnings.append(f"manifest_unavailable:{manifest_file}")
            return report

        if runtime_identity is None or not runtime_identity.is_complete():
            report.warnings.append("staleness_check_unimplemented")
        else:
            stale_reason = self._check_manifest_mismatch(manifest, runtime_identity)
            if stale_reason is not None:
                report.actions.append(
                    MaintenanceAction(
                        kind=ActionKind.REBUILD_STALE,
                        pool_identifier=pool_identifier,
                        reason=stale_reason,
                        priority=5,
                    )
                )

        try:
            store = load_persistent_store(
                pool_identifier=pool_identifier,
                embedding_dim=manifest.embedding_dim,
                hnsw_path=hnsw_path,
                metadata_db_path=metadata_path,
            )
            if store.should_compact(threshold=compaction_threshold):
                stats = store.get_stats()
                report.actions.append(
                    MaintenanceAction(
                        kind=ActionKind.COMPACT,
                        pool_identifier=pool_identifier,
                        reason=f"tombstone_ratio={stats['tombstone_ratio']:.2f}",
                        priority=2,
                    )
                )
        except Exception as exc:
            report.warnings.append(f"compaction_check_unavailable:{type(exc).__name__}")

        return report

    def execute_actions(
        self, actions: List[MaintenanceAction], *, dry_run: bool = False
    ) -> dict:
        """
        Execute maintenance actions.

        Args:
            actions: List of actions to execute
            dry_run: If True, log actions but don't execute

        Returns:
            Execution report with results per action
        """
        report = {
            "dry_run": dry_run,
            "actions_attempted": len(actions),
            "actions_succeeded": 0,
            "actions_failed": 0,
            "actions_not_executed": 0,
            "details": [],
            "warnings": [],
        }

        for action in actions:
            if dry_run:
                report["details"].append(
                    {
                        "action": action.kind.value,
                        "pool": action.pool_identifier,
                        "status": "dry_run_skip",
                        "reason": action.reason,
                    }
                )
                continue

            try:
                if action.kind in (ActionKind.BUILD_MISSING, ActionKind.REBUILD_STALE):
                    report["actions_not_executed"] += 1
                    report["warnings"].append(f"execution_unimplemented:{action.kind.value}")
                    report["details"].append(
                        {
                            "action": action.kind.value,
                            "pool": action.pool_identifier,
                            "status": "not_executed_missing_inventory",
                            "reason": action.reason,
                        }
                    )
                    continue

                if action.kind == ActionKind.COMPACT:
                    compact_stats = self._compact_index(action.pool_identifier)

                report["actions_succeeded"] += 1
                report["details"].append(
                    {
                        "action": action.kind.value,
                        "pool": action.pool_identifier,
                        "status": "success",
                        "stats": compact_stats if action.kind == ActionKind.COMPACT else None,
                    }
                )
            except Exception as e:
                report["actions_failed"] += 1
                report["details"].append(
                    {
                        "action": action.kind.value,
                        "pool": action.pool_identifier,
                        "status": "failed",
                        "error": str(e),
                    }
                )

        return report

    # --- Internal helpers ---

    def _get_manifest_path(self, pool_identifier: str) -> Path:
        """Get path to index manifest for a pool."""
        return manifest_path(pool_identifier)

    def _check_manifest_mismatch(
        self, manifest: SemanticIndexManifest, runtime_identity: RuntimeIndexIdentity
    ) -> Optional[str]:
        """Check runtime identity against manifest for staleness."""
        if manifest.embedding_dim != runtime_identity.embedding_dim:
            return (
                f"embedding_dim_mismatch: manifest={manifest.embedding_dim}, "
                f"runtime={runtime_identity.embedding_dim}"
            )

        if manifest.embedding_model_fingerprint and runtime_identity.embedding_model_fingerprint:
            if manifest.embedding_model_fingerprint != runtime_identity.embedding_model_fingerprint:
                return (
                    "embedding_model_fingerprint_mismatch: "
                    f"manifest={manifest.embedding_model_fingerprint}, "
                    f"runtime={runtime_identity.embedding_model_fingerprint}"
                )
        elif runtime_identity.embedding_model_id is not None:
            if manifest.embedding_model_id != runtime_identity.embedding_model_id:
                return (
                    "embedding_model_mismatch: "
                    f"manifest={manifest.embedding_model_id}, "
                    f"runtime={runtime_identity.embedding_model_id}"
                )

        if runtime_identity.chunking_policy_id is not None:
            if manifest.chunking_policy_id != runtime_identity.chunking_policy_id:
                return (
                    "chunking_policy_mismatch: "
                    f"manifest={manifest.chunking_policy_id}, "
                    f"runtime={runtime_identity.chunking_policy_id}"
                )

        return None

    def _build_index(self, pool_identifier: str) -> None:
        """Build index from scratch (placeholder)."""
        # Real implementation would use SemanticIndexBuilder
        pass

    def _rebuild_index(self, pool_identifier: str) -> None:
        """Rebuild existing index (placeholder)."""
        # Real implementation would use SemanticIndexBuilder.rebuild_slice
        pass

    def _compact_index(self, pool_identifier: str) -> dict:
        """Compact index using PersistentVectorStore."""
        manifest = read_manifest(pool_identifier)
        if manifest is None:
            raise RuntimeError("Manifest unavailable for compaction")

        hnsw_path = hnsw_index_path(pool_identifier)
        metadata_path = metadata_db_path(pool_identifier)

        store = load_persistent_store(
            pool_identifier=pool_identifier,
            embedding_dim=manifest.embedding_dim,
            hnsw_path=hnsw_path,
            metadata_db_path=metadata_path,
        )
        return store.compact()
