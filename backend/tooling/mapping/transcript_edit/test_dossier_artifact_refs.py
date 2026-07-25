"""Tests for dossier-qualified artifact ref grammar and runtime resolution."""

from __future__ import annotations

import pytest

from tooling.mapping.transcript_edit.dossier_artifact_refs import (
    DossierArtifactRefError,
    DossierArtifactRefTarget,
    build_dossier_artifact_ref_index,
    parse_dossier_qualified_ref,
    qualify_leaf_ref,
)


def _index(*, entries=None, bindings=None, dossier_id: str = "d1"):
    bindings = frozenset(bindings or {("seg_a", "tx_a"), ("seg_b", "tx_b")})
    return build_dossier_artifact_ref_index(
        dossier_id=dossier_id,
        topology_fingerprint="fp-test",
        entries=entries or [],
        run_bindings=bindings,
    )


def test_exact_startup_ref_still_resolves() -> None:
    q = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    index = _index(
        entries=[
            (
                q,
                DossierArtifactRefTarget(
                    segment_id="seg_a",
                    transcription_id="tx_a",
                    leaf_ref="t0:raw:draft_1",
                ),
            )
        ]
    )
    assert index.resolve(q).leaf_ref == "t0:raw:draft_1"


def test_valid_qualified_working_revision_resolves() -> None:
    index = _index()
    q = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="transcript_edit:working:rev:0007",
    )
    target = index.resolve(q)
    assert target.segment_id == "seg_a"
    assert target.transcription_id == "tx_a"
    assert target.leaf_ref == "transcript_edit:working:rev:0007"


def test_aggregate_working_ref_is_runtime_resolvable() -> None:
    index = _index()
    q = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="transcript_edit:working",
    )
    assert index.resolve(q).leaf_ref == "transcript_edit:working"


def test_valid_qualified_derived_ref_resolves() -> None:
    index = _index()
    opaque = "a" * 32
    q = qualify_leaf_ref(
        segment_id="seg_b",
        transcription_id="tx_b",
        leaf_ref=f"image:derived:{opaque}",
    )
    target = index.resolve(q)
    assert target.leaf_ref == f"image:derived:{opaque}"


def test_unknown_segment_run_refuses() -> None:
    index = _index()
    q = qualify_leaf_ref(
        segment_id="seg_missing",
        transcription_id="tx_a",
        leaf_ref="transcript_edit:working:rev:0001",
    )
    with pytest.raises(DossierArtifactRefError) as exc:
        index.resolve(q)
    assert exc.value.code == "dossier_ref_run_not_in_topology"


def test_unsupported_dynamic_leaf_kind_refuses() -> None:
    index = _index()
    q = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="t0:raw:draft_1",
    )
    with pytest.raises(DossierArtifactRefError) as exc:
        index.resolve(q)
    assert exc.value.code == "dossier_ref_kind_not_runtime_resolvable"


def test_malformed_revision_digits_refuse() -> None:
    index = _index()
    q = (
        "dossier_segment:seg_a:run:tx_a:transcript_edit:working:rev:12"
    )
    with pytest.raises(DossierArtifactRefError) as exc:
        index.resolve(q)
    assert exc.value.code == "dossier_base_revision_invalid"


def test_parse_rejects_non_dossier_grammar() -> None:
    with pytest.raises(DossierArtifactRefError) as exc:
        parse_dossier_qualified_ref("transcript_edit:working:rev:0001")
    assert exc.value.code == "dossier_ref_invalid"


def test_index_entries_must_belong_to_run_bindings() -> None:
    q = qualify_leaf_ref(segment_id="seg_x", transcription_id="tx_x", leaf_ref="t0:raw:draft_1")
    with pytest.raises(DossierArtifactRefError) as exc:
        build_dossier_artifact_ref_index(
            dossier_id="d1",
            topology_fingerprint="fp",
            entries=[
                (
                    q,
                    DossierArtifactRefTarget(
                        segment_id="seg_x",
                        transcription_id="tx_x",
                        leaf_ref="t0:raw:draft_1",
                    ),
                )
            ],
            run_bindings=frozenset({("seg_a", "tx_a")}),
        )
    assert exc.value.code == "dossier_ref_run_not_in_topology"


def test_empty_index_still_carries_run_bindings() -> None:
    index = _index(entries=[], bindings={("seg_a", "tx_a")})
    assert index.has_run("seg_a", "tx_a")
    assert not index.has_run("seg_b", "tx_b")
