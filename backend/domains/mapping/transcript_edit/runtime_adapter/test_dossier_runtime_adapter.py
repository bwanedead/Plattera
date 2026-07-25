"""Tests for dossier-mode transcript-edit runtime adapter launch wiring."""

from __future__ import annotations

import json
from pathlib import Path

import config.paths as paths_mod
import pytest
import tooling.mapping.transcript_edit.paths as te_paths

from domains.mapping.transcript_edit.execution.dossier_tool_specs import (
    build_dossier_transcript_edit_tool_specs,
)
from domains.mapping.transcript_edit.execution.tool_specs import build_transcript_edit_tool_specs
from domains.mapping.transcript_edit.payloads.startup_inventory import (
    T0DraftDescriptor,
    TranscriptEditDraftInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)
from domains.mapping.transcript_edit.runtime_adapter import adapter as adapter_mod
from domains.mapping.transcript_edit.runtime_adapter import dossier_composition as dossier_comp_mod
from domains.mapping.transcript_edit.runtime_adapter.adapter import (
    build_transcript_edit_runtime_adapter,
)
from harness.execution.contracts import ExecutionStepRequest
from harness.runtime.composition import ToolBinding
from services.dossier.segment_topology import TopologyRunInput, TopologySegmentInput
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    build_dossier_transcript_edit_startup_inventory_from_segments,
)
from tooling.mapping.transcript_edit.paths import transcript_edit_output_path


def _dossiers_root(tmp_path: Path) -> Path:
    root = tmp_path / "dossiers_data"
    root.mkdir(parents=True)
    return root


def _patch_roots(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)


def _minimal_run_layout(root: Path, dossier_id: str, transcription_id: str) -> None:
    run = root / "views" / "transcriptions" / dossier_id / transcription_id
    raw = run / "raw"
    raw.mkdir(parents=True)
    (raw / f"{transcription_id}_draft_1.json").write_text(
        json.dumps({"sections": [{"body": f"t0 {transcription_id}"}]}),
        encoding="utf-8",
    )
    (run / "run.json").write_text(
        json.dumps({"completed_drafts": [f"{transcription_id}_draft_1"]}),
        encoding="utf-8",
    )


def _leaf_builder(**kwargs):
    tid = kwargs["transcription_id"]
    return TranscriptEditStartupInventory(
        scope=TranscriptEditScope(
            dossier_id=kwargs["dossier_id"],
            transcription_id=tid,
            segment_id=kwargs.get("segment_id"),
            workspace_id=kwargs.get("workspace_id"),
            run_id=kwargs.get("run_id"),
        ),
        t0_drafts=(
            T0DraftDescriptor(
                ref_id="t0:raw:draft_1",
                variant_label="draft 1",
                source_file_stem=f"{tid}_draft_1",
            ),
        ),
        transcript_edit_drafts=TranscriptEditDraftInventory(working_draft_exists=False),
    )


def _install_two_segment_inventory(monkeypatch, tmp_path, *, workspace_id: str = "ws-adapter"):
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    dossier_id = "d1"
    _minimal_run_layout(root, dossier_id, "tx_a")
    _minimal_run_layout(root, dossier_id, "tx_b")

    def _build(*, dossier_id: str, run_id=None, workspace_id=None, **_kwargs):
        return build_dossier_transcript_edit_startup_inventory_from_segments(
            dossier_id=dossier_id,
            workspace_id=workspace_id,
            run_id=run_id,
            segments=(
                TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),
                TopologySegmentInput("seg_b", 1, (TopologyRunInput("tx_b", 0),)),
            ),
            association_positions={"tx_a": 1, "tx_b": 2},
            leaf_inventory_builder=_leaf_builder,
        )

    monkeypatch.setattr(adapter_mod, "build_dossier_transcript_edit_startup_inventory", _build)
    return root, dossier_id, workspace_id


def _block_ids(surface) -> list[str]:
    return [
        block.metadata["transcript_edit.prompt_block"]["block_id"] for block in surface.blocks
    ]


def _binding(surface, tool_id: str):
    return next(b for b in surface.tool_bindings if b.tool_id == tool_id).handler


def _leaf_launch(**extra):
    ctx = {
        "dossier_id": "dossier-1",
        "transcription_id": "tx-1",
        "segment_id": "seg-1",
        "run_id": "run-1",
    }
    ctx.update(extra)
    return ctx


def _dossier_launch(**extra):
    ctx = {
        "transcript_edit_scope_mode": "dossier",
        "dossier_id": "d1",
        "workspace_id": "ws-adapter",
        "run_id": "ws-adapter",
    }
    ctx.update(extra)
    return ctx


