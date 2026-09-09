"""MAPDEP-BR-026: provisional decision continuity (schema v2) + compact handoff."""

from __future__ import annotations

import json

import pytest

from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    MAX_DECISIONS_PER_REQUEST,
    MAX_PERSISTED_TRANSCRIPT_EDIT_DECISIONS,
    TRANSCRIPT_EDIT_DECISIONS_FIELD,
    TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION,
)
from tooling.mapping.deed_to_ir.transcript_handoff_loading import (
    TranscriptHandoffLoadError,
    load_transcript_edit_output_handoff,
)
from tooling.mapping.transcript_edit._apply_transcript_edits_test_helpers import (
    decision,
    root,
    save_base,
    seed_run,
)
from tooling.mapping.transcript_edit.apply_transcript_edits import apply_transcript_edits
from tooling.mapping.transcript_edit.apply_transcript_edits_contract import (
    ApplyTranscriptEditsContractError,
    validate_apply_transcript_edits_request,
)
from tooling.mapping.transcript_edit.draft_persistence import publish_transcript_edit_output
from tooling.mapping.transcript_edit.paths import (
    transcript_edit_output_path,
    transcript_edit_revision_path,
)
from tooling.mapping.transcript_edit.transcript_edit_decision_summary import (
    TranscriptEditDecisionProjectionError,
    project_transcript_edit_decision_summary,
)
from tooling.mapping.transcript_edit.transcript_edit_decisions_validate import (
    PersistedProvenanceError,
    validate_persisted_transcript_edit_decisions,
)


def _persisted_record(
    *,
    decision_id: str,
    determination: str,
    uncertainty_reasons: list[str],
    expected: str = "Range 7 west",
    replacement: str = "Range 77 west",
    evidence_refs: list[str] | None = None,
    candidate_values: list[str] | None = None,
    basis: str = "basis",
) -> dict:
    body: dict = {
        "decision_id": decision_id,
        "determination": determination,
        "uncertainty_reasons": list(uncertainty_reasons),
        "verification_basis": basis,
        "evidence_refs": evidence_refs if evidence_refs is not None else [],
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "edits": [
            {
                "lane": "source_transcript_verbatim",
                "expected_text": expected,
                "replacement_text": replacement,
                "start_offset": 0,
                "end_offset": len(replacement),
            }
        ],
    }
    if candidate_values is not None:
        body["candidate_values"] = list(candidate_values)
    return body


def test_valid_provisional_and_earned_v2_contract():
    provisional = validate_apply_transcript_edits_request(
        {
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    determination="provisional",
                    uncertainty_reasons=["observer_disagreement"],
                    candidate_values=["1703", "180.3"],
                )
            ],
        }
    )
    assert provisional.decisions[0].uncertainty_reasons == ("observer_disagreement",)

    earned = validate_apply_transcript_edits_request(
        {
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    determination="earned",
                    uncertainty_reasons=[],
                    evidence_refs=["image:derived:focused"],
                )
            ],
        }
    )
    assert earned.decisions[0].uncertainty_reasons == ()
    assert earned.decisions[0].evidence_refs == ("image:derived:focused",)


def test_provisional_without_reasons_and_earned_with_reasons_refuse():
    with pytest.raises(ApplyTranscriptEditsContractError) as missing:
        validate_apply_transcript_edits_request(
            {
                "base_revision_ref": "transcript_edit:working:rev:0001",
                "decisions": [
                    {
                        "decision_id": "d1",
                        "determination": "provisional",
                        "verification_basis": "ok",
                        "evidence_refs": [],
                        "edits": [
                            {
                                "lane": "source_transcript_verbatim",
                                "expected_text": "a",
                                "replacement_text": "b",
                            }
                        ],
                    }
                ],
            }
        )
    assert missing.value.reason_code == "uncertainty_reasons_required"

    with pytest.raises(ApplyTranscriptEditsContractError) as empty_prov:
        validate_apply_transcript_edits_request(
            {
                "base_revision_ref": "transcript_edit:working:rev:0001",
                "decisions": [decision(uncertainty_reasons=[])],
            }
        )
    assert empty_prov.value.reason_code == "provisional_requires_uncertainty_reasons"

    with pytest.raises(ApplyTranscriptEditsContractError) as earned_reasons:
        validate_apply_transcript_edits_request(
            {
                "base_revision_ref": "transcript_edit:working:rev:0001",
                "decisions": [
                    decision(
                        determination="earned",
                        uncertainty_reasons=["source_ambiguous"],
                        evidence_refs=["image:derived:x"],
                    )
                ],
            }
        )
    assert earned_reasons.value.reason_code == "earned_requires_empty_uncertainty_reasons"


