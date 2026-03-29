from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.pipelines.image_to_text.pipeline import ImageToTextPipeline
from backend.domains.mapping.transcript_edit.contracts import TranscriptEditAgentRunResult
from backend.prompts.image_to_text import get_available_extraction_modes, get_image_to_text_prompt


def _pipeline_stub() -> ImageToTextPipeline:
    pipeline = ImageToTextPipeline.__new__(ImageToTextPipeline)
    pipeline.transcription_edit_persistence = None
    pipeline.transcription_edit_run_registry = None
    pipeline._maybe_trigger_transcript_edit_agent_background = lambda **kwargs: None  # type: ignore[method-assign]
    return pipeline


def test_prompts_expose_relaxed_legal_mode() -> None:
    modes = get_available_extraction_modes()
    assert "legal_document_json_relaxed" in modes
    prompt = get_image_to_text_prompt("legal_document_json_relaxed")
    assert "JSON object" in prompt
    assert "Section on natural breaks" in prompt
    assert "typically 4–12" in prompt


def test_json_mode_kind_switches_between_strict_and_relaxed() -> None:
    pipeline = _pipeline_stub()
    assert pipeline._json_mode_kind("legal_document_json") == "strict"
    assert pipeline._json_mode_kind("legal_document_json_relaxed") == "relaxed"
    assert pipeline._json_mode_kind("generic_document_json") is False


def test_relaxed_mode_valid_json_normalizes_without_repair() -> None:
    pipeline = _pipeline_stub()
    result = {
        "success": True,
        "extracted_text": json.dumps(
            {
                "documentId": "doc-1",
                "sections": [
                    {"id": 7, "body": "A"},
                    {"id": 22, "body": "B"},
                ],
            }
        ),
        "metadata": {},
        "tokens_used": 11,
    }
    out = pipeline._postprocess_legal_json_result(
        result=result,
        extraction_mode="legal_document_json_relaxed",
        model="gpt-4o",
    )
    payload = json.loads(out["extracted_text"])
    assert payload["sections"][0]["id"] == 1
    assert payload["sections"][1]["id"] == 2
    assert out["metadata"]["json_extraction"]["validation_passed"] is True
    assert out["metadata"]["json_extraction"]["repair_invoked"] is False


def test_relaxed_mode_invalid_json_invokes_repair_path(monkeypatch) -> None:
    pipeline = _pipeline_stub()

    def _fake_persist(*, raw_output: str, model: str, context: dict):  # type: ignore[no-untyped-def]
        return "artifact://raw"

    def _fake_repair(*, raw_output: str, context: dict):  # type: ignore[no-untyped-def]
        return (
            {
                "documentId": "repaired",
                "sections": [{"id": 1, "body": "Repaired body"}],
            },
            "artifact://repair_snapshot",
        )

    monkeypatch.setattr(pipeline, "_persist_relaxed_raw_output_for_postmortem", _fake_persist)
    monkeypatch.setattr(pipeline, "_repair_relaxed_json_with_edit_loop", _fake_repair)

    out = pipeline._postprocess_legal_json_result(
        result={"success": True, "extracted_text": "{bad json", "metadata": {}},
        extraction_mode="legal_document_json_relaxed",
        model="gpt-4o",
        context={"dossier_id": "D1"},
    )
    payload = json.loads(out["extracted_text"])
    assert payload["documentId"] == "repaired"
    assert out["metadata"]["json_extraction"]["repair_invoked"] is True
    assert out["metadata"]["json_extraction"]["raw_output_ref"] == "artifact://raw"
    assert out["metadata"]["json_extraction"]["repair_snapshot_ref"] == "artifact://repair_snapshot"


