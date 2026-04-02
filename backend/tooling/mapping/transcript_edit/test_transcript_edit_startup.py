"""Startup inventory + hydration: dossier-backed transcript_edit tooling."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from tooling.mapping.transcript_edit.draft_loading import hydrate_t0_draft_refs
from tooling.mapping.transcript_edit.image_loading import hydrate_source_image_context
from tooling.mapping.transcript_edit.startup_inventory import build_transcript_edit_startup_inventory

_PRACTICE_DOSSIER = "9f5eecb6-cd7e-483c-b691-b76aa7132e8e"
_PRACTICE_TX = "draft_legal_text_image"

_FORBIDDEN_STARTUP_KEYS = frozenset({"head", "head_ref", "head_json", "current_head", "transcript_head"})


def _assert_no_forbidden_keys(obj: object) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert str(k).lower() not in _FORBIDDEN_STARTUP_KEYS, f"forbidden key: {k}"
            _assert_no_forbidden_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_forbidden_keys(item)


def test_practice_dossier_startup_lists_peer_t0_and_images():
    inv = build_transcript_edit_startup_inventory(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
    )
    assert inv.scope.dossier_id == _PRACTICE_DOSSIER
    stems = {d.source_file_stem for d in inv.t0_drafts}
    assert {"draft_legal_text_image_v1", "draft_legal_text_image_v2", "draft_legal_text_image_v3"}.issubset(stems)
    assert "draft_legal_text_image" in stems or len(stems) >= 3
    assert inv.source_images, "expected association image refs"
    roles = {img.role for img in inv.source_images}
    assert "source_original" in roles
    plain = asdict(inv)
    _assert_no_forbidden_keys(plain)
    for img in inv.source_images:
        assert img.ref_id.startswith("image:assoc:")
        assert "base64" not in json.dumps(asdict(img)).lower()


def test_startup_snippet_previews_are_short_non_authoritative():
    inv = build_transcript_edit_startup_inventory(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
    )
    for d in inv.t0_drafts:
        if d.snippet_preview:
            assert len(d.snippet_preview) <= 240
    full = hydrate_t0_draft_refs(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
        ref_ids=[inv.t0_drafts[0].ref_id],
        max_refs=1,
    )
    assert len(full.drafts[0].text) > 500


def test_hydrate_single_and_multiple_t0():
    inv = build_transcript_edit_startup_inventory(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
    )
    r1 = [d.ref_id for d in inv.t0_drafts if d.source_file_stem == "draft_legal_text_image_v1"]
    assert r1
    out = hydrate_t0_draft_refs(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
        ref_ids=r1,
        max_refs=8,
    )
    assert len(out.drafts) == 1
    assert "Right of Way" in out.drafts[0].text
    refs = [d.ref_id for d in inv.t0_drafts if d.source_file_stem.startswith("draft_legal_text_image_v")]
    out2 = hydrate_t0_draft_refs(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
        ref_ids=refs,
        max_refs=8,
    )
    assert len(out2.drafts) == len(refs)
    assert not out2.errors


def test_hydrate_respects_cap(tmp_path, monkeypatch):
    import config.paths as paths_mod

    root = tmp_path / "dossiers_data"
    run = root / "views" / "transcriptions" / "d1" / "t1" / "raw"
    run.mkdir(parents=True)
    for i in range(10):
        p = run / f"stem_{i}.json"
        p.write_text(json.dumps({"sections": [{"body": f"text-{i}"}]}), encoding="utf-8")
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)

    ref_ids = [f"t0:raw:stem_{i}" for i in range(10)]
    out = hydrate_t0_draft_refs(
        dossier_id="d1",
        transcription_id="t1",
        ref_ids=ref_ids,
        max_refs=3,
    )
    assert len(out.drafts) == 3


def test_hydrate_invalid_and_missing_refs(tmp_path, monkeypatch):
    import config.paths as paths_mod

    root = tmp_path / "dossiers_data"
    rr = root / "views" / "transcriptions" / "d1" / "t1" / "raw"
    rr.mkdir(parents=True)
    (rr / "only.json").write_text(json.dumps({"sections": [{"body": "x"}]}), encoding="utf-8")
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)

    out = hydrate_t0_draft_refs(
        dossier_id="d1",
        transcription_id="t1",
        ref_ids=["bogus", "t0:raw:only", "t0:raw:missing_z"],
        max_refs=8,
    )
    codes = {e["code"] for e in out.errors}
    assert "invalid_ref" in codes
    assert "not_found" in codes
    assert any(d.ref_id == "t0:raw:only" for d in out.drafts)


def test_source_image_hydration_ok_for_practice():
    inv = build_transcript_edit_startup_inventory(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
    )
    orig = next((i for i in inv.source_images if i.role == "source_original"), None)
    assert orig
    ctx = hydrate_source_image_context(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
        ref_id=orig.ref_id,
    )
    assert ctx["status"] == "ok"
    assert ctx.get("exists") is True
    assert "size_bytes" in ctx


def test_hydrate_transcript_edit_working_not_present():
    from tooling.mapping.transcript_edit.draft_loading import hydrate_transcript_edit_working_draft

    r = hydrate_transcript_edit_working_draft(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
        ref_id="transcript_edit:working",
    )
    assert r["status"] == "error"
    assert r.get("code") == "not_found"


def test_missing_run_dir_structured():
    inv = build_transcript_edit_startup_inventory(
        dossier_id="00000000-0000-0000-0000-000000000001",
        transcription_id="nonexistent_transcription_xyz",
    )
    assert inv.t0_drafts == ()
    assert any(m.code == "transcription_run_dir_missing" for m in inv.missing_resources)

