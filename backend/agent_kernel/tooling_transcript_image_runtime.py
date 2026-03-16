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

from .tooling_artifacts import _coerce_artifact_ref, _persist_json_artifact, _read_str, _summarize_text, _tool_refusal_result
from .tooling_transcript_image_helpers import (
    _apply_region_transform,
    _bounded_float,
    _build_transcript_image_verify_prompt,
    _coerce_crop_box,
    _coerce_grid_spec,
    _coerce_requested_crop_box,
    _create_image_evidence_artifacts,
    _encode_image_for_verification,
    _load_region_lineage_for_ref,
    _persist_grid_overlay_artifact,
    _persist_region_lineage_metadata,
    _read_image_size,
    _selector_type_from_target,
    _summarize_image_verify_results,
    _coerce_image_verify_result,
)

def _execute_explicit_image_evidence_mode(
    *,
    service: OpenAIService,
    inputs: Mapping[str, Any],
    dossier_id: str,
    source_ref: str,
    image_file: Path,
    model: str,
    mode: str,
) -> Mapping[str, Any]:
    if mode == "inspection_reference":
        image_size = _read_image_size(image_file)
        if image_size is None:
            return _tool_refusal_result("tx_image_inspection_source_image_unreadable")
        grid_spec = _coerce_grid_spec(inputs.get("grid_spec"))
        grid_overlay_ref = _persist_grid_overlay_artifact(
            source_image_path=image_file,
            dossier_id=dossier_id,
            grid_spec=grid_spec,
        )
        inspection_payload = {
            "artifact_type": "transcript_image_inspection",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_image_path": str(image_file),
            "source_transcript_ref": source_ref,
            "image_width": int(image_size[0]),
            "image_height": int(image_size[1]),
            "grid_spec": grid_spec,
            "grid_overlay_ref": grid_overlay_ref.model_dump(mode="json"),
        }
        inspection_ref = _persist_json_artifact(
            category="transcript_image_inspection",
            dossier_id=dossier_id,
            payload=inspection_payload,
        )
        return {
            "artifact_ref": inspection_ref,
            "reason_codes": ["tx_image_inspection_ready"],
            "tx_source_transcript_ref": source_ref,
            "tx_image_path": str(image_file),
            "tx_image_inspection_ref": inspection_ref.model_dump(mode="json"),
            "image_width": int(image_size[0]),
            "image_height": int(image_size[1]),
            "grid_spec": grid_spec,
            "grid_overlay_ref": grid_overlay_ref.model_dump(mode="json"),
        }

    if mode == "select_region":
        image_size = _read_image_size(image_file)
        if image_size is None:
            return _tool_refusal_result("tx_image_select_region_source_image_unreadable")
        target = inputs.get("target") if isinstance(inputs.get("target"), Mapping) else {}
        selector_type = _selector_type_from_target(target)
        crop_box = _coerce_requested_crop_box(
            target=target,
            image_width=int(image_size[0]),
            image_height=int(image_size[1]),
        )
        if crop_box is None:
            return _tool_refusal_result("tx_image_select_region_invalid_crop")
        zoom_factor = _bounded_float(
            (target.get("zoom_factor") if isinstance(target, Mapping) else inputs.get("zoom_factor")),
            default=2.2,
            minimum=1.0,
            maximum=6.0,
        )
        check_id = _read_str(inputs.get("check_id") or (target.get("check_id") if isinstance(target, Mapping) else None)) or "select_region"
        decision_key = _read_str(inputs.get("decision_key") or (target.get("decision_key") if isinstance(target, Mapping) else None))
        isolate = _create_image_evidence_artifacts(
            source_image_path=image_file,
            dossier_id=dossier_id,
            check_id=check_id,
            decision_key=decision_key,
            zoom_factor=zoom_factor,
            locator_result={
                "status": "located",
                "confidence": "high",
                "reason": "Agent-selected crop.",
                "crop_box": crop_box,
                "context_crop_box": None,
            },
        )
        lineage_ref = _persist_region_lineage_metadata(
            dossier_id=dossier_id,
            region_ref=(isolate.get("tx_image_evidence_region_ref") if isinstance(isolate.get("tx_image_evidence_region_ref"), ArtifactRef) else None),
            source_image_path=image_file,
            parent_region_ref=None,
            crop_box=crop_box,
            zoom_factor=zoom_factor,
            creation_mode="select_region",
            selector_type=selector_type,
        )
        region_ref = isolate.get("tx_image_evidence_region_ref")
        return {
            "artifact_ref": lineage_ref,
            "reason_codes": ["tx_image_region_selected"],
            "tx_source_transcript_ref": source_ref,
            "tx_image_path": str(image_file),
            "tx_image_evidence_region_ref": (
                region_ref.model_dump(mode="json")
                if isinstance(region_ref, ArtifactRef)
                else None
            ),
            "tx_image_evidence_context_ref": (
                isolate.get("tx_image_evidence_context_ref").model_dump(mode="json")
                if isinstance(isolate.get("tx_image_evidence_context_ref"), ArtifactRef)
                else None
            ),
            "crop_box": crop_box,
            "zoom_factor": zoom_factor,
            "selector_type": selector_type,
            "tx_image_region_lineage_ref": lineage_ref.model_dump(mode="json"),
            "tx_image_region_lineage": {
                "creation_mode": "select_region",
                "source_image_path": str(image_file),
                "crop_box": crop_box,
                "zoom_factor": zoom_factor,
                "selector_type": selector_type,
                "parent_region_ref": None,
            },
        }

    if mode == "refine_region":
        target = inputs.get("target") if isinstance(inputs.get("target"), Mapping) else {}
        parent_region_ref = _coerce_artifact_ref(target.get("region_ref") if isinstance(target, Mapping) else None)
        if parent_region_ref is None:
            return _tool_refusal_result("tx_image_refine_region_missing_parent")
        parent_path = Path(parent_region_ref.artifact_path)
        if not parent_path.exists():
            return _tool_refusal_result("tx_image_refine_region_parent_not_found")
        parent_lineage = _load_region_lineage_for_ref(parent_region_ref)
        source_image_path = Path(
            _read_str((parent_lineage or {}).get("source_image_path"))
            or str(parent_path)
        )
        image_size = _read_image_size(source_image_path)
        if image_size is None:
            return _tool_refusal_result("tx_image_refine_region_source_unreadable")
        base_crop = _coerce_crop_box((parent_lineage or {}).get("crop_box"))
        if base_crop is None:
            base_crop = {"x": 0, "y": 0, "width": int(image_size[0]), "height": int(image_size[1])}
        parent_selector_type = _read_str((parent_lineage or {}).get("selector_type")) or "unknown"
        transform = _read_str(target.get("transform") if isinstance(target, Mapping) else None) or "expand"
        amount = _bounded_float(target.get("amount") if isinstance(target, Mapping) else None, default=0.2, minimum=0.01, maximum=3.0)
        refined_crop = _apply_region_transform(
            crop_box=base_crop,
            transform=transform,
            amount=amount,
            image_width=int(image_size[0]),
            image_height=int(image_size[1]),
        )
        if refined_crop is None:
            return _tool_refusal_result("tx_image_refine_region_invalid_transform")
        parent_zoom = _bounded_float((parent_lineage or {}).get("zoom_factor"), default=1.0, minimum=1.0, maximum=6.0)
        zoom_factor = parent_zoom
        if transform == "set_zoom":
            zoom_factor = _bounded_float(amount, default=parent_zoom, minimum=1.0, maximum=6.0)
        check_id = _read_str(target.get("check_id") if isinstance(target, Mapping) else None) or "refine_region"
        decision_key = _read_str(target.get("decision_key") if isinstance(target, Mapping) else None)
        isolate = _create_image_evidence_artifacts(
            source_image_path=source_image_path,
            dossier_id=dossier_id,
            check_id=check_id,
            decision_key=decision_key,
            zoom_factor=zoom_factor,
            locator_result={
                "status": "located",
                "confidence": "high",
                "reason": "Agent-refined crop.",
                "crop_box": refined_crop,
                "context_crop_box": None,
            },
        )
        lineage_ref = _persist_region_lineage_metadata(
            dossier_id=dossier_id,
            region_ref=(isolate.get("tx_image_evidence_region_ref") if isinstance(isolate.get("tx_image_evidence_region_ref"), ArtifactRef) else None),
            source_image_path=source_image_path,
            parent_region_ref=parent_region_ref,
            crop_box=refined_crop,
            zoom_factor=zoom_factor,
            creation_mode="refine_region",
            selector_type="refine_transform",
        )
        region_ref = isolate.get("tx_image_evidence_region_ref")
        return {
            "artifact_ref": lineage_ref,
            "reason_codes": ["tx_image_region_refined"],
            "tx_source_transcript_ref": source_ref,
            "tx_image_path": str(source_image_path),
            "tx_image_evidence_region_ref": (
                region_ref.model_dump(mode="json")
                if isinstance(region_ref, ArtifactRef)
                else None
            ),
            "tx_image_evidence_context_ref": (
                isolate.get("tx_image_evidence_context_ref").model_dump(mode="json")
                if isinstance(isolate.get("tx_image_evidence_context_ref"), ArtifactRef)
                else None
            ),
            "crop_box": refined_crop,
            "zoom_factor": zoom_factor,
            "selector_type": "refine_transform",
            "parent_region_ref": parent_region_ref.model_dump(mode="json"),
            "tx_image_region_lineage_ref": lineage_ref.model_dump(mode="json"),
            "tx_image_region_lineage": {
                "creation_mode": "refine_region",
                "source_image_path": str(source_image_path),
                "crop_box": refined_crop,
                "zoom_factor": zoom_factor,
                "selector_type": "refine_transform",
                "parent_selector_type": parent_selector_type,
                "parent_region_ref": parent_region_ref.model_dump(mode="json"),
            },
        }

    if mode == "verify_region":
        target = inputs.get("target") if isinstance(inputs.get("target"), Mapping) else {}
        region_ref = _coerce_artifact_ref(target.get("region_ref") if isinstance(target, Mapping) else None)
        if region_ref is None:
            return _tool_refusal_result("tx_image_verify_region_missing_region_ref")
        region_path = Path(region_ref.artifact_path)
        if not region_path.exists():
            return _tool_refusal_result("tx_image_verify_region_not_found")
        query = _read_str(target.get("query") if isinstance(target, Mapping) else None) or _read_str(inputs.get("query"))
        if not query:
            return _tool_refusal_result("tx_image_verify_region_missing_query")
        check_id = _read_str(target.get("check_id") if isinstance(target, Mapping) else None) or "verify_region"
        expected_text = _read_str(target.get("expected_text") if isinstance(target, Mapping) else None) or _read_str(inputs.get("expected_text"))
        region_lineage = _load_region_lineage_for_ref(region_ref) or {}
        image_b64, render_meta = _encode_image_for_verification(
            image_path=region_path,
            crop_box=None,
            zoom_factor=1.0,
        )
        prompt = _build_transcript_image_verify_prompt(
            check_id=check_id,
            query=query,
            expected_text=expected_text,
            run_link_id=_read_str(inputs.get("run_link_id")) or "",
            mission_objective=_read_str(inputs.get("mission_objective")) or "",
            model=model,
        )
        response = service.call_vision(
            prompt=prompt,
            image_data=image_b64,
            model=model,
            json_mode="relaxed",
            max_tokens=1600,
            detail="high",
        )
        result_item = _coerce_image_verify_result(
            check_id=check_id,
            query=query,
            expected_text=expected_text,
            response=response,
        )
        result_item["render_meta"] = render_meta
        result_item["locator"] = {"status": "located", "source": "agent_selected_region_ref"}
        result_item["tx_image_evidence_region_ref"] = region_ref.model_dump(mode="json")
        if isinstance(region_lineage, dict) and region_lineage:
            result_item["region_lineage"] = {
                "source_image_path": _read_str(region_lineage.get("source_image_path")),
                "crop_box": (
                    dict(region_lineage.get("crop_box"))
                    if isinstance(region_lineage.get("crop_box"), Mapping)
                    else None
                ),
                "selector_type": _read_str(region_lineage.get("selector_type")),
                "parent_region_ref": (
                    dict(region_lineage.get("parent_region_ref"))
                    if isinstance(region_lineage.get("parent_region_ref"), Mapping)
                    else None
                ),
                "creation_mode": _read_str(region_lineage.get("creation_mode")),
                "zoom_factor": region_lineage.get("zoom_factor"),
            }
        summary = _summarize_image_verify_results([result_item])
        payload = {
            "artifact_type": "transcript_image_verification",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dossier_id": dossier_id,
            "source_transcript_ref": source_ref,
            "image_path": str(region_path),
            "model": model,
            "summary": summary,
            "results": [result_item],
            "image_evidence_regions": [
                {
                    "check_id": check_id,
                    "status": "located",
                    "confidence": "high",
                    "reason": "Agent-selected region.",
                    "crop_box": None,
                    "context_crop_box": None,
                    "selector_type": _read_str(region_lineage.get("selector_type")) or "unknown",
                    "tx_image_evidence_region_ref": region_ref.model_dump(mode="json"),
                    "tx_image_evidence_context_ref": None,
                }
            ],
        }
        artifact_ref = _persist_json_artifact(
            category="transcript_image_verify",
            dossier_id=dossier_id,
            payload=payload,
        )
        return {
            "artifact_ref": artifact_ref,
            "reason_codes": ["tx_image_verified"],
            "tx_source_transcript_ref": source_ref,
            "tx_image_path": str(region_path),
            "tx_image_verify_summary": summary,
            "tx_image_verify_results": [
                {
                    "check_id": result_item.get("check_id"),
                    "status": result_item.get("status"),
                    "confidence": result_item.get("confidence"),
                    "observed_text": _summarize_text(str(result_item.get("observed_text") or ""))[:220],
                    "reason": _summarize_text(str(result_item.get("reason") or ""))[:220],
                    "locator_status": "located",
                    "tx_image_evidence_region_ref": region_ref.model_dump(mode="json"),
                    "tx_image_evidence_context_ref": None,
                }
            ],
            "tx_image_evidence_region_ref": region_ref.model_dump(mode="json"),
            "tx_image_evidence_context_ref": None,
        }

    return _tool_refusal_result("tx_image_evidence_mode_unsupported")
