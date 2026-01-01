from __future__ import annotations

import json
from pathlib import Path

import config.paths as paths_mod
from corpus.virtual_provider import VirtualCorpusProvider

from .engine.retrieval_engine import RetrievalEngine
from .lanes.provenance.lane import ProvenanceLane
from .lanes.provenance.recipes import ProvenanceRecipe


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _patch_dossiers_root(monkeypatch, root: Path) -> None:
    def _patched_dossiers_root() -> Path:
        root.mkdir(parents=True, exist_ok=True)
        return root

    monkeypatch.setattr(paths_mod, "dossiers_root", _patched_dossiers_root)


def test_provenance_canonical_stack_returns_expected_cards(tmp_path, monkeypatch) -> None:
    root = tmp_path / "dossiers_data"
    _patch_dossiers_root(monkeypatch, root)

    dossier_id = "D1"
    _write_json(
        root / "views" / "transcriptions" / dossier_id / "final" / "dossier_final.json",
        {
            "dossier_id": dossier_id,
            "dossier_title": "Test Dossier",
            "generated_at": "2024-01-01T00:00:00Z",
            "stitched_text": "Final text",
            "sha256": "dummy-final",
        },
    )
    _write_json(
        root / "artifacts" / "schemas" / dossier_id / "latest.json",
        {"schema_id": "S1", "schema_sha256": "dummy-schema"},
    )
    _write_json(
        root / "artifacts" / "georefs" / dossier_id / "latest.json",
        {"georef_id": "G1", "sha256": "dummy-georef"},
    )

    lane = ProvenanceLane(provider=VirtualCorpusProvider())
    result = lane.search(dossier_id, recipe=ProvenanceRecipe.CANONICAL_STACK)

    assert len(result.cards) == 3
    expected_ids = {
        f"prov:final:{dossier_id}",
        f"prov:schema_latest:{dossier_id}",
        f"prov:georef_latest:{dossier_id}",
    }
    assert {card.id for card in result.cards} == expected_ids
    assert {card.spans[0].entry.entry_id for card in result.cards} == {
        f"final:{dossier_id}",
        f"schema_latest:{dossier_id}",
        f"georef_latest:{dossier_id}",
    }


def test_provenance_missing_artifacts_is_nonfatal(tmp_path, monkeypatch) -> None:
    root = tmp_path / "dossiers_data"
    _patch_dossiers_root(monkeypatch, root)

    dossier_id = "D2"
    _write_json(
        root / "views" / "transcriptions" / dossier_id / "final" / "dossier_final.json",
        {
            "dossier_id": dossier_id,
            "dossier_title": "Test Dossier",
            "generated_at": "2024-01-01T00:00:00Z",
            "stitched_text": "Only final text",
            "sha256": "dummy-final",
        },
    )

    lane = ProvenanceLane(provider=VirtualCorpusProvider())
    result = lane.search(dossier_id, recipe=ProvenanceRecipe.CANONICAL_STACK)

    assert len(result.cards) == 1
    assert set(result.debug.get("missing", [])) >= {"schema_json", "georef_json"}


def test_engine_dispatch_provenance_lane(tmp_path, monkeypatch) -> None:
    root = tmp_path / "dossiers_data"
    _patch_dossiers_root(monkeypatch, root)

    dossier_id = "D3"
    _write_json(
        root / "views" / "transcriptions" / dossier_id / "final" / "dossier_final.json",
        {
            "dossier_id": dossier_id,
            "dossier_title": "Test Dossier",
            "generated_at": "2024-01-01T00:00:00Z",
            "stitched_text": "Final text",
            "sha256": "dummy-final",
        },
    )

    lane = ProvenanceLane(provider=VirtualCorpusProvider())
    engine = RetrievalEngine(provenance_lane=lane)

    lane_result = lane.search(dossier_id)
    engine_result = engine.search(dossier_id, lanes=["provenance"])

    assert {card.id for card in engine_result.cards} == {card.id for card in lane_result.cards}
