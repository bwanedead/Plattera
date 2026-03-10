from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.tooling import (
    TranscriptImageVerificationTool,
    TranscriptOrientBaselineTool,
    TranscriptSpanOpenerTool,
)
from backend.transcript_edit.persistence import TranscriptionEditPersistenceService


def test_tx_open_transcript_spans_supports_offsets_and_anchors() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "transcript.json"
        payload = {
            "sections": [
                {"id": "s1", "body": "Beginning at NW corner."},
                {"id": "s2", "body": "Thence east 100 feet to point of beginning."},
            ]
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

        tool = TranscriptSpanOpenerTool()
        by_offsets = tool.open_transcript_spans(
            {
                "dossier_id": "D1",
                "source_transcript_ref": str(path),
                "spans": [{"span_id": "a", "start_char": 0, "end_char": 20}],
            }
        )
        assert by_offsets["reason_codes"] == ["tx_spans_opened"]
        artifact_ref = by_offsets.get("artifact_ref")
        assert artifact_ref is not None
        artifact_path = (
            artifact_ref.get("artifact_path")
            if isinstance(artifact_ref, dict)
            else getattr(artifact_ref, "artifact_path", None)
        )
        assert isinstance(artifact_path, str)
        assert Path(artifact_path).exists()
        spans = by_offsets["spans"]
        assert isinstance(spans, list) and spans
        assert "Beginning at" in spans[0]["text"]

        by_anchors = tool.open_transcript_spans(
            {
                "source_transcript_ref": str(path),
                "anchors": [{"span_id": "b", "start_anchor": "Beginning at", "end_anchor": "point of beginning"}],
            }
        )
        assert by_anchors["reason_codes"] == ["tx_spans_opened"]
        spans2 = by_anchors["spans"]
        assert isinstance(spans2, list) and spans2
        assert "point of beginning" in spans2[0]["text"]


class _FakeCompletionMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeCompletionChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeCompletionMessage(content)


class _FakeCompletionResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeCompletionChoice(content)]


class _FakeChatCompletions:
    def create(self, **kwargs: Any) -> _FakeCompletionResponse:
        del kwargs
        return _FakeCompletionResponse(
            json.dumps(
                {
                    "items": [
                        {
                            "key": "range",
                            "state": "verified",
                            "selected_value": "Range 75 West",
                            "alternatives": ["Range 75 West"],
                            "confidence": "high",
                            "layer_tag": "layer1_canonical_recovery",
                            "operational_impact": "mapping_blocking",
                            "block_reason": "ambiguity",
                            "required_information": "",
                            "minimal_user_action": "",
                            "resolution_options": ["Range 75 West"],
                            "self_retrievable": "yes",
                            "retrieval_attempted": True,
                            "retrieval_blocker": None,
                            "verification_required": False,
                            "attempt_summary": "resolved",
                            "evidence_refs": ["orient_llm"],
                            "provenance": "orient_llm",
                        }
                    ]
                }
            )
        )


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.chat = type("_FakeChat", (), {"completions": _FakeChatCompletions()})()


class _FakeOpenAIService:
    def __init__(self) -> None:
        self.models = {"gpt-5.2": {"api_model_name": "gpt-5.2"}}
        self.client = _FakeOpenAIClient()

    def is_available(self) -> bool:
        return True


def _write_transcript(path: Path, body: str) -> None:
    path.write_text(
        json.dumps(
            {
                "documentId": "doc1",
                "sections": [{"id": 1, "body": body}],
            }
        ),
        encoding="utf-8",
    )


