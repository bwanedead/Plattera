"""Tests for shared delegate subtask trace helpers."""

from __future__ import annotations

from harness.runtime.orchestration.subtasks.trace_fields import (
    build_subtask_trace,
    compact_image_refs_for_trace,
    compact_subtask_trace,
    compact_subtask_trace_for_prompt,
    format_delegate_trace_timing_parts,
)


def test_build_subtask_trace_includes_wall_and_epoch_fields() -> None:
    trace = build_subtask_trace(
        model="gpt-5.4",
        prompt_char_count=1200,
        image_attachment_count=1,
        hydration_seconds=0.1,
        prompt_build_seconds=0.02,
        model_call_seconds=4.5,
        output_normalize_seconds=0.01,
        started_at_epoch_seconds=1_700_000_000.0,
        finished_at_epoch_seconds=1_700_000_004.6,
        wall_seconds=4.63,
        retry_count=0,
    )
    assert trace["wall_seconds"] == 4.63
    assert trace["total_seconds"] == 4.63
    assert trace["started_at_epoch_seconds"] == 1_700_000_000.0
    assert trace["finished_at_epoch_seconds"] == 1_700_000_004.6


def test_compact_image_refs_strips_paths_and_b64() -> None:
    refs = compact_image_refs_for_trace(
        [
            {
                "ref_id": "image:derived:abc",
                "width_height": [800, 600],
                "size_bytes": 120_000,
                "mime_type": "image/png",
                "b64": "SECRET",
                "absolute_path": "C:/secret/path.png",
            }
        ]
    )
    assert refs == [
        {
            "ref_id": "image:derived:abc",
            "width_height": [800, 600],
            "size_bytes": 120_000,
            "mime_type": "image/png",
        }
    ]


def test_compact_subtask_trace_for_prompt_includes_bounded_timing_only() -> None:
    trace = compact_subtask_trace_for_prompt(
        {
            "model": "gpt-5.4",
            "wall_seconds": 3.2,
            "model_call_seconds": 3.0,
            "retry_count": 1,
            "prompt_char_count": 900,
            "image_attachment_count": 2,
            "hydration_seconds": 0.1,
            "raw_prompt_text": "strip",
        }
    )
    assert trace == {
        "wall_seconds": 3.2,
        "model_call_seconds": 3.0,
        "retry_count": 1,
        "prompt_char_count": 900,
        "image_attachment_count": 2,
    }


def test_format_delegate_trace_timing_parts_has_no_semantic_labels() -> None:
    parts = format_delegate_trace_timing_parts(
        {
            "wall_seconds": 2.5,
            "model_call_seconds": 2.1,
            "retry_count": 0,
            "prompt_char_count": 400,
            "image_attachment_count": 1,
            "image_refs": [
                {
                    "ref_id": "image:derived:abc",
                    "width_height": [640, 480],
                    "size_bytes": 50_000,
                    "mime_type": "image/png",
                }
            ],
        }
    )
    joined = " ".join(parts)
    assert "wall=2.5s" in joined
    assert "image_ref=image:derived:abc" in joined
    assert "size=[640, 480]" in joined or "size=" in joined
    for forbidden in ("slow", "bad", "inefficient"):
        assert forbidden not in joined.lower()


def test_format_delegate_trace_includes_llm_call_trace_tokens() -> None:
    parts = format_delegate_trace_timing_parts(
        {
            "wall_seconds": 80.55,
            "prompt_char_count": 4140,
            "llm_call_trace": {
                "input_tokens": 900,
                "cached_input_tokens": 120,
                "output_tokens": 200,
                "reasoning_tokens": 50,
                "retry_count_observed": None,
                "max_retries_configured": 4,
                "streaming_requested": False,
            },
        }
    )
    joined = " ".join(parts)
    assert "wall=80.55s" in joined
    assert "prompt_chars=4140" in joined
    assert "tokens=input=900" in joined
    assert "cached=120" in joined
    assert "output=200" in joined
    assert "retries=?" in joined
    assert "streaming=false" in joined


def test_format_delegate_trace_includes_requested_and_effective_streaming() -> None:
    parts = format_delegate_trace_timing_parts(
        {
            "wall_seconds": 10.0,
            "llm_call_trace": {
                "streaming_requested": True,
                "streaming_supported": False,
                "streaming_effective": False,
            },
        }
    )
    joined = " ".join(parts)
    assert "streaming=requested=true effective=false" in joined


def test_format_delegate_trace_includes_streaming_phase_timing() -> None:
    parts = format_delegate_trace_timing_parts(
        {
            "wall_seconds": 10.0,
            "llm_call_trace": {
                "streaming_requested": True,
                "provider_wait_seconds": 4.0,
                "response_stream_seconds": 6.0,
            },
        }
    )
    joined = " ".join(parts)
    assert "streaming=true" in joined
    assert "provider_wait=4.0s" in joined
    assert "response_stream=6.0s" in joined


def test_build_subtask_trace_embeds_llm_call_trace() -> None:
    trace = build_subtask_trace(
        model="gpt-5.4",
        prompt_char_count=100,
        wall_seconds=1.2,
        llm_call_trace={
            "provider": "openai",
            "call_role": "delegate",
            "call_name": "delegate_subtask",
            "model": "gpt-5.4",
            "started_at_epoch_seconds": 1.0,
            "finished_at_epoch_seconds": 2.2,
            "wall_seconds": 1.2,
            "prompt_char_count": 100,
            "response_char_count": 20,
            "input_tokens": 10,
            "output_tokens": 5,
            "streaming_requested": False,
            "streaming_supported": True,
            "b64": "SECRET",
        },
    )
    assert trace["llm_call_trace"]["call_role"] == "delegate"
    assert "b64" not in trace["llm_call_trace"]


def test_compact_subtask_trace_preserves_existing_fields() -> None:
    trace = compact_subtask_trace(
        {
            "model": "gpt-5.4",
            "prompt_char_count": 100,
            "image_attachment_count": 0,
            "hydration_seconds": 0.01,
            "prompt_build_seconds": 0.01,
            "model_call_seconds": 1.0,
            "output_normalize_seconds": 0.01,
            "wall_seconds": 1.03,
            "total_seconds": 1.03,
            "retry_count": 0,
            "b64": "strip",
        }
    )
    assert trace is not None
    assert trace.get("model_call_seconds") == 1.0
    assert trace.get("wall_seconds") == 1.03
    assert "b64" not in trace
