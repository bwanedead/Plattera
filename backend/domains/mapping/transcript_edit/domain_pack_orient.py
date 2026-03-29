from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from agent_kernel.models import KernelStepRequest, StepExecutionState

from config.paths import agent_kernel_artifacts_root
from harness.orchestration_kernel.contracts import OrchestratorContext

from .blocker_registry import (
    initialize_blocker_registry,
    set_convention_context,
    sync_registry_from_ledger,
)
from .convention_situating import situate_document_convention
from .decision_ledger import initialize_decision_ledger, update_ledger_from_orient_baseline
from .decision_ledger_adapter import transcript_edit_unified_and_closure_read_from_loop_state
from .execution_action_ids import TX_ORIENT_AND_BASELINE
from .llm_startup_understanding import (
    apply_llm_startup_to_ledger_and_registry,
    fallback_decision_key_for_startup_merge,
)
from .loop_runtime import (
    idempotency_key as _make_idempotency_key,
    read_step_outputs_inline,
    read_str,
)
from .state_projection import sync_pending_feedback_cache_from_registry

if TYPE_CHECKING:
    from .domain_pack import TranscriptEditDomainPack


_LOG = logging.getLogger(__name__)


def orient_domain_pack(pack: "TranscriptEditDomainPack", context: OrchestratorContext) -> None:
    """Initialize transcript-edit domain state from the orient baseline step."""

    request = pack._request
    session_manager = context.session_manager
    session_id = context.session_id
    request_id_prefix = context.request_id_prefix

    _rw = str(getattr(request, "resume_working_transcript_ref", None) or "").strip()
    _src = str(request.source_transcript_ref or "").strip()
    _oseed = str(getattr(request, "original_seed_transcript_ref", None) or "").strip()
    if _rw:
        pack._state.current_transcript_ref = _rw
        _LOG.info(
            "TX_DOMAIN_PACK working_transcript ► request_id=%s ref=resume_working path=%s",
            request_id_prefix,
            _rw[:120],
        )
    elif _src:
        pack._state.current_transcript_ref = _src
    elif not pack._state.current_transcript_ref and request.source_text:
        pass

    pack._working_transcript_override = _rw or None

    if not pack._state.decision_ledger:
        pack._state.decision_ledger = initialize_decision_ledger()
    if not pack._state.blocker_registry:
        if isinstance(request.resume_blocker_registry, dict) and request.resume_blocker_registry:
            pack._state.blocker_registry = dict(request.resume_blocker_registry)
            _LOG.info(
                "TX_DOMAIN_PACK orient_resume_blocker_registry ► request_id=%s",
                request_id_prefix,
            )
        else:
            _reg_src = _oseed or _src or str(pack._state.current_transcript_ref or "").strip()
            pack._state.blocker_registry = initialize_blocker_registry(
                run_id=request_id_prefix,
                session_id=session_id,
                source_transcript_ref=_reg_src or request.source_transcript_ref,
            )

    resume_prompt_id = str(request.resume_pending_feedback_prompt_id or "").strip() or None
    resume_decision_key = str(request.resume_pending_feedback_decision_key or "").strip().lower() or None
    if resume_prompt_id and not pack._state.pending_feedback_prompt_id:
        pack._state.pending_feedback_prompt_id = resume_prompt_id
        pack._state.pending_feedback_decision_key = resume_decision_key
        _LOG.info(
            "TX_DOMAIN_PACK orient_resume_feedback_identity ► request_id=%s prompt_id=%s",
            request_id_prefix,
            resume_prompt_id,
        )

    pack._pre_source_hash = ""

    if not pack._state.seed_transcript_ref:
        if _oseed:
            pack._state.seed_transcript_ref = _oseed
        elif _rw and _src:
            pack._state.seed_transcript_ref = _src
        elif pack._state.current_transcript_ref:
            pack._state.seed_transcript_ref = pack._state.current_transcript_ref

    orient_inputs: dict[str, Any] = {
        "dossier_id": request.dossier_id,
        "model": pack._loop_model,
        "run_link_id": request_id_prefix,
        "mission_objective": pack._mission_objective,
    }
    if pack._state.current_transcript_ref:
        orient_inputs["source_transcript_ref"] = pack._state.current_transcript_ref
    elif request.source_text:
        orient_inputs["source_text"] = request.source_text
    if request.candidate_refs:
        orient_inputs["candidate_refs"] = list(request.candidate_refs[:request.max_candidates_for_orient])
    elif request.candidate_texts:
        orient_inputs["candidate_texts"] = list(request.candidate_texts[:request.max_candidates_for_orient])

    orient = session_manager.step(
        KernelStepRequest(
            session_id=session_id,
            action_type=TX_ORIENT_AND_BASELINE,
            inputs=orient_inputs,
            idempotency_key=_make_idempotency_key(
                f"{request_id_prefix}:orient", 0, orient_inputs
            ),
        )
    )
    pack._orient_baseline_failure_reason = None
    if orient.execution_state != StepExecutionState.EXECUTED:
        inline = read_step_outputs_inline(orient.step_record) if orient.step_record else {}
        kernel_refusal = inline.get("kernel_refusal") if isinstance(inline.get("kernel_refusal"), dict) else {}
        refusal_code = str(kernel_refusal.get("reason_code") or "").strip()
        if not refusal_code and orient.refusal is not None:
            refusal_code = str(orient.refusal.reason_code or "").strip()
        pack._orient_baseline_failure_reason = refusal_code or "tx_orient_baseline_step_refused"
        _LOG.warning(
            "TX_DOMAIN_PACK orient_refused ► request_id=%s reason=%s",
            request_id_prefix,
            pack._orient_baseline_failure_reason,
        )
    if orient.execution_state == StepExecutionState.EXECUTED and orient.dashboard:
        pack._state.latest_refs = orient.dashboard.latest_refs.model_dump(mode="json")
        orient_inline = read_step_outputs_inline(orient.step_record)
        orient_src_ref = read_str(orient_inline.get("tx_source_transcript_ref"))
        if pack._working_transcript_override:
            pack._state.current_transcript_ref = pack._working_transcript_override
        elif orient_src_ref:
            pack._state.current_transcript_ref = orient_src_ref
        pack._pre_source_hash = read_str(orient_inline.get("tx_source_transcript_hash")) or ""
        if read_str(orient_inline.get("tx_span_seeds_ref")):
            pack._state.span_seeds_ref = read_str(orient_inline.get("tx_span_seeds_ref"))
        orient_items = [
            item
            for item in (orient_inline.get("tx_orient_items") or [])
            if isinstance(item, dict)
        ]
        pack._state.decision_ledger = update_ledger_from_orient_baseline(
            ledger=pack._state.decision_ledger,
            orient_items=orient_items,
        )
        startup_raw = orient_inline.get("tx_startup_understanding")
        if not isinstance(startup_raw, dict):
            startup_raw = {}
        fallback_key = fallback_decision_key_for_startup_merge(
            orient_items=orient_items,
            startup=startup_raw,
        )
        merge_stats: dict[str, Any] = {}
        pack._state.decision_ledger, pack._state.blocker_registry = apply_llm_startup_to_ledger_and_registry(
            ledger=pack._state.decision_ledger,
            registry=pack._state.blocker_registry,
            startup=startup_raw,
            merge_stats=merge_stats,
            fallback_decision_key=fallback_key,
        )
        pack._state.llm_startup_understanding = (
            dict(pack._state.decision_ledger.get("llm_startup_understanding"))
            if isinstance(pack._state.decision_ledger.get("llm_startup_understanding"), dict)
            else None
        )
        pack._state.convention_context = situate_document_convention(orient_items=orient_items)
        pack._state.blocker_registry = set_convention_context(
            registry=pack._state.blocker_registry,
            convention_context=pack._state.convention_context,
        )
        orient_llm_contacts = max(1, int(orient_inline.get("tx_orient_llm_contacts") or 1))
        for _ in range(orient_llm_contacts):
            context.loop_memory.register_llm_contact()

    _, read_after_orient = transcript_edit_unified_and_closure_read_from_loop_state(pack._state)
    pack._state.blocker_registry = sync_registry_from_ledger(
        registry=pack._state.blocker_registry,
        decision_ledger=read_after_orient,
        run_id=request_id_prefix,
        session_id=session_id,
        source_transcript_ref=pack._state.current_transcript_ref,
    )
    sync_pending_feedback_cache_from_registry(state=pack._state)

    if not pack._state.t0_candidate_refs and not request.candidate_refs and not request.candidate_texts:
        source_ref = pack._state.current_transcript_ref or ""
        if source_ref:
            source_path = Path(source_ref)
            if source_path.parent.is_dir():
                stem = source_path.stem.split("_v")[0]
                siblings = sorted(source_path.parent.glob(f"{stem}_v*.json"))
                pack._state.t0_candidate_refs = [str(path) for path in siblings[:10]]
                if pack._state.t0_candidate_refs:
                    _LOG.info(
                        "TX_DOMAIN_PACK t0_candidates_discovered ► request_id=%s count=%d",
                        request_id_prefix,
                        len(pack._state.t0_candidate_refs),
                    )

    if not pack._state.investigation_summary_ref:
        pack._state.investigation_summary_ref = generate_investigation_summary(
            pack,
            request_id_prefix=request_id_prefix,
            dossier_id=request.dossier_id or "unknown",
            llm_contact_at_generation=context.loop_memory.llm_contact_count,
        )
        if pack._state.investigation_summary_ref:
            pack._state.initial_recon_complete = True
            pack._state.latest_refs["tx_investigation_summary_ref"] = {
                "path": pack._state.investigation_summary_ref
            }

    _, orient_read = transcript_edit_unified_and_closure_read_from_loop_state(pack._state)
    items = orient_read.get("items") or []
    ledger_item_count = len(items) if isinstance(items, list) else 0
    _LOG.info(
        "TX_DOMAIN_PACK orient_complete ► request_id=%s ledger_keys=%s",
        request_id_prefix,
        ledger_item_count,
    )