# --- Compatibility -----------------------------------------------------------


def test_selector_absent_preserves_four_block_leaf_surface() -> None:
    adapter = build_transcript_edit_runtime_adapter()
    pack = adapter.domain_pack
    surface = adapter.build_turn_surface(_leaf_launch())
    assert surface.surface_id == "transcript_edit"
    assert len(surface.blocks) == 4
    assert _block_ids(surface)[:3] == [b.block_id for b in pack.build_semantic_prompt_blocks()]
    assert _block_ids(surface)[3] == "transcript_edit_startup_context"
    assert surface.payload["transcript_edit"] == pack.build_surface_payload()
    assert [b.tool_id for b in surface.tool_bindings] == [
        s.tool_id for s in build_transcript_edit_tool_specs()
    ]


def test_explicit_transcription_mode_matches_leaf_surface() -> None:
    adapter = build_transcript_edit_runtime_adapter()
    absent = adapter.build_turn_surface(_leaf_launch())
    explicit = adapter.build_turn_surface(_leaf_launch(transcript_edit_scope_mode="transcription"))
    assert _block_ids(explicit) == _block_ids(absent)
    assert explicit.payload["transcript_edit"] == absent.payload["transcript_edit"]
    publish = next(
        s
        for s in explicit.payload["transcript_edit"]["tool_specs"]
        if s["tool_id"] == "publish_workspace_artifact"
    )
    assert "source_revision_ref" in publish["expected_request_json_shape"]["properties"]
    assert "source_revision_refs" not in publish["expected_request_json_shape"]["properties"]


def test_selector_absent_without_transcription_id_still_refuses() -> None:
    adapter = build_transcript_edit_runtime_adapter()
    with pytest.raises(ValueError, match="transcription_id_required"):
        adapter.build_turn_surface({"dossier_id": "dossier-1", "workspace_id": "ws"})


def test_leaf_action_ids_unchanged() -> None:
    adapter = build_transcript_edit_runtime_adapter()
    surface = adapter.build_turn_surface(_leaf_launch())
    assert [b.tool_id for b in surface.tool_bindings] == [
        "hydrate_artifact_refs",
        "transform_artifact",
        "save_workspace_artifact",
        "copy_forward_save_workspace_artifact",
        "publish_workspace_artifact",
    ]


# --- Selector validation -----------------------------------------------------


def test_dossier_selector_selects_dossier_mode(tmp_path, monkeypatch) -> None:
    _install_two_segment_inventory(monkeypatch, tmp_path)
    adapter = build_transcript_edit_runtime_adapter()
    surface = adapter.build_turn_surface(_dossier_launch())
    assert len(surface.blocks) == 5
    assert "transcript_edit_dossier_guidance" in _block_ids(surface)


@pytest.mark.parametrize(
    "value",
    ["", "DOSSIER", "leaf", True, False, 1, 0, ["dossier"], {"mode": "dossier"}],
)
def test_invalid_scope_mode_refuses(value) -> None:
    adapter = build_transcript_edit_runtime_adapter()
    with pytest.raises(ValueError, match="transcript_edit_scope_mode_invalid"):
        adapter.build_turn_surface(_leaf_launch(transcript_edit_scope_mode=value))


@pytest.mark.parametrize(
    "extra",
    [
        {"transcription_id": "tx_a"},
        {"segment_id": "seg_a"},
        {"transcription_id": "tx_a", "segment_id": "seg_a"},
        {"transcription_id": 12},
        {"segment_id": ["seg"]},
    ],
)
def test_dossier_leaf_scope_conflict(tmp_path, monkeypatch, extra) -> None:
    called = {"n": 0}

    def boom(**_kwargs):
        called["n"] += 1
        raise AssertionError("inventory must not build on leaf conflict")

    monkeypatch.setattr(adapter_mod, "build_dossier_transcript_edit_startup_inventory", boom)
    adapter = build_transcript_edit_runtime_adapter()
    with pytest.raises(ValueError, match="transcript_edit_dossier_leaf_scope_conflict"):
        adapter.build_turn_surface(_dossier_launch(**extra))
    assert called["n"] == 0


