from __future__ import annotations

from pathlib import Path

import pytest

from .maintenance_controller import (
    ActionKind,
    MaintenanceAction,
    MaintenanceController,
    MaintenanceReport,
    RuntimeIndexIdentity,
)
from ..lanes.semantic.manifest import (
    MANIFEST_SCHEMA_VERSION,
    SemanticIndexManifest,
    write_manifest,
)


def test_diagnose_reports_missing_index(tmp_path: Path, monkeypatch) -> None:
    """When manifest doesn't exist, should recommend BUILD_MISSING."""
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)
    controller = MaintenanceController()

    report = controller.diagnose(pool_identifier="TEST_POOL", dry_run=True)

    assert report.has_actions()
    assert len(report.actions) == 1
    assert report.actions[0].kind == ActionKind.BUILD_MISSING
    assert report.actions[0].pool_identifier == "TEST_POOL"
    assert "missing" in report.actions[0].reason.lower()
    assert report.actions[0].priority == 10


def test_diagnose_dry_run_does_not_mutate(tmp_path: Path, monkeypatch) -> None:
    """Diagnose with dry_run=True should not modify filesystem."""
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)
    controller = MaintenanceController()

    # Get initial state
    manifest_path = controller._get_manifest_path("TEST_POOL")
    existed_before = manifest_path.exists()

    # Run diagnose
    report = controller.diagnose(pool_identifier="TEST_POOL", dry_run=True)

    # Verify no filesystem changes
    existed_after = manifest_path.exists()
    assert existed_before == existed_after


def test_diagnose_includes_metadata() -> None:
    """Diagnose should include metadata about pool and dry_run mode."""
    controller = MaintenanceController()

    report = controller.diagnose(pool_identifier="MY_POOL", dry_run=True)

    assert report.metadata["pool_identifier"] == "MY_POOL"
    assert report.metadata["dry_run"] is True
    assert report.metadata["compaction_threshold"] == 0.3


def test_diagnose_with_existing_manifest(tmp_path: Path, monkeypatch) -> None:
    """When manifest exists, should not recommend BUILD_MISSING."""
    # Patch assets_root to use tmp_path
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)

    manifest = SemanticIndexManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        pool_identifier="TEST_POOL",
        embedding_dim=384,
        embedding_model_id="test-model",
        chunking_policy_id="test-policy",
    )
    write_manifest("TEST_POOL", manifest)

    pool_root = tmp_path / "semantic_indexes" / "TEST_POOL"
    (pool_root / "hnsw.bin").write_text("stub", encoding="utf-8")
    (pool_root / "metadata.db").write_text("stub", encoding="utf-8")

    class StubStore:
        def should_compact(self, threshold: float = 0.3) -> bool:
            return False

    monkeypatch.setattr(
        "retrieval.engine.maintenance_controller.load_persistent_store",
        lambda **kwargs: StubStore(),
    )

    controller = MaintenanceController()
    report = controller.diagnose(pool_identifier="TEST_POOL", dry_run=True)

    # Should not have BUILD_MISSING action
    build_actions = [a for a in report.actions if a.kind == ActionKind.BUILD_MISSING]
    assert len(build_actions) == 0


def test_execute_actions_dry_run_does_not_execute() -> None:
    """Execute with dry_run=True should log but not run actions."""
    controller = MaintenanceController()

    actions = [
        MaintenanceAction(
            kind=ActionKind.BUILD_MISSING,
            pool_identifier="TEST",
            reason="test",
            priority=1,
        )
    ]

    result = controller.execute_actions(actions, dry_run=True)

    assert result["dry_run"] is True
    assert result["actions_attempted"] == 1
    assert result["details"][0]["status"] == "dry_run_skip"


