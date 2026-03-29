from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.tooling.mapping.transcription_edit.apply import apply_plan_to_sections
from backend.tooling.mapping.transcription_edit.contracts import (
    EditPlanV0,
    TranscriptDocumentV0,
    TranscriptSectionV0,
    transcript_text_hash,
)
from backend.services.workflows.mapping.transcription_edit.persistence import TranscriptionEditPersistenceService
from backend.tooling.mapping.transcription_edit.section_adapter import sections_to_text_with_index_map


def test_apply_plan_to_sections_preserves_ids_and_structure() -> None:
    document = TranscriptDocumentV0(
        source_transcript_ref="artifact://src",
        sections=[
            TranscriptSectionV0(id="s1", body="Beginning at NW corner."),
            TranscriptSectionV0(id="s2", body="Thence South 45E 100 feet to point of beginning."),
        ],
    )
    text, _ = sections_to_text_with_index_map(document.sections)
    plan = EditPlanV0(
        source_transcript_ref="artifact://src",
        source_transcript_hash=transcript_text_hash(text),
        plan_id="p1",
        summary="fix corner",
        ops=[
            {
                "op_id": "op-1",
                "op_type": "replace_clause",
                "change_class": "semantic",
                "confidence": "high",
                "review_required": True,
                "reason": "faithful tie fix",
                "evidence_refs": [],
                "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(text)},
                "expected_old": {"old_excerpt": "NW corner"},
                "new_text": "NW corner of Section 2",
            }
        ],
    )
    report, output_document = apply_plan_to_sections(plan=plan, document=document)
    assert report.applied_count == 1
    assert [section.id for section in output_document.sections] == ["s1", "s2"]
    assert "Section 2" in output_document.sections[0].body
    assert output_document.sections[1].body.startswith("Thence South")


def test_apply_plan_to_sections_refuses_cross_section_replace() -> None:
    document = TranscriptDocumentV0(
        source_transcript_ref="artifact://src",
        sections=[
            TranscriptSectionV0(id="s1", body="alpha"),
            TranscriptSectionV0(id="s2", body="beta"),
        ],
    )
    text, _ = sections_to_text_with_index_map(document.sections)
    plan = EditPlanV0(
        source_transcript_ref="artifact://src",
        source_transcript_hash=transcript_text_hash(text),
        plan_id="p2",
        summary="cross section",
        ops=[
            {
                "op_id": "op-1",
                "op_type": "replace_span",
                "change_class": "structural",
                "confidence": "medium",
                "review_required": True,
                "reason": "cross section not allowed",
                "evidence_refs": [],
                "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(text)},
                "expected_old": {"old_excerpt": "alpha\n\nbeta"},
                "new_text": "gamma",
            }
        ],
    )
    report, _ = apply_plan_to_sections(plan=plan, document=document)
    assert report.refused_count == 1
    assert report.op_results[0].reason_code == "cross_section_edit_not_supported"


def test_persistence_saves_section_preserving_transcript_and_mapping_pointer(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    persistence = TranscriptionEditPersistenceService(root=root)
    source_payload = {
        "sections": [
            {"id": "s1", "body": "Beginning at NW corner."},
            {"id": "s2", "body": "Thence South 45E 100 feet to point of beginning."},
        ]
    }
    source = tmp_path / "source.json"
    source.write_text(json.dumps(source_payload), encoding="utf-8")
    source_text = "Beginning at NW corner.\n\nThence South 45E 100 feet to point of beginning."
    plan = EditPlanV0(
        source_transcript_ref=str(source),
        source_transcript_hash=transcript_text_hash(source_text),
        plan_id="p3",
        summary="fix text",
        ops=[
            {
                "op_id": "op-1",
                "op_type": "replace_line",
                "change_class": "normalization",
                "confidence": "high",
                "review_required": False,
                "reason": "normalize heading",
                "evidence_refs": [],
                "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(source_text)},
                "expected_old": {"old_excerpt": "NW"},
                "new_text": "Northwest",
            }
        ],
    )
    document = TranscriptDocumentV0(
        source_transcript_ref=str(source),
        source_transcript_hash=transcript_text_hash(source_text),
        sections=[
            TranscriptSectionV0(id="s1", body="Beginning at NW corner."),
            TranscriptSectionV0(id="s2", body="Thence South 45E 100 feet to point of beginning."),
        ],
    )
    source_ref = persistence.save_source_transcript_input(dossier_id="d1", document=document)
    apply_report, output_document = apply_plan_to_sections(plan=plan, document=document)
    edited_ref = persistence.save_edited_transcript(dossier_id="d1", document=output_document)
    pointer_ref = persistence.write_latest_transcript_for_mapping(
        dossier_id="d1",
        transcript_ref=edited_ref,
        transcript_hash=apply_report.output_transcript_hash,
        run_id="tx_edit_test",
    )
    assert Path(source_ref).exists()
    edited_path = Path(edited_ref)
    payload = json.loads(edited_path.read_text(encoding="utf-8"))
    assert "sections" in payload
    assert payload["sections"][0]["id"] == "s1"
    assert "Northwest corner" in payload["sections"][0]["body"]
    assert Path(pointer_ref).exists()




