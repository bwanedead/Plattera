"""Tests for deed-to-IR final package validation repair packets and minimum shape."""

from __future__ import annotations

import json
import tempfile

from domains.mapping.deed_to_ir.payloads.final_package_example import (
    build_prepare_deed_to_ir_final_package_explicit_example_request,
)
from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS
from tooling.mapping.deed_to_ir.final_package_preview_persistence import prepare_deed_to_ir_final_package
from tooling.mapping.deed_to_ir.final_package_preview_projection import (
    render_final_package_validation_timeline_lines,
)
from tooling.mapping.deed_to_ir.final_package_validation import (
    build_prepare_validation_repair_packet,
    build_rejected_payload_summary,
    compute_preserve_sections,
)
from tooling.mapping.deed_to_ir.test_final_package_preview import (
    _context,
    _patch_deed_root,
    _prepare_mapping,
    _valid_rows,
)


def test_rejected_payload_summary_reports_received_type_for_non_list_sections() -> None:
    summary = build_rejected_payload_summary(
        scope_results={"scope_id": "alpha", "status": "handoffable", "summary": "secret"},
        external_dependencies=[],
        closure_dimensions=[],
        notes=None,
    )
    assert summary["scope_results"] == {
        "count": 0,
        "row_keys": [],
        "received_type": "object",
    }
    assert summary["notes"]["received_type"] == "null"
    dumped = json.dumps(summary)
    assert "alpha" not in dumped
    assert "secret" not in dumped


def test_rejected_payload_summary_includes_counts_and_keys_not_values() -> None:
    summary = build_rejected_payload_summary(
        scope_results=[
            {"scope_id": "alpha", "status": "handoffable", "summary": "secret value"},
        ],
        external_dependencies=[
            {"dependency_id": "dep_1", "status": "missing", "summary": "wrong", "title": "nope"},
        ],
        closure_dimensions=[],
        notes=[{"note_id": "n1", "summary": "note secret"}],
    )
    dumped = json.dumps(summary)
    assert "secret value" not in dumped
    assert "note secret" not in dumped
    assert summary["scope_results"]["count"] == 1
    assert summary["scope_results"]["row_keys"] == [["scope_id", "status", "summary"]]
    assert summary["external_dependencies"]["row_keys"] == [
        ["dependency_id", "status", "summary", "title"]
    ]


def test_preserve_sections_excludes_invalid_section() -> None:
    errors = [
        {"path": "external_dependencies[0].affected_scope", "code": "missing", "message": "missing"},
        {"path": "external_dependencies[0].summary", "code": "extra_forbidden", "message": "extra"},
    ]
    preserve = compute_preserve_sections(
        errors,
        scope_results=[{"scope_id": "a", "status": "handoffable"}],
        external_dependencies=[{"dependency_id": "dep", "status": "missing"}],
        closure_dimensions=[{"dimension_id": "layer_1_deed_meaning_to_ir_fidelity", "status": "closed"}],
        notes=[{"note_id": "n1", "summary": "note"}],
    )
    assert preserve == ["scope_results", "closure_dimensions", "notes"]


def test_prepare_validation_refusal_includes_repair_packet(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            scope_results=[{"scope_id": "example_scope_1", "status": "handoffable"}],
            external_dependencies=[
                {
                    "dependency_id": "missing_source",
                    "status": "missing",
                    "summary": "wrong field",
                }
            ],
            closure_dimensions=[
                {"dimension_id": dimension_id, "status": "partial"}
                for dimension_id in sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
            ],
            notes=[{"note_id": "note_1", "summary": "keep me"}],
        )

        assert result["executed"] is False
        outputs = result["outputs"]
        assert outputs["validation_errors"]
        assert outputs["rejected_payload_summary"]["scope_results"]["count"] == 1
        assert outputs["row_contract_summary"]["external_dependencies"]["forbidden_common"] == [
            "title",
            "summary",
        ]
        assert outputs["repair_hint"]
        assert outputs["preserve_sections"] == ["scope_results", "closure_dimensions", "notes"]


