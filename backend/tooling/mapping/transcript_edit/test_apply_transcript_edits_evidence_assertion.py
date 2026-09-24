"""Optional root evidence_refs is an exact assertion, not a second evidence lane."""

from __future__ import annotations

import json

import pytest

from domains.mapping.transcript_edit.execution.dossier_tool_specs import (
    build_dossier_transcript_edit_tool_specs,
)
from domains.mapping.transcript_edit.execution.tool_specs import (
    build_transcript_edit_tool_specs,
)
from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    ALLOWED_UNCERTAINTY_REASONS,
    TRANSCRIPT_EDIT_DECISIONS_FIELD,
)
from domains.mapping.transcript_edit.runtime_adapter.tool_refusal_boundary import (
    apply_tool_refusal_boundary,
    retryable_reason_codes_for_action,
)
from tooling.mapping.transcript_edit._apply_transcript_edits_test_helpers import (
    decision,
    root,
    save_base,
    seed_run,
)
from tooling.mapping.transcript_edit.apply_transcript_edits import apply_transcript_edits
from tooling.mapping.transcript_edit.apply_transcript_edits_contract import (
    APPLY_UNKNOWN_REQUEST_FIELDS_REPAIR_HINT,
    validate_apply_transcript_edits_request,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.paths import transcript_edit_revision_path
from tooling.mapping.transcript_edit.test_apply_transcript_edits_dossier import (
    _seed_apply_workspace,
)
from tooling.mapping.transcript_edit.working_revision_transaction import (
    current_working_head_ref,
)

_REF_A = "image:derived:synth-a"
_REF_B = "image:derived:synth-b"
_OMIT = object()


def _workspace(tmp_path, monkeypatch, ws: str, *, fresh: bool = True):
    dossiers = root(tmp_path, monkeypatch) if fresh else None
    dossier_id, transcription_id = "d1", "t1"
    if fresh:
        seed_run(dossiers, dossier_id, transcription_id)
    save_base(d=dossier_id, tx=transcription_id, ws=ws, source="Range 7 west")
    return dossier_id, transcription_id, ws


def _request(*, evidence_refs: list[str] | None = None, root_refs: object = _OMIT, **decision_kwargs):
    body = {
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "decisions": [decision(evidence_refs=evidence_refs, **decision_kwargs)],
    }
    if root_refs is not _OMIT:
        body["evidence_refs"] = root_refs
    return body


def _apply(dossier_id, transcription_id, ws, request):
    return apply_transcript_edits(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=ws,
        request=request,
    )


def _head(dossier_id, transcription_id, ws):
    return current_working_head_ref(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=ws,
    )


def _revision(dossier_id, transcription_id, ws, digits: str) -> dict:
    path = transcript_edit_revision_path(dossier_id, transcription_id, ws, digits)
    return json.loads(path.read_text(encoding="utf-8"))


def _decision_evidence(document: dict) -> list:
    payload = document["payload"]
    rows = payload[TRANSCRIPT_EDIT_DECISIONS_FIELD]["decisions"]
    return [list(row["evidence_refs"]) for row in rows]


def test_leaf_without_root_evidence_refs_is_unchanged(tmp_path, monkeypatch) -> None:
    dossier_id, transcription_id, ws = _workspace(tmp_path, monkeypatch, "ws-plain")
    out = _apply(dossier_id, transcription_id, ws, _request(evidence_refs=[_REF_A, _REF_B]))
    assert out["executed"] is True
    assert out["outputs"]["idempotent_replay"] is False
    assert out["outputs"]["evidence_refs"] == [_REF_A, _REF_B]
    assert _decision_evidence(_revision(dossier_id, transcription_id, ws, "0002")) == [
        [_REF_A, _REF_B]
    ]


def test_exact_root_assertion_matches_request_without_it(tmp_path, monkeypatch) -> None:
    plain_ids = _workspace(tmp_path, monkeypatch, "ws-plain-match")
    asserted_ids = _workspace(tmp_path, monkeypatch, "ws-asserted-match", fresh=False)
    plain_request = _request(evidence_refs=[_REF_B, _REF_A, _REF_B])
    asserted_request = _request(
        evidence_refs=[_REF_B, _REF_A, _REF_B],
        root_refs=[_REF_B, _REF_A],
    )
    assert (
        validate_apply_transcript_edits_request(plain_request).request_identity
        == validate_apply_transcript_edits_request(asserted_request).request_identity
    )
    plain = _apply(*plain_ids, plain_request)
    asserted = _apply(*asserted_ids, asserted_request)
    assert plain["executed"] is True and asserted["executed"] is True
    assert plain["outputs"]["evidence_refs"] == asserted["outputs"]["evidence_refs"] == [
        _REF_B,
        _REF_A,
    ]
    assert _decision_evidence(_revision(*plain_ids, "0002")) == _decision_evidence(
        _revision(*asserted_ids, "0002")
    )


def test_replay_identity_is_independent_of_valid_assertion_order(tmp_path, monkeypatch) -> None:
    dossier_id, transcription_id, ws = _workspace(tmp_path, monkeypatch, "ws-replay")
    plain = _request(evidence_refs=[_REF_A])
    asserted = _request(evidence_refs=[_REF_A], root_refs=[_REF_A])
    first = _apply(dossier_id, transcription_id, ws, plain)
    second = _apply(dossier_id, transcription_id, ws, asserted)
    assert first["outputs"]["idempotent_replay"] is False
    assert second["outputs"]["idempotent_replay"] is True
    assert second["outputs"]["working_draft_ref"] == first["outputs"]["working_draft_ref"]
    assert not transcript_edit_revision_path(dossier_id, transcription_id, ws, "0003").exists()

    other = _workspace(tmp_path, monkeypatch, "ws-replay-reverse", fresh=False)
    first_asserted = _apply(*other, asserted)
    second_plain = _apply(*other, plain)
    assert first_asserted["outputs"]["idempotent_replay"] is False
    assert second_plain["outputs"]["idempotent_replay"] is True
    assert not transcript_edit_revision_path(other[0], other[1], other[2], "0003").exists()


@pytest.mark.parametrize(
    "root_refs",
    [
        [_REF_A, _REF_B, "image:derived:synth-other"],
        [_REF_A],
        [_REF_A, _REF_A, _REF_B],
        [_REF_B, _REF_A],
        ["image:derived:synth-other"],
        [f" {_REF_A}", _REF_B],
        [_REF_A, f"{_REF_B} "],
        [f" {_REF_A} ", f" {_REF_B}"],
    ],
)
def test_inexact_root_assertion_refuses_without_write(tmp_path, monkeypatch, root_refs) -> None:
    dossier_id, transcription_id, ws = _workspace(tmp_path, monkeypatch, "ws-bad-assertion")
    out = _apply(
        dossier_id,
        transcription_id,
        ws,
        _request(evidence_refs=[_REF_A, _REF_B], root_refs=root_refs),
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "evidence_assertion_mismatch"
    assert _head(dossier_id, transcription_id, ws) == "transcript_edit:working:rev:0001"
    assert not transcript_edit_revision_path(dossier_id, transcription_id, ws, "0002").exists()


@pytest.mark.parametrize(
    "root_refs",
    [None, "image:derived:synth-a", {"ref": _REF_A}, True, 1, [_REF_A, 2], [_REF_A, "  "]],
)
def test_malformed_root_evidence_refs_refuse_without_coercion(
    tmp_path, monkeypatch, root_refs
) -> None:
    dossier_id, transcription_id, ws = _workspace(tmp_path, monkeypatch, "ws-malformed")
    out = _apply(
        dossier_id,
        transcription_id,
        ws,
        _request(evidence_refs=[_REF_A], root_refs=root_refs),
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] in {
        "invalid_string_list",
        "invalid_string_list_item",
    }
    assert _head(dossier_id, transcription_id, ws) == "transcript_edit:working:rev:0001"


def test_root_evidence_does_not_repair_missing_decision_evidence(tmp_path, monkeypatch) -> None:
    dossier_id, transcription_id, ws = _workspace(tmp_path, monkeypatch, "ws-earned")
    earned = decision(determination="earned", evidence_refs=[])
    out = _apply(
        dossier_id,
        transcription_id,
        ws,
        {
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [earned],
            "evidence_refs": [_REF_A],
        },
    )
    assert out["refusal"]["reason_code"] == "earned_requires_evidence_refs"
    missing = decision()
    del missing["evidence_refs"]
    refused = _apply(
        dossier_id,
        transcription_id,
        ws,
        {
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [missing],
            "evidence_refs": [_REF_A],
        },
    )
    assert refused["refusal"]["reason_code"] == "invalid_string_list"
    assert _head(dossier_id, transcription_id, ws) == "transcript_edit:working:rev:0001"


def test_unknown_root_field_hint_and_uncertainty_hint(tmp_path, monkeypatch) -> None:
    dossier_id, transcription_id, ws = _workspace(tmp_path, monkeypatch, "ws-hints")
    unknown = _apply(
        dossier_id,
        transcription_id,
        ws,
        {**_request(evidence_refs=[]), "note": "extra"},
    )
    assert unknown["refusal"]["reason_code"] == "unknown_request_fields"
    assert unknown["outputs"]["error"]["repair_hint"] == APPLY_UNKNOWN_REQUEST_FIELDS_REPAIR_HINT

    prose = _apply(
        dossier_id,
        transcription_id,
        ws,
        _request(uncertainty_reasons=["the mark was unclear"]),
    )
    assert prose["refusal"]["reason_code"] == "invalid_uncertainty_reason"
    hint = prose["outputs"]["error"]["repair_hint"]
    assert "verification_basis" in hint
    assert "the mark was unclear" not in hint
    bounded = apply_tool_refusal_boundary("apply_transcript_edits", prose)
    assert bounded["refusal"]["retryable"] is True
    assert "evidence_assertion_mismatch" in retryable_reason_codes_for_action(
        "apply_transcript_edits"
    )


def test_decision_whitespace_still_normalizes_and_root_whitespace_does_not(
    tmp_path, monkeypatch
) -> None:
    dossier_id, transcription_id, ws = _workspace(tmp_path, monkeypatch, "ws-decision-strip")
    padded_decision = f" {_REF_A} "
    out = _apply(
        dossier_id,
        transcription_id,
        ws,
        _request(evidence_refs=[padded_decision], root_refs=[_REF_A]),
    )
    assert out["executed"] is True
    assert out["outputs"]["evidence_refs"] == [_REF_A]
    assert _decision_evidence(_revision(dossier_id, transcription_id, ws, "0002")) == [[_REF_A]]

    refused_ids = _workspace(tmp_path, monkeypatch, "ws-root-space", fresh=False)
    refused = _apply(
        *refused_ids,
        _request(evidence_refs=[_REF_A], root_refs=[padded_decision]),
    )
    assert refused["executed"] is False
    assert refused["refusal"]["reason_code"] == "evidence_assertion_mismatch"
    assert _head(*refused_ids) == "transcript_edit:working:rev:0001"
    assert not transcript_edit_revision_path(*refused_ids, "0002").exists()


def test_dossier_qualified_assertion_advances_lineage_and_unqualified_refuses(
    tmp_path, monkeypatch
) -> None:
    dossier_id, ws, base_ref, apply = _seed_apply_workspace(
        tmp_path, monkeypatch, ws="ws-dossier-assert"
    )
    qualified = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="t0:raw:draft_1",
    )
    out = apply(
        {
            "base_revision_ref": base_ref,
            "decisions": [
                decision(
                    evidence_refs=[qualified],
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "Range 7 west",
                            "replacement_text": "Range 77 west",
                        }
                    ],
                )
            ],
            "evidence_refs": [qualified],
        }
    )
    assert out["executed"] is True, out
    assert transcript_edit_revision_path(dossier_id, "tx_a", ws, "0002").exists()

    unqualified = apply(
        {
            "base_revision_ref": base_ref,
            "decisions": [decision(evidence_refs=[])],
            "evidence_refs": ["image:derived:synth-a"],
        }
    )
    assert unqualified["executed"] is False
    assert unqualified["refusal"]["reason_code"] == "dossier_ref_required"
    assert not transcript_edit_revision_path(dossier_id, "tx_a", ws, "0003").exists()