@pytest.mark.parametrize(
    "reasons,code",
    [
        (["not_a_reason"], "invalid_uncertainty_reason"),
        (["source_ambiguous", "source_ambiguous"], "duplicate_uncertainty_reason"),
        ([123], "invalid_uncertainty_reason"),
        (
            [
                "observer_disagreement",
                "source_ambiguous",
                "packet_insufficient",
                "context_insufficient",
                "evidence_incomplete",
            ],
            "too_many_uncertainty_reasons",
        ),
    ],
)
def test_malformed_uncertainty_reasons_refuse(reasons, code):
    with pytest.raises(ApplyTranscriptEditsContractError) as raised:
        validate_apply_transcript_edits_request(
            {
                "base_revision_ref": "transcript_edit:working:rev:0001",
                "decisions": [decision(uncertainty_reasons=reasons)],
            }
        )
    assert raised.value.reason_code == code


def test_pre_v2_managed_provenance_refuses_without_mutation(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.paths import transcript_edit_latest_pointer_path
    from tooling.mapping.transcript_edit.working_revision_atomic_io import (
        compact_dumps,
        content_sha256_of_doc,
    )

    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-prev2"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west")
    rev_path = transcript_edit_revision_path(d, tx, ws, "0001")
    doc = json.loads(rev_path.read_text(encoding="utf-8"))
    doc["payload"][TRANSCRIPT_EDIT_DECISIONS_FIELD] = {
        "schema_version": 1,
        "decisions": [
            {
                "decision_id": "legacy",
                "determination": "provisional",
                "verification_basis": "basis",
                "evidence_refs": [],
                "base_revision_ref": "transcript_edit:working:rev:0001",
                "edits": [
                    {
                        "lane": "source_transcript_verbatim",
                        "expected_text": "Range 7 west",
                        "replacement_text": "Range 7 west",
                        "start_offset": 0,
                        "end_offset": 13,
                    }
                ],
            }
        ],
    }
    body = json.dumps(doc, indent=2, sort_keys=True, allow_nan=False) + "\n"
    rev_path.write_text(body, encoding="utf-8")
    latest_path = transcript_edit_latest_pointer_path(d, tx, ws)
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["content_sha256"] = content_sha256_of_doc(doc)
    latest["byte_length"] = len(compact_dumps(doc).encode("utf-8"))
    latest_path.write_text(
        json.dumps(latest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    before = rev_path.read_bytes()

    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [decision()],
        },
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "unsupported_provenance_schema"
    assert rev_path.read_bytes() == before
    assert not transcript_edit_revision_path(d, tx, ws, "0002").exists()

    with pytest.raises(PersistedProvenanceError) as raised:
        validate_persisted_transcript_edit_decisions(payload=doc["payload"])
    assert raised.value.reason_code == "unsupported_provenance_schema"


def test_stable_id_supersession_lifecycle(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-life"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="AAA BBB CCC")

    first = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    decision_id="focus",
                    uncertainty_reasons=["observer_disagreement"],
                    candidate_values=["AAA", "XXX"],
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "AAA",
                            "replacement_text": "XXX",
                        }
                    ],
                ),
                decision(
                    decision_id="keep",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "CCC",
                            "replacement_text": "ZZZ",
                        }
                    ],
                ),
            ],
        },
    )
    assert first["executed"] is True
    rev2 = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    assert rev2["payload"]["source_transcript_verbatim"] == "XXX BBB ZZZ"
    by_id = {
        row["decision_id"]: row
        for row in rev2["payload"][TRANSCRIPT_EDIT_DECISIONS_FIELD]["decisions"]
    }
    assert set(by_id) == {"focus", "keep"}
    assert by_id["focus"]["determination"] == "provisional"
    assert by_id["focus"]["uncertainty_reasons"] == ["observer_disagreement"]

    # provisional → revised provisional (same id)
    revised = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0002",
            "decisions": [
                decision(
                    decision_id="focus",
                    uncertainty_reasons=["source_ambiguous"],
                    candidate_values=["XXX", "YYY"],
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "XXX",
                            "replacement_text": "YYY",
                        }
                    ],
                )
            ],
        },
    )
    assert revised["executed"] is True
    rev3 = json.loads(transcript_edit_revision_path(d, tx, ws, "0003").read_text(encoding="utf-8"))
    rows3 = rev3["payload"][TRANSCRIPT_EDIT_DECISIONS_FIELD]["decisions"]
    assert [r["decision_id"] for r in rows3].count("focus") == 1
    by_id3 = {r["decision_id"]: r for r in rows3}
    assert by_id3["focus"]["uncertainty_reasons"] == ["source_ambiguous"]
    assert by_id3["focus"]["edits"][0]["replacement_text"] == "YYY"
    assert by_id3["keep"]["determination"] == "provisional"
    assert rev3["payload"]["source_transcript_verbatim"] == "YYY BBB ZZZ"

    # provisional → earned (same id)
    earned = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0003",
            "decisions": [
                decision(
                    decision_id="focus",
                    determination="earned",
                    uncertainty_reasons=[],
                    evidence_refs=["image:derived:earn"],
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "YYY",
                            "replacement_text": "YYY",
                        }
                    ],
                )
            ],
        },
    )
    assert earned["executed"] is True
    rev4 = json.loads(transcript_edit_revision_path(d, tx, ws, "0004").read_text(encoding="utf-8"))
    by_id4 = {
        r["decision_id"]: r
        for r in rev4["payload"][TRANSCRIPT_EDIT_DECISIONS_FIELD]["decisions"]
    }
    assert by_id4["focus"]["determination"] == "earned"
    assert by_id4["focus"]["uncertainty_reasons"] == []
    assert by_id4["keep"]["decision_id"] == "keep"

    # earned → corrected provisional
    corrected = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0004",
            "decisions": [
                decision(
                    decision_id="focus",
                    determination="provisional",
                    uncertainty_reasons=["evidence_incomplete"],
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "YYY",
                            "replacement_text": "QQQ",
                        }
                    ],
                )
            ],
        },
    )
    assert corrected["executed"] is True
    rev5 = json.loads(transcript_edit_revision_path(d, tx, ws, "0005").read_text(encoding="utf-8"))
    by_id5 = {
        r["decision_id"]: r
        for r in rev5["payload"][TRANSCRIPT_EDIT_DECISIONS_FIELD]["decisions"]
    }
    assert by_id5["focus"]["determination"] == "provisional"
    assert by_id5["focus"]["uncertainty_reasons"] == ["evidence_incomplete"]
    assert rev5["payload"]["source_transcript_verbatim"] == "QQQ BBB ZZZ"

    # Immutable prior revision retains prior posture
    assert by_id4["focus"]["determination"] == "earned"
    assert by_id3["focus"]["uncertainty_reasons"] == ["source_ambiguous"]
    assert len(by_id5) == 2