def test_strict_mode_never_invokes_repair_for_invalid_json() -> None:
    pipeline = _pipeline_stub()
    out = pipeline._postprocess_legal_json_result(
        result={"success": True, "extracted_text": "{bad json", "metadata": {}},
        extraction_mode="legal_document_json",
        model="gpt-4o",
    )
    assert out["extracted_text"] == "{bad json"
    assert out["metadata"]["json_extraction"]["validation_passed"] is False
    assert out["metadata"]["json_extraction"]["repair_invoked"] is False


def test_process_relaxed_full_path_malformed_json_repairs_to_sections(monkeypatch) -> None:
    pipeline = _pipeline_stub()

    class _FakeService:
        def process_image_with_text(self, **kwargs):  # type: ignore[no-untyped-def]
            return {
                "success": True,
                "extracted_text": "{ malformed",
                "tokens_used": 42,
                "metadata": {"provider": "fake"},
            }

    monkeypatch.setattr(pipeline, "_get_service_for_model", lambda model: _FakeService())
    monkeypatch.setattr(pipeline, "_prepare_image", lambda image_path, enhancement_settings=None: ("base64", "jpeg"))
    monkeypatch.setattr(pipeline, "_persist_relaxed_raw_output_for_postmortem", lambda **kwargs: "artifact://raw")
    monkeypatch.setattr(
        pipeline,
        "_repair_relaxed_json_with_edit_loop",
        lambda **kwargs: (
            {"documentId": "repaired", "sections": [{"id": 1, "body": "Repaired section body"}]},
            "artifact://repair",
        ),
    )

    out = pipeline.process("fake.png", model="gpt-4o", extraction_mode="legal_document_json_relaxed")
    assert out["success"] is True
    payload = json.loads(out["extracted_text"])
    assert payload["sections"][0]["body"] == "Repaired section body"
    assert out["metadata"]["json_extraction"]["validation_passed"] is False
    assert out["metadata"]["json_extraction"]["repair_invoked"] is True
    assert out["metadata"]["json_extraction"]["raw_output_ref"] == "artifact://raw"
    assert out["metadata"]["json_extraction"]["repair_snapshot_ref"] == "artifact://repair"


def test_relaxed_mode_unrecoverable_returns_failure_with_artifacts(monkeypatch) -> None:
    pipeline = _pipeline_stub()
    monkeypatch.setattr(pipeline, "_persist_relaxed_raw_output_for_postmortem", lambda **kwargs: "artifact://raw")
    monkeypatch.setattr(pipeline, "_repair_relaxed_json_with_edit_loop", lambda **kwargs: (None, "artifact://repair"))

    out = pipeline._postprocess_legal_json_result(
        result={"success": True, "extracted_text": "{bad json", "metadata": {}},
        extraction_mode="legal_document_json_relaxed",
        model="gpt-4o",
        context={"dossier_id": "D1"},
    )
    assert out["success"] is False
    assert out["error"] == "relaxed_json_validation_and_repair_failed"
    assert out["metadata"]["json_extraction"]["raw_output_ref"] == "artifact://raw"
    assert out["metadata"]["json_extraction"]["repair_snapshot_ref"] == "artifact://repair"


