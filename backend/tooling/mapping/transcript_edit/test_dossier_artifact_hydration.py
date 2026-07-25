"""Tests for dossier-qualified artifact hydration router."""

from __future__ import annotations

from typing import Any

from tooling.mapping.transcript_edit.dossier_artifact_hydration import (
    hydrate_dossier_artifact_refs,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import (
    DossierArtifactRefTarget,
    build_dossier_artifact_ref_index,
    qualify_leaf_ref,
)


def _index_for(*pairs: tuple[str, str, str], dossier_id: str = "d1"):
    entries = []
    bindings: set[tuple[str, str]] = set()
    for segment_id, transcription_id, leaf_ref in pairs:
        bindings.add((segment_id, transcription_id))
        qualified = qualify_leaf_ref(
            segment_id=segment_id,
            transcription_id=transcription_id,
            leaf_ref=leaf_ref,
        )
        entries.append(
            (
                qualified,
                DossierArtifactRefTarget(
                    segment_id=segment_id,
                    transcription_id=transcription_id,
                    leaf_ref=leaf_ref,
                ),
            )
        )
    return build_dossier_artifact_ref_index(
        dossier_id=dossier_id,
        topology_fingerprint="fp-test",
        entries=entries,
        run_bindings=frozenset(bindings),
    )


def _factory_tracking(calls: list[tuple[str, list[str]]]):
    def factory(*, dossier_id: str, transcription_id: str, workspace_key: str | None):
        def handler(request: Any) -> Any:
            inputs = request if isinstance(request, dict) else {}
            refs = list(inputs.get("ref_ids") or [])
            calls.append((transcription_id, refs))
            results = []
            errors = []
            for rid in refs:
                if rid == "bad:leaf":
                    errors.append({"ref_id": rid, "code": "not_found", "message": "missing"})
                else:
                    results.append(
                        {
                            "ref_id": rid,
                            "kind": "t0_draft",
                            "text": f"{transcription_id}:{rid}",
                        }
                    )
            return {
                "executed": True,
                "outputs": {
                    "results": results,
                    "errors": errors,
                    "cap_exceeded": False,
                    "hydrated_count": len(results),
                },
            }

        return handler

    return factory


def test_two_segments_hydrate_in_one_request_preserving_order() -> None:
    index = _index_for(
        ("seg_a", "tx_a", "t0:raw:draft_1"),
        ("seg_b", "tx_b", "t0:raw:draft_1"),
        ("seg_a", "tx_a", "t0:raw:draft_2"),
    )
    q1 = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    q2 = qualify_leaf_ref(segment_id="seg_b", transcription_id="tx_b", leaf_ref="t0:raw:draft_1")
    q3 = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_2")
    calls: list[tuple[str, list[str]]] = []
    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[q1, q2, q3],
        max_refs=8,
        handler_factory=_factory_tracking(calls),
    )
    assert out["executed"] is True
    result_ids = [r["ref_id"] for r in out["outputs"]["results"]]
    assert result_ids == [q1, q2, q3]
    assert result_ids[0] != result_ids[1]
    assert out["outputs"]["results"][0]["segment_id"] == "seg_a"
    assert out["outputs"]["results"][0]["transcription_id"] == "tx_a"
    assert out["outputs"]["results"][1]["segment_id"] == "seg_b"
    called_txs = {tx for tx, _refs in calls}
    assert called_txs == {"tx_a", "tx_b"}


def test_index_dossier_mismatch_refused() -> None:
    index = _index_for(("seg_a", "tx_a", "t0:raw:draft_1"), dossier_id="dossier-a")
    q1 = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    out = hydrate_dossier_artifact_refs(
        dossier_id="dossier-b",
        ref_index=index,
        ref_ids=[q1],
        max_refs=8,
        handler_factory=_factory_tracking([]),
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "index_dossier_mismatch"


def test_ref_ids_tuple_refused() -> None:
    index = _index_for(("seg_a", "tx_a", "t0:raw:draft_1"))
    q1 = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=(q1,),  # type: ignore[arg-type]
        max_refs=8,
        handler_factory=_factory_tracking([]),
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "ref_ids_invalid_type"


def test_max_refs_bool_and_numeric_string_refused() -> None:
    index = _index_for(("seg_a", "tx_a", "t0:raw:draft_1"))
    q1 = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    out_bool = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[q1],
        max_refs=True,  # type: ignore[arg-type]
        handler_factory=_factory_tracking([]),
    )
    assert out_bool["executed"] is False
    assert out_bool["refusal"]["reason_code"] == "max_refs_invalid"

    out_str = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[q1],
        max_refs="8",  # type: ignore[arg-type]
        handler_factory=_factory_tracking([]),
    )
    assert out_str["executed"] is False
    assert out_str["refusal"]["reason_code"] == "max_refs_invalid"


