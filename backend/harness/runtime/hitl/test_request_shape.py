from __future__ import annotations

from harness.runtime.hitl.request_shape import normalize_hitl_request


def test_normalize_hitl_request_preserves_evidence_packet_context() -> None:
    req = normalize_hitl_request(
        {
            "message": "Which range is correct?",
            "choices": ["Range 74", "Range 75", "Unable to determine", "Other / needs nuance"],
            "context": {
                "evidence_refs": ["image:derived:crop-1", "image:derived:crop-2"],
                "primary_evidence_ref": "image:derived:crop-1",
                "annotated_evidence_ref": "image:derived:crop-2",
                "question_regions": [{"label": "range call", "x": 10, "y": 20, "w": 80, "h": 24}],
            },
        },
        iteration=7,
    )
    assert req["choices"][-2:] == ["Unable to determine", "Other / needs nuance"]
    assert req["context"]["primary_evidence_ref"] == "image:derived:crop-1"
    assert req["context"]["annotated_evidence_ref"] == "image:derived:crop-2"
    assert req["context"]["evidence_refs"] == ["image:derived:crop-1", "image:derived:crop-2"]
    assert isinstance(req["context"]["question_regions"], list)