@pytest.mark.parametrize("pad", [" {ref}", "{ref} ", " {ref} "])
def test_dossier_whitespace_altered_root_ref_refuses_without_write(
    tmp_path, monkeypatch, pad: str
) -> None:
    dossier_id, _ws, base_ref, apply = _seed_apply_workspace(
        tmp_path, monkeypatch, ws="ws-dossier-space"
    )
    qualified = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="t0:raw:draft_1",
    )
    out = apply(
        {
            "base_revision_ref": base_ref,
            "decisions": [decision(evidence_refs=[qualified])],
            "evidence_refs": [pad.format(ref=qualified)],
        }
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "evidence_assertion_mismatch"
    assert not transcript_edit_revision_path(dossier_id, "tx_a", "ws-dossier-space", "0002").exists()


def test_dossier_unknown_field_hint_and_uncertainty_hint_survive(tmp_path, monkeypatch) -> None:
    _dossier_id, _ws, base_ref, apply = _seed_apply_workspace(
        tmp_path, monkeypatch, ws="ws-dossier-hint"
    )
    unknown = apply(
        {
            "base_revision_ref": base_ref,
            "decisions": [decision(evidence_refs=[])],
            "extra": True,
        }
    )
    assert unknown["refusal"]["reason_code"] == "unknown_request_fields"
    assert unknown["outputs"]["error"]["repair_hint"] == APPLY_UNKNOWN_REQUEST_FIELDS_REPAIR_HINT
    assert "\\" not in unknown["outputs"]["error"]["repair_hint"]

    prose = apply(
        {
            "base_revision_ref": base_ref,
            "decisions": [decision(evidence_refs=[], uncertainty_reasons=["free prose"])],
        }
    )
    assert prose["refusal"]["reason_code"] == "invalid_uncertainty_reason"
    assert "verification_basis" in prose["outputs"]["error"]["repair_hint"]


def test_leaf_and_dossier_shapes_agree_on_accepted_grammar() -> None:
    leaf = next(spec for spec in build_transcript_edit_tool_specs() if spec.tool_id == "apply_transcript_edits")
    dossier = next(
        spec
        for spec in build_dossier_transcript_edit_tool_specs()
        if spec.tool_id == "apply_transcript_edits"
    )
    for spec in (leaf, dossier):
        shape = spec.expected_request_json_shape
        assert "evidence_refs" in shape["properties"]
        assert "evidence_refs" not in shape["required"]
        enum = shape["properties"]["decisions"]["items"]["properties"]["uncertainty_reasons"][
            "items"
        ]["enum"]
        assert enum == sorted(ALLOWED_UNCERTAINTY_REASONS)
        assert "not an evidence source" in spec.expected_request_shape.lower()
        for code in sorted(ALLOWED_UNCERTAINTY_REASONS):
            assert code in spec.expected_request_shape
    assert leaf.expected_request_json_shape["properties"]["evidence_refs"]["type"] == "array"
    assert (
        dossier.expected_request_json_shape["properties"]["evidence_refs"]
        == leaf.expected_request_json_shape["properties"]["evidence_refs"]
    )
