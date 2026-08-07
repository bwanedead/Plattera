"""Tests for generic harness LLM call trace builder and instrumentation."""

from __future__ import annotations

import json

import pytest

from harness.runtime.llm.instrumented_caller import (
    extract_trace_from_exception,
    instrument_model_caller,
)
from harness.runtime.llm.llm_call_trace import (
    LLM_CALL_TRACE_FIELDS,
    build_llm_call_trace,
    build_llm_call_trace_from_response,
    collect_llm_call_traces,
    extract_service_tier_requested,
    extract_streaming_requested,
    extract_usage_fields,
    resolve_call_role,
    sanitize_llm_call_trace,
    trace_is_json_serializable,
)
from harness.runtime.orchestration.llm_turn_choose_action_support import (
    build_llm_io_audit_record,
    build_repair_audit_record,
)
from harness.runtime.orchestration.repair_lane import RepairAttempt
from services.llm.call_options import LlmCallOptions


def test_trace_builder_produces_bounded_serializable_shape() -> None:
    trace = build_llm_call_trace(
        call_role="parent",
        call_name="choose_action",
        model="gpt-5.4",
        started_at_epoch_seconds=100.0,
        finished_at_epoch_seconds=157.4,
        prompt_char_count=187161,
        response_char_count=4200,
        input_tokens=40086,
        output_tokens=900,
    )
    assert set(trace.keys()).issubset(set(LLM_CALL_TRACE_FIELDS))
    assert trace["streaming_requested"] is False
    assert trace["streaming_supported"] is True
    assert trace["wall_seconds"] == 57.4
    assert trace_is_json_serializable(trace)
    json.dumps(trace)


def test_usage_extraction_reads_nested_reasoning_tokens() -> None:
    usage = extract_usage_fields(
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 40,
                "total_tokens": 140,
                "completion_tokens_details": {"reasoning_tokens": 28},
            }
        }
    )
    assert usage["reasoning_tokens"] == 28
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 40


def test_usage_extraction_prefers_top_level_reasoning_tokens() -> None:
    usage = extract_usage_fields(
        {
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "reasoning_tokens": 3,
                "completion_tokens_details": {"reasoning_tokens": 99},
                "total_tokens": 15,
            }
        }
    )
    assert usage["reasoning_tokens"] == 3


def test_usage_extraction_handles_cached_and_missing_usage() -> None:
    usage = extract_usage_fields(
        {
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "reasoning_tokens": 2,
                "total_tokens": 14,
                "cached_input_tokens": 3,
            }
        }
    )
    assert usage == {
        "input_tokens": 10,
        "cached_input_tokens": 3,
        "output_tokens": 4,
        "reasoning_tokens": 2,
        "total_tokens": 14,
    }
    assert extract_usage_fields({})["input_tokens"] is None


