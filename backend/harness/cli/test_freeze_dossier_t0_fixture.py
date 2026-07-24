"""CLI coverage for freeze_dossier_t0_fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from harness.cli.freeze_dossier_t0_fixture import main


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed(tmp_path: Path) -> tuple[Path, Path, Path, Path, str, str]:
    dossiers_root = tmp_path / "dossiers_data"
    destination_root = tmp_path / "out"
    dossier_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    img1 = tmp_path / "page1.png"
    img2 = tmp_path / "page2.png"
    img1.write_bytes(b"cli-page-1")
    img2.write_bytes(b"cli-page-2")
    _write_json(
        dossiers_root / "associations" / f"assoc_{dossier_id}.json",
        {
            "dossier_id": dossier_id,
            "associations": [
                {
                    "transcription_id": "draft_a",
                    "position": 1,
                    "metadata": {
                        "processing_params": {
                            "model": "gpt-o4-mini",
                            "extraction_mode": "legal_document_json",
                            "redundancy_count": 2,
                        },
                        "provenance": {"source": {"file_hash": _sha(img1)}},
                    },
                },
                {
                    "transcription_id": "draft_b",
                    "position": 2,
                    "metadata": {
                        "processing_params": {
                            "model": "gpt-o4-mini",
                            "extraction_mode": "legal_document_json",
                            "redundancy_count": 2,
                        },
                        "provenance": {"source": {"file_hash": _sha(img2)}},
                    },
                },
            ],
        },
    )
    for tid in ("draft_a", "draft_b"):
        tx = dossiers_root / "views" / "transcriptions" / dossier_id / tid
        _write_json(tx / "run.json", {"status": "completed", "processing_params": {}})
        _write_json(tx / "raw" / f"{tid}_v1.json", {"ok": True})
        _write_json(tx / "consensus" / "llm.json", {"skip": True})
    return dossiers_root, destination_root, img1, img2, dossier_id, "cli_fixture"


def test_cli_create_then_idempotent_replay(tmp_path: Path, capsys) -> None:
    dossiers_root, destination_root, img1, img2, dossier_id, fixture_id = _seed(tmp_path)
    argv = [
        "--dossiers-root",
        str(dossiers_root),
        "--destination-root",
        str(destination_root),
        "--fixture-id",
        fixture_id,
        "--dossier-id",
        dossier_id,
        "--segment",
        f"1|draft_a|{img1}|{_sha(img1)}|page1.png",
        "--segment",
        f"2|draft_b|{img2}|{_sha(img2)}|page2.png",
        "--write-set-manifest",
    ]
    assert main(argv) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == "ok"
    assert created["created"] is True
    assert created["idempotent_replay"] is False
    assert created["segment_count"] == 2
    assert Path(created["manifest_path"]).is_file()
    assert Path(created["fixture_set_manifest_path"]).is_file()

    assert main(argv) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["status"] == "ok"
    assert replay["idempotent_replay"] is True
    assert replay["created"] is False
    set_path = Path(created["fixture_set_manifest_path"])
    before = set_path.read_bytes()
    mtime = set_path.stat().st_mtime_ns
    assert main(argv) == 0
    capsys.readouterr()
    assert set_path.read_bytes() == before
    assert set_path.stat().st_mtime_ns == mtime

def test_cli_conflict_returns_error_payload(tmp_path: Path, capsys) -> None:
    dossiers_root, destination_root, img1, img2, dossier_id, fixture_id = _seed(tmp_path)
    base = [
        "--dossiers-root",
        str(dossiers_root),
        "--destination-root",
        str(destination_root),
        "--fixture-id",
        fixture_id,
        "--dossier-id",
        dossier_id,
        "--segment",
        f"1|draft_a|{img1}|{_sha(img1)}|page1.png",
        "--segment",
        f"2|draft_b|{img2}|{_sha(img2)}|page2.png",
    ]
    assert main(base) == 0
    capsys.readouterr()
    conflict = [
        "--dossiers-root",
        str(dossiers_root),
        "--destination-root",
        str(destination_root),
        "--fixture-id",
        fixture_id,
        "--dossier-id",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "--segment",
        f"1|draft_a|{img1}|{_sha(img1)}|page1.png",
        "--segment",
        f"2|draft_b|{img2}|{_sha(img2)}|page2.png",
    ]
    assert main(conflict) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["reason"] == "dossier_t0_fixture_conflict"