def test_tx_orient_baseline_uses_refs_and_reports_hydration_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        canonical_path = root / "canonical.json"
        _write_transcript(canonical_path, "Canonical transcript text.")
        candidate_refs: list[str] = []
        for idx in range(1, 6):
            path = root / f"candidate_{idx}.json"
            _write_transcript(path, f"Candidate {idx} range token text.")
            candidate_refs.append(str(path))
        tool = TranscriptOrientBaselineTool(
            persistence=TranscriptionEditPersistenceService(root=root / "artifacts"),
            service=_FakeOpenAIService(),
        )
        result = tool.orient_and_baseline(
            {
                "dossier_id": "D1",
                "canonical_ref": str(canonical_path),
                "candidate_refs": candidate_refs,
                "max_candidates_for_orient": 3,
                "max_total_hydrated_bytes": 50000,
                "max_bytes_per_candidate": 10000,
                "selection_strategy": "first_middle_last",
            }
        )
        assert result["reason_codes"] == ["tx_orient_baseline_completed"]
        hydration = result.get("tx_orient_hydration")
        assert isinstance(hydration, dict)
        assert hydration["payload_mode"] == "refs"
        assert hydration["inline_fallback_used"] is False
        assert hydration["candidate_refs_total"] == 5
        assert hydration["candidate_refs_hydrated"] == 3
        assert hydration["candidate_refs_skipped"] == 2
        assert hydration["hydration_selection_strategy"] == "first_middle_last"


def test_tx_orient_baseline_ref_budget_exhausted_refuses() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        canonical_path = root / "canonical.json"
        _write_transcript(canonical_path, "Canonical transcript text.")
        candidate_path = root / "candidate_1.json"
        _write_transcript(candidate_path, "x" * 6000)
        tool = TranscriptOrientBaselineTool(
            persistence=TranscriptionEditPersistenceService(root=root / "artifacts"),
            service=_FakeOpenAIService(),
        )
        result = tool.orient_and_baseline(
            {
                "dossier_id": "D1",
                "canonical_ref": str(canonical_path),
                "candidate_refs": [str(candidate_path)],
                "max_candidates_for_orient": 1,
                "max_total_hydrated_bytes": 2000,
                "max_bytes_per_candidate": 10000,
            }
        )
        assert result["reason_codes"] == ["orient_hydration_budget_exhausted"]
        refusal = result.get("kernel_refusal")
        assert isinstance(refusal, dict)
        assert refusal.get("reason_code") == "orient_hydration_budget_exhausted"


class _FakeImageVisionService:
    def __init__(self) -> None:
        self.models = {"gpt-5.2": {"api_model_name": "gpt-5.2"}}
        self.client = object()
        self.calls: list[str] = []

    def is_available(self) -> bool:
        return True

    def call_vision(self, *, prompt: str, image_data: str, model: str, json_mode: str, max_tokens: int, detail: str) -> dict[str, Any]:
        del image_data, model, json_mode, max_tokens, detail
        self.calls.append(prompt)
        if "Locate where likely visual evidence appears" in prompt:
            return {
                "success": True,
                "text": json.dumps(
                    {
                        "status": "located",
                        "confidence": "medium",
                        "crop_box": {"x": 8, "y": 10, "width": 60, "height": 30},
                        "context_crop_box": {"x": 0, "y": 0, "width": 90, "height": 60},
                        "reason": "Likely clause with numeric token.",
                    }
                ),
            }
        return {
            "success": True,
            "text": json.dumps(
                {
                    "status": "match",
                    "confidence": "high",
                    "observed_text": "Range 74 West",
                    "reason": "Token visible in focused crop.",
                }
            ),
        }


def _write_sample_image(path: Path) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (120, 90), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((5, 8, 110, 78), outline=(0, 0, 0), width=2)
    draw.text((10, 15), "Range 74 West", fill=(0, 0, 0))
    img.save(path, format="PNG")


def test_tx_image_verify_creates_evidence_region_artifacts_and_surfaces_refs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        image_path = root / "source.png"
        transcript_path = root / "source.json"
        _write_sample_image(image_path)
        transcript_path.write_text(json.dumps({"sections": [{"id": "s1", "body": "Range token."}]}), encoding="utf-8")
        tool = TranscriptImageVerificationTool(service=_FakeImageVisionService())
        result = tool.verify_transcript_with_image(
            {
                "dossier_id": "D1",
                "source_transcript_ref": str(transcript_path),
                "image_ref": str(image_path),
                "checks": [{"check_id": "range_check_1", "query": "Does this show Range 74 West?", "decision_key": "range"}],
                "model": "gpt-5.2",
            }
        )
        assert result["reason_codes"] == ["tx_image_verified"]
        assert isinstance(result.get("tx_image_evidence_region_ref"), dict)
        assert isinstance(result.get("tx_image_evidence_context_ref"), dict)
        regions = result.get("tx_image_evidence_regions")
        assert isinstance(regions, list) and regions
        first = regions[0]
        assert str(first.get("status") or "") == "located"
        assert isinstance(first.get("crop_box"), dict)
        region_ref = first.get("tx_image_evidence_region_ref")
        assert isinstance(region_ref, dict)
        assert Path(str(region_ref.get("artifact_path") or "")).exists()


