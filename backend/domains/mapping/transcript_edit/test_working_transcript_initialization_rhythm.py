"""Offline checks for MAPDEP-BR-034 exact-T0 initialization rhythm teaching."""

from __future__ import annotations

from pathlib import Path

from domains.mapping.transcript_edit.execution.dossier_tool_specs import (
    build_dossier_transcript_edit_tool_specs,
)
from domains.mapping.transcript_edit.execution.tool_specs import (
    build_transcript_edit_tool_specs,
)
from domains.mapping.transcript_edit.payloads import (
    DossierTranscriptEditScope,
    DossierTranscriptEditStartupInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)
from domains.mapping.transcript_edit.prompting.branch import (
    TRANSCRIPT_EDIT_BRANCH_VERSION,
    build_transcript_edit_branch_blocks,
)
from domains.mapping.transcript_edit.prompting.surfaces.dossier_guidance import (
    TRANSCRIPT_EDIT_DOSSIER_GUIDANCE_VERSION,
    build_transcript_edit_dossier_guidance_block,
)
from domains.mapping.transcript_edit.prompting.surfaces.procedural_guidance import (
    TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION,
    build_transcript_edit_procedural_guidance_blocks,
)
from domains.mapping.transcript_edit.prompting.surfaces.startup_context import (
    TRANSCRIPT_EDIT_STARTUP_CONTEXT_VERSION,
    build_startup_context_block,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CHANGELOG = _REPO_ROOT / "docs" / "architecture" / "harness" / "doctrine-changelog.md"

_BR033_TOOL_ORDER = (
    "hydrate_artifact_refs",
    "transform_artifact",
    "initialize_working_transcript",
    "save_workspace_artifact",
    "copy_forward_save_workspace_artifact",
    "apply_transcript_edits",
    "publish_workspace_artifact",
)

_TRUTH_RANKING_CLAIMS = (
    "best t0 is",
    "authoritative peer",
    "consensus draft is true",
    "agreement is evidence",
    "rank the t0",
    "automatically select the best",
    "copied peer is authoritative",
    "must reconcile all peers before initialize",
    "exhaustive peer reconciliation before initialize",
)

_EVALUATION_DEED_FACTS = (
    "range 7 west",
    "range 77 west",
    "range 75",
    "range 74",
    "nw corner",
    "n 4°",
    "n 4 deg",
    "1638",
    "seg1-location",
    "marked corner",
)


def _guidance() -> str:
    return build_transcript_edit_procedural_guidance_blocks()[0].text


def _branch() -> str:
    return build_transcript_edit_branch_blocks()[0].text


def _dossier() -> str:
    return build_transcript_edit_dossier_guidance_block().text


def _leaf_startup() -> str:
    return build_startup_context_block(
        TranscriptEditStartupInventory(
            scope=TranscriptEditScope(dossier_id="d1", transcription_id="tx1"),
        )
    ).text


def _dossier_startup() -> str:
    return build_startup_context_block(
        DossierTranscriptEditStartupInventory(
            scope=DossierTranscriptEditScope(
                dossier_id="d1",
                run_id="r1",
                workspace_id="w1",
            ),
            topology_fingerprint="a" * 64,
            segment_count=0,
            segments=(),
            topology_diagnostics=(),
        )
    ).text


def _all_teaching() -> str:
    return "\n".join((_guidance(), _branch(), _dossier(), _leaf_startup(), _dossier_startup()))


def test_versions_bumped() -> None:
    assert TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION == "v50"
    assert TRANSCRIPT_EDIT_BRANCH_VERSION == "v37"
    assert TRANSCRIPT_EDIT_DOSSIER_GUIDANCE_VERSION == "v3"
    assert TRANSCRIPT_EDIT_STARTUP_CONTEXT_VERSION == "v6"
    assert build_transcript_edit_procedural_guidance_blocks()[0].version == "v50"
    assert build_transcript_edit_branch_blocks()[0].version == "v37"
    assert build_transcript_edit_dossier_guidance_block().version == "v3"
    assert (
        build_startup_context_block(
            TranscriptEditStartupInventory(
                scope=TranscriptEditScope(dossier_id="d1", transcription_id="tx1"),
            )
        ).version
        == "v6"
    )


def test_initialization_is_unverified_exact_t0_baseline() -> None:
    guidance = _guidance().lower()
    branch = _branch().lower()
    assert "initialize" in guidance
    assert "exact t0" in guidance
    assert "unverified candidate" in guidance
    assert "both transcript lanes" in guidance
    assert "empty decision ledger" in guidance
    assert "verifies nothing" in guidance
    assert "unverified candidate baseline" in branch


def test_copy_source_is_not_truth_ranking() -> None:
    guidance = _guidance().lower()
    branch = _branch().lower()
    dossier = _dossier().lower()
    assert "not ranking that peer as truth" in guidance
    assert "not ranking the peer as truth" in branch
    assert "not ranking the peer as truth" in dossier
    assert "treat peer agreement as evidence" in guidance
    combined = _all_teaching().lower()
    for claim in _TRUTH_RANKING_CLAIMS:
        assert claim not in combined, claim


def test_initialization_is_preferred_when_useful_not_mandatory() -> None:
    guidance = _guidance().lower()
    assert "useful source-shaped baseline" in guidance
    assert "exact in-scope t0" in guidance
    assert "not a mandatory phase or gate" in guidance
    assert "decline a severely deficient" in guidance
    assert "without first adjudicating every reading" in guidance
    assert "checklist or scoring system" in guidance
    assert "copy-transport fitness" not in guidance
    assert "you can name" not in guidance
    assert "usable here means" not in guidance


def test_initialization_does_not_satisfy_final_publication() -> None:
    branch = _branch().lower()
    guidance = _guidance().lower()
    assert "does not satisfy the final source-observed transcript obligation" in branch
    assert "verify text" in branch
    assert "earn decisions" in branch
    assert "resolve investigation state" in branch
    assert "must not weaken that final standard" in guidance
    assert "published output must still satisfy" in guidance


def test_returned_revision_feeds_apply() -> None:
    guidance = _guidance().lower()
    assert "apply_transcript_edits" in guidance
    assert "returned exact working revision" in guidance
    assert "source-supported corrections" in guidance
    assert "unchanged-text confirmations" in guidance


def test_existing_lineage_is_continued() -> None:
    guidance = _guidance().lower()
    dossier = _dossier().lower()
    assert "already exists, continue that lineage" in guidance
    assert "do not attempt to initialize it again" in guidance
    assert "already has a working revision, continue it" in dossier


def test_full_save_remains_available_even_when_t0_exists() -> None:
    guidance = _guidance().lower()
    assert "save_workspace_artifact" in guidance
    assert "even if a technically copyable t0 exists" in guidance
    assert "genuinely need to author the initial working artifact" in guidance
    assert "author an honest first transcript" not in guidance
    assert "no t0 can be copied for this lineage" not in guidance


def test_dossier_uses_qualified_refs_for_worked_segment_only() -> None:
    dossier = _dossier().lower()
    assert "dossier-qualified exact t0 ref" in dossier
    assert "qualified ref identifies the segment/run lineage" in dossier
    assert "segment being worked" in dossier
    assert "do not initialize every dossier segment merely as setup" in dossier
    assert "establish or edit only the working lineage" in dossier
    assert "adjacent segments may still be inspected" in dossier
    assert "work only on the segment currently being handled" not in dossier
    assert "useful source-shaped baseline" in dossier
    assert "even if a technically copyable t0 exists" in dossier
    assert "do not require every segment to be initialized" in dossier
    assert "explicitly chosen exact working revision" in dossier
    assert "source_revision_refs" in dossier


def test_startup_capabilities_include_full_tool_family() -> None:
    leaf = _leaf_startup().lower()
    dossier = _dossier_startup().lower()
    for name in (
        "initialize_working_transcript",
        "save_workspace_artifact",
        "copy_forward_save_workspace_artifact",
        "apply_transcript_edits",
        "publish_workspace_artifact",
    ):
        assert name in leaf, name
        assert name in dossier, name
    assert "unverified baseline" in leaf
    assert "dossier-qualified exact t0" in dossier
    assert "one chosen exact qualified working revision per topology segment" in dossier
    assert "when no t0 can be copied" not in leaf
    assert "when no t0 can be copied" not in dossier


def test_investigation_continues_reconciling_evidence() -> None:
    guidance = _guidance().lower()
    dossier = _dossier().lower()
    assert "copy-source selection does not require exhaustive peer reconciliation" in guidance
    assert "reconciled during ordinary investigation" in guidance
    assert "copy-source selection does not require exhaustive peer reconciliation" in dossier
    assert "reconciled during ordinary investigation" in dossier
    assert "publication performs the final reconciliation" in guidance
    assert "publication performs the final reconciliation" in dossier


def test_prompt_tool_menu_keeps_br033_order() -> None:
    leaf_ids = tuple(spec.tool_id for spec in build_transcript_edit_tool_specs())
    dossier_ids = tuple(spec.tool_id for spec in build_dossier_transcript_edit_tool_specs())
    assert leaf_ids == _BR033_TOOL_ORDER
    assert dossier_ids == _BR033_TOOL_ORDER


def test_no_evaluation_deed_facts_in_teaching() -> None:
    combined = _all_teaching().lower()
    for banned in _EVALUATION_DEED_FACTS:
        assert banned not in combined, banned


def test_changelog_records_br034() -> None:
    text = _CHANGELOG.read_text(encoding="utf-8")
    assert "2026-09-15" in text
    assert "working-initialization rhythm" in text
    assert "v47→v48" in text or "v47 → v48" in text
    assert "te-br034-20260915/working-initialization-rhythm-ledger.md" in text