def test_dossier_workspace_required_before_inventory(tmp_path, monkeypatch) -> None:
    called = {"n": 0}

    def boom(**_kwargs):
        called["n"] += 1
        raise AssertionError("topology/inventory must not load")

    monkeypatch.setattr(adapter_mod, "build_dossier_transcript_edit_startup_inventory", boom)
    adapter = build_transcript_edit_runtime_adapter()
    with pytest.raises(ValueError, match="dossier_runtime_workspace_required"):
        adapter.build_turn_surface(
            {
                "transcript_edit_scope_mode": "dossier",
                "dossier_id": "d1",
            }
        )
    assert called["n"] == 0


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("dossier_id", 99, "dossier_id_invalid_type"),
        ("workspace_id", 1, "workspace_id_invalid_type"),
        ("run_id", True, "run_id_invalid_type"),
    ],
)
def test_dossier_scope_fields_not_string_coerced(field, value, code) -> None:
    adapter = build_transcript_edit_runtime_adapter()
    ctx = _dossier_launch()
    ctx[field] = value
    with pytest.raises(ValueError, match=code):
        adapter.build_turn_surface(ctx)


# --- Surface coherence -------------------------------------------------------


def test_dossier_surface_five_blocks_canonical_order(tmp_path, monkeypatch) -> None:
    _install_two_segment_inventory(monkeypatch, tmp_path)
    adapter = build_transcript_edit_runtime_adapter()
    surface = adapter.build_turn_surface(_dossier_launch())
    assert _block_ids(surface) == [
        "mapping_family_branch",
        "transcript_edit_domain_branch",
        "transcript_edit_procedural_guidance",
        "transcript_edit_dossier_guidance",
        "transcript_edit_startup_context",
    ]


def test_startup_context_lists_ordered_segments_and_runs(tmp_path, monkeypatch) -> None:
    _install_two_segment_inventory(monkeypatch, tmp_path)
    adapter = build_transcript_edit_runtime_adapter()
    surface = adapter.build_turn_surface(_dossier_launch())
    startup = surface.blocks[-1].content
    assert "seg_a" in startup and "seg_b" in startup
    assert "tx_a" in startup and "tx_b" in startup


def test_payload_uses_dossier_contracts_including_plural_publish(tmp_path, monkeypatch) -> None:
    _install_two_segment_inventory(monkeypatch, tmp_path)
    adapter = build_transcript_edit_runtime_adapter()
    launch = _dossier_launch()
    surface = adapter.build_turn_surface(launch)
    bundle = adapter_mod.build_dossier_transcript_edit_startup_inventory(
        dossier_id=launch["dossier_id"],
        workspace_id=launch["workspace_id"],
        run_id=launch["run_id"],
    )
    expected = adapter.domain_pack.build_surface_payload(startup_inventory=bundle.inventory)
    payload = surface.payload["transcript_edit"]
    assert payload == expected
    assert [s["tool_id"] for s in payload["tool_specs"]] == [
        s.tool_id for s in build_dossier_transcript_edit_tool_specs()
    ]
    publish = next(s for s in payload["tool_specs"] if s["tool_id"] == "publish_workspace_artifact")
    assert "source_revision_refs" in publish["expected_request_json_shape"]["properties"]
    assert "source_revision_ref" not in publish["expected_request_json_shape"]["properties"]


def test_bound_tool_ids_match_payload(tmp_path, monkeypatch) -> None:
    _install_two_segment_inventory(monkeypatch, tmp_path)
    adapter = build_transcript_edit_runtime_adapter()
    surface = adapter.build_turn_surface(_dossier_launch())
    assert [b.tool_id for b in surface.tool_bindings] == surface.payload["transcript_edit"][
        "tool_ids"
    ]


def test_raw_inventory_and_ref_index_absent_from_payload(tmp_path, monkeypatch) -> None:
    _install_two_segment_inventory(monkeypatch, tmp_path)
    adapter = build_transcript_edit_runtime_adapter()
    surface = adapter.build_turn_surface(_dossier_launch())
    blob = json.dumps(surface.payload)
    assert "startup_inventory" not in surface.payload["transcript_edit"]
    assert "ref_index" not in blob
    assert "DossierArtifactRefIndex" not in blob
    assert "DossierStartupInventoryBundle" not in blob


def test_same_inventory_selects_prompt_and_contracts(tmp_path, monkeypatch) -> None:
    _install_two_segment_inventory(monkeypatch, tmp_path)
    adapter = build_transcript_edit_runtime_adapter()
    pack = adapter.domain_pack
    launch = _dossier_launch()
    bundle = adapter_mod.build_dossier_transcript_edit_startup_inventory(
        dossier_id=launch["dossier_id"],
        workspace_id=launch["workspace_id"],
        run_id=launch["run_id"],
    )
    dossier_payload = pack.build_surface_payload(startup_inventory=bundle.inventory)
    dossier_blocks = pack.build_runtime_prompt_blocks(startup_inventory=bundle.inventory)
    leaf_inventory = TranscriptEditStartupInventory(
        scope=TranscriptEditScope(dossier_id="d1", transcription_id="tx_a"),
    )
    leaf_payload = pack.build_surface_payload(startup_inventory=leaf_inventory)
    leaf_blocks = pack.build_runtime_prompt_blocks(startup_inventory=leaf_inventory)
    assert len(dossier_blocks) == 5
    assert len(leaf_blocks) == 4
    assert dossier_payload != leaf_payload

    surface = adapter.build_turn_surface(launch)
    assert surface.payload["transcript_edit"] == dossier_payload
    assert len(surface.blocks) == len(dossier_blocks)
    assert _block_ids(surface) == [b.block_id for b in dossier_blocks]