def test_unknown_ref_is_explicit_error() -> None:
    index = _index_for(("seg_a", "tx_a", "t0:raw:draft_1"))
    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=["dossier_segment:nope:run:tx_a:t0:raw:draft_1"],
        max_refs=8,
        handler_factory=_factory_tracking([]),
    )
    assert out["executed"] is True
    assert out["outputs"]["results"] == []
    assert any(
        e.get("code") == "dossier_ref_run_not_in_topology" for e in out["outputs"]["errors"]
    )


def test_malformed_empty_ref_refuses_request() -> None:
    index = _index_for(("seg_a", "tx_a", "t0:raw:draft_1"))
    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[""],
        max_refs=8,
        handler_factory=_factory_tracking([]),
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "ref_id_invalid_type"


def test_unknown_ref_partial_success() -> None:
    index = _index_for(("seg_a", "tx_a", "t0:raw:draft_1"))
    q1 = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[q1, "dossier_segment:missing:run:tx_x:t0:raw:draft_1"],
        max_refs=8,
        handler_factory=_factory_tracking([]),
    )
    assert out["executed"] is True
    assert [r["ref_id"] for r in out["outputs"]["results"]] == [q1]
    assert any(
        e.get("code") == "dossier_ref_run_not_in_topology" for e in out["outputs"]["errors"]
    )


def test_leaf_error_does_not_erase_other_segment_success() -> None:
    index = _index_for(
        ("seg_a", "tx_a", "t0:raw:draft_1"),
        ("seg_b", "tx_b", "bad:leaf"),
    )
    q_ok = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    q_bad = qualify_leaf_ref(segment_id="seg_b", transcription_id="tx_b", leaf_ref="bad:leaf")
    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[q_ok, q_bad],
        max_refs=8,
        handler_factory=_factory_tracking([]),
    )
    assert [r["ref_id"] for r in out["outputs"]["results"]] == [q_ok]
    bad_err = next(e for e in out["outputs"]["errors"] if e.get("ref_id") == q_bad)
    assert bad_err["segment_id"] == "seg_b"
    assert bad_err["transcription_id"] == "tx_b"
    assert bad_err["code"] == "not_found"
    assert bad_err["message"] == "Leaf hydrator reported an error for this ref."


