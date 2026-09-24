"""MAPDEP-BR-040: point-anchored window judgment in live procedural doctrine."""

from __future__ import annotations

from pathlib import Path

from domains.mapping.transcript_edit.prompting.surfaces.procedural_guidance import (
    TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION,
    build_transcript_edit_procedural_guidance_blocks,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CHANGELOG = _REPO_ROOT / "docs" / "architecture" / "harness" / "doctrine-changelog.md"

_BANNED_EVAL_FACTS = (
    "curve station",
    "muse1",
    "range 7 west",
    "range 77 west",
    "1638",
    "marked corner",
)


def _guidance() -> str:
    return build_transcript_edit_procedural_guidance_blocks()[0].text


def _lower() -> str:
    return _guidance().lower()


def test_procedural_version_is_v50() -> None:
    assert TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION == "v50"
    assert build_transcript_edit_procedural_guidance_blocks()[0].version == "v50"


def test_anchor_and_window_are_distinct() -> None:
    text = _lower()
    assert "the point identifies the exact atom" in text or "the point anchors the claim" in text
    assert "observation window" in text or "the window decides" in text
    assert "does not turn the atom into a span-shaped resolution unit" in text
    assert "does not enlarge the resolution atom" in text


def test_templates_and_extents_both_remain_legitimate() -> None:
    text = _lower()
    assert "templates remain the economical default" in text or "templates stay first-class" in text
    assert "extents are not mandatory" in text
    assert "not every packet needs a custom window" in text or "not always superior" in text
    assert "window_extents_norm" in text
    assert "small_plus" in text
    assert "not a universal starting shape" in text


def test_asymmetric_context_is_judgment() -> None:
    text = _lower()
    assert "materially asymmetric" in text
    assert "wrapping" in text or "wrapped" in text
    assert "source edge" in text
    assert "neighboring" in text


def test_first_pass_packet_shaping() -> None:
    text = _lower()
    assert "too-tight" in text or "too tight" in text
    assert "initial point-crop request" in text or "first packet" in text
    assert "already apparent" in text or "already shows" in text


def test_overlay_covers_placement_and_window() -> None:
    text = _lower()
    assert "point sanity" in text
    assert "window sanity" in text
    assert "resolved bounds" in text
    assert 'show:["box"]' in _guidance() or "show:" in text and "box" in text


def test_box_display_is_not_mandatory() -> None:
    text = _lower()
    assert "not a requirement on every packet" in text
    assert "must show box" not in text
    assert "always include box" not in text
    assert "every packet" in text and "box" in text


def test_correct_anchor_keeps_window_adjustment_separate() -> None:
    text = _lower()
    assert "if the anchor is right" in text or "point is right" in text
    assert "reshape the window" in text
    assert "do not move a correct anchor" in text


def test_no_fixed_retry_or_batch_rule() -> None:
    text = _lower()
    assert "no fixed retry count" in text
    assert "no one-adjustment ceiling" in text or "one-adjustment ceiling" in text
    assert "not by a fixed point count" in text
    assert "always enlarge" in text  # taught as what not to do


def test_extents_are_not_a_prohibited_generic_box() -> None:
    text = _lower()
    assert "not the prohibited practice" in text or "not that prohibited generic box" in text
    assert "canonical point-crop" in text or "point-anchored crop" in text


def test_existing_observation_and_apply_teachings_remain() -> None:
    text = _lower()
    assert "off_target" in text
    assert "insufficient_context" in text
    assert "unreadable" in text
    assert "status: completed" in text or "does not earn a value" in text
    assert "candidate" in text and "not earned truth" in text or "not proof" in text
    assert "not proof that the source lacks the target" in text
    assert "apply_transcript_edits" in text
    assert "provisional" in text
    assert "do not hydrate" in text
    assert "bullseye" in text
    assert "initialize" in text


def test_no_evaluation_deed_contamination() -> None:
    combined = _lower() + "\n" + _CHANGELOG.read_text(encoding="utf-8").lower()
    for banned in _BANNED_EVAL_FACTS:
        assert banned not in combined, banned


def _changelog_rows() -> list[list[str]]:
    rows: list[list[str]] = []
    for line in _CHANGELOG.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("| 20"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    return rows


def test_changelog_records_br040() -> None:
    text = _CHANGELOG.read_text(encoding="utf-8")
    assert "2026-09-21" in text
    assert "v48→v49" in text or "v48 → v49" in text
    assert "te-br040-20260921/point-anchored-window-judgment-ledger.md" in text
    assert "anchor" in text.lower() and "window" in text.lower()


def test_changelog_keeps_br040_and_delegate_rows_separate() -> None:
    rows = _changelog_rows()
    br040 = [
        cells
        for cells in rows
        if cells and cells[0] == "2026-09-21" and "source-reading packet workflow" in cells[1]
    ]
    delegate = [
        cells
        for cells in rows
        if cells
        and cells[0] == "2026-09-16"
        and "delegate-observation worklist" in cells[1]
    ]
    assert len(br040) == 1
    assert len(delegate) == 1
    assert len(br040[0]) == 5
    assert len(delegate[0]) == 5
    br040_text = " | ".join(br040[0])
    delegate_text = " | ".join(delegate[0])
    assert "delegate-observation" not in br040_text
    assert "One integration turn earned" not in br040_text
    assert "v48→v49" not in delegate_text
    assert "point-anchored-window-judgment-ledger" not in delegate_text
    assert "procedural v48 unchanged" in delegate[0][1]
    assert delegate[0][4].endswith("false earned state")
