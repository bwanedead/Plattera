"""Tests for read-only dossier segment topology."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from services.dossier.segment_topology import (
    DossierSegmentTopologyError,
    TopologyRunInput,
    TopologySegmentInput,
    build_dossier_segment_topology,
    load_dossier_segment_topology,
)


def _seg(
    segment_id: str,
    position: int,
    *transcription_ids: str,
) -> TopologySegmentInput:
    runs = tuple(
        TopologyRunInput(transcription_id=tid, position=i)
        for i, tid in enumerate(transcription_ids)
    )
    return TopologySegmentInput(segment_id=segment_id, position=position, runs=runs)


def test_one_segment_one_run() -> None:
    topo = build_dossier_segment_topology(
        dossier_id="d1",
        segments=[_seg("seg_a", 0, "tx_a")],
        association_positions={"tx_a": 1},
    )
    assert len(topo.segments) == 1
    assert topo.segments[0].runs[0].transcription_id == "tx_a"
    assert topo.segments[0].runs[0].association_present is True
    assert topo.diagnostics == ()


def test_two_ordered_segments() -> None:
    topo = build_dossier_segment_topology(
        dossier_id="d1",
        segments=[_seg("seg_b", 1, "tx_b"), _seg("seg_a", 0, "tx_a")],
        association_positions={"tx_a": 1, "tx_b": 2},
    )
    assert [s.segment_id for s in topo.segments] == ["seg_a", "seg_b"]
    assert [s.position for s in topo.segments] == [0, 1]


def test_one_segment_multiple_runs_all_retained() -> None:
    topo = build_dossier_segment_topology(
        dossier_id="d1",
        segments=[_seg("seg_a", 0, "tx_a", "tx_b", "tx_c")],
        association_positions={"tx_a": 1, "tx_b": 2, "tx_c": 3},
    )
    assert [r.transcription_id for r in topo.segments[0].runs] == ["tx_a", "tx_b", "tx_c"]


def test_fifteen_ordered_segments() -> None:
    segments = [_seg(f"seg_{i}", i, f"tx_{i}") for i in range(15)]
    assoc = {f"tx_{i}": i + 1 for i in range(15)}
    topo = build_dossier_segment_topology(
        dossier_id="d1",
        segments=segments,
        association_positions=assoc,
    )
    assert len(topo.segments) == 15
    assert [s.segment_id for s in topo.segments] == [f"seg_{i}" for i in range(15)]


def test_duplicate_segment_id_refused() -> None:
    with pytest.raises(DossierSegmentTopologyError) as exc:
        build_dossier_segment_topology(
            dossier_id="d1",
            segments=[_seg("seg_a", 0, "tx_a"), _seg("seg_a", 1, "tx_b")],
            association_positions={"tx_a": 1, "tx_b": 2},
        )
    assert exc.value.code == "duplicate_segment_id"


def test_duplicate_segment_position_refused() -> None:
    with pytest.raises(DossierSegmentTopologyError) as exc:
        build_dossier_segment_topology(
            dossier_id="d1",
            segments=[_seg("seg_a", 0, "tx_a"), _seg("seg_b", 0, "tx_b")],
            association_positions={"tx_a": 1, "tx_b": 2},
        )
    assert exc.value.code == "duplicate_segment_position"


def test_transcription_bound_to_multiple_segments_refused() -> None:
    with pytest.raises(DossierSegmentTopologyError) as exc:
        build_dossier_segment_topology(
            dossier_id="d1",
            segments=[_seg("seg_a", 0, "tx_shared"), _seg("seg_b", 1, "tx_shared")],
            association_positions={"tx_shared": 1},
        )
    assert exc.value.code == "transcription_bound_to_multiple_segments"


def test_duplicate_transcription_id_within_segment_refused() -> None:
    with pytest.raises(DossierSegmentTopologyError) as exc:
        build_dossier_segment_topology(
            dossier_id="d1",
            segments=[
                TopologySegmentInput(
                    segment_id="seg_a",
                    position=0,
                    runs=(
                        TopologyRunInput("tx_dup", 0),
                        TopologyRunInput("tx_dup", 1),
                    ),
                )
            ],
            association_positions={"tx_dup": 1},
        )
    assert exc.value.code == "duplicate_transcription_id_in_segment"


def test_non_string_identity_refused_before_sort() -> None:
    with pytest.raises(DossierSegmentTopologyError) as exc:
        build_dossier_segment_topology(
            dossier_id="d1",
            segments=[
                TopologySegmentInput(segment_id=12, position=0, runs=(TopologyRunInput("tx_a", 0),))  # type: ignore[arg-type]
            ],
            association_positions={"tx_a": 1},
        )
    assert exc.value.code == "invalid_segment_id"


def test_boolean_segment_position_refused() -> None:
    with pytest.raises(DossierSegmentTopologyError) as exc:
        build_dossier_segment_topology(
            dossier_id="d1",
            segments=[
                TopologySegmentInput(segment_id="seg_a", position=True, runs=(TopologyRunInput("tx_a", 0),))  # type: ignore[arg-type]
            ],
            association_positions={"tx_a": 1},
        )
    assert exc.value.code == "invalid_segment_position"


def test_boolean_run_position_refused() -> None:
    with pytest.raises(DossierSegmentTopologyError) as exc:
        build_dossier_segment_topology(
            dossier_id="d1",
            segments=[
                TopologySegmentInput(
                    segment_id="seg_a",
                    position=0,
                    runs=(TopologyRunInput("tx_a", True),),  # type: ignore[arg-type]
                )
            ],
            association_positions={"tx_a": 1},
        )
    assert exc.value.code == "invalid_run_position"


def test_boolean_association_position_refused() -> None:
    with pytest.raises(DossierSegmentTopologyError) as exc:
        build_dossier_segment_topology(
            dossier_id="d1",
            segments=[_seg("seg_a", 0, "tx_a")],
            association_positions={"tx_a": True},  # type: ignore[dict-item]
        )
    assert exc.value.code == "invalid_association_position"


def test_zero_association_position_refused() -> None:
    with pytest.raises(DossierSegmentTopologyError) as exc:
        build_dossier_segment_topology(
            dossier_id="d1",
            segments=[_seg("seg_a", 0, "tx_a")],
            association_positions={"tx_a": 0},
        )
    assert exc.value.code == "invalid_association_position"


def test_missing_run_association_diagnostic() -> None:
    topo = build_dossier_segment_topology(
        dossier_id="d1",
        segments=[_seg("seg_a", 0, "tx_a")],
        association_positions={},
    )
    assert any(d.code == "missing_run_association" for d in topo.diagnostics)
    assert topo.segments[0].runs[0].association_present is False


def test_unbound_association_diagnostic() -> None:
    topo = build_dossier_segment_topology(
        dossier_id="d1",
        segments=[_seg("seg_a", 0, "tx_a")],
        association_positions={"tx_a": 1, "tx_orphan": 2},
    )
    assert any(
        d.code == "unbound_association" and d.transcription_id == "tx_orphan"
        for d in topo.diagnostics
    )
    assert len(topo.segments) == 1


def test_reordering_changes_fingerprint() -> None:
    a = build_dossier_segment_topology(
        dossier_id="d1",
        segments=[_seg("seg_a", 0, "tx_a"), _seg("seg_b", 1, "tx_b")],
        association_positions={"tx_a": 1, "tx_b": 2},
    )
    b = build_dossier_segment_topology(
        dossier_id="d1",
        segments=[_seg("seg_b", 0, "tx_b"), _seg("seg_a", 1, "tx_a")],
        association_positions={"tx_a": 1, "tx_b": 2},
    )
    assert a.topology_fingerprint != b.topology_fingerprint


def test_fingerprint_ignores_timestamps_and_host_paths() -> None:
    first = build_dossier_segment_topology(
        dossier_id="d1",
        segments=[_seg("seg_a", 0, "tx_a")],
        association_positions={"tx_a": 1},
    )
    second = build_dossier_segment_topology(
        dossier_id="d1",
        segments=[_seg("seg_a", 0, "tx_a")],
        association_positions={"tx_a": 1},
    )
    assert first.topology_fingerprint == second.topology_fingerprint
    assert len(first.topology_fingerprint) == 64
    assert all(c in "0123456789abcdef" for c in first.topology_fingerprint)


def _tree_fp(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return out


def test_load_topology_leaves_source_tree_byte_identical(tmp_path: Path, monkeypatch) -> None:
    import config.paths as paths_mod
    import services.dossier.association_service as assoc_mod
    import services.dossier.management_service as mgmt_mod

    root = tmp_path / "dossiers_data"
    mgmt = root / "management"
    assoc = root / "associations"
    views = root / "views" / "transcriptions" / "d-load"
    mgmt.mkdir(parents=True)
    assoc.mkdir(parents=True)
    (views / "tx1").mkdir(parents=True)
    (views / "tx1" / "run.json").write_text(
        json.dumps({"status": "completed", "completed_drafts": []}),
        encoding="utf-8",
    )
    (views / "tx2").mkdir(parents=True)
    (views / "tx2" / "run.json").write_text(
        json.dumps({"status": "completed", "completed_drafts": []}),
        encoding="utf-8",
    )

    dossier_id = "d-load"
    (mgmt / f"dossier_{dossier_id}.json").write_text(
        json.dumps(
            {
                "id": dossier_id,
                "title": "Load Test",
                "description": "",
                "created_at": "2020-01-01T00:00:00",
                "updated_at": "2020-01-01T00:00:00",
                "manual_segments": [],
                "segment_name_overrides": {},
            }
        ),
        encoding="utf-8",
    )
    (assoc / f"assoc_{dossier_id}.json").write_text(
        json.dumps(
            {
                "dossier_id": dossier_id,
                "associations": [
                    {
                        "transcription_id": "tx1",
                        "position": 1,
                        "added_at": "2020-01-01T00:00:00",
                        "metadata": {},
                    },
                    {
                        "transcription_id": "tx2",
                        "position": 2,
                        "added_at": "2020-01-01T00:00:00",
                        "metadata": {},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_management_root", lambda: mgmt)
    monkeypatch.setattr(paths_mod, "dossiers_associations_root", lambda: assoc)
    monkeypatch.setattr(paths_mod, "dossiers_views_root", lambda: root / "views" / "transcriptions")
    monkeypatch.setattr(mgmt_mod, "dossiers_management_root", lambda: mgmt)
    monkeypatch.setattr(mgmt_mod, "dossiers_views_root", lambda: root / "views" / "transcriptions")
    monkeypatch.setattr(mgmt_mod, "dossier_run_root", lambda d, t: views / t)
    monkeypatch.setattr(assoc_mod, "dossiers_associations_root", lambda: assoc)

    before = _tree_fp(root)
    topo = load_dossier_segment_topology(dossier_id)
    after = _tree_fp(root)
    assert before == after
    assert len(topo.segments) == 2
    assert [r.transcription_id for s in topo.segments for r in s.runs] == ["tx1", "tx2"]


def test_load_refuses_duplicate_association_transcription_ids(monkeypatch) -> None:
    from types import SimpleNamespace

    import services.dossier.segment_topology as topo_mod

    class FakeMgmt:
        def get_dossier(self, dossier_id: str):
            return SimpleNamespace(
                segments=[
                    SimpleNamespace(
                        id="seg_a",
                        position=0,
                        runs=[SimpleNamespace(transcription_id="tx1", position=0)],
                    )
                ]
            )

    class FakeAssoc:
        def get_dossier_transcriptions(self, dossier_id: str):
            return [
                SimpleNamespace(transcription_id="tx1", position=1),
                SimpleNamespace(transcription_id="tx1", position=2),
            ]

    monkeypatch.setattr(
        topo_mod,
        "DossierManagementService",
        FakeMgmt,
        raising=False,
    )
    # Patch where load imports from.
    import services.dossier.management_service as mgmt_mod
    import services.dossier.association_service as assoc_mod

    monkeypatch.setattr(mgmt_mod, "DossierManagementService", FakeMgmt)
    monkeypatch.setattr(assoc_mod, "TranscriptionAssociationService", FakeAssoc)

    with pytest.raises(DossierSegmentTopologyError) as exc:
        load_dossier_segment_topology("d1")
    assert exc.value.code == "duplicate_association_transcription_id"