def test_request_vs_persisted_capacity_separation(tmp_path, monkeypatch):
    assert MAX_PERSISTED_TRANSCRIPT_EDIT_DECISIONS > MAX_DECISIONS_PER_REQUEST

    import tooling.mapping.transcript_edit.apply_transcript_edits_engine as engine_mod
    import tooling.mapping.transcript_edit.transcript_edit_decisions_validate as validate_mod

    monkeypatch.setattr(engine_mod, "MAX_PERSISTED_TRANSCRIPT_EDIT_DECISIONS", 2)
    monkeypatch.setattr(validate_mod, "MAX_PERSISTED_TRANSCRIPT_EDIT_DECISIONS", 2)

    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-cap"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="AAA BBB CCC")

    too_many_request = {
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "decisions": [
            decision(
                decision_id=f"r{i}",
                edits=[
                    {
                        "lane": "source_transcript_verbatim",
                        "expected_text": "AAA",
                        "replacement_text": "AAA",
                    }
                ],
            )
            for i in range(MAX_DECISIONS_PER_REQUEST + 1)
        ],
    }
    refused_req = apply_transcript_edits(
        dossier_id=d, transcription_id=tx, workspace_id=ws, request=too_many_request
    )
    assert refused_req["executed"] is False
    assert refused_req["refusal"]["reason_code"] == "too_many_decisions"

    filled = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    decision_id="p0",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "AAA",
                            "replacement_text": "XXX",
                        }
                    ],
                ),
                decision(
                    decision_id="p1",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "BBB",
                            "replacement_text": "YYY",
                        }
                    ],
                ),
            ],
        },
    )
    assert filled["executed"] is True
    before = transcript_edit_revision_path(d, tx, ws, "0002").read_bytes()

    overflow = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0002",
            "decisions": [
                decision(
                    decision_id="overflow",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "CCC",
                            "replacement_text": "ZZZ",
                        }
                    ],
                )
            ],
        },
    )
    assert overflow["executed"] is False
    assert overflow["refusal"]["reason_code"] == "too_many_persisted_decisions"
    assert transcript_edit_revision_path(d, tx, ws, "0002").read_bytes() == before
    assert not transcript_edit_revision_path(d, tx, ws, "0003").exists()