def test_execute_actions_reports_success_count() -> None:
    """Execute should count succeeded and failed actions."""
    class CompactingController(MaintenanceController):
        def _compact_index(self, pool_identifier: str) -> dict:
            return {"tombstones_removed": 5}

    controller = CompactingController()

    actions = [
        MaintenanceAction(ActionKind.BUILD_MISSING, "POOL1", "reason1"),
        MaintenanceAction(ActionKind.REBUILD_STALE, "POOL2", "reason2"),
        MaintenanceAction(ActionKind.COMPACT, "POOL3", "reason3"),
    ]

    result = controller.execute_actions(actions, dry_run=False)

    assert result["dry_run"] is False
    assert result["actions_attempted"] == 3
    assert result["actions_succeeded"] == 1
    assert result["actions_failed"] == 0
    assert result["actions_not_executed"] == 2
    assert "execution_unimplemented:build_missing" in result["warnings"]
    assert "execution_unimplemented:rebuild_stale" in result["warnings"]


def test_execute_actions_handles_failures() -> None:
    """Execute should catch and report failures."""

    class FailingController(MaintenanceController):
        def _compact_index(self, pool_identifier: str) -> dict:
            raise ValueError("Simulated compact failure")

    controller = FailingController()

    actions = [
        MaintenanceAction(ActionKind.COMPACT, "POOL1", "reason"),
    ]

    result = controller.execute_actions(actions, dry_run=False)

    assert result["actions_succeeded"] == 0
    assert result["actions_failed"] == 1
    assert result["details"][0]["status"] == "failed"
    assert "Simulated compact failure" in result["details"][0]["error"]


def test_execute_actions_includes_details() -> None:
    """Execute should include details for each action."""
    controller = MaintenanceController()

    actions = [
        MaintenanceAction(ActionKind.BUILD_MISSING, "POOL1", "missing"),
        MaintenanceAction(ActionKind.COMPACT, "POOL2", "fragmented"),
    ]

    result = controller.execute_actions(actions, dry_run=True)

    assert len(result["details"]) == 2
    assert result["details"][0]["action"] == "build_missing"
    assert result["details"][0]["pool"] == "POOL1"
    assert result["details"][1]["action"] == "compact"
    assert result["details"][1]["pool"] == "POOL2"


def test_maintenance_report_has_actions() -> None:
    """MaintenanceReport.has_actions() should reflect action count."""
    report = MaintenanceReport()
    assert not report.has_actions()

    report.actions.append(MaintenanceAction(ActionKind.BUILD_MISSING, "POOL", "reason"))
    assert report.has_actions()


def test_action_kinds_are_deterministic() -> None:
    """Action kinds should have stable string values."""
    assert ActionKind.BUILD_MISSING.value == "build_missing"
    assert ActionKind.REBUILD_STALE.value == "rebuild_stale"
    assert ActionKind.COMPACT.value == "compact"


def test_diagnose_handles_corrupt_manifest(tmp_path: Path, monkeypatch) -> None:
    """When manifest is corrupt JSON, should add warning."""
    manifest_dir = tmp_path / "semantic_indexes" / "TEST_POOL"
    manifest_dir.mkdir(parents=True)
    manifest_path = manifest_dir / "manifest.json"

    # Write corrupt JSON
    with open(manifest_path, "w") as f:
        f.write("{ corrupt json")

    (manifest_dir / "hnsw.bin").write_text("stub", encoding="utf-8")
    (manifest_dir / "metadata.db").write_text("stub", encoding="utf-8")

    # Patch assets_root
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)

    controller = MaintenanceController()
    report = controller.diagnose(pool_identifier="TEST_POOL", dry_run=True)

    assert len(report.warnings) > 0
    assert any("manifest_unavailable" in w for w in report.warnings)


def test_diagnose_staleness_mismatch_adds_action(tmp_path: Path, monkeypatch) -> None:
    """Manifest mismatch should yield REBUILD_STALE action."""
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)

    manifest = SemanticIndexManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        pool_identifier="TEST_POOL",
        embedding_dim=384,
        embedding_model_id="model_a",
        chunking_policy_id="policy_a",
        embedding_model_fingerprint=None,
    )
    write_manifest("TEST_POOL", manifest)

    pool_root = tmp_path / "semantic_indexes" / "TEST_POOL"
    (pool_root / "hnsw.bin").write_text("stub", encoding="utf-8")
    (pool_root / "metadata.db").write_text("stub", encoding="utf-8")

    class StubStore:
        def should_compact(self, threshold: float = 0.3) -> bool:
            return False

    monkeypatch.setattr(
        "retrieval.engine.maintenance_controller.load_persistent_store",
        lambda **kwargs: StubStore(),
    )

    runtime_identity = RuntimeIndexIdentity(
        embedding_dim=384,
        embedding_model_id="model_b",
        chunking_policy_id="policy_a",
    )

    controller = MaintenanceController()
    report = controller.diagnose(pool_identifier="TEST_POOL", runtime_identity=runtime_identity, dry_run=True)

    assert any(a.kind == ActionKind.REBUILD_STALE for a in report.actions)


