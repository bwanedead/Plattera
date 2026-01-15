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

from config.paths import assets_root


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


@dataclass
class MaintenanceController:
    """
    Controller for retrieval system maintenance.

    Orchestrates index build/rebuild/compact operations explicitly,
    never invoked from query paths.
    """

    def diagnose(self, *, pool_identifier: str = "FINAL_SEGMENTS", dry_run: bool = True) -> MaintenanceReport:
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

        # Check if index exists
        manifest_path = self._get_manifest_path(pool_identifier)
        if not manifest_path.exists():
            report.actions.append(
                MaintenanceAction(
                    kind=ActionKind.BUILD_MISSING,
                    pool_identifier=pool_identifier,
                    reason=f"Index manifest not found at {manifest_path}",
                    priority=10,
                )
            )
            return report

        # Check if index is stale (placeholder logic - could check manifest timestamps, model versions, etc.)
        # For now, we just check existence
        manifest_data = self._load_manifest(manifest_path)
        if manifest_data is None:
            report.warnings.append(f"Failed to load manifest from {manifest_path}")
            return report

        # Check for stale indicators (model changes, policy changes, etc.)
        if self._is_stale(manifest_data):
            report.actions.append(
                MaintenanceAction(
                    kind=ActionKind.REBUILD_STALE,
                    pool_identifier=pool_identifier,
                    reason="Index configuration mismatch or outdated",
                    priority=5,
                )
            )

        # Check if compaction is needed (placeholder logic)
        if self._needs_compaction(manifest_data):
            report.actions.append(
                MaintenanceAction(
                    kind=ActionKind.COMPACT,
                    pool_identifier=pool_identifier,
                    reason="Index fragmentation detected",
                    priority=2,
                )
            )

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
            "details": [],
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

            # Execute action (placeholder - would call actual build/rebuild/compact)
            try:
                if action.kind == ActionKind.BUILD_MISSING:
                    self._build_index(action.pool_identifier)
                elif action.kind == ActionKind.REBUILD_STALE:
                    self._rebuild_index(action.pool_identifier)
                elif action.kind == ActionKind.COMPACT:
                    self._compact_index(action.pool_identifier)

                report["actions_succeeded"] += 1
                report["details"].append(
                    {
                        "action": action.kind.value,
                        "pool": action.pool_identifier,
                        "status": "success",
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
        return assets_root() / "semantic_indexes" / pool_identifier / "manifest.json"

    def _load_manifest(self, path: Path) -> Optional[dict]:
        """Load manifest JSON from path."""
        try:
            import json

            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _is_stale(self, manifest_data: dict) -> bool:
        """Check if manifest indicates stale index (placeholder)."""
        # Real implementation would check:
        # - embedding_model_id vs current model
        # - chunking_policy_id vs current policy
        # - schema_version vs current version
        return False

    def _needs_compaction(self, manifest_data: dict) -> bool:
        """Check if index needs compaction (placeholder)."""
        # Real implementation would check vector store fragmentation
        return False

    def _build_index(self, pool_identifier: str) -> None:
        """Build index from scratch (placeholder)."""
        # Real implementation would use SemanticIndexBuilder
        pass

    def _rebuild_index(self, pool_identifier: str) -> None:
        """Rebuild existing index (placeholder)."""
        # Real implementation would use SemanticIndexBuilder.rebuild_slice
        pass

    def _compact_index(self, pool_identifier: str) -> None:
        """Compact index (placeholder)."""
        # Real implementation would use PersistentVectorStore compaction
        pass