def test_projector_provisional_priority_and_omission_counts():
    payload = {
        TRANSCRIPT_EDIT_DECISIONS_FIELD: {
            "schema_version": 2,
            "decisions": [
                _persisted_record(
                    decision_id="e1",
                    determination="earned",
                    uncertainty_reasons=[],
                    evidence_refs=["image:derived:e"],
                    replacement="earned-text",
                    expected="earned-text",
                ),
                _persisted_record(
                    decision_id="p1",
                    determination="provisional",
                    uncertainty_reasons=["observer_disagreement"],
                    candidate_values=["a", "b"],
                    replacement="prov-text",
                    expected="prov-text",
                ),
            ],
        },
    }
    summary = project_transcript_edit_decision_summary(
        sources=[{"payload": payload, "segment_id": "seg-a"}],
        max_rows=1,
    )
    assert summary["counts"]["source"] == 2
    assert summary["counts"]["retained"] == 1
    assert summary["counts"]["omitted"] == 1
    assert summary["counts"]["provisional"] == 1
    assert summary["counts"]["earned"] == 0
    assert summary["decisions"][0]["decision_id"] == "p1"
    assert summary["decisions"][0]["segment_id"] == "seg-a"
    assert "path" not in summary["decisions"][0]
    assert "absolute_path" not in summary["decisions"][0]


