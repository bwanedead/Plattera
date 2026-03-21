"""Concrete tool dependency implementations for step-driven kernel actions."""

from __future__ import annotations

import base64
import io
import json
import os
import hashlib
import tempfile
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from config.paths import (
    agent_kernel_artifacts_root,
    dossiers_associations_root,
    dossiers_feature_graphs_artifacts_root,
)
from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView
from corpus.virtual_provider import VirtualCorpusProvider
from feature_graph.artifacts import create_compile_artifact, create_ir_artifact, create_judge_artifact
from feature_graph.bundle import bundle_feature_graph
from feature_graph.compiler import compile_graph
from feature_graph.judge import judge_graph
from feature_graph.models import FeatureGraph
from retrieval.engine.retrieval_engine import RetrievalEngine
from retrieval.filters.models import RetrievalFilters
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService
from transcript_edit.apply import (
    apply_plan_to_sections,
    materialize_canonical_input,
)
from transcript_edit.contracts import (
    Confidence,
    EditLoopStartRequestV0,
    EditPlanV0,
    LocatorAnchorsV0,
    TranscriptSpanSeedLabel,
    TranscriptSpanSeedOrigin,
    TranscriptSpanSeedV1,
    TranscriptSpanSeedsArtifactV1,
    TranscriptDocumentV0,
    transcript_text_hash,
)
from transcript_edit.persistence import TranscriptionEditPersistenceService
from transcript_edit.span_seeds import (
    build_transcript_span_seeds_artifact,
    load_transcript_text_for_seeds,
)
from transcript_edit.validators import run_validators
from services.llm.openai import OpenAIService

from .run_artifact import ArtifactRef, ValidationInline

logger = logging.getLogger(__name__)

from agents.common.identity_composer import (
    Domain,
    InheritanceMode,
    Surface,
    compose_identity_header,
)

from .tooling_artifacts import _coerce_artifact_ref, _read_json_dict, _read_str, _tool_refusal_result
from .tooling_text_spans import _bounded_int