def test_tx_image_verify_falls_back_to_full_image_when_locator_unclear() -> None:
    class _UnclearLocatorService(_FakeImageVisionService):
        def call_vision(self, *, prompt: str, image_data: str, model: str, json_mode: str, max_tokens: int, detail: str) -> dict[str, Any]:
            del image_data, model, json_mode, max_tokens, detail
            self.calls.append(prompt)
            if "Locate where likely visual evidence appears" in prompt:
                return {"success": True, "text": json.dumps({"status": "unclear", "confidence": "low", "reason": "Not enough contrast."})}
            return {
                "success": True,
                "text": json.dumps({"status": "unclear", "confidence": "low", "observed_text": "", "reason": "Cannot read token."}),
            }

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        image_path = root / "source.png"
        transcript_path = root / "source.json"
        _write_sample_image(image_path)
        transcript_path.write_text(json.dumps({"sections": [{"id": "s1", "body": "Range token."}]}), encoding="utf-8")
        tool = TranscriptImageVerificationTool(service=_UnclearLocatorService())
        result = tool.verify_transcript_with_image(
            {
                "dossier_id": "D1",
                "source_transcript_ref": str(transcript_path),
                "image_ref": str(image_path),
                "checks": [{"check_id": "range_check_1", "query": "Find range token.", "decision_key": "range"}],
                "model": "gpt-5.2",
            }
        )
        assert result["reason_codes"] == ["tx_image_verified"]
        regions = result.get("tx_image_evidence_regions")
        assert isinstance(regions, list) and regions
        assert str((regions[0] or {}).get("status") or "") == "unclear"


def test_tx_image_verify_does_not_double_crop_when_region_artifact_is_used() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        image_path = root / "source.png"
        transcript_path = root / "source.json"
        _write_sample_image(image_path)
        transcript_path.write_text(json.dumps({"sections": [{"id": "s1", "body": "Range token."}]}), encoding="utf-8")
        tool = TranscriptImageVerificationTool(service=_FakeImageVisionService())
        result = tool.verify_transcript_with_image(
            {
                "dossier_id": "D1",
                "source_transcript_ref": str(transcript_path),
                "image_ref": str(image_path),
                "checks": [{"check_id": "range_check_1", "query": "Does this show Range 74 West?", "decision_key": "range"}],
                "model": "gpt-5.2",
            }
        )
        artifact_ref = result.get("artifact_ref")
        artifact_path = (
            str(artifact_ref.get("artifact_path") or "")
            if isinstance(artifact_ref, dict)
            else str(getattr(artifact_ref, "artifact_path", "") or "")
        )
        assert artifact_path
        payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        rows = payload.get("results")
        assert isinstance(rows, list) and rows
        render_meta = rows[0].get("render_meta") if isinstance(rows[0], dict) else {}
        assert isinstance(render_meta, dict)
        assert render_meta.get("crop_box") is None
        # Locator crop is 60x30, isolated artifact default zoom is 2.2 -> 132x66.
        assert render_meta.get("rendered_size") == [132, 66]


