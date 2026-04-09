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

_FORBIDDEN_STARTUP_KEYS = frozenset(
    {"head", "head_ref", "head_json", "current_head", "transcript_head", "selected_final_ref", "final_selection"}
)


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
    assert stems == {"draft_legal_text_image_draft_1", "draft_legal_text_image_draft_2", "draft_legal_text_image_draft_3"}
    assert [d.ref_id for d in inv.t0_drafts] == ["t0:raw:draft_1", "t0:raw:draft_2", "t0:raw:draft_3"]
    assert [d.variant_label for d in inv.t0_drafts] == ["draft 1", "draft 2", "draft 3"]
    assert "draft_legal_text_image" not in stems
    assert any(m.code == "t0_legacy_pointer_file_present" for m in inv.missing_resources)
    assert inv.source_images, "expected association image refs"
    roles = {img.role for img in inv.source_images}
    assert roles == {"source_original"}
    plain = asdict(inv)
    _assert_no_forbidden_keys(plain)
    for img in inv.source_images:
        assert img.ref_id.startswith("image:assoc:")
        assert "base64" not in json.dumps(asdict(img)).lower()


def _max_nested_string_len(obj: object) -> int:
    best = 0
    if isinstance(obj, str):
        return len(obj)
    if isinstance(obj, dict):
        for v in obj.values():
            best = max(best, _max_nested_string_len(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            best = max(best, _max_nested_string_len(v))
    return best


def test_startup_snippet_previews_are_short_non_authoritative():
    inv = build_transcript_edit_startup_inventory(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
    )
    for d in inv.t0_drafts:
        if d.snippet_preview:
            assert len(d.snippet_preview) <= 240
    plain = asdict(inv)
    slim = {k: v for k, v in plain.items() if k != "missing_resources"}
    assert _max_nested_string_len(slim) <= 280
    full = hydrate_t0_draft_refs(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
        ref_ids=[inv.t0_drafts[0].ref_id],
        max_refs=1,
    )
    assert len(full.drafts[0].text) > 500


def test_hydrate_legacy_pointer_alias_rejected():
    out = hydrate_t0_draft_refs(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
        ref_ids=[f"t0:raw:{_PRACTICE_TX}"],
        max_refs=8,
    )
    assert out.drafts == ()
    assert any(e.get("code") == "legacy_pointer_alias" for e in out.errors)


def test_hydrate_single_and_multiple_t0():
    inv = build_transcript_edit_startup_inventory(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
    )
    r1 = [d.ref_id for d in inv.t0_drafts if d.source_file_stem == "draft_legal_text_image_draft_1"]
    assert r1 == ["t0:raw:draft_1"]
    out = hydrate_t0_draft_refs(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
        ref_ids=r1,
        max_refs=8,
    )
    assert len(out.drafts) == 1
    assert "Right of Way" in out.drafts[0].text
    refs = [d.ref_id for d in inv.t0_drafts if d.source_file_stem.startswith("draft_legal_text_image_draft_")]
    out2 = hydrate_t0_draft_refs(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
        ref_ids=refs,
        max_refs=8,
    )
    assert len(out2.drafts) == len(refs)
    assert not out2.cap_exceeded
    assert not any(e.get("code") == "cap_exceeded" for e in out2.errors)


def test_hydrate_respects_cap(tmp_path, monkeypatch):
    import config.paths as paths_mod

    root = tmp_path / "dossiers_data"
    run = root / "views" / "transcriptions" / "d1" / "t1" / "raw"
    run.mkdir(parents=True)
    for i in range(10):
        p = run / f"stem_{i}.json"
        p.write_text(json.dumps({"sections": [{"body": f"text-{i}"}]}), encoding="utf-8")
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)

    ref_ids = [f"t0:raw:draft_{i + 1}" for i in range(10)]
    out = hydrate_t0_draft_refs(
        dossier_id="d1",
        transcription_id="t1",
        ref_ids=ref_ids,
        max_refs=3,
    )
    assert len(out.drafts) == 3
    assert out.cap_exceeded is True
    assert len(out.omitted_ref_ids) == 7
    assert set(out.omitted_ref_ids) == {f"t0:raw:draft_{i + 1}" for i in range(3, 10)}
    assert any(e.get("code") == "cap_exceeded" for e in out.errors)


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
        ref_ids=["bogus", "t0:raw:draft_1", "t0:raw:missing_z"],
        max_refs=8,
    )
    codes = {e["code"] for e in out.errors}
    assert "invalid_ref" in codes
    assert "not_found" in codes
    assert any(d.ref_id == "t0:raw:draft_1" for d in out.drafts)


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


