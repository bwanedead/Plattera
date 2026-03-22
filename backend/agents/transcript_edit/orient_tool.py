"""Transcript-edit orientation step: domain-owned adapter over generic orientation containers.

Generic JSON validation lives in ``agent_kernel.orientation``; checklist seeds and deed hints are domain-only.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from .startup_posture import transcript_mapping_blocking_from_startup_item
from agent_kernel.run_artifact import ArtifactRef
from agent_kernel.tooling_artifacts import _read_str, _tool_refusal_result
from agent_kernel.tooling_text_spans import _bounded_int

from .orient_checklist_adapter import coerce_transcript_edit_orient_payload
from .orient_prompts import (
    build_transcript_edit_orient_repair_message,
    build_transcript_edit_orient_system_message,
    build_transcript_edit_orient_user_message,
)
from .orient_span_seeds import build_transcript_orient_span_seeds, coerce_orient_span_seed_dict

from services.llm.openai import OpenAIService
from transcript_edit.apply import materialize_canonical_input
from transcript_edit.contracts import EditLoopStartRequestV0, TranscriptSpanSeedsArtifactV1
from transcript_edit.persistence import TranscriptionEditPersistenceService

logger = logging.getLogger(__name__)


@dataclass
class TranscriptOrientBaselineTool:
    """Run LLM orientation for transcript-edit; emits checklist seeds + startup understanding."""

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
        system_msg = build_transcript_edit_orient_system_message(
            run_link_id=run_link_id,
            mission_objective=mission_objective,
            model=model,
        )
        user_msg = build_transcript_edit_orient_user_message(
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
                user_msg = build_transcript_edit_orient_repair_message(error_reason=last_error, raw_content="")
                continue
            message = completion.choices[0].message if completion.choices else None
            raw_content = message.content if message is not None and isinstance(message.content, str) else ""
            try:
                parsed = json.loads(raw_content)
                if not isinstance(parsed, dict):
                    raise ValueError("tx_orient_baseline_non_object_json")
                orient_payload = coerce_transcript_edit_orient_payload(parsed)
                break
            except Exception as exc:
                last_error = f"tx_orient_baseline_parse_error:{type(exc).__name__}"
                user_msg = build_transcript_edit_orient_repair_message(error_reason=last_error, raw_content=raw_content)
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

        checklist_items = list(orient_payload.get("checklist_seed_items") or [])
        for row in checklist_items:
            if not isinstance(row, dict):
                continue
            ss = row.get("span_seed")
            if isinstance(ss, dict):
                coerced_ss = coerce_orient_span_seed_dict(ss)
                row["span_seed"] = coerced_ss if coerced_ss is not None else ss

        startup_understanding = (
            orient_payload.get("startup_understanding")
            if isinstance(orient_payload.get("startup_understanding"), dict)
            else {}
        )
        seeds = build_transcript_orient_span_seeds(
            startup_understanding=startup_understanding,
            checklist_seed_items=checklist_items,
        )
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
        persist_payload = {
            "startup_understanding": startup_understanding,
            "checklist_seed_items": checklist_items,
        }
        baseline_ref = self.persistence.save_raw_model_output(
            dossier_id=dossier_id,
            payload={
                "artifact_type": "tx_orient_baseline_v1",
                "model": model,
                "source_transcript_ref": canonical.source_transcript_ref,
                "source_transcript_hash": canonical.source_transcript_hash,
                "orient_payload": persist_payload,
                "tx_span_seeds_ref": span_seeds_ref,
                "tx_orient_raw_output_ref": raw_output_ref,
                "hydration_summary": hydration_summary,
            },
        )
        items = checklist_items
        su = startup_understanding
        ledger_rows = [r for r in (su.get("initial_ledger_items") or []) if isinstance(r, dict)]
        checklist_mb = sum(
            1
            for item in items
            if isinstance(item, dict)
            and str(item.get("operational_impact") or "").strip().lower() == "mapping_blocking"
            and str(item.get("state") or "unknown") in {"unknown", "candidate_found", "disputed", "accepted_with_risk"}
        )
        ledger_mb = sum(
            1
            for row in ledger_rows
            if transcript_mapping_blocking_from_startup_item(row)
            and str(row.get("state") or "unknown").strip().lower()
            in {"unknown", "candidate_found", "disputed", "accepted_with_risk"}
        )
        mapping_blocking_count = checklist_mb + ledger_mb
        optional_count = max(0, len(items) - checklist_mb) + max(0, len(ledger_rows) - ledger_mb)
        return {
            "artifact_ref": ArtifactRef(artifact_path=baseline_ref),
            "reason_codes": ["tx_orient_baseline_completed"],
            "tx_source_transcript_ref": canonical.source_transcript_ref,
            "tx_source_transcript_hash": canonical.source_transcript_hash,
            "tx_orient_items": items,
            "tx_orient_summary": {
                "item_count": len(items),
                "candidate_work_item_count": len(ledger_rows),
                "mapping_blocking_count": mapping_blocking_count,
                "optional_count": optional_count,
            },
            "tx_orient_hydration": hydration_summary,
            "tx_span_seeds_ref": span_seeds_ref,
            "tx_orient_raw_output_ref": raw_output_ref,
            "tx_orient_llm_contacts": attempts_made,
            "tx_startup_understanding": startup_understanding,
        }


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
