"""Controller loop split module (Pass 6)."""

from __future__ import annotations

import json
import hashlib
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root, dossiers_feature_graphs_artifacts_root
from feature_graph.operations import get_supported_operations, get_unsupported_operations

from agent_kernel.models import (
    ActionType,
    KernelRefusal,
    KernelSessionStartRequest,
    KernelSessionStartResult,
    KernelStepRequest,
    KernelStepResult,
    StepExecutionState,
    StopReason,
    TerminalOutcome,
    TerminalOutcomeKind,
)
from agent_kernel.session import KernelSessionManager

from .contracts import (
    DeclareDoneJustification,
    KernelStepProposal,
    action_tool_specs_for_menu,
    action_how_to_guide,
    coerce_action_type,
    tool_cheatsheet_entries,
    validate_action_args,
)
from .prompting import (
    build_developer_message,
    build_refusal_repair_user_message,
    build_repair_user_message,
    build_user_message,
)
from .retrieval_intents import classify_retrieval_degradation, map_retrieval_intent_to_inputs
from .tool_specs import ToolSpec
from .bootstrap import load_transcript_span_seeds_for_mapping, materialize_seed_spans_from_text

_MAX_CONTROLLER_INPUT_BYTES = 4096
_MAX_EVENTS = 200
_MAX_EVENT_CHARS = 2000
_MAX_TOTAL_BYTES = 262144
_MAX_ERROR_CHARS = 1000
_MAX_TRACE_ITEMS = 8
_MAX_PLAN_BULLETS = 8
_MAX_GAP_KINDS = 8
_MAX_REASON_CODES = 8
_MAX_REFUSAL_STREAK = 3
_RUN_SUMMARY_EVERY_EXECUTED_STEPS = 5
_MAX_HINT_FILE_BYTES = 65536
_MAX_HINT_READ_BYTES = 32768
_RUN_SUMMARY_LOG_MAX_BYTES = 24576
_RUN_SUMMARY_LOG_MAX_ENTRIES = 40
_MAX_DISPLAY_DELTA_CHARS = 220

logger = logging.getLogger(__name__)

from .controller_guardrails import _read_str

def _bootstrap_deed_span_index_from_transcript_seeds(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    request_id: str,
    bootstrap_context: dict[str, object],
) -> KernelStepResult | None:
    dossier_id = _read_str(bootstrap_context.get("dossier_id"))
    if dossier_id is None:
        return None
    deed_text = bootstrap_context.get("deed_text_full")
    deed_ref = _read_str(bootstrap_context.get("deed_text_artifact_ref"))
    deed_fingerprint = bootstrap_context.get("deed_fingerprint")
    if not isinstance(deed_text, str) or not deed_text:
        return None
    if deed_ref is None or not isinstance(deed_fingerprint, dict):
        return None
    seed_bundle = load_transcript_span_seeds_for_mapping(dossier_id=dossier_id)
    if seed_bundle is None:
        return None
    spans = materialize_seed_spans_from_text(deed_text=deed_text, seed_bundle=seed_bundle, max_spans=24)
    if not spans:
        return None
    upserts: list[dict[str, object]] = []
    for span in spans:
        start_char = int(span["start_char"])
        end_char = int(span["end_char"])
        label = str(span.get("label") or "misc")
        seed_id = str(span.get("seed_id") or f"seed_{len(upserts)+1:02d}")
        intended = deed_text[start_char:end_char]
        upserts.append(
            {
                "span_id": seed_id,
                "kind": "transcript_seed",
                "labels": [label],
                "status": "proposed",
                "start_char": start_char,
                "end_char": end_char,
                "anchor": {
                    "start_snippet": str(span.get("start_anchor") or "")[:200],
                    "end_snippet": str(span.get("end_anchor") or "")[:200],
                },
                "agent_intent": {"intended_verbatim_text": intended[:2000]},
            }
        )
    if not upserts:
        return None
    payload = {
        "dossier_id": dossier_id,
        "deed_text_artifact_ref": deed_ref,
        "deed_fingerprint": deed_fingerprint,
        "upserts": upserts,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:12]
    return session_manager.step(
        KernelStepRequest(
            session_id=session_id,
            idempotency_key=f"bootstrap-seed-upsert-{digest}",
            action_type=ActionType.UPSERT_DEED_SPAN_INDEX,
            inputs=payload,
            notes=f"request_id={request_id}",
        )
    )


def _build_bootstrap_context(start_request: KernelSessionStartRequest) -> dict[str, object]:
    context: dict[str, object] = {
        "dossier_id": start_request.dossier_id,
        "source_entry_ref": start_request.source_entry_ref,
        "initial_ir_ref": start_request.initial_ir_ref,
    }
    graph = start_request.initial_graph_json if isinstance(start_request.initial_graph_json, dict) else None
    if graph is not None:
        metadata = graph.get("metadata")
        if isinstance(metadata, dict):
            deed_ref = metadata.get("deed_text_artifact_ref")
            excerpt = metadata.get("deed_text_excerpt")
            if isinstance(deed_ref, str) and deed_ref:
                context["deed_text_artifact_ref"] = deed_ref
            if isinstance(excerpt, str) and excerpt:
                context["deed_text_excerpt"] = excerpt[:512]
    deed_text_full = _read_deed_text_from_artifact_ref(context.get("deed_text_artifact_ref"))
    if deed_text_full is not None:
        context["deed_text_full"] = deed_text_full
        context["deed_fingerprint"] = _controller_deed_fingerprint(deed_text_full)
    return context


def _read_deed_text_from_artifact_ref(raw_ref: object) -> str | None:
    if not isinstance(raw_ref, str) or not raw_ref.strip():
        return None
    try:
        path = Path(raw_ref).resolve()
        root = agent_kernel_artifacts_root().resolve()
        if path != root and root not in path.parents:
            return None
        if not path.exists() or not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        text = payload.get("text")
        if isinstance(text, str) and text:
            return text
    except Exception:
        return None
    return None


def _controller_deed_fingerprint(text: str) -> dict[str, object]:
    return {
        "sha256_12": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
        "length_chars": len(text),
    }