def test_prepare_refuses_empty_scope_results(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        rows = _valid_rows()
        rows["scope_results"] = []

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **rows,
        )

        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "final_package_incomplete"
        assert "scope_results" in result["outputs"]["missing_sections"]


def test_prepare_refuses_empty_closure_dimensions(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        rows = _valid_rows()
        rows["closure_dimensions"] = []

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **rows,
        )

        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "final_package_incomplete"
        assert "closure_dimensions" in result["outputs"]["missing_sections"]
        assert result["outputs"]["missing_closure_dimensions"]


def test_prepare_refuses_missing_required_closure_dimension_ids(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        rows = _valid_rows()
        rows["closure_dimensions"] = [
            {"dimension_id": "layer_4_map_handoffability_scoped_completion", "status": "partial"}
        ]

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **rows,
        )

        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "final_package_incomplete"
        assert "layer_1_deed_meaning_to_ir_fidelity" in result["outputs"]["missing_closure_dimensions"]


def test_run11_hollow_shape_is_rejected(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            scope_results=[],
            external_dependencies=[
                {
                    "dependency_id": "missing_source",
                    "affected_scope": "example_scope_beta",
                    "description": "Fixed dependency row only.",
                    "status": "missing",
                }
            ],
            closure_dimensions=[],
            notes=[],
        )

        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "final_package_incomplete"


def test_timeline_renders_received_type_for_object_shaped_sections() -> None:
    outputs = build_prepare_validation_repair_packet(
        validation_errors=[
            {"path": "scope_results", "code": "list_type", "message": "Input should be a valid list"},
        ],
        scope_results={"scope_id": "unique_scope_token_xyz", "status": "handoffable"},
        external_dependencies=[],
        closure_dimensions=[],
        notes=[],
    )
    lines = render_final_package_validation_timeline_lines(outputs)
    body = "\n".join(lines)
    assert "scope_results: count=0 received_type=object keys=[]" in body
    assert "unique_scope_token_xyz" not in body


def test_timeline_renders_compact_validation_failure_details() -> None:
    outputs = build_prepare_validation_repair_packet(
        validation_errors=[
            {
                "path": "external_dependencies[0].affected_scope",
                "code": "missing",
                "message": "Field required",
            },
            {
                "path": "external_dependencies[0].summary",
                "code": "extra_forbidden",
                "message": "Extra inputs are not permitted",
            },
        ],
        scope_results=[{"scope_id": "a", "status": "handoffable", "summary": "x", "title": "y"}],
        external_dependencies=[{"dependency_id": "dep", "status": "missing", "summary": "bad"}],
        closure_dimensions=[
            {"dimension_id": "layer_1_deed_meaning_to_ir_fidelity", "status": "closed", "summary": "s"}
        ],
        notes=[{"note_id": "n1", "summary": "note"}],
    )
    lines = render_final_package_validation_timeline_lines(outputs)
    body = "\n".join(lines)
    assert "final_package_validation:" in body
    assert "external_dependencies[0].summary" in body
    assert "preserve_sections:" in body
    assert "scope_results" in body
    assert "secret" not in body


def test_prepare_example_contains_all_sections_without_practice_tokens() -> None:
    from domains.mapping.deed_to_ir.payloads.final_package_example import (
        build_prepare_deed_to_ir_final_package_explicit_example_request,
    )

    example = build_prepare_deed_to_ir_final_package_explicit_example_request()
    assert len(example["scope_results"]) == 2
    assert len(example["external_dependencies"]) == 1
    assert len(example["closure_dimensions"]) == 4
    assert len(example["notes"]) == 1
    dumped = json.dumps(example).lower()
    for forbidden in ("parcel_1", "parcel_2", "range 74", "range 75", "canal", "practice", "518", "542"):
        assert forbidden not in dumped
