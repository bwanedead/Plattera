from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.tooling import TranscriptOrientBaselineTool, TranscriptSpanOpenerTool
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