def test_diagnose_compaction_recommended(tmp_path: Path, monkeypatch) -> None:
    """Compaction should be recommended when should_compact returns True."""
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)

    manifest = SemanticIndexManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        pool_identifier="TEST_POOL",
        embedding_dim=384,
        embedding_model_id="model_a",
        chunking_policy_id="policy_a",
    )
    write_manifest("TEST_POOL", manifest)

    pool_root = tmp_path / "semantic_indexes" / "TEST_POOL"
    (pool_root / "hnsw.bin").write_text("stub", encoding="utf-8")
    (pool_root / "metadata.db").write_text("stub", encoding="utf-8")

    class StubStore:
        def should_compact(self, threshold: float = 0.3) -> bool:
            return True

        def get_stats(self) -> dict:
            return {"tombstone_ratio": 0.5}

    monkeypatch.setattr(
        "retrieval.engine.maintenance_controller.load_persistent_store",
        lambda **kwargs: StubStore(),
    )

    controller = MaintenanceController()
    report = controller.diagnose(pool_identifier="TEST_POOL", runtime_identity=None, dry_run=True)

    assert any(a.kind == ActionKind.COMPACT for a in report.actions)
    assert any("tombstone_ratio" in a.reason for a in report.actions if a.kind == ActionKind.COMPACT)


def test_diagnose_warns_when_staleness_unimplemented(tmp_path: Path, monkeypatch) -> None:
    """Missing runtime identity should add staleness_check_unimplemented warning."""
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)

    manifest = SemanticIndexManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        pool_identifier="TEST_POOL",
        embedding_dim=384,
        embedding_model_id="model_a",
        chunking_policy_id="policy_a",
    )
    write_manifest("TEST_POOL", manifest)

    pool_root = tmp_path / "semantic_indexes" / "TEST_POOL"
    (pool_root / "hnsw.bin").write_text("stub", encoding="utf-8")
    (pool_root / "metadata.db").write_text("stub", encoding="utf-8")

    monkeypatch.setattr(
        "retrieval.engine.maintenance_controller.load_persistent_store",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("nope")),
    )

    controller = MaintenanceController()
    report = controller.diagnose(pool_identifier="TEST_POOL", runtime_identity=None, dry_run=True)

    assert "staleness_check_unimplemented" in report.warnings
    assert any(w.startswith("compaction_check_unavailable") for w in report.warnings)


def test_controller_never_called_from_search() -> None:
    """
    Verify controller is not imported or called from retrieval_engine.search().

    This is a contract test - maintenance must remain explicit.
    """
    # Read retrieval_engine.py to verify no maintenance imports
    engine_path = Path(__file__).parent / "retrieval_engine.py"
    if engine_path.exists():
        with open(engine_path, "r") as f:
            content = f.read()
            assert "maintenance_controller" not in content.lower()
            assert "MaintenanceController" not in content


def test_action_priority_ordering() -> None:
    """Actions should be prioritizable for execution order."""
    high = MaintenanceAction(ActionKind.BUILD_MISSING, "P1", "urgent", priority=10)
    low = MaintenanceAction(ActionKind.COMPACT, "P2", "not urgent", priority=1)

    actions = [low, high]
    sorted_actions = sorted(actions, key=lambda a: a.priority, reverse=True)

    assert sorted_actions[0].kind == ActionKind.BUILD_MISSING
    assert sorted_actions[1].kind == ActionKind.COMPACT