def test_projector_rejects_bound_smaller_than_minimum_envelope():
    from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
        MAX_DECISION_SUMMARY_SERIALIZED_CHARS,
    )
    from tooling.mapping.transcript_edit.transcript_edit_decision_summary import (
        TranscriptEditDecisionProjectionError,
        minimum_decision_summary_serialized_chars,
        project_transcript_edit_decision_summary,
    )

    minimum = minimum_decision_summary_serialized_chars()
    assert minimum > 0

    with pytest.raises(TranscriptEditDecisionProjectionError) as too_small:
        project_transcript_edit_decision_summary(
            sources=[{"payload": {}}],
            max_serialized_chars=minimum - 1,
        )
    assert too_small.value.reason_code == "projection_bound_too_small"

    exact = project_transcript_edit_decision_summary(
        sources=[{"payload": {}}],
        max_serialized_chars=minimum,
    )
    assert exact["counts"]["source"] == 0
    assert exact["decisions"] == []
    assert (
        len(
            __import__("json").dumps(
                exact, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        )
        == minimum
    )

    normal = project_transcript_edit_decision_summary(sources=[{"payload": {}}])
    normal_ser = __import__("json").dumps(
        normal, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    assert len(normal_ser) <= MAX_DECISION_SUMMARY_SERIALIZED_CHARS
    assert len(normal_ser) == minimum


def test_projector_oversized_replacement_records_omission_count():
    long_text = "x" * 200
    payload = {
        TRANSCRIPT_EDIT_DECISIONS_FIELD: {
            "schema_version": 2,
            "decisions": [
                _persisted_record(
                    decision_id="big",
                    determination="provisional",
                    uncertainty_reasons=["other"],
                    expected=long_text,
                    replacement=long_text,
                )
            ],
        }
    }
    summary = project_transcript_edit_decision_summary(sources=[{"payload": payload}])
    assert summary["counts"]["source"] == 1
    assert summary["counts"]["retained"] == 1
    assert summary["counts"]["omitted"] == 0
    row = summary["decisions"][0]
    assert row["replacements"] == []
    assert row["replacement_edits_omitted_count"] == 1


def test_projector_serialized_ceiling_and_collection_omissions():
    import json

    from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
        MAX_DECISION_SUMMARY_CANDIDATES,
        MAX_DECISION_SUMMARY_EVIDENCE_REFS,
        MAX_DECISION_SUMMARY_SERIALIZED_CHARS,
    )

    candidates = [f"cand-{i}" for i in range(MAX_DECISION_SUMMARY_CANDIDATES + 3)]
    evidence = [f"image:derived:ref-{i}" for i in range(MAX_DECISION_SUMMARY_EVIDENCE_REFS + 4)]
    payload = {
        TRANSCRIPT_EDIT_DECISIONS_FIELD: {
            "schema_version": 2,
            "decisions": [
                {
                    **_persisted_record(
                        decision_id="p1",
                        determination="provisional",
                        uncertainty_reasons=["observer_disagreement"],
                        candidate_values=candidates,
                        evidence_refs=evidence,
                        expected="short",
                        replacement="short",
                    ),
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "short",
                            "replacement_text": "short",
                            "start_offset": 0,
                            "end_offset": 5,
                        },
                        {
                            "lane": "normalized_or_mapping_transcript",
                            "expected_text": "norm",
                            "replacement_text": "norm2",
                            "start_offset": 0,
                            "end_offset": 5,
                        },
                    ],
                },
                _persisted_record(
                    decision_id="e1",
                    determination="earned",
                    uncertainty_reasons=[],
                    evidence_refs=["image:derived:earn"],
                    expected="earn",
                    replacement="earn",
                ),
            ],
        }
    }
    # Force pressure with a tiny serialized ceiling while keeping both rows candidate.
    summary = project_transcript_edit_decision_summary(
        sources=[{"payload": payload}],
        max_serialized_chars=900,
    )
    assert summary["counts"]["source"] == summary["counts"]["retained"] + summary["counts"][
        "omitted"
    ]
    assert summary["counts"]["source_provisional"] == 1
    assert summary["counts"]["source_earned"] == 1
    serialized = json.dumps(
        summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    assert len(serialized) <= 900
    # Full-cap path still respects the hard domain ceiling.
    full = project_transcript_edit_decision_summary(sources=[{"payload": payload}])
    full_ser = json.dumps(
        full, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    assert len(full_ser) <= MAX_DECISION_SUMMARY_SERIALIZED_CHARS
    row = next(r for r in full["decisions"] if r["decision_id"] == "p1")
    assert len(row["candidate_values"]) == MAX_DECISION_SUMMARY_CANDIDATES
    assert row["candidate_values_omitted_count"] == 3
    assert len(row["evidence_refs"]) == MAX_DECISION_SUMMARY_EVIDENCE_REFS
    assert row["evidence_refs_omitted_count"] == 4
    assert len(row["replacements"]) == 2
    assert {r["lane"] for r in row["replacements"]} == {
        "source_transcript_verbatim",
        "normalized_or_mapping_transcript",
    }


def test_leaf_publish_handoff_preserves_compact_provisional(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-pub"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west")
    applied = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    uncertainty_reasons=["observer_disagreement"],
                    candidate_values=["7", "77"],
                    evidence_refs=["image:derived:focused"],
                )
            ],
        },
    )
    assert applied["executed"] is True
    pub = publish_transcript_edit_output(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        source_revision_ref="transcript_edit:working:rev:0002",
    )
    assert pub["executed"] is True
    loaded = load_transcript_edit_output_handoff(
        output_path=transcript_edit_output_path(d, tx, ws)
    )
    summary = loaded["transcript_edit_decision_summary"]
    assert summary["schema_version"] == 2
    assert summary["counts"]["source"] == 1
    assert summary["counts"]["provisional"] == 1
    row = summary["decisions"][0]
    assert row["decision_id"] == "d1"
    assert row["determination"] == "provisional"
    assert row["uncertainty_reasons"] == ["observer_disagreement"]
    assert row["candidate_values"] == ["7", "77"]
    assert "image:derived:focused" in row["evidence_refs"]
    assert row["replacements"] == [
        {
            "lane": "source_transcript_verbatim",
            "replacement_text": "Range 77 west",
        }
    ]
    dumped = json.dumps(loaded)
    assert "absolute_path" not in dumped
    assert str(tmp_path) not in dumped or "dossiers_data" not in row