def test_post_t0_trigger_uses_text_fallback_without_auto_promote(monkeypatch) -> None:
    pipeline = ImageToTextPipeline.__new__(ImageToTextPipeline)
    calls: dict[str, object] = {}

    class _RegistryStub:
        def create_run(self, *, run_id: str, request: dict):  # type: ignore[no-untyped-def]
            calls["run_id"] = run_id
            calls["request"] = request
            return {}

        def update_run(self, *, run_id: str, patch: dict):  # type: ignore[no-untyped-def]
            calls["updated_run_id"] = run_id
            calls["patch"] = patch
            return {}

    pipeline.transcription_edit_run_registry = _RegistryStub()
    monkeypatch.setattr(
        pipeline,
        "_resolve_post_t0_source_transcript_ref",
        lambda *, dossier_id, transcription_id, best_result_index=None: None,
    )
    monkeypatch.setattr(
        "backend.pipelines.image_to_text.pipeline.run_orchestration_kernel_transcript_loop",
        lambda **_kw: TranscriptEditAgentRunResult(
            run_artifact_ref="ref://run",
            session_id="s1",
            iterations=1,
            status="completed",
            reason_code="ok",
            latest_refs={"x": 1},
            review_required=False,
        ),
    )
    monkeypatch.setenv("PLATTERA_POST_T0_TX_AGENT_MODE", "audit_then_repair_then_promote")
    monkeypatch.setenv("PLATTERA_POST_T0_TX_AGENT_EXECUTION", "sync")

    pipeline._maybe_trigger_transcript_edit_agent_background(
        extraction_mode="legal_document_json_relaxed",
        normalized_payload={"sections": [{"id": 1, "body": "Beginning at NW corner."}]},
        context={"dossier_id": "D1", "transcription_id": "T1"},
    )
    req = calls.get("request")
    assert isinstance(req, dict)
    assert req["auto_promote"] is False
    patch = calls.get("patch")
    assert isinstance(patch, dict)
    snapshot = patch.get("snapshot")
    assert isinstance(snapshot, dict)
    assert snapshot.get("status") == "completed"


def test_post_t0_trigger_prefers_transcript_ref_and_allows_promote(monkeypatch) -> None:
    pipeline = ImageToTextPipeline.__new__(ImageToTextPipeline)
    captured: dict[str, object] = {}

    class _RegistryStub:
        def create_run(self, *, run_id: str, request: dict):  # type: ignore[no-untyped-def]
            return {}

        def update_run(self, *, run_id: str, patch: dict):  # type: ignore[no-untyped-def]
            captured["patch"] = patch
            return {}

    pipeline.transcription_edit_run_registry = _RegistryStub()
    monkeypatch.setattr(
        pipeline,
        "_resolve_post_t0_source_transcript_ref",
        lambda *, dossier_id, transcription_id, best_result_index=None: "C:/tmp/source_ref.json",
    )

    def _fake_run(**_kw):  # type: ignore[no-untyped-def]
        captured["request"] = _kw.get("request")
        return TranscriptEditAgentRunResult(
            run_artifact_ref="ref://run",
            session_id="s1",
            iterations=1,
            status="completed",
            reason_code="ok",
            latest_refs={},
            review_required=False,
        )

    monkeypatch.setattr("backend.pipelines.image_to_text.pipeline.run_orchestration_kernel_transcript_loop", _fake_run)
    monkeypatch.setenv("PLATTERA_POST_T0_TX_AGENT_MODE", "audit_then_repair_then_promote")
    monkeypatch.setenv("PLATTERA_POST_T0_TX_AGENT_EXECUTION", "sync")

    pipeline._maybe_trigger_transcript_edit_agent_background(
        extraction_mode="legal_document_json_relaxed",
        normalized_payload={"sections": [{"id": 1, "body": "Beginning at NW corner."}]},
        context={"dossier_id": "D1", "transcription_id": "T1"},
    )
    req = captured.get("request")
    assert req is not None
    assert req.source_transcript_ref == "C:/tmp/source_ref.json"
    assert req.auto_promote is True


def test_resolve_post_t0_source_transcript_ref_prefers_best_versioned_draft(tmp_path, monkeypatch) -> None:
    pipeline = _pipeline_stub()
    dossier_id = "D1"
    transcription_id = "T1"
    raw = tmp_path / "views" / "transcriptions" / dossier_id / transcription_id / "raw"
    raw.mkdir(parents=True)
    versioned = raw / f"{transcription_id}_v2.json"
    base = raw / f"{transcription_id}.json"
    versioned.write_text("{}", encoding="utf-8")
    base.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("backend.pipelines.image_to_text.pipeline.dossiers_root", lambda: tmp_path)

    ref = pipeline._resolve_post_t0_source_transcript_ref(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        best_result_index=1,
    )
    assert ref == str(versioned)