def test_successful_result_strips_host_and_binary_fields_but_keeps_semantics() -> None:
    index = _index_for(
        ("seg_a", "tx_a", "t0:raw:draft_1"),
        ("seg_b", "tx_b", "image:assoc:tx_b:original"),
    )
    q_draft = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    q_img = qualify_leaf_ref(
        segment_id="seg_b",
        transcription_id="tx_b",
        leaf_ref="image:assoc:tx_b:original",
    )
    win_path = r"C:\Users\example\AppData\Local\Plattera\Data\dossiers_data\raw\tx_a_draft_1.json"
    abs_path = r"C:\Users\example\AppData\Local\Plattera\Data\images\tx_b.jpg"
    leaf_draft = {
        "ref_id": "t0:raw:draft_1",
        "kind": "t0_draft",
        "text": "BEGINNING at a point",
        "path": win_path,
        "payload": {
            "status": "ready",
            "basename": "tx_a_draft_1.json",
            "nested": {
                "absolute_path": abs_path,
                "role": "t0_peer",
                "b64": "QUJD",
                "parameters": {"dpi": 300},
            },
        },
        "image_b64": "iVBORw0KGgo=",
        "bytes": b"secret-bytes",
    }
    leaf_image = {
        "ref_id": "image:assoc:tx_b:original",
        "kind": "source_image",
        "absolute_path": abs_path,
        "exists": True,
        "basename": "tx_b.jpg",
        "width": 1200,
        "height": 800,
        "role": "source_original",
        "parent_ref": "image:assoc:tx_b:original",
        "crop_img": {"pixels": [1, 2, 3]},
        "image": {"obj": True},
        "image_obj": object(),
        "base64": "YmFk",
    }
    evidence_bytes = b"\xff\xd8\xffevidence"

    def factory(*, dossier_id: str, transcription_id: str, workspace_key: str | None):
        def handler(request):
            if transcription_id == "tx_a":
                return {
                    "executed": True,
                    "outputs": {
                        "results": [leaf_draft],
                        "errors": [],
                        "cap_exceeded": False,
                        "hydrated_count": 1,
                    },
                }
            return {
                "executed": True,
                "outputs": {
                    "results": [leaf_image],
                    "errors": [],
                    "cap_exceeded": False,
                    "hydrated_count": 1,
                },
                "image_evidence": [
                    {
                        "ref_id": "image:assoc:tx_b:original",
                        "mime": "image/jpeg",
                        "bytes": evidence_bytes,
                        "absolute_path": abs_path,
                    }
                ],
            }

        return handler

    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[q_draft, q_img],
        max_refs=8,
        handler_factory=factory,
    )
    assert [r["ref_id"] for r in out["outputs"]["results"]] == [q_draft, q_img]
    draft = out["outputs"]["results"][0]
    image = out["outputs"]["results"][1]

    assert draft["text"] == "BEGINNING at a point"
    assert draft["payload"]["status"] == "ready"
    assert draft["payload"]["basename"] == "tx_a_draft_1.json"
    assert draft["payload"]["nested"]["role"] == "t0_peer"
    assert draft["payload"]["nested"]["parameters"] == {"dpi": 300}
    assert "path" not in draft
    assert "image_b64" not in draft
    assert "bytes" not in draft
    assert "absolute_path" not in draft["payload"]["nested"]
    assert "b64" not in draft["payload"]["nested"]

    assert image["exists"] is True
    assert image["basename"] == "tx_b.jpg"
    assert image["width"] == 1200
    assert image["height"] == 800
    assert image["role"] == "source_original"
    assert image["parent_ref"] == "image:assoc:tx_b:original"
    assert "absolute_path" not in image
    assert "crop_img" not in image
    assert "image" not in image
    assert "image_obj" not in image
    assert "base64" not in image

    # Leaf originals must remain untouched.
    assert leaf_draft["path"] == win_path
    assert leaf_image["absolute_path"] == abs_path

    results_blob = str(out["outputs"]["results"])
    assert win_path not in results_blob
    assert abs_path not in results_blob
    assert "AppData" not in results_blob
    assert "QUJD" not in results_blob
    assert "iVBORw0KGgo=" not in results_blob

    assert "image_evidence" in out
    evidence = out["image_evidence"][0]
    assert evidence["ref_id"] == q_img
    assert evidence["leaf_ref_id"] == "image:assoc:tx_b:original"
    assert evidence["segment_id"] == "seg_b"
    assert evidence["transcription_id"] == "tx_b"
    assert evidence["bytes"] == evidence_bytes
    assert evidence["absolute_path"] == abs_path


def test_leaf_error_message_with_windows_path_is_not_forwarded() -> None:
    index = _index_for(
        ("seg_a", "tx_a", "t0:raw:draft_1"),
        ("seg_b", "tx_b", "t0:raw:draft_1"),
    )
    q_ok = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    q_bad = qualify_leaf_ref(segment_id="seg_b", transcription_id="tx_b", leaf_ref="t0:raw:draft_1")
    win_path = r"C:\Users\example\AppData\Local\Plattera\Data\missing.json"

    def factory(*, dossier_id: str, transcription_id: str, workspace_key: str | None):
        def handler(request):
            if transcription_id == "tx_b":
                return {
                    "executed": True,
                    "outputs": {
                        "results": [],
                        "errors": [
                            {
                                "ref_id": "t0:raw:draft_1",
                                "code": "not_found",
                                "message": f"cannot open {win_path}",
                            }
                        ],
                        "cap_exceeded": False,
                        "hydrated_count": 0,
                    },
                }
            return {
                "executed": True,
                "outputs": {
                    "results": [
                        {"ref_id": "t0:raw:draft_1", "kind": "t0_draft", "text": "ok"}
                    ],
                    "errors": [],
                    "cap_exceeded": False,
                    "hydrated_count": 1,
                },
            }

        return handler

    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[q_ok, q_bad],
        max_refs=8,
        handler_factory=factory,
    )
    assert [r["ref_id"] for r in out["outputs"]["results"]] == [q_ok]
    err = next(e for e in out["outputs"]["errors"] if e.get("ref_id") == q_bad)
    assert err["code"] == "not_found"
    assert err["message"] == "Leaf hydrator reported an error for this ref."
    assert err["segment_id"] == "seg_b"
    assert err["transcription_id"] == "tx_b"
    blob = str(out)
    assert win_path not in blob
    assert "AppData" not in blob
    assert "cannot open" not in blob