def test_build_trace_from_provider_response_maps_ids_and_error() -> None:
    trace = build_llm_call_trace_from_response(
        raw_response={
            "success": False,
            "error": "provider timeout",
            "usage": {"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
            "response_id": "resp_123",
            "request_id": "req_456",
            "service_tier_returned": "default",
        },
        call_role="parent",
        call_name="choose_action",
        model="gpt-5.4",
        prompt_char_count=100,
        started_at_epoch_seconds=1.0,
        finished_at_epoch_seconds=2.0,
    )
    assert trace["error_type"] == "provider_failure"
    assert trace["error_message_preview"] == "provider timeout"
    assert trace["response_id"] == "resp_123"
    assert trace["request_id"] == "req_456"
    assert trace["input_tokens"] == 5


def test_extract_service_tier_requested_reads_call_options_and_kwargs() -> None:
    assert extract_service_tier_requested(
        kwargs={"service_tier": "flex"},
        call_options=LlmCallOptions(phase="choose_action", service_tier="priority"),
    ) == "priority"
    assert extract_service_tier_requested(kwargs={"service_tier": "flex"}) == "flex"
    assert extract_service_tier_requested(
        raw_response={"service_tier_requested": "default"}
    ) == "default"


def test_instrumented_caller_passes_service_tier_into_trace() -> None:
    def _fake_caller(prompt: str, model: str, **kwargs):
        return {"success": True, "text": "{}", "service_tier_requested": "flex"}

    wrapped = instrument_model_caller(_fake_caller)
    result = wrapped(
        "hello",
        "gpt-5.4",
        call_options=LlmCallOptions(output_mode="json_object", phase="choose_action", service_tier="priority"),
    )
    trace = result["llm_call_trace"]
    assert trace["service_tier_requested"] == "priority"


def test_instrumented_caller_string_response_passes_through_without_embedded_trace() -> None:
    def _fake_caller(prompt: str, model: str, **kwargs):
        return '{"actions":[]}'

    wrapped = instrument_model_caller(_fake_caller)
    result = wrapped("hello", "gpt-5.4")
    assert isinstance(result, str)
    assert "llm_call_trace" not in result


def test_instrumented_caller_attaches_trace_to_mapping_response() -> None:
    def _fake_caller(prompt: str, model: str, **kwargs):
        return {
            "success": True,
            "text": '{"actions":[]}',
            "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
        }

    wrapped = instrument_model_caller(_fake_caller)
    result = wrapped(
        "hello",
        "gpt-5.4",
        call_options=LlmCallOptions(output_mode="json_object", phase="choose_action"),
    )
    assert isinstance(result, dict)
    trace = result.get("llm_call_trace")
    assert isinstance(trace, dict)
    assert trace["call_role"] == "parent"
    assert trace["call_name"] == "choose_action"
    assert trace["prompt_char_count"] == 5


def test_instrumented_caller_attaches_trace_to_exception() -> None:
    def _boom(prompt: str, model: str, **kwargs):
        raise RuntimeError("network down")

    wrapped = instrument_model_caller(_boom)
    with pytest.raises(RuntimeError, match="network down") as excinfo:
        wrapped("hello", "gpt-5.4", call_options=LlmCallOptions(phase="delegate_subtask"))
    trace = extract_trace_from_exception(excinfo.value)
    assert trace is not None
    assert trace["call_role"] == "delegate"
    assert trace["error_type"] == "RuntimeError"
    assert "network down" in str(trace["error_message_preview"])


def _audit_context(*, iterations: int = 1):
    continuity = type(
        "C",
        (),
        {"pending_agent_hydration": None, "pinned_refs_hydration": None},
    )()
    loop_memory = type(
        "LM",
        (),
        {"iterations": iterations, "contract_feedback": {}, "continuity": continuity},
    )()
    return type("Ctx", (), {"loop_memory": loop_memory})()


def test_parent_turn_audit_includes_llm_call_trace() -> None:
    record = build_llm_io_audit_record(
        context=_audit_context(iterations=1),  # type: ignore[arg-type]
        started_at_epoch_seconds=1.0,
        prompt_mode="normal",
        prompt="prompt",
        raw_response={
            "text": "{}",
            "llm_call_trace": build_llm_call_trace(
                call_role="parent",
                call_name="choose_action",
                model="gpt-5.4",
                started_at_epoch_seconds=1.0,
                finished_at_epoch_seconds=2.0,
                prompt_char_count=6,
            ),
        },
        parse_ok=True,
        parse_reason_code=None,
        plan=None,
        repair_records=None,
        parse_error_detail=None,
        original_action_count_attempted=None,
        mission_state_before=None,
        resolution_state_before=None,
        latest_refs_before={},
    )
    assert "llm_call_trace" in record
    assert record["llm_call_trace"]["call_role"] == "parent"


def test_parent_turn_audit_uses_plural_for_repair_trace() -> None:
    parent_trace = build_llm_call_trace(
        call_role="parent",
        call_name="choose_action",
        model="gpt-5.4",
        started_at_epoch_seconds=1.0,
        finished_at_epoch_seconds=2.0,
        prompt_char_count=10,
    )
    repair_trace = build_llm_call_trace(
        call_role="repair",
        call_name="choose_action_repair",
        model="gpt-5.4",
        started_at_epoch_seconds=2.0,
        finished_at_epoch_seconds=3.0,
        prompt_char_count=8,
    )
    record = build_llm_io_audit_record(
        context=_audit_context(iterations=2),  # type: ignore[arg-type]
        started_at_epoch_seconds=1.0,
        prompt_mode="normal",
        prompt="prompt",
        raw_response={"text": "{}", "llm_call_trace": parent_trace},
        parse_ok=False,
        parse_reason_code="invalid_json",
        plan=None,
        repair_records=[build_repair_audit_record(
            RepairAttempt(
                repair_prompt_text="repair",
                repair_raw_response_text="{}",
                repair_parse_ok=True,
                repair_parse_reason_code=None,
                repair_parsed_action_plan=None,
                repair_error=None,
                llm_call_trace=repair_trace,
            )
        )],
        parse_error_detail="bad json",
        original_action_count_attempted=1,
        mission_state_before=None,
        resolution_state_before=None,
        latest_refs_before={},
    )
    assert isinstance(record.get("llm_call_traces"), list)
    assert len(record["llm_call_traces"]) == 2
    assert record["llm_call_traces"][1]["call_role"] == "repair"


def test_collect_llm_call_traces_strips_raw_payload_keys() -> None:
    trace = sanitize_llm_call_trace(
        {
            "provider": "openai",
            "call_role": "parent",
            "call_name": "choose_action",
            "model": "gpt-5.4",
            "started_at_epoch_seconds": 1.0,
            "finished_at_epoch_seconds": 2.0,
            "wall_seconds": 1.0,
            "prompt_char_count": 10,
            "response_char_count": 2,
            "b64": "SECRET",
            "raw_prompt_text": "SECRET",
        }
    )
    assert "b64" not in trace
    assert "raw_prompt_text" not in trace


def test_resolve_call_role_maps_phases() -> None:
    assert resolve_call_role(phase="choose_action") == "parent"
    assert resolve_call_role(phase="choose_action_repair") == "repair"
    assert resolve_call_role(phase="delegate_subtask") == "delegate"
    assert resolve_call_role(phase="continuity_compaction") == "subagent"


def test_non_streaming_trace_does_not_fake_first_event_timing() -> None:
    trace = build_llm_call_trace(
        call_role="parent",
        call_name="choose_action",
        model="gpt-5.4",
        started_at_epoch_seconds=100.0,
        finished_at_epoch_seconds=157.4,
        prompt_char_count=100,
        streaming_requested=False,
    )
    assert "first_response_event_at_epoch_seconds" not in trace
    assert "provider_wait_seconds" not in trace
    assert "response_stream_seconds" not in trace


def test_streaming_trace_includes_first_event_timing() -> None:
    trace = build_llm_call_trace_from_response(
        raw_response={
            "success": True,
            "text": "{}",
            "streaming_requested": True,
            "first_response_event_at_epoch_seconds": 105.0,
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        },
        call_role="parent",
        call_name="choose_action",
        model="gpt-5.4",
        prompt_char_count=100,
        started_at_epoch_seconds=100.0,
        finished_at_epoch_seconds=110.0,
        streaming_requested=True,
    )
    assert trace["streaming_requested"] is True
    assert trace["first_response_event_at_epoch_seconds"] == 105.0
    assert trace["provider_wait_seconds"] == 5.0
    assert trace["response_stream_seconds"] == 5.0
    assert trace["time_to_first_response_event_seconds"] == 5.0


def test_extract_streaming_requested_reads_call_options() -> None:
    assert extract_streaming_requested(
        call_options=LlmCallOptions(streaming=True),
    ) is True
    assert extract_streaming_requested(
        kwargs={"stream": True},
    ) is True
    assert extract_streaming_requested() is False


def test_instrumented_caller_streaming_trace_has_phase_timing() -> None:
    def _fake_caller(prompt: str, model: str, **kwargs):
        return {
            "success": True,
            "text": "{}",
            "streaming_requested": True,
            "first_response_event_at_epoch_seconds": 12.5,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    wrapped = instrument_model_caller(_fake_caller)
    result = wrapped(
        "hello",
        "gpt-5.4",
        call_options=LlmCallOptions(streaming=True, phase="choose_action"),
    )
    trace = result["llm_call_trace"]
    assert trace["streaming_requested"] is True
    assert trace["provider_wait_seconds"] is not None
    assert trace["response_stream_seconds"] is not None
