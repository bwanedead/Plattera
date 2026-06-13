"""Tests for harness LLM streaming config resolution."""

from __future__ import annotations

from harness.runtime.llm.streaming_config import (
    apply_streaming_to_call_options,
    resolve_llm_streaming_enabled,
)
from services.llm.call_options import LlmCallOptions


def test_resolve_llm_streaming_disabled_by_default() -> None:
    assert resolve_llm_streaming_enabled() is False
    assert resolve_llm_streaming_enabled({}) is False


def test_resolve_llm_streaming_from_run_context() -> None:
    assert resolve_llm_streaming_enabled({"llm_streaming": True}) is True
    assert resolve_llm_streaming_enabled({"openai_streaming": True}) is True
    assert resolve_llm_streaming_enabled({"streaming": "yes"}) is True
    assert resolve_llm_streaming_enabled({"llm_streaming": False}) is False
    assert resolve_llm_streaming_enabled({"llm_streaming": "false"}) is False
    assert resolve_llm_streaming_enabled({"openai_streaming": "off"}) is False
    assert resolve_llm_streaming_enabled({"streaming": "0"}) is False


def test_run_context_explicit_false_beats_env(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_LLM_STREAMING", "true")
    assert resolve_llm_streaming_enabled({"llm_streaming": False}) is False
    assert resolve_llm_streaming_enabled({"openai_streaming": "false"}) is False
    assert resolve_llm_streaming_enabled({"streaming": False}) is False


def test_run_context_explicit_true_beats_env_false(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_LLM_STREAMING", "false")
    assert resolve_llm_streaming_enabled({"llm_streaming": True}) is True


def test_apply_streaming_to_call_options_preserves_other_fields(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_LLM_STREAMING", "true")
    base = LlmCallOptions(output_mode="json_object", phase="choose_action")
    out = apply_streaming_to_call_options(base, run_context={})
    assert out.streaming is True
    assert out.output_mode == "json_object"
    assert out.phase == "choose_action"


def test_apply_streaming_override_false_even_when_context_true() -> None:
    base = LlmCallOptions(streaming=False)
    out = apply_streaming_to_call_options(
        base,
        run_context={"llm_streaming": True},
        streaming=False,
    )
    assert out.streaming is False


def test_apply_streaming_respects_context_false_over_env(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_LLM_STREAMING", "true")
    base = LlmCallOptions(output_mode="json_object", phase="choose_action")
    out = apply_streaming_to_call_options(base, run_context={"llm_streaming": False})
    assert out.streaming is False
