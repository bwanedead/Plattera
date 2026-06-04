"""Tests for atom evidence worklist timeline rendering."""

from __future__ import annotations

from pathlib import Path

from harness.audit.atom_evidence_worklist_timeline import render_atom_evidence_worklist_timeline
from harness.audit.artifact_ref_links import ArtifactLinkContext
from harness.audit.run_audit_writer import RunAuditWriter


def _worklist_turn(*, priority_rows: list[dict], unmatched: list[dict] | None = None) -> dict:
    counts = {
        "atoms_total": 20,
        "open": 10,
        "closed": 10,
        "blocked": 1,
        "packet_ready_unused": 6,
        "packet_used_not_determined": 2,
        "unmatched_packet_refs": len(unmatched or []),
    }
    block: dict = {
        "kind": "atom_evidence_worklist",
        "counts": counts,
        "priority_rows": priority_rows,
    }
    if unmatched:
        block["unmatched_packet_refs"] = unmatched
    return {
        "turn_index": 6,
        "parse_ok": True,
        "prompt_observability_summary": {"atom_evidence_worklist": block},
    }


def test_timeline_renders_turn_six_style_unused_packets() -> None:
    ready_rows = [
        {
            "atom_id": f"p1_atom_{i}",
            "status": "open",
            "utilization_status": "open_packet_ready_unused",
            "packet_refs": [
                {
                    "crop_ref": f"image:derived:crop-p1_atom_{i}",
                    "overlay_ref": "image:derived:master-parcel1",
                    "source_alias": f"p1_atom_{i}",
                    "letter": "A",
                    "created_turn": 6,
                }
            ],
        }
        for i in range(6)
    ]
    used_rows = [
        {
            "atom_id": f"p1_used_{i}",
            "status": "open",
            "utilization_status": "open_packet_used_not_determined",
            "packet_refs": [
                {
                    "crop_ref": f"image:derived:crop-p1_used_{i}",
                    "overlay_ref": "image:derived:master-parcel1",
                    "source_alias": f"p1_used_{i}",
                    "created_turn": 6,
                    "delegate_refs": [
                        {
                            "delegate_ref": f"subtask:turn7:read_p1_used_{i}",
                            "delegate_status": "ambiguous",
                        }
                    ],
                }
            ],
        }
        for i in range(2)
    ]
    lines = render_atom_evidence_worklist_timeline(
        _worklist_turn(priority_rows=ready_rows + used_rows)
    )
    body = "\n".join(lines)
    assert "Atom Evidence Worklist:" in body
    assert "6 packet-ready-unused" in body
    assert "open packet ready unused:" in body
    assert "p1_atom_0 ->" in body
    assert "open packet used not determined:" in body
    assert "status ambiguous" in body
    assert "b64" not in body


def test_timeline_renders_unmatched_packet_with_delegate() -> None:
    lines = render_atom_evidence_worklist_timeline(
        _worklist_turn(
            priority_rows=[],
            unmatched=[
                {
                    "source_alias": "p1_orphan",
                    "crop_ref": "image:derived:crop-orphan",
                    "overlay_ref": "image:derived:master-1",
                    "created_turn": 6,
                    "delegate_refs": [
                        {
                            "delegate_ref": "subtask:turn7:read_orphan",
                            "delegate_status": "failed",
                        }
                    ],
                }
            ],
        )
    )
    body = "\n".join(lines)
    assert "unmatched packet refs:" in body
    assert "p1_orphan ->" in body
    assert "subtask:turn7:read_orphan" in body
    assert "status failed" in body


def test_timeline_renders_shared_evidence_without_alias_match_claim() -> None:
    lines = render_atom_evidence_worklist_timeline(
        _worklist_turn(
            priority_rows=[
                {
                    "atom_id": "p1_acreage",
                    "status": "open",
                    "utilization_status": "open_evidence_referenced_not_determined",
                    "packet_refs": [
                        {
                            "crop_ref": "image:derived:crop-other",
                            "overlay_ref": "image:derived:master-1",
                            "source_alias": "p1_other",
                            "match_kind": "shared_evidence_ref",
                            "created_turn": 6,
                        }
                    ],
                }
            ],
        )
    )
    body = "\n".join(lines)
    assert "open evidence referenced not determined:" in body
    assert "shared/cited crop" in body
    assert "alias p1_other" in body
    assert "direct alias" not in body.lower()


def test_timeline_integrates_with_human_timeline_and_links(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run-worklist")
    writer.observe_llm_io(
        _worklist_turn(
            priority_rows=[
                {
                    "atom_id": "p1_acreage",
                    "status": "open",
                    "utilization_status": "open_packet_ready_unused",
                    "packet_refs": [
                        {
                            "crop_ref": "image:derived:crop-acreage",
                            "overlay_ref": "image:derived:master-acreage",
                            "source_alias": "p1_acreage",
                            "created_turn": 6,
                        }
                    ],
                }
            ],
        )
    )
    timeline_path = tmp_path / "run-worklist" / "audit" / "human" / "timeline.md"
    body = timeline_path.read_text(encoding="utf-8")
    assert "Atom Evidence Worklist:" in body
    assert "image:derived:crop-acreage" in body
    assert "b64" not in body
    assert "data:image/" not in body


def test_render_with_link_context_formats_refs() -> None:
    context = ArtifactLinkContext(
        timeline_path=Path("audit/human/timeline.md"),
        ref_path_index={"image:derived:crop-acreage": "artifacts/crop-acreage.png"},
    )
    lines = render_atom_evidence_worklist_timeline(
        _worklist_turn(
            priority_rows=[
                {
                    "atom_id": "p1_acreage",
                    "status": "open",
                    "utilization_status": "open_packet_ready_unused",
                    "packet_refs": [
                        {
                            "crop_ref": "image:derived:crop-acreage",
                            "source_alias": "p1_acreage",
                            "created_turn": 6,
                        }
                    ],
                }
            ],
        ),
        link_context=context,
    )
    body = "\n".join(lines)
    assert "crop-acreage.png" in body or "image:derived:crop-acreage" in body