def test_dossier_ordered_segment_aware_projection():
    sources = [
        {
            "segment_id": "seg-1",
            "transcription_id": "tx_a",
            "payload": {
                TRANSCRIPT_EDIT_DECISIONS_FIELD: {
                    "schema_version": 2,
                    "decisions": [
                        _persisted_record(
                            decision_id="a",
                            determination="earned",
                            uncertainty_reasons=[],
                            evidence_refs=["image:derived:a"],
                        )
                    ],
                }
            },
        },
        {
            "segment_id": "seg-2",
            "transcription_id": "tx_b",
            "payload": {
                TRANSCRIPT_EDIT_DECISIONS_FIELD: {
                    "schema_version": 2,
                    "decisions": [
                        _persisted_record(
                            decision_id="b",
                            determination="provisional",
                            uncertainty_reasons=["packet_insufficient"],
                        )
                    ],
                }
            },
        },
    ]
    summary = project_transcript_edit_decision_summary(sources=sources, max_rows=2)
    assert summary["counts"]["source"] == 2
    # Provisional prioritized under pressure ordering even if later in source order.
    assert [r["decision_id"] for r in summary["decisions"]] == ["b", "a"]
    assert summary["decisions"][0]["segment_id"] == "seg-2"
    assert summary["decisions"][1]["segment_id"] == "seg-1"


def test_malformed_provenance_cannot_silently_disappear_from_handoff(tmp_path):
    output = tmp_path / "output.json"
    output.write_text(
        json.dumps(
            {
                "published_at": "2026-01-01T00:00:00Z",
                "source_revision_ref": "transcript_edit:working:rev:0001",
                "revision_snapshot": {
                    "ref_id": "transcript_edit:working:rev:0001",
                    "payload": {
                        "source_transcript_verbatim": "x",
                        TRANSCRIPT_EDIT_DECISIONS_FIELD: {
                            "schema_version": 1,
                            "decisions": [],
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(TranscriptHandoffLoadError) as raised:
        load_transcript_edit_output_handoff(output_path=output)
    assert "unsupported_provenance_schema" in str(raised.value)


def test_stale_base_and_replay_unchanged(tmp_path, monkeypatch):
    dossiers = root(tmp_path, monkeypatch)
    d, tx, ws = "d1", "t1", "ws-replay"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source="Range 7 west")
    req = {
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "decisions": [decision()],
    }
    first = apply_transcript_edits(
        dossier_id=d, transcription_id=tx, workspace_id=ws, request=req
    )
    assert first["executed"] is True
    second = apply_transcript_edits(
        dossier_id=d, transcription_id=tx, workspace_id=ws, request=req
    )
    assert second["executed"] is True
    assert second["outputs"]["working_draft_ref"] == first["outputs"]["working_draft_ref"]
    stale = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    decision_id="other",
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": "Range 77 west",
                            "replacement_text": "Range 8 west",
                        }
                    ],
                )
            ],
        },
    )
    assert stale["executed"] is False
    assert stale["refusal"]["reason_code"] == "stale_base_revision"


def test_host_binary_fields_cannot_enter_compact_handoff():
    with pytest.raises(TranscriptEditDecisionProjectionError):
        project_transcript_edit_decision_summary(
            sources=[
                {
                    "payload": {
                        TRANSCRIPT_EDIT_DECISIONS_FIELD: {
                            "schema_version": 2,
                            "decisions": [
                                {
                                    **_persisted_record(
                                        decision_id="bad",
                                        determination="provisional",
                                        uncertainty_reasons=["other"],
                                    ),
                                    "absolute_path": "C:/secret",
                                }
                            ],
                        }
                    }
                }
            ]
        )