def generate_investigation_summary(
    pack: "TranscriptEditDomainPack",
    *,
    request_id_prefix: str,
    dossier_id: str,
    llm_contact_at_generation: int,
) -> str | None:
    """Persist a bounded orient-time summary for later focus packets."""

    try:
        state = pack._state
        _, read_ledger = transcript_edit_unified_and_closure_read_from_loop_state(state)
        items_list = read_ledger.get("items") or []
        if not isinstance(items_list, list):
            items_list = []

        top_discrepancies: list[dict[str, Any]] = []
        for item in items_list:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip().lower()
            top_discrepancies.append(
                {
                    "key": key,
                    "verdict": item.get("verdict"),
                    "mapping_blocking": item.get("mapping_blocking", False),
                    "state": item.get("state"),
                }
            )
        top_discrepancies.sort(key=lambda x: (not x.get("mapping_blocking", False), x.get("key", "")))
        top_discrepancies = top_discrepancies[:5]

        summary = {
            "artifact_kind": "tx_investigation_summary",
            "schema_version": "v1",
            "run_id": request_id_prefix,
            "generated_at_llm_contact": llm_contact_at_generation,
            "initial_recon_complete": True,
            "source_transcript_ref": state.current_transcript_ref,
            "seed_transcript_ref": state.seed_transcript_ref,
            "t0_candidate_refs": list(state.t0_candidate_refs or []),
            "t0_candidate_count": len(state.t0_candidate_refs or []),
            "working_draft_selection_basis": "heuristic_v2_seed",
            "top_discrepancies": top_discrepancies,
            "evidence_lanes_available": ["span", "image", "hitl"],
            "coverage": {
                "orient_baseline_complete": True,
                "image_evidence_attempted": False,
                "span_evidence_attempted": False,
                "hitl_received": False,
            },
        }

        root = (
            agent_kernel_artifacts_root()
            / "tool_outputs"
            / "tx_investigation_summary"
            / dossier_id
        )
        root.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        artifact_name = f"investigation_summary_{ts}_{uuid4().hex[:8]}.json"
        path = root / artifact_name

        fd, tmp_path = tempfile.mkstemp(prefix="inv_summary_", suffix=".json", dir=str(root))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file_handle:
                json.dump(summary, file_handle, ensure_ascii=False, indent=2)
                file_handle.flush()
                os.fsync(file_handle.fileno())
            try:
                os.replace(tmp_path, str(path))
            except PermissionError:
                with path.open("w", encoding="utf-8") as file_handle:
                    json.dump(summary, file_handle, ensure_ascii=False, indent=2)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

        _LOG.info(
            "TX_DOMAIN_PACK investigation_summary_persisted ► request_id=%s path=%s",
            request_id_prefix,
            path,
        )
        return str(path)
    except Exception:
        _LOG.exception(
            "TX_DOMAIN_PACK investigation_summary_failed ► request_id=%s", request_id_prefix
        )
        return None


def load_investigation_excerpt(pack: "TranscriptEditDomainPack") -> dict[str, Any] | None:
    """Return a compact persisted investigation summary excerpt for model-facing packets."""

    ref = pack._state.investigation_summary_ref
    if not ref:
        return None
    try:
        with open(ref, encoding="utf-8") as file_handle:
            data = json.load(file_handle)
        return {
            "working_draft_basis": data.get("working_draft_selection_basis"),
            "source_transcript_ref": data.get("source_transcript_ref"),
            "t0_candidate_count": data.get("t0_candidate_count", 0),
            "top_discrepancies": data.get("top_discrepancies") or [],
            "evidence_lanes_available": data.get("evidence_lanes_available") or [],
            "coverage": data.get("coverage") or {},
        }
    except Exception:
        return None