@dataclass
class TranscriptOrientBaselineTool:
    """Run startup semantic orientation and emit a deterministic baseline payload."""

    persistence: TranscriptionEditPersistenceService = field(default_factory=TranscriptionEditPersistenceService)
    service: OpenAIService = field(default_factory=OpenAIService)

    def orient_and_baseline(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        dossier_id = _read_str(inputs.get("dossier_id")) or "adhoc"
        canonical_ref = _read_str(inputs.get("canonical_ref"))
        source_ref = _read_str(
            canonical_ref
            or inputs.get("source_transcript_ref")
            or inputs.get("transcript_ref")
            or inputs.get("tx_source_transcript_ref")
        )
        source_text = _read_str(inputs.get("source_text"))
        if source_ref is None and source_text is None:
            return _tool_refusal_result("tx_orient_baseline_missing_source_transcript")
        if not self.service.is_available() or getattr(self.service, "client", None) is None:
            return _tool_refusal_result("tx_orient_baseline_service_unavailable")
        try:
            canonical = materialize_canonical_input(
                EditLoopStartRequestV0(
                    dossier_id=dossier_id,
                    source_transcript_ref=source_ref,
                    source_text=source_text,
                    mode="audit_only",
                )
            )
        except Exception:
            return _tool_refusal_result("tx_orient_baseline_invalid_source_transcript")

        model = _read_str(inputs.get("model")) or "gpt-5.2"
        api_model = self.service.models.get(model, {}).get("api_model_name", model)
        max_attempts = _bounded_int(inputs.get("max_attempts"), default=2, minimum=1, maximum=3)

        raw_candidate_refs = _coerce_str_list(inputs.get("candidate_refs"), limit=10)
        raw_candidates = inputs.get("candidate_texts")
        inline_candidate_texts = [str(item) for item in raw_candidates[:10] if isinstance(item, str)] if isinstance(raw_candidates, list) else []
        payload_mode = "refs" if raw_candidate_refs else "inline_texts"
        inline_fallback_used = not raw_candidate_refs and bool(inline_candidate_texts)
        selection_strategy = _read_str(inputs.get("selection_strategy")) or "first_middle_last"
        max_candidates_for_orient = _bounded_int(
            inputs.get("max_candidates_for_orient"),
            default=3,
            minimum=1,
            maximum=10,
        )
        max_total_hydrated_bytes = _bounded_int(
            inputs.get("max_total_hydrated_bytes"),
            default=120000,
            minimum=2000,
            maximum=2000000,
        )
        max_bytes_per_candidate = _bounded_int(
            inputs.get("max_bytes_per_candidate"),
            default=40000,
            minimum=500,
            maximum=500000,
        )

        candidate_refs_hydrated = 0
        candidate_refs_skipped = 0
        hydrated_total_bytes = 0
        hydration_budget_applied = False
        selected_candidate_refs: list[str] = []
        candidate_texts: list[str] = []
        if raw_candidate_refs:
            selected_candidate_refs = _select_candidate_refs_for_orient(
                refs=raw_candidate_refs,
                max_candidates=max_candidates_for_orient,
                strategy=selection_strategy,
            )
            candidate_refs_skipped += max(0, len(raw_candidate_refs) - len(selected_candidate_refs))
            for ref in selected_candidate_refs:
                hydrated_text = _hydrate_candidate_text_for_orient(ref)
                if hydrated_text is None:
                    hydration_budget_applied = True
                    candidate_refs_skipped += 1
                    continue
                bounded_text = _truncate_utf8_bytes(hydrated_text, max_bytes_per_candidate)
                text_bytes = len(bounded_text.encode("utf-8"))
                if hydrated_total_bytes + text_bytes > max_total_hydrated_bytes:
                    hydration_budget_applied = True
                    candidate_refs_skipped += 1
                    continue
                hydrated_total_bytes += text_bytes
                candidate_refs_hydrated += 1
                candidate_texts.append(bounded_text)
            hydration_budget_applied = hydration_budget_applied or candidate_refs_hydrated < len(raw_candidate_refs)
            if candidate_refs_hydrated <= 0:
                return {
                    "artifact_ref": None,
                    "reason_codes": ["orient_hydration_budget_exhausted"],
                    "kernel_refusal": {
                        "reason_code": "orient_hydration_budget_exhausted",
                        "missing_inputs": [],
                        "retryable": False,
                        "blocked_by_budget": True,
                        "blocked_by_invariant": False,
                    },
                    "tx_source_transcript_ref": canonical.source_transcript_ref,
                    "tx_source_transcript_hash": canonical.source_transcript_hash,
                    "tx_orient_hydration": {
                        "payload_mode": payload_mode,
                        "inline_fallback_used": inline_fallback_used,
                        "candidate_refs_total": len(raw_candidate_refs),
                        "candidate_refs_hydrated": candidate_refs_hydrated,
                        "candidate_refs_skipped": candidate_refs_skipped,
                        "hydration_budget_applied": True,
                        "hydration_selection_strategy": selection_strategy,
                        "max_candidates_for_orient": max_candidates_for_orient,
                        "max_total_hydrated_bytes": max_total_hydrated_bytes,
                        "hydrated_total_bytes": hydrated_total_bytes,
                    },
                }
        else:
            candidate_texts = [text for text in inline_candidate_texts if text.strip()]

        hydration_summary = {
            "payload_mode": payload_mode,
            "inline_fallback_used": inline_fallback_used,
            "candidate_refs_total": len(raw_candidate_refs),
            "candidate_refs_hydrated": candidate_refs_hydrated,
            "candidate_refs_skipped": candidate_refs_skipped,
            "hydration_budget_applied": hydration_budget_applied,
            "hydration_selection_strategy": selection_strategy,
            "max_candidates_for_orient": max_candidates_for_orient,
            "max_total_hydrated_bytes": max_total_hydrated_bytes,
            "hydrated_total_bytes": hydrated_total_bytes,
            "selected_candidate_refs": selected_candidate_refs,
        }
        logger.info(
            "TX_ORIENT_HYDRATION ► payload_mode=%s refs_total=%s refs_hydrated=%s refs_skipped=%s strategy=%s budget_applied=%s hydrated_total_bytes=%s",
            payload_mode,
            len(raw_candidate_refs),
            candidate_refs_hydrated,
            candidate_refs_skipped,
            selection_strategy,
            hydration_budget_applied,
            hydrated_total_bytes,
        )
        run_link_id = _read_str(inputs.get("run_link_id")) or ""
        mission_objective = _read_str(inputs.get("mission_objective")) or ""
        system_msg = _build_tx_orient_system_message(
            run_link_id=run_link_id,
            mission_objective=mission_objective,
            model=model,
        )
        user_msg = _build_tx_orient_user_message(
            transcript_text=canonical.transcript_text,
            candidate_texts=candidate_texts,
        )
        raw_content = ""
        orient_payload: dict[str, Any] | None = None
        last_error = "tx_orient_baseline_invalid_response"
        attempts_made = 0
        for _ in range(max_attempts):
            attempts_made += 1
            try:
                params: dict[str, Any] = {
                    "model": api_model,
                    "messages": [
                        {"role": "developer", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    "response_format": {"type": "json_object"},
                }
                if "gpt-5" in str(api_model):
                    params["max_completion_tokens"] = 8000
                    params["reasoning_effort"] = "medium"
                else:
                    params["max_tokens"] = 4000
                    params["temperature"] = 0
                completion = self.service.client.chat.completions.create(**params)
            except Exception as exc:
                last_error = f"tx_orient_baseline_api_error:{type(exc).__name__}"
                user_msg = _build_tx_orient_repair_message(error_reason=last_error, raw_content="")
                continue
            message = completion.choices[0].message if completion.choices else None
            raw_content = message.content if message is not None and isinstance(message.content, str) else ""
            try:
                parsed = json.loads(raw_content)
                if not isinstance(parsed, dict):
                    raise ValueError("tx_orient_baseline_non_object_json")
                orient_payload = _coerce_tx_orient_payload(parsed)
                break
            except Exception as exc:
                last_error = f"tx_orient_baseline_parse_error:{type(exc).__name__}"
                user_msg = _build_tx_orient_repair_message(error_reason=last_error, raw_content=raw_content)
                continue

        raw_output_ref = self.persistence.save_raw_model_output(
            dossier_id=dossier_id,
            payload={
                "artifact_type": "tx_orient_raw_output",
                "model": model,
                "api_model": api_model,
                "source_transcript_ref": canonical.source_transcript_ref,
                "source_transcript_hash": canonical.source_transcript_hash,
                "hydration_summary": hydration_summary,
                "raw_content": raw_content,
                "error": None if orient_payload is not None else last_error,
            },
        )
        if orient_payload is None:
            return {
                "artifact_ref": None,
                "reason_codes": ["tx_orient_baseline_invalid_output"],
                "kernel_refusal": {
                    "reason_code": "tx_orient_baseline_invalid_output",
                    "missing_inputs": [],
                    # Parse/empty-items failures are recoverable (repair prompt, model swap, HITL).
                    "retryable": True,
                    "blocked_by_budget": False,
                    "blocked_by_invariant": False,
                },
                "tx_orient_raw_output_ref": raw_output_ref,
                "tx_source_transcript_ref": canonical.source_transcript_ref,
                "tx_source_transcript_hash": canonical.source_transcript_hash,
                "tx_orient_hydration": hydration_summary,
                "tx_orient_llm_contacts": attempts_made,
            }

        seeds = _coerce_orient_span_seeds(orient_payload)
        span_seeds_ref = self.persistence.save_transcript_span_seeds(
            dossier_id=dossier_id,
            artifact=TranscriptSpanSeedsArtifactV1(
                created_at=datetime.now(timezone.utc).isoformat(),
                dossier_id=dossier_id,
                source_transcript_ref=canonical.source_transcript_ref,
                source_transcript_hash=canonical.source_transcript_hash,
                seeds=seeds,
            ),
        )
        baseline_ref = self.persistence.save_raw_model_output(
            dossier_id=dossier_id,
            payload={
                "artifact_type": "tx_orient_baseline_v1",
                "model": model,
                "source_transcript_ref": canonical.source_transcript_ref,
                "source_transcript_hash": canonical.source_transcript_hash,
                "orient_payload": orient_payload,
                "tx_span_seeds_ref": span_seeds_ref,
                "tx_orient_raw_output_ref": raw_output_ref,
                "hydration_summary": hydration_summary,
            },
        )
        items = orient_payload.get("items") if isinstance(orient_payload.get("items"), list) else []
        mapping_blocking_count = sum(
            1
            for item in items
            if isinstance(item, dict)
            and str(item.get("operational_impact") or "").strip().lower() == "mapping_blocking"
            and str(item.get("state") or "unknown") in {"unknown", "candidate_found", "disputed", "accepted_with_risk"}
        )
        optional_count = max(0, len(items) - mapping_blocking_count)
        return {
            "artifact_ref": ArtifactRef(artifact_path=baseline_ref),
            "reason_codes": ["tx_orient_baseline_completed"],
            "tx_source_transcript_ref": canonical.source_transcript_ref,
            "tx_source_transcript_hash": canonical.source_transcript_hash,
            "tx_orient_items": items,
            "tx_orient_summary": {
                "item_count": len(items),
                "mapping_blocking_count": mapping_blocking_count,
                "optional_count": optional_count,
            },
            "tx_orient_hydration": hydration_summary,
            "tx_span_seeds_ref": span_seeds_ref,
            "tx_orient_raw_output_ref": raw_output_ref,
            "tx_orient_llm_contacts": attempts_made,
        }


def _build_tx_orient_system_message(
    *,
    run_link_id: str = "",
    mission_objective: str = "",
    model: str = "",
) -> str:
    identity = compose_identity_header(
        run_link_id=run_link_id,
        mission_objective=mission_objective,
        domain=Domain.TRANSCRIPT_EDIT,
        surface=Surface.TX_ORIENT_BASELINE,
        inheritance_mode=InheritanceMode.LIGHT,
        model=model,
    )
    leaf = (
        "You are a transcript orientation engine for legal deed text. "
        "Do not propose edits or plans. "
        "Classify each mapping decision with explicit layer and operational impact. "
        "Layer values: layer1_canonical_recovery, layer2_canonical_sanity, "
        "layer3_dependency, layer4_transcript_quality_optional. "
        "Operational impact values: mapping_blocking or transcript_quality_only. "
        "State values: unknown, candidate_found, verified, disputed, accepted_with_risk."
    )
    return identity.header_text + leaf


def _build_tx_orient_user_message(*, transcript_text: str, candidate_texts: list[str]) -> str:
    payload = {
        "task": "orient_and_baseline",
        "decision_keys": [
            "township",
            "range",
            "section",
            "tie_distance",
            "tie_bearing",
            "acreage",
            "closure_or_pob",
        ],
        "output_schema": {
            "items": [
                {
                    "key": "decision key",
                    "state": "unknown|candidate_found|verified|disputed|accepted_with_risk",
                    "selected_value": "string|null",
                    "alternatives": ["string"],
                    "confidence": "low|medium|high",
                    "layer_tag": "layer1_canonical_recovery|layer2_canonical_sanity|layer3_dependency|layer4_transcript_quality_optional",
                    "operational_impact": "mapping_blocking|transcript_quality_only",
                    "block_reason": "ambiguity|contradiction|dependency",
                    "required_information": "string",
                    "minimal_user_action": "string",
                    "resolution_options": ["string"],
                    "self_retrievable": "yes|conditional",
                    "retrieval_attempted": "boolean",
                    "retrieval_blocker": "string|null",
                    "verification_required": "boolean",
                    "attempt_summary": "string",
                    "evidence_refs": ["string"],
                    "span_seed": {
                        "label": "pob|call_chain|plss|tie_to_corner|closure|exception|acreage|misc",
                        "confidence": "low|medium|high",
                        "notes": "string",
                        "start_anchor": "string",
                        "end_anchor": "string",
                        "occurrence": 1,
                    },
                }
            ]
        },
        "candidate_texts": candidate_texts,
        "transcript_text": transcript_text,
    }
    return json.dumps(payload, ensure_ascii=False)


def _build_tx_orient_repair_message(*, error_reason: str, raw_content: str) -> str:
    payload = {
        "task": "repair_invalid_orient_response",
        "error_reason": error_reason,
        "previous_output_excerpt": raw_content[:1000],
        "instruction": "Return valid JSON object with top-level 'items' array only.",
    }
    return json.dumps(payload, ensure_ascii=False)


def _coerce_tx_orient_payload(raw: dict[str, Any]) -> dict[str, Any]:
    raw_items = raw.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("tx_orient_baseline_items_missing")
    allowed_keys = {
        "township",
        "range",
        "section",
        "tie_distance",
        "tie_bearing",
        "acreage",
        "closure_or_pob",
    }
    state_values = {"unknown", "candidate_found", "verified", "disputed", "accepted_with_risk"}
    confidence_values = {"low", "medium", "high"}
    layer_values = {
        "layer1_canonical_recovery",
        "layer2_canonical_sanity",
        "layer3_dependency",
        "layer4_transcript_quality_optional",
    }
    impact_values = {"mapping_blocking", "transcript_quality_only"}
    block_reason_values = {"ambiguity", "contradiction", "dependency"}
    self_retrievable_values = {"yes", "conditional"}
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip().lower()
        if key not in allowed_keys or key in seen:
            continue
        seen.add(key)
        state = str(entry.get("state") or "unknown").strip().lower()
        if state not in state_values:
            state = "unknown"
        confidence = str(entry.get("confidence") or "medium").strip().lower()
        if confidence not in confidence_values:
            confidence = "medium"
        layer_tag = str(entry.get("layer_tag") or "layer1_canonical_recovery").strip().lower()
        if layer_tag not in layer_values:
            layer_tag = "layer1_canonical_recovery"
        operational_impact = str(entry.get("operational_impact") or "mapping_blocking").strip().lower()
        if operational_impact not in impact_values:
            operational_impact = "mapping_blocking"
        block_reason = str(entry.get("block_reason") or "ambiguity").strip().lower()
        if block_reason not in block_reason_values:
            block_reason = "ambiguity"
        self_retrievable = str(entry.get("self_retrievable") or "conditional").strip().lower()
        if self_retrievable not in self_retrievable_values:
            self_retrievable = "conditional"
        alternatives = _coerce_string_list(entry.get("alternatives"), limit=8)
        resolution_options = _coerce_string_list(entry.get("resolution_options"), limit=8)
        evidence_refs = _coerce_string_list(entry.get("evidence_refs"), limit=12)
        selected_value = _read_str(entry.get("selected_value"))
        retrieval_blocker = _read_str(entry.get("retrieval_blocker"))
        span_seed = entry.get("span_seed") if isinstance(entry.get("span_seed"), dict) else None
        items.append(
            {
                "key": key,
                "state": state,
                "selected_value": selected_value,
                "alternatives": alternatives,
                "confidence": confidence,
                "layer_tag": layer_tag,
                "operational_impact": operational_impact,
                "block_reason": block_reason,
                "required_information": str(entry.get("required_information") or "").strip(),
                "minimal_user_action": str(entry.get("minimal_user_action") or "").strip(),
                "resolution_options": resolution_options,
                "self_retrievable": self_retrievable,
                "retrieval_attempted": bool(entry.get("retrieval_attempted")),
                "retrieval_blocker": retrieval_blocker,
                "verification_required": bool(entry.get("verification_required")),
                "attempt_summary": str(entry.get("attempt_summary") or "").strip(),
                "evidence_refs": evidence_refs,
                "provenance": str(entry.get("provenance") or "orient_llm").strip() or "orient_llm",
                "span_seed": _coerce_orient_span_seed_dict(span_seed) if span_seed else None,
            }
        )
    if not items:
        raise ValueError("tx_orient_baseline_items_empty")
    return {"items": items}


def _coerce_orient_span_seed_dict(raw: dict[str, Any]) -> dict[str, Any] | None:
    label_raw = str(raw.get("label") or "misc").strip().lower()
    allowed_labels = {
        "pob",
        "call_chain",
        "plss",
        "tie_to_corner",
        "closure",
        "exception",
        "acreage",
        "misc",
    }
    label = label_raw if label_raw in allowed_labels else "misc"
    start_anchor = str(raw.get("start_anchor") or "").strip()
    end_anchor = str(raw.get("end_anchor") or "").strip()
    if len(start_anchor) < 8 or len(end_anchor) < 8:
        return None
    occurrence = _bounded_int(raw.get("occurrence"), default=1, minimum=1, maximum=200)
    confidence = str(raw.get("confidence") or "medium").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"
    return {
        "label": label,
        "confidence": confidence,
        "notes": str(raw.get("notes") or "").strip()[:500] or None,
        "start_anchor": start_anchor[:500],
        "end_anchor": end_anchor[:500],
        "occurrence": occurrence,
    }


def _coerce_orient_span_seeds(orient_payload: dict[str, Any]) -> list[TranscriptSpanSeedV1]:
    seeds: list[TranscriptSpanSeedV1] = []
    items = orient_payload.get("items") if isinstance(orient_payload.get("items"), list) else []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        raw_seed = item.get("span_seed")
        if not isinstance(raw_seed, dict):
            continue
        label_value = str(raw_seed.get("label") or "misc")
        try:
            label = TranscriptSpanSeedLabel(label_value)
        except Exception:
            label = TranscriptSpanSeedLabel.MISC
        confidence_value = str(raw_seed.get("confidence") or "medium")
        try:
            confidence = Confidence(confidence_value)
        except Exception:
            confidence = Confidence.MEDIUM
        try:
            seed = TranscriptSpanSeedV1(
                seed_id=f"seed_orient_{index:02d}",
                label=label,
                seed_origin=TranscriptSpanSeedOrigin.AGENT,
                seed_confidence=confidence,
                notes=_read_str(raw_seed.get("notes")),
                locator=LocatorAnchorsV0(
                    start_anchor=str(raw_seed.get("start_anchor")),
                    end_anchor=str(raw_seed.get("end_anchor")),
                    occurrence=_bounded_int(raw_seed.get("occurrence"), default=1, minimum=1, maximum=200),
                ),
            )
        except Exception:
            continue
        seeds.append(seed)
        if len(seeds) >= 24:
            break
    return seeds


def _hydrate_candidate_text_for_orient(source_ref: str) -> str | None:
    try:
        canonical = materialize_canonical_input(
            EditLoopStartRequestV0(
                source_transcript_ref=source_ref,
                mode="audit_only",
            )
        )
    except Exception:
        return None
    text = str(canonical.transcript_text or "").strip()
    return text or None


def _select_candidate_refs_for_orient(
    *,
    refs: list[str],
    max_candidates: int,
    strategy: str,
) -> list[str]:
    unique_refs: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        value = str(ref or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        unique_refs.append(value)
    if len(unique_refs) <= max_candidates:
        return unique_refs
    normalized_strategy = str(strategy or "").strip().lower()
    if normalized_strategy != "first_middle_last":
        normalized_strategy = "first_middle_last"
    del normalized_strategy
    indices = _even_sample_indices(total=len(unique_refs), count=max_candidates)
    return [unique_refs[idx] for idx in indices]


def _even_sample_indices(*, total: int, count: int) -> list[int]:
    if total <= 0 or count <= 0:
        return []
    if count >= total:
        return list(range(total))
    if count == 1:
        return [0]
    out: list[int] = []
    for pos in range(count):
        idx = int(round(pos * (total - 1) / (count - 1)))
        if idx not in out:
            out.append(idx)
    candidate = 0
    while len(out) < count and candidate < total:
        if candidate not in out:
            out.append(candidate)
        candidate += 1
    out.sort()
    return out


def _truncate_utf8_bytes(text: str, max_bytes: int) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    clipped = raw[:max_bytes]
    return clipped.decode("utf-8", errors="ignore")


def _coerce_str_list(raw: Any, *, limit: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = _read_str(item)
        if value is None or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def _coerce_string_list(raw: Any, *, limit: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text or text in values:
            continue
        values.append(text[:200])
        if len(values) >= limit:
            break
    return values