def test_hydrate_transcript_edit_requires_workspace_key():
    from tooling.mapping.transcript_edit.draft_loading import hydrate_transcript_edit_working_draft

    r = hydrate_transcript_edit_working_draft(
        dossier_id=_PRACTICE_DOSSIER,
        transcription_id=_PRACTICE_TX,
        ref_id="transcript_edit:working",
    )
    assert r["status"] == "error"
    assert r.get("code") == "workspace_required"


def test_pointer_only_raw_emits_structured_gap(tmp_path, monkeypatch):
    import config.paths as paths_mod

    root = tmp_path / "dossiers_data"
    raw = root / "views" / "transcriptions" / "d1" / "t_tx" / "raw"
    raw.mkdir(parents=True)
    (raw / "t_tx.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)

    inv = build_transcript_edit_startup_inventory(dossier_id="d1", transcription_id="t_tx")
    assert inv.t0_drafts == ()
    assert any(m.code == "t0_only_legacy_pointer_no_peer_drafts" for m in inv.missing_resources)


def test_completed_drafts_mismatch_extra_raw_file(tmp_path, monkeypatch):
    import config.paths as paths_mod

    root = tmp_path / "dossiers_data"
    base = root / "views" / "transcriptions" / "d1" / "t1"
    raw = base / "raw"
    raw.mkdir(parents=True)
    (base / "run.json").write_text(json.dumps({"completed_drafts": ["stem_a"]}), encoding="utf-8")
    (raw / "stem_a.json").write_text(json.dumps({"sections": [{"body": "a"}]}), encoding="utf-8")
    (raw / "stem_extra.json").write_text(json.dumps({"sections": [{"body": "x"}]}), encoding="utf-8")
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)

    inv = build_transcript_edit_startup_inventory(dossier_id="d1", transcription_id="t1")
    assert {d.source_file_stem for d in inv.t0_drafts} == {"stem_a"}
    assert [d.ref_id for d in inv.t0_drafts] == ["t0:raw:draft_1"]
    assert any(m.code == "t0_raw_file_not_in_completed_drafts" and m.detail == "stem_extra" for m in inv.missing_resources)


def test_startup_inventory_rejects_unsafe_dossier_path_segment(tmp_path, monkeypatch):
    import config.paths as paths_mod

    root = tmp_path / "dossiers_data"
    root.mkdir(parents=True)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)

    inv = build_transcript_edit_startup_inventory(
        dossier_id="d1/../evil",
        transcription_id="t1",
        run_id="ws1",
    )
    assert inv.t0_drafts == ()
    assert any(m.code == "launch_scope_path_invalid" for m in inv.missing_resources)


def test_hydrate_t0_invalid_scope_path_returns_structured_error():
    out = hydrate_t0_draft_refs(
        dossier_id="x/y",
        transcription_id="t1",
        ref_ids=["t0:raw:stem"],
        max_refs=8,
    )
    assert out.drafts == ()
    assert any(e.get("code") == "invalid_scope_path" for e in out.errors)


def test_source_image_hydration_invalid_dossier_scope():
    ctx = hydrate_source_image_context(
        dossier_id="../bad",
        transcription_id="t1",
        ref_id="image:assoc:t1:original",
    )
    assert ctx["status"] == "error"
    assert ctx.get("code") == "invalid_scope_path"


def test_missing_run_dir_structured():
    inv = build_transcript_edit_startup_inventory(
        dossier_id="00000000-0000-0000-0000-000000000001",
        transcription_id="nonexistent_transcription_xyz",
    )
    assert inv.t0_drafts == ()
    assert any(m.code == "transcription_run_dir_missing" for m in inv.missing_resources)
