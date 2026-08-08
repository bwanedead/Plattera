"""Fake-client tests for MetaModelService (no live Meta API calls)."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from services.llm.call_options import LlmCallOptions
from services.llm.meta import (
    META_DEFAULT_BASE_URL,
    META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
    MetaModelService,
    _get_meta_api_key,
    _get_meta_base_url,
)


SECRET_KEY = "meta-test-secret-key-do-not-leak"


class _FakeResponsesAPI:
    def __init__(
        self,
        *,
        response: Any | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self.last_kwargs: dict[str, Any] | None = None
        self._response = response
        self._raise_exc = raise_exc

    def create(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response


class _FakeClient:
    def __init__(self, responses: _FakeResponsesAPI) -> None:
        self.responses = responses


def _ok_response(
    *,
    text: str = "hello",
    status: str = "completed",
    usage: SimpleNamespace | None = None,
    model: str = META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
    response_id: str = "resp_meta_1",
    output: list[Any] | None = None,
    incomplete_reason: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=response_id,
        model=model,
        status=status,
        output_text=text,
        output=output or [],
        usage=usage,
        incomplete_details=(
            SimpleNamespace(reason=incomplete_reason) if incomplete_reason else None
        ),
    )


def _service_with_fake(
    *,
    response: Any | None = None,
    raise_exc: Exception | None = None,
) -> tuple[MetaModelService, _FakeResponsesAPI]:
    service = MetaModelService()
    fake = _FakeResponsesAPI(response=response, raise_exc=raise_exc)
    service.client = _FakeClient(fake)
    return service, fake


def test_missing_key_provider_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("META_MODEL_API_KEY", raising=False)
    # Generic MODEL_API_KEY must not unlock the Meta provider.
    monkeypatch.setenv("MODEL_API_KEY", "should-not-be-used")
    assert _get_meta_api_key() is None
    service = MetaModelService()
    assert service.is_available() is False
    result = service.call_text("hi", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert result["success"] is False
    assert "not configured" in str(result["error"]).lower()


def test_present_key_provider_available(monkeypatch) -> None:
    monkeypatch.setenv("META_MODEL_API_KEY", SECRET_KEY)
    monkeypatch.delenv("META_MODEL_API_BASE_URL", raising=False)
    service = MetaModelService()
    assert service.is_available() is True
    assert service.client is not None


def test_blank_base_url_uses_canonical_default(monkeypatch) -> None:
    monkeypatch.setenv("META_MODEL_API_BASE_URL", "   ")
    assert _get_meta_base_url() == META_DEFAULT_BASE_URL


def test_explicit_base_url_stripped_and_used(monkeypatch) -> None:
    monkeypatch.setenv("META_MODEL_API_BASE_URL", "  https://example.meta.test/v1  ")
    assert _get_meta_base_url() == "https://example.meta.test/v1"


def test_key_never_appears_in_logs_or_failures(monkeypatch, caplog) -> None:
    monkeypatch.setenv("META_MODEL_API_KEY", SECRET_KEY)
    service, fake = _service_with_fake(
        raise_exc=RuntimeError(f"boom including {SECRET_KEY}")
    )
    with caplog.at_level(logging.INFO):
        result = service.call_text("prompt", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert result["success"] is False
    blob = str(result) + " ".join(r.message for r in caplog.records)
    assert SECRET_KEY not in blob
    assert fake.last_kwargs is not None


def test_muse_contributor_catalog_entry() -> None:
    entry = MetaModelService.models[META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID]
    assert entry["name"] == "Muse Spark 1.2 Contributor"
    assert entry["provider"] == "meta"
    assert entry["cost_tier"] == "contributor"
    assert entry["capabilities"] == ["text", "vision", "reasoning"]
    assert entry["api_model_name"] == META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID
    assert entry["context_window_tokens"] == 1_048_576
    assert "max_output_tokens" not in entry
    assert MetaModelService().supports_streaming() is False


def test_plain_text_request_shape() -> None:
    service, fake = _service_with_fake(response=_ok_response(text="ok"))
    result = service.call_text("plain prompt", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert result["success"] is True
    assert fake.last_kwargs is not None
    assert fake.last_kwargs["model"] == META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID
    assert fake.last_kwargs["store"] is False
    assert "text" not in fake.last_kwargs
    content = fake.last_kwargs["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "plain prompt"}


def test_json_object_mode_uses_text_format() -> None:
    service, fake = _service_with_fake(response=_ok_response(text='{"ok":true}'))
    result = service.call_text(
        "json prompt",
        META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
        call_options=LlmCallOptions(output_mode="json_object", phase="choose_action"),
    )
    assert result["success"] is True
    assert result["text"] == '{"ok":true}'
    assert isinstance(result["text"], str)
    assert fake.last_kwargs["text"] == {"format": {"type": "json_object"}}
    assert fake.last_kwargs["max_output_tokens"] == 32_000
    assert fake.last_kwargs["reasoning"] == {"effort": "medium"}


def test_one_image_and_ordered_multi_images() -> None:
    service, fake = _service_with_fake(response=_ok_response())
    service.call_text(
        "see",
        META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
        call_options=LlmCallOptions(
            image_attachments=(
                {"b64": "AAA", "media_type": "image/png"},
                {"b64": "BBB", "media_type": "image/jpeg"},
            )
        ),
    )
    content = fake.last_kwargs["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert content[1] == {
        "type": "input_image",
        "image_url": "data:image/png;base64,AAA",
    }
    assert content[2] == {
        "type": "input_image",
        "image_url": "data:image/jpeg;base64,BBB",
    }


def test_delegate_phase_budget() -> None:
    service, fake = _service_with_fake(response=_ok_response())
    service.call_text(
        "delegate work",
        META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
        call_options=LlmCallOptions(phase="delegate_subtask"),
    )
    assert fake.last_kwargs["max_output_tokens"] == 8_000


def test_explicit_max_tokens_authoritative() -> None:
    service, fake = _service_with_fake(response=_ok_response())
    service.call_text(
        "limited",
        META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
        max_tokens=1234,
        call_options=LlmCallOptions(output_mode="json_object", phase="choose_action"),
    )
    assert fake.last_kwargs["max_output_tokens"] == 1234
    assert "reasoning" not in fake.last_kwargs


def test_streaming_requested_fails_stably() -> None:
    service, fake = _service_with_fake(response=_ok_response())
    result = service.call_text(
        "stream me",
        META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
        call_options=LlmCallOptions(streaming=True),
    )
    assert result["success"] is False
    assert result["finish_reason"] == "streaming_unsupported"
    assert "streaming" in str(result["error"]).lower()
    assert fake.last_kwargs is None


def test_successful_usage_mapping_and_none_optional_dims() -> None:
    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        input_tokens_details=SimpleNamespace(cached_tokens=3),
        output_tokens_details=SimpleNamespace(reasoning_tokens=7),
    )
    service, _ = _service_with_fake(response=_ok_response(text="done", usage=usage))
    result = service.call_text("p", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert result["success"] is True
    assert result["usage"] == {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "cached_input_tokens": 3,
        "reasoning_tokens": 7,
        "total_tokens": 30,
    }
    assert result["model"] == META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID
    assert result["provider_model"] == META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID
    assert result["api_model"] == META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID
    assert result["finish_reason"] == "stop"
    assert result["response_id"] == "resp_meta_1"

    sparse = SimpleNamespace(
        input_tokens=1,
        output_tokens=2,
        total_tokens=None,
        input_tokens_details=None,
        output_tokens_details=None,
    )
    service2, _ = _service_with_fake(response=_ok_response(text="x", usage=sparse))
    result2 = service2.call_text("p", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert result2["usage"]["cached_input_tokens"] is None
    assert result2["usage"]["reasoning_tokens"] is None
    assert result2["usage"]["total_tokens"] is None


def test_length_truncation_preserves_partial_text() -> None:
    service, _ = _service_with_fake(
        response=_ok_response(
            text='{"partial":true',
            status="incomplete",
            incomplete_reason="max_output_tokens",
            usage=SimpleNamespace(
                input_tokens=1,
                output_tokens=5,
                total_tokens=6,
                input_tokens_details=None,
                output_tokens_details=None,
            ),
        )
    )
    result = service.call_text(
        "p",
        META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
        call_options=LlmCallOptions(output_mode="json_object", phase="choose_action"),
    )
    assert result["success"] is False
    assert result["finish_reason"] == "length"
    assert "truncated" in str(result["error"]).lower()
    assert result["text"] == '{"partial":true'


def test_non_length_incomplete_is_not_truncation() -> None:
    service, _ = _service_with_fake(
        response=_ok_response(
            text="partial-incomplete",
            status="incomplete",
            incomplete_reason="content_filter",
        )
    )
    # Without a refusal content part, non-length incomplete stays incomplete.
    result = service.call_text("p", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert result["success"] is False
    assert result["finish_reason"] == "incomplete"
    assert "incomplete" in str(result["error"]).lower()
    assert "truncated" not in str(result["error"]).lower()
    assert result["text"] == "partial-incomplete"


def test_incomplete_refusal_classified_as_content_filter() -> None:
    refusal_part = SimpleNamespace(type="refusal", refusal="policy blocked")
    msg = SimpleNamespace(type="message", content=[refusal_part])
    service, fake = _service_with_fake(
        response=_ok_response(
            text="",
            status="incomplete",
            incomplete_reason="max_output_tokens",
            output=[msg],
        )
    )
    result = service.call_text("p", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert result["success"] is False
    assert result["finish_reason"] == "content_filter"
    assert result["text"] == "policy blocked"
    assert fake.last_kwargs is not None


def test_empty_output_and_completed_refusal() -> None:
    empty_svc, _ = _service_with_fake(response=_ok_response(text=""))
    empty = empty_svc.call_text("p", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert empty["success"] is False
    assert "empty" in str(empty["error"]).lower()

    refusal_part = SimpleNamespace(type="refusal", refusal="blocked")
    msg = SimpleNamespace(type="message", content=[refusal_part])
    refusal_svc, _ = _service_with_fake(
        response=_ok_response(text="", output=[msg])
    )
    refused = refusal_svc.call_text("p", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert refused["success"] is False
    assert refused["finish_reason"] == "content_filter"


def test_failed_and_cancelled_remain_distinct() -> None:
    failed_svc, _ = _service_with_fake(
        response=_ok_response(text="x", status="failed")
    )
    failed = failed_svc.call_text("p", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert failed["success"] is False
    assert failed["finish_reason"] == "failed"

    cancelled_svc, _ = _service_with_fake(
        response=_ok_response(text="y", status="cancelled")
    )
    cancelled = cancelled_svc.call_text("p", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert cancelled["success"] is False
    assert cancelled["finish_reason"] == "cancelled"


def test_sdk_exception_no_secret_leak(monkeypatch) -> None:
    monkeypatch.setenv("META_MODEL_API_KEY", SECRET_KEY)
    service, _ = _service_with_fake(raise_exc=ConnectionError("network down"))
    result = service.call_text("p", META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID)
    assert result["success"] is False
    assert "ConnectionError" in str(result["error"])
    assert SECRET_KEY not in str(result)


def test_call_vision_reuses_multimodal_path() -> None:
    service, fake = _service_with_fake(response=_ok_response(text="seen"))
    result = service.call_vision(
        "describe",
        "IMGDATA",
        META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
        media_type="image/webp",
    )
    assert result["success"] is True
    content = fake.last_kwargs["input"][0]["content"]
    assert content[1]["image_url"] == "data:image/webp;base64,IMGDATA"


def test_call_vision_preserves_options_and_appends_image() -> None:
    service, fake = _service_with_fake(response=_ok_response(text="seen"))
    existing = LlmCallOptions(
        output_mode="json_object",
        phase="delegate_subtask",
        service_tier="priority",
        streaming=False,
        image_attachments=(
            {"b64": "ONE", "media_type": "image/png"},
            {"b64": "TWO", "media_type": "image/jpeg"},
        ),
    )
    result = service.call_vision(
        "describe",
        "THREE",
        META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
        media_type="image/webp",
        call_options=existing,
    )
    assert result["success"] is True
    assert fake.last_kwargs["text"] == {"format": {"type": "json_object"}}
    assert fake.last_kwargs["max_output_tokens"] == 8_000
    content = fake.last_kwargs["input"][0]["content"]
    assert [c.get("image_url") for c in content if c.get("type") == "input_image"] == [
        "data:image/png;base64,ONE",
        "data:image/jpeg;base64,TWO",
        "data:image/webp;base64,THREE",
    ]
    # Existing options object must not be mutated.
    assert len(existing.image_attachments) == 2


def test_call_vision_rejects_invalid_image_without_provider_call() -> None:
    service, fake = _service_with_fake(response=_ok_response())
    for bad in ("", "   ", None, 123):
        result = service.call_vision(
            "describe",
            bad,  # type: ignore[arg-type]
            META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
        )
        assert result["success"] is False
        assert fake.last_kwargs is None

    result_media = service.call_vision(
        "describe",
        "OK",
        META_MUSE_SPARK_CONTRIBUTOR_MODEL_ID,
        media_type="   ",
    )
    assert result_media["success"] is False
    assert fake.last_kwargs is None
