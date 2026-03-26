"""Stable facade for controller loop public surface and compatibility helpers."""

from __future__ import annotations

from .controller_runtime import (
    ControllerLoopError,
    ControllerRunResult,
    IterationDigestClient,
    NextStepLLMClient,
    run_controller_loop,
)
from .controller_transcript import (
    restore_transcript_event_hook,
    set_transcript_event_hook,
    _append_event,
    _controller_proposal_log_payload,
)
from . import controller_bootstrap as _controller_bootstrap_module
from .controller_context import _build_context_packet, _safe_artifact_hint
from .controller_guardrails import (
    _compute_controller_idempotency_key,
    _ir_health_from_hint,
    _semantic_span_repair_signature_for_context,
    _semantic_span_repair_thrash_refusal,
)
from .controller_proposals import _autofill_known_args, _build_fix_skeleton, _refusal_repair_request
from .controller_summary import _bound_run_summary_memory, _build_run_summary_entry
from .bootstrap import load_transcript_span_seeds_for_mapping, materialize_seed_spans_from_text


def _bootstrap_deed_span_index_from_transcript_seeds(*args: object, **kwargs: object):
    """Compatibility wrapper that preserves controller-module monkeypatch seams."""
    _controller_bootstrap_module.load_transcript_span_seeds_for_mapping = load_transcript_span_seeds_for_mapping
    _controller_bootstrap_module.materialize_seed_spans_from_text = materialize_seed_spans_from_text
    return _controller_bootstrap_module._bootstrap_deed_span_index_from_transcript_seeds(*args, **kwargs)