def test_silent_leaf_omission_becomes_explicit_error() -> None:
    index = _index_for(
        ("seg_a", "tx_a", "t0:raw:draft_1"),
        ("seg_b", "tx_b", "t0:raw:draft_1"),
    )
    q_a = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    q_b = qualify_leaf_ref(segment_id="seg_b", transcription_id="tx_b", leaf_ref="t0:raw:draft_1")

    def factory(*, dossier_id: str, transcription_id: str, workspace_key: str | None):
        def handler(request):
            # Silently omit requested refs for tx_b; succeed for tx_a.
            if transcription_id == "tx_b":
                return {
                    "executed": True,
                    "outputs": {
                        "results": [],
                        "errors": [],
                        "cap_exceeded": False,
                        "hydrated_count": 0,
                    },
                }
            return {
                "executed": True,
                "outputs": {
                    "results": [
                        {"ref_id": "t0:raw:draft_1", "kind": "t0_draft", "text": "ok"}
                    ],
                    "errors": [],
                    "cap_exceeded": False,
                    "hydrated_count": 1,
                },
            }

        return handler

    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[q_a, q_b],
        max_refs=8,
        handler_factory=factory,
    )
    assert [r["ref_id"] for r in out["outputs"]["results"]] == [q_a]
    omit = next(e for e in out["outputs"]["errors"] if e.get("ref_id") == q_b)
    assert omit["code"] == "hydration_silent_omission"
    assert omit["segment_id"] == "seg_b"
    assert omit["transcription_id"] == "tx_b"


def test_malformed_leaf_results_collection() -> None:
    index = _index_for(("seg_a", "tx_a", "t0:raw:draft_1"))
    q1 = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")

    def factory(*, dossier_id: str, transcription_id: str, workspace_key: str | None):
        def handler(request):
            return {
                "executed": True,
                "outputs": {
                    "results": {"ref_id": "t0:raw:draft_1"},
                    "errors": [],
                    "cap_exceeded": False,
                    "hydrated_count": 0,
                },
            }

        return handler

    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[q1],
        max_refs=8,
        handler_factory=factory,
    )
    assert out["outputs"]["results"] == []
    err = out["outputs"]["errors"][0]
    assert err["code"] == "hydration_invalid_leaf_results"
    assert err["segment_id"] == "seg_a"
    assert err["transcription_id"] == "tx_a"


def test_leaf_exception_does_not_leak_host_path() -> None:
    index = _index_for(("seg_a", "tx_a", "t0:raw:draft_1"))
    q1 = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    win_path = r"C:\Users\example\AppData\Local\Plattera\Data\secret.json"

    def factory(*, dossier_id: str, transcription_id: str, workspace_key: str | None):
        def handler(request):
            raise OSError(f"cannot read {win_path}")

        return handler

    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[q1],
        max_refs=8,
        handler_factory=factory,
    )
    blob = str(out)
    assert win_path not in blob
    assert "AppData" not in blob
    err = out["outputs"]["errors"][0]
    assert err["code"] == "transcription_hydration_error"
    assert err["segment_id"] == "seg_a"


def test_hydration_is_read_only_no_side_effects(tmp_path) -> None:
    index = _index_for(("seg_a", "tx_a", "t0:raw:draft_1"))
    q1 = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    marker = tmp_path / "marker.txt"
    marker.write_text("before", encoding="utf-8")

    def factory(*, dossier_id: str, transcription_id: str, workspace_key: str | None):
        def handler(request):
            assert marker.read_text(encoding="utf-8") == "before"
            return {
                "executed": True,
                "outputs": {
                    "results": [{"ref_id": "t0:raw:draft_1", "kind": "t0_draft", "text": "ok"}],
                    "errors": [],
                    "cap_exceeded": False,
                    "hydrated_count": 1,
                },
            }

        return handler

    out = hydrate_dossier_artifact_refs(
        dossier_id="d1",
        ref_index=index,
        ref_ids=[q1],
        handler_factory=factory,
    )
    assert out["outputs"]["hydrated_count"] == 1
    assert marker.read_text(encoding="utf-8") == "before"
