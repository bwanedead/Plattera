from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.pipelines.image_to_text.pipeline import ImageToTextPipeline
from backend.prompts.image_to_text import get_available_extraction_modes, get_image_to_text_prompt


def _pipeline_stub() -> ImageToTextPipeline:
    pipeline = ImageToTextPipeline.__new__(ImageToTextPipeline)
    pipeline.transcription_edit_run_service = None
    pipeline.transcription_edit_persistence = None
    return pipeline


def test_prompts_expose_relaxed_legal_mode() -> None:
    modes = get_available_extraction_modes()
    assert "legal_document_json_relaxed" in modes
    prompt = get_image_to_text_prompt("legal_document_json_relaxed")
    assert "JSON object" in prompt


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