def test_mismatched_bindings_refuse(tmp_path, monkeypatch) -> None:
    _install_two_segment_inventory(monkeypatch, tmp_path)

    def bad_bindings(*, bundle):
        return (ToolBinding(tool_id="unexpected_tool", handler=lambda _r: {}),)

    monkeypatch.setattr(
        dossier_comp_mod,
        "build_dossier_transcript_edit_tool_bindings",
        bad_bindings,
    )
    adapter = build_transcript_edit_runtime_adapter()
    with pytest.raises(ValueError, match="transcript_edit_runtime_tool_binding_mismatch"):
        adapter.build_turn_surface(_dossier_launch())


# --- Production-shaped integration -------------------------------------------


def test_adapter_hydrate_save_publish_two_segments(tmp_path, monkeypatch) -> None:
    _, dossier_id, workspace_id = _install_two_segment_inventory(monkeypatch, tmp_path)
    adapter = build_transcript_edit_runtime_adapter()
    surface = adapter.build_turn_surface(_dossier_launch(workspace_id=workspace_id, run_id=workspace_id))

    hydrate = _binding(surface, "hydrate_artifact_refs")
    save = _binding(surface, "save_workspace_artifact")
    publish = _binding(surface, "publish_workspace_artifact")

    t0_a = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    hydrated = hydrate(
        ExecutionStepRequest(
            session_id="s1",
            action_id="hydrate_artifact_refs",
            inputs={"ref_ids": [t0_a], "max_refs": 4},
        )
    )
    assert hydrated["executed"] is True
    assert hydrated["outputs"]["hydrated_count"] == 1

    refs = []
    for sid, tid, text in (("seg_a", "tx_a", "A"), ("seg_b", "tx_b", "B")):
        out = save(
            {
                "target_ref": qualify_leaf_ref(
                    segment_id=sid, transcription_id=tid, leaf_ref="t0:raw:draft_1"
                ),
                "draft_payload": {
                    "source_transcript_verbatim": text,
                    "normalized_or_mapping_transcript": f"{text}N",
                },
            }
        )
        assert out["executed"] is True
        refs.append(out["outputs"]["working_draft_ref"])

    published = publish(
        ExecutionStepRequest(
            session_id="s1",
            action_id="publish_workspace_artifact",
            inputs={"source_revision_refs": refs},
        )
    )
    assert published["executed"] is True
    assert published["outputs"]["output_ref"] == "transcript_edit:output"
    assert published["outputs"]["output_revision_ref"].startswith(
        "transcript_edit:dossier_output:sha256:"
    )
    for tid in ("tx_a", "tx_b"):
        assert not transcript_edit_output_path(dossier_id, tid, workspace_id).exists()


# --- Continuity --------------------------------------------------------------


def test_rebuild_with_preserved_dossier_selector(tmp_path, monkeypatch) -> None:
    _install_two_segment_inventory(monkeypatch, tmp_path)
    adapter = build_transcript_edit_runtime_adapter()
    launch = _dossier_launch()
    first = adapter.build_turn_surface(launch)
    second = adapter.build_turn_surface(dict(launch))
    assert _block_ids(first) == _block_ids(second)
    assert first.payload["transcript_edit"]["tool_specs"] == second.payload["transcript_edit"][
        "tool_specs"
    ]


def test_enrich_launch_context_retains_selector_and_generic_deltas() -> None:
    adapter = build_transcript_edit_runtime_adapter()
    launch = {
        "transcript_edit_scope_mode": "dossier",
        "dossier_id": "d1",
        "workspace_id": "ws",
    }
    enriched = adapter.enrich_launch_context(launch)
    assert launch["transcript_edit_scope_mode"] == "dossier"
    assert "transcript_edit_scope_mode" not in enriched  # deltas only; does not rewrite selector
    assert enriched.get("llm_streaming") is True
    assert "action_batch_policy" in enriched
    assert "delegate_observation_worklist_reminder" in enriched