def test_tx_image_inspection_reference_and_select_refine_verify_region_modes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        image_path = root / "source.png"
        transcript_path = root / "source.json"
        _write_sample_image(image_path)
        transcript_path.write_text(json.dumps({"sections": [{"id": "s1", "body": "Range token."}]}), encoding="utf-8")
        tool = TranscriptImageVerificationTool(service=_FakeImageVisionService())

        inspection = tool.verify_transcript_with_image(
            {
                "dossier_id": "D1",
                "source_transcript_ref": str(transcript_path),
                "image_ref": str(image_path),
                "mode": "inspection_reference",
                "grid_spec": {"rows": 4, "cols": 4},
                "model": "gpt-5.2",
            }
        )
        assert inspection["reason_codes"] == ["tx_image_inspection_ready"]
        assert isinstance(inspection.get("tx_image_inspection_ref"), dict)
        assert int(inspection.get("image_width") or 0) > 0
        assert int(inspection.get("image_height") or 0) > 0

        selected = tool.verify_transcript_with_image(
            {
                "dossier_id": "D1",
                "source_transcript_ref": str(transcript_path),
                "image_ref": str(image_path),
                "mode": "select_region",
                "target": {
                    "crop_box_pixels": {"x": 8, "y": 10, "width": 60, "height": 30},
                    "zoom_factor": 2.0,
                    "decision_key": "range",
                },
                "model": "gpt-5.2",
            }
        )
        assert selected["reason_codes"] == ["tx_image_region_selected"]
        region_ref = selected.get("tx_image_evidence_region_ref")
        assert isinstance(region_ref, dict)
        assert Path(str(region_ref.get("artifact_path") or "")).exists()
        assert isinstance(selected.get("tx_image_region_lineage_ref"), dict)
        assert str(selected.get("selector_type") or "") == "pixel_box"

        refined = tool.verify_transcript_with_image(
            {
                "dossier_id": "D1",
                "source_transcript_ref": str(transcript_path),
                "image_ref": str(image_path),
                "mode": "refine_region",
                "target": {
                    "region_ref": region_ref,
                    "transform": "expand",
                    "amount": 0.25,
                    "decision_key": "range",
                },
                "model": "gpt-5.2",
            }
        )
        assert refined["reason_codes"] == ["tx_image_region_refined"]
        refined_ref = refined.get("tx_image_evidence_region_ref")
        assert isinstance(refined_ref, dict)
        assert str(refined_ref.get("artifact_path") or "") != str(region_ref.get("artifact_path") or "")
        assert isinstance(refined.get("parent_region_ref"), dict)

        verified = tool.verify_transcript_with_image(
            {
                "dossier_id": "D1",
                "source_transcript_ref": str(transcript_path),
                "image_ref": str(image_path),
                "mode": "verify_region",
                "target": {
                    "region_ref": refined_ref,
                    "query": "Does this show Range 74 West?",
                    "expected_text": "Range 74 West",
                },
                "model": "gpt-5.2",
            }
        )
        assert verified["reason_codes"] == ["tx_image_verified"]
        rows = verified.get("tx_image_verify_results")
        assert isinstance(rows, list) and rows


def test_tx_image_select_region_records_selector_type_for_normalized_pixel_and_grid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        image_path = root / "source.png"
        transcript_path = root / "source.json"
        _write_sample_image(image_path)
        transcript_path.write_text(json.dumps({"sections": [{"id": "s1", "body": "Range token."}]}), encoding="utf-8")
        tool = TranscriptImageVerificationTool(service=_FakeImageVisionService())

        def _select(target: dict[str, Any]) -> dict[str, Any]:
            return tool.verify_transcript_with_image(
                {
                    "dossier_id": "D1",
                    "source_transcript_ref": str(transcript_path),
                    "image_ref": str(image_path),
                    "mode": "select_region",
                    "target": target,
                    "model": "gpt-5.2",
                }
            )

        normalized = _select(
            {
                "crop_box_normalized": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.2},
                "zoom_factor": 2.0,
                "decision_key": "range",
            }
        )
        pixel = _select(
            {
                "crop_box_pixels": {"x": 8, "y": 10, "width": 40, "height": 20},
                "zoom_factor": 2.0,
                "decision_key": "range",
            }
        )
        grid = _select(
            {
                "grid_selection": {"row_start": 1, "row_end": 2, "col_start": 1, "col_end": 3},
                "grid_spec": {"rows": 6, "cols": 6},
                "zoom_factor": 2.0,
                "decision_key": "range",
            }
        )

        assert str(normalized.get("selector_type") or "") == "normalized_box"
        assert str(pixel.get("selector_type") or "") == "pixel_box"
        assert str(grid.get("selector_type") or "") == "grid_selection"

        lineage_ref = normalized.get("tx_image_region_lineage_ref")
        lineage_path = Path(str((lineage_ref or {}).get("artifact_path") or ""))
        assert lineage_path.exists()
        lineage_payload = json.loads(lineage_path.read_text(encoding="utf-8"))
        assert str(lineage_payload.get("selector_type") or "") == "normalized_box"
