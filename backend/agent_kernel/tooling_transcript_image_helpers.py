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
from tooling.mapping.transcription_edit.apply import (
    apply_plan_to_sections,
    materialize_canonical_input,
)
from tooling.mapping.transcription_edit.contracts import (
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
from services.workflows.mapping.transcription_edit.persistence import TranscriptionEditPersistenceService
from tooling.mapping.transcription_edit.span_seeds import (
    build_transcript_span_seeds_artifact,
    load_transcript_text_for_seeds,
)
from tooling.mapping.transcription_edit.validators import run_validators
from services.llm.openai import OpenAIService

from .run_artifact import ArtifactRef, ValidationInline

logger = logging.getLogger(__name__)

from domains.common.identity_composer import (
    Domain,
    InheritanceMode,
    Surface,
    compose_identity_header,
)

from .tooling_artifacts import (
    _coerce_artifact_ref,
    _infer_dossier_id_from_transcript_ref,
    _infer_transcription_id_from_transcript_ref,
    _persist_binary_artifact,
    _persist_json_artifact,
    _persist_text_artifact,
    _read_json_dict,
    _read_str,
    _summarize_text,
    _tool_refusal_result,
)
from .tooling_text_spans import _bounded_float, _bounded_int

def _coerce_grid_spec(raw: Any) -> dict[str, int]:
    value = raw if isinstance(raw, Mapping) else {}
    rows = _bounded_int(value.get("rows"), default=6, minimum=2, maximum=20)
    cols = _bounded_int(value.get("cols"), default=6, minimum=2, maximum=20)
    return {"rows": rows, "cols": cols}


def _persist_grid_overlay_artifact(
    *,
    source_image_path: Path,
    dossier_id: str,
    grid_spec: dict[str, int],
) -> ArtifactRef:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError(f"pillow_unavailable:{exc}") from exc
    with Image.open(source_image_path) as img:
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        rows = max(2, int(grid_spec.get("rows", 6)))
        cols = max(2, int(grid_spec.get("cols", 6)))
        cell_w = max(1, img.width // cols)
        cell_h = max(1, img.height // rows)
        for c in range(1, cols):
            x = c * cell_w
            draw.line((x, 0, x, img.height), fill=(255, 0, 0), width=1)
        for r in range(1, rows):
            y = r * cell_h
            draw.line((0, y, img.width, y), fill=(255, 0, 0), width=1)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=92)
    return _persist_binary_artifact(
        category="transcript_image_inspection_grid",
        dossier_id=dossier_id,
        data=out.getvalue(),
        suffix=".jpg",
    )


def _coerce_requested_crop_box(
    *,
    target: Mapping[str, Any],
    image_width: int,
    image_height: int,
) -> dict[str, int] | None:
    crop_pixels = _coerce_crop_box(target.get("crop_box_pixels"))
    if crop_pixels is not None:
        clamped = _clamp_crop_box(crop_box=crop_pixels, image_width=image_width, image_height=image_height)
        return _enforce_min_crop_size(clamped, image_width=image_width, image_height=image_height)
    normalized = target.get("crop_box_normalized")
    crop_from_norm = _coerce_normalized_crop_box(
        normalized=normalized,
        image_width=image_width,
        image_height=image_height,
    )
    if crop_from_norm is not None:
        return _enforce_min_crop_size(crop_from_norm, image_width=image_width, image_height=image_height)
    selection = target.get("grid_selection")
    crop_from_grid = _coerce_grid_selection_crop_box(
        selection=selection,
        image_width=image_width,
        image_height=image_height,
        grid_spec=_coerce_grid_spec(target.get("grid_spec")),
    )
    if crop_from_grid is not None:
        return _enforce_min_crop_size(crop_from_grid, image_width=image_width, image_height=image_height)
    return None


def _selector_type_from_target(target: Mapping[str, Any]) -> str:
    if isinstance(target.get("crop_box_normalized"), Mapping):
        return "normalized_box"
    if isinstance(target.get("crop_box_pixels"), Mapping):
        return "pixel_box"
    if isinstance(target.get("grid_selection"), Mapping):
        return "grid_selection"
    return "unknown"


def _enforce_min_crop_size(
    crop_box: dict[str, int] | None,
    *,
    image_width: int,
    image_height: int,
    min_size: int = 20,
) -> dict[str, int] | None:
    if not isinstance(crop_box, dict):
        return None
    x = int(crop_box.get("x", 0))
    y = int(crop_box.get("y", 0))
    width = max(min_size, int(crop_box.get("width", min_size)))
    height = max(min_size, int(crop_box.get("height", min_size)))
    return _clamp_crop_box(
        crop_box={"x": x, "y": y, "width": width, "height": height},
        image_width=image_width,
        image_height=image_height,
    )


def _coerce_normalized_crop_box(
    *,
    normalized: Any,
    image_width: int,
    image_height: int,
) -> dict[str, int] | None:
    if not isinstance(normalized, Mapping):
        return None
    try:
        x = float(normalized.get("x", 0.0))
        y = float(normalized.get("y", 0.0))
        width = float(normalized.get("width", 0.0))
        height = float(normalized.get("height", 0.0))
    except Exception:
        return None
    if width <= 0.0 or height <= 0.0:
        return None
    box = {
        "x": int(round(max(0.0, x) * image_width)),
        "y": int(round(max(0.0, y) * image_height)),
        "width": int(round(width * image_width)),
        "height": int(round(height * image_height)),
    }
    return _clamp_crop_box(crop_box=box, image_width=image_width, image_height=image_height)


def _coerce_grid_selection_crop_box(
    *,
    selection: Any,
    image_width: int,
    image_height: int,
    grid_spec: dict[str, int],
) -> dict[str, int] | None:
    if not isinstance(selection, Mapping):
        return None
    rows = max(2, int(grid_spec.get("rows", 6)))
    cols = max(2, int(grid_spec.get("cols", 6)))
    row_start = _bounded_int(selection.get("row_start"), default=0, minimum=0, maximum=rows - 1)
    row_end = _bounded_int(selection.get("row_end"), default=row_start, minimum=row_start, maximum=rows - 1)
    col_start = _bounded_int(selection.get("col_start"), default=0, minimum=0, maximum=cols - 1)
    col_end = _bounded_int(selection.get("col_end"), default=col_start, minimum=col_start, maximum=cols - 1)
    cell_w = image_width / float(cols)
    cell_h = image_height / float(rows)
    box = {
        "x": int(round(col_start * cell_w)),
        "y": int(round(row_start * cell_h)),
        "width": int(round((col_end - col_start + 1) * cell_w)),
        "height": int(round((row_end - row_start + 1) * cell_h)),
    }
    return _clamp_crop_box(crop_box=box, image_width=image_width, image_height=image_height)


def _apply_region_transform(
    *,
    crop_box: dict[str, int],
    transform: str,
    amount: float,
    image_width: int,
    image_height: int,
) -> dict[str, int] | None:
    t = str(transform or "").strip().lower()
    x = int(crop_box.get("x", 0))
    y = int(crop_box.get("y", 0))
    w = int(crop_box.get("width", 0))
    h = int(crop_box.get("height", 0))
    if w <= 0 or h <= 0:
        return None
    if t in {"expand", "shrink"}:
        factor = 1.0 + float(amount) if t == "expand" else max(0.2, 1.0 - float(amount))
        new_w = int(round(w * factor))
        new_h = int(round(h * factor))
        cx = x + (w // 2)
        cy = y + (h // 2)
        x = cx - (new_w // 2)
        y = cy - (new_h // 2)
        w = new_w
        h = new_h
    elif t in {"shift_up", "shift_down", "shift_left", "shift_right"}:
        shift_x = int(round(w * float(amount)))
        shift_y = int(round(h * float(amount)))
        if t == "shift_up":
            y -= shift_y
        elif t == "shift_down":
            y += shift_y
        elif t == "shift_left":
            x -= shift_x
        elif t == "shift_right":
            x += shift_x
    elif t == "set_zoom":
        # No geometry change; zoom handled by caller.
        pass
    else:
        return None
    return _clamp_crop_box(crop_box={"x": x, "y": y, "width": w, "height": h}, image_width=image_width, image_height=image_height)


def _persist_region_lineage_metadata(
    *,
    dossier_id: str,
    region_ref: ArtifactRef | None,
    source_image_path: Path,
    parent_region_ref: ArtifactRef | None,
    crop_box: dict[str, int],
    zoom_factor: float,
    creation_mode: str,
    selector_type: str | None,
) -> ArtifactRef:
    payload = {
        "artifact_type": "transcript_image_region_lineage",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "region_ref": region_ref.model_dump(mode="json") if isinstance(region_ref, ArtifactRef) else None,
        "source_image_path": str(source_image_path),
        "parent_region_ref": parent_region_ref.model_dump(mode="json") if isinstance(parent_region_ref, ArtifactRef) else None,
        "crop_box": dict(crop_box),
        "zoom_factor": float(round(zoom_factor, 3)),
        "creation_mode": str(creation_mode or "").strip().lower() or None,
        "selector_type": str(selector_type or "").strip().lower() or None,
    }
    return _persist_json_artifact(
        category="transcript_image_region_lineage",
        dossier_id=dossier_id,
        payload=payload,
    )


def _load_region_lineage_for_ref(region_ref: ArtifactRef) -> dict[str, Any] | None:
    try:
        root = agent_kernel_artifacts_root() / "tool_outputs" / "transcript_image_region_lineage"
        if not root.exists():
            return None
        region_path = str(region_ref.artifact_path)
        for path in root.rglob("*.json"):
            data = _read_json_dict(path)
            if not isinstance(data, dict):
                continue
            ref = data.get("region_ref") if isinstance(data.get("region_ref"), dict) else {}
            if str(ref.get("artifact_path") or "").strip() == region_path:
                return data
    except Exception:
        return None
    return None


def _coerce_image_verify_checks(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_checks = inputs.get("checks")
    checks: list[dict[str, Any]] = []
    if isinstance(raw_checks, list):
        for item in raw_checks[:8]:
            if isinstance(item, dict):
                checks.append(dict(item))
    elif isinstance(raw_checks, dict):
        checks.append(dict(raw_checks))
    else:
        query = _read_str(inputs.get("query"))
        if query:
            checks.append({"check_id": "single_check", "query": query, "expected_text": _read_str(inputs.get("expected_text"))})
    return checks


def _coerce_crop_box(raw: Any) -> dict[str, int] | None:
    if not isinstance(raw, Mapping):
        return None
    try:
        x = int(raw.get("x"))  # type: ignore[arg-type]
        y = int(raw.get("y"))  # type: ignore[arg-type]
        width = int(raw.get("width"))  # type: ignore[arg-type]
        height = int(raw.get("height"))  # type: ignore[arg-type]
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return {"x": x, "y": y, "width": width, "height": height}


def _locate_image_evidence_region(
    *,
    service: OpenAIService,
    image_path: Path,
    model: str,
    check_id: str,
    query: str,
    expected_text: str | None,
    decision_key: str | None,
    fallback_crop_box: dict[str, int] | None,
    precomputed_region_path: Path | None = None,
    run_link_id: str = "",
    mission_objective: str = "",
) -> dict[str, Any]:
    if isinstance(precomputed_region_path, Path) and precomputed_region_path.exists():
        image_size = _read_image_size(precomputed_region_path)
        if image_size is not None:
            return {
                "check_id": check_id,
                "decision_key": decision_key,
                "status": "located",
                "crop_box": {"x": 0, "y": 0, "width": int(image_size[0]), "height": int(image_size[1])},
                "context_crop_box": None,
                "confidence": "high",
                "reason": "Reusing precomputed focused evidence region artifact.",
                "source": "precomputed_region_ref",
                "precomputed_region_path": str(precomputed_region_path),
            }
    if isinstance(fallback_crop_box, dict):
        return {
            "check_id": check_id,
            "decision_key": decision_key,
            "status": "located",
            "crop_box": dict(fallback_crop_box),
            "context_crop_box": None,
            "confidence": "medium",
            "reason": "Using provided crop box for focused verification.",
            "source": "provided_crop_box",
        }
    try:
        image_b64, render_meta = _encode_image_for_verification(
            image_path=image_path,
            crop_box=None,
            zoom_factor=1.0,
        )
        prompt = _build_transcript_image_locator_prompt(
            check_id=check_id,
            query=query,
            expected_text=expected_text,
            decision_key=decision_key,
            image_size=render_meta.get("rendered_size"),
            run_link_id=run_link_id,
            mission_objective=mission_objective,
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
        normalized = _coerce_image_evidence_locator_result(
            check_id=check_id,
            decision_key=decision_key,
            response=response,
            image_width=int((render_meta.get("rendered_size") or [0, 0])[0] or 0),
            image_height=int((render_meta.get("rendered_size") or [0, 0])[1] or 0),
        )
        return normalized
    except Exception as exc:
        return {
            "check_id": check_id,
            "decision_key": decision_key,
            "status": "unclear",
            "crop_box": None,
            "context_crop_box": None,
            "confidence": "low",
            "reason": f"locator_failed:{_summarize_text(str(exc))[:120]}",
            "source": "locator_error",
        }


def _create_image_evidence_artifacts(
    *,
    source_image_path: Path,
    dossier_id: str,
    check_id: str,
    decision_key: str | None,
    zoom_factor: float,
    locator_result: dict[str, Any],
) -> dict[str, Any]:
    precomputed_region_path = _read_str(locator_result.get("precomputed_region_path"))
    if precomputed_region_path and Path(precomputed_region_path).exists():
        region_ref = ArtifactRef(artifact_path=precomputed_region_path)
        return {
            "tx_image_evidence_region_ref": region_ref,
            "tx_image_evidence_context_ref": None,
            "region_image_path": precomputed_region_path,
            "context_image_path": None,
        }
    crop_box = _coerce_crop_box(locator_result.get("crop_box"))
    context_crop_box = _coerce_crop_box(locator_result.get("context_crop_box"))
    if crop_box is None:
        return {
            "tx_image_evidence_region_ref": None,
            "tx_image_evidence_context_ref": None,
            "region_image_path": None,
            "context_image_path": None,
        }
    region_ref, region_path = _persist_image_crop_artifact(
        source_image_path=source_image_path,
        dossier_id=dossier_id,
        category="transcript_image_evidence_region",
        crop_box=crop_box,
        zoom_factor=zoom_factor,
    )
    context_ref = None
    context_path = None
    if context_crop_box is not None:
        context_ref, context_path = _persist_image_crop_artifact(
            source_image_path=source_image_path,
            dossier_id=dossier_id,
            category="transcript_image_evidence_context",
            crop_box=context_crop_box,
            zoom_factor=1.0,
        )
    metadata_payload = {
        "artifact_type": "transcript_image_evidence_region",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_image_path": str(source_image_path),
        "check_id": check_id,
        "decision_key": decision_key,
        "crop_box": crop_box,
        "context_crop_box": context_crop_box,
        "zoom_factor": float(round(zoom_factor, 3)),
        "locator_status": str(locator_result.get("status") or "unclear"),
        "locator_confidence": str(locator_result.get("confidence") or "low"),
        "locator_reason": str(locator_result.get("reason") or "")[:320],
        "tx_image_evidence_region_ref": region_ref.model_dump(mode="json"),
        "tx_image_evidence_context_ref": context_ref.model_dump(mode="json") if isinstance(context_ref, ArtifactRef) else None,
    }
    _persist_json_artifact(
        category="transcript_image_evidence_regions",
        dossier_id=dossier_id,
        payload=metadata_payload,
    )
    return {
        "tx_image_evidence_region_ref": region_ref,
        "tx_image_evidence_context_ref": context_ref,
        "region_image_path": region_path,
        "context_image_path": context_path,
    }


def _persist_image_crop_artifact(
    *,
    source_image_path: Path,
    dossier_id: str,
    category: str,
    crop_box: dict[str, int],
    zoom_factor: float,
) -> tuple[ArtifactRef, str]:
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError(f"pillow_unavailable:{exc}") from exc
    with Image.open(source_image_path) as img:
        img = img.convert("RGB")
        x = max(0, int(crop_box.get("x", 0)))
        y = max(0, int(crop_box.get("y", 0)))
        width = max(1, int(crop_box.get("width", 1)))
        height = max(1, int(crop_box.get("height", 1)))
        x2 = min(img.width, x + width)
        y2 = min(img.height, y + height)
        if x2 <= x or y2 <= y:
            x = 0
            y = 0
            x2 = img.width
            y2 = img.height
        cropped = img.crop((x, y, x2, y2))
        bounded_zoom = _bounded_float(zoom_factor, default=1.0, minimum=1.0, maximum=6.0)
        if bounded_zoom > 1.0:
            target_w = max(1, int(round(cropped.width * bounded_zoom)))
            target_h = max(1, int(round(cropped.height * bounded_zoom)))
            cropped = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        cropped.save(out, format="JPEG", quality=95)
    ref = _persist_binary_artifact(
        category=category,
        dossier_id=dossier_id,
        data=out.getvalue(),
        suffix=".jpg",
    )
    return ref, ref.artifact_path


def _read_image_size(image_path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(image_path) as img:
            return int(img.width), int(img.height)
    except Exception:
        return None


def _encode_image_for_verification(
    *,
    image_path: Path,
    crop_box: dict[str, int] | None,
    zoom_factor: float,
) -> tuple[str, dict[str, Any]]:
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError(f"pillow_unavailable:{exc}") from exc
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        original_size = [img.width, img.height]
        applied_crop: dict[str, int] | None = None
        if isinstance(crop_box, dict):
            x = max(0, int(crop_box.get("x", 0)))
            y = max(0, int(crop_box.get("y", 0)))
            width = max(1, int(crop_box.get("width", 1)))
            height = max(1, int(crop_box.get("height", 1)))
            x2 = min(img.width, x + width)
            y2 = min(img.height, y + height)
            if x2 > x and y2 > y:
                img = img.crop((x, y, x2, y2))
                applied_crop = {"x": x, "y": y, "width": x2 - x, "height": y2 - y}
        if zoom_factor > 1.0:
            target_w = max(1, int(round(img.width * zoom_factor)))
            target_h = max(1, int(round(img.height * zoom_factor)))
            img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=95)
        encoded = base64.b64encode(out.getvalue()).decode("ascii")
        return encoded, {
            "original_size": original_size,
            "rendered_size": [img.width, img.height],
            "crop_box": applied_crop,
            "zoom_factor": round(float(zoom_factor), 3),
        }


def _build_transcript_image_verify_prompt(
    *,
    check_id: str,
    query: str,
    expected_text: str | None,
    run_link_id: str = "",
    mission_objective: str = "",
    model: str = "",
) -> str:
    identity = compose_identity_header(
        run_link_id=run_link_id,
        mission_objective=mission_objective,
        domain=Domain.TRANSCRIPT_EDIT,
        surface=Surface.TX_IMAGE_VERIFIER,
        inheritance_mode=InheritanceMode.LIGHT,
        model=model,
    )
    payload = {
        "run_identity": {
            "run_link_id": identity.metadata.run_link_id,
            "mission_objective": identity.metadata.mission_objective,
            "domain": identity.metadata.domain,
            "surface": identity.metadata.surface,
            "constitution_version": identity.metadata.constitution_version,
        },
        "identity_context": identity.header_text,
        "task": "Verify a transcript claim against the provided deed image.",
        "instructions": [
            "Carefully read the image text relevant to the query.",
            "If uncertain, set status='unclear' and explain why.",
        ],
        "output_schema": {
            "check_id": "string",
            "status": "match|mismatch|unclear",
            "observed_text": "string",
            "confidence": "low|medium|high",
            "reason": "string",
        },
        "check": {
            "check_id": check_id,
            "query": query,
            "expected_text": expected_text or "",
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _build_transcript_image_locator_prompt(
    *,
    check_id: str,
    query: str,
    expected_text: str | None,
    decision_key: str | None,
    image_size: Any,
    run_link_id: str = "",
    mission_objective: str = "",
    model: str = "",
) -> str:
    identity = compose_identity_header(
        run_link_id=run_link_id,
        mission_objective=mission_objective,
        domain=Domain.TRANSCRIPT_EDIT,
        surface=Surface.TX_IMAGE_LOCATOR,
        inheritance_mode=InheritanceMode.LIGHT,
        model=model,
    )
    payload = {
        "run_identity": {
            "run_link_id": identity.metadata.run_link_id,
            "mission_objective": identity.metadata.mission_objective,
            "domain": identity.metadata.domain,
            "surface": identity.metadata.surface,
            "constitution_version": identity.metadata.constitution_version,
        },
        "identity_context": identity.header_text,
        "task": "Locate where likely visual evidence appears for a transcript verification query.",
        "instructions": [
            "If you cannot confidently localize, return status='unclear' or status='not_found'.",
            "Crop coordinates must be pixel integers in the source image coordinate system.",
        ],
        "output_schema": {
            "check_id": "string",
            "decision_key": "string|null",
            "status": "located|unclear|not_found",
            "crop_box": {"x": 0, "y": 0, "width": 0, "height": 0},
            "context_crop_box": {"x": 0, "y": 0, "width": 0, "height": 0},
            "confidence": "low|medium|high",
            "anchor_snippet": "string|null",
            "reason": "string",
        },
        "check": {
            "check_id": check_id,
            "decision_key": decision_key,
            "query": query,
            "expected_text": expected_text or "",
            "image_size": image_size,
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _coerce_image_evidence_locator_result(
    *,
    check_id: str,
    decision_key: str | None,
    response: Mapping[str, Any],
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    if not bool(response.get("success")):
        return {
            "check_id": check_id,
            "decision_key": decision_key,
            "status": "unclear",
            "crop_box": None,
            "context_crop_box": None,
            "confidence": "low",
            "reason": _summarize_text(str(response.get("error") or "locator_vision_call_failed"))[:260],
            "source": "vision_error",
        }
    raw_text = _read_str(response.get("text")) or ""
    parsed: dict[str, Any] = {}
    try:
        loaded = json.loads(raw_text)
        if isinstance(loaded, dict):
            parsed = loaded
    except Exception:
        parsed = {}
    status = str(parsed.get("status") or "").strip().lower()
    if status not in {"located", "unclear", "not_found"}:
        status = "unclear"
    confidence = str(parsed.get("confidence") or "").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low" if status != "located" else "medium"
    crop_box = _coerce_crop_box(parsed.get("crop_box"))
    context_crop_box = _coerce_crop_box(parsed.get("context_crop_box"))
    if isinstance(crop_box, dict):
        crop_box = _clamp_crop_box(crop_box=crop_box, image_width=image_width, image_height=image_height)
    if isinstance(context_crop_box, dict):
        context_crop_box = _clamp_crop_box(crop_box=context_crop_box, image_width=image_width, image_height=image_height)
    if status == "located" and not isinstance(crop_box, dict):
        status = "unclear"
        confidence = "low"
    reason = _summarize_text(str(parsed.get("reason") or ""))[:320]
    anchor_snippet = _summarize_text(str(parsed.get("anchor_snippet") or ""))[:160] or None
    return {
        "check_id": check_id,
        "decision_key": decision_key,
        "status": status,
        "crop_box": crop_box,
        "context_crop_box": context_crop_box,
        "confidence": confidence,
        "anchor_snippet": anchor_snippet,
        "reason": reason or None,
        "source": "vision_locator",
    }


def _clamp_crop_box(*, crop_box: dict[str, int], image_width: int, image_height: int) -> dict[str, int] | None:
    width_limit = max(1, int(image_width))
    height_limit = max(1, int(image_height))
    x = max(0, min(width_limit - 1, int(crop_box.get("x", 0))))
    y = max(0, min(height_limit - 1, int(crop_box.get("y", 0))))
    width = max(1, int(crop_box.get("width", 1)))
    height = max(1, int(crop_box.get("height", 1)))
    x2 = min(width_limit, x + width)
    y2 = min(height_limit, y + height)
    if x2 <= x or y2 <= y:
        return None
    return {"x": x, "y": y, "width": int(x2 - x), "height": int(y2 - y)}


def _coerce_image_verify_result(
    *,
    check_id: str,
    query: str,
    expected_text: str | None,
    response: Mapping[str, Any],
) -> dict[str, Any]:
    if not bool(response.get("success")):
        return {
            "check_id": check_id,
            "query": query,
            "expected_text": expected_text,
            "status": "unclear",
            "confidence": "low",
            "observed_text": "",
            "reason": _summarize_text(str(response.get("error") or "vision_call_failed"))[:260],
        }
    raw_text = _read_str(response.get("text")) or ""
    parsed = {}
    try:
        loaded = json.loads(raw_text)
        if isinstance(loaded, dict):
            parsed = loaded
    except Exception:
        parsed = {}
    status = str(parsed.get("status") or "").strip().lower()
    if status not in {"match", "mismatch", "unclear"}:
        status = "unclear"
    confidence = str(parsed.get("confidence") or "").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low" if status == "unclear" else "medium"
    observed = _read_str(parsed.get("observed_text")) or _summarize_text(raw_text)[:220]
    reason = _read_str(parsed.get("reason")) or ("model_reported_match" if status == "match" else "model_reported_mismatch")
    return {
        "check_id": _read_str(parsed.get("check_id")) or check_id,
        "query": query,
        "expected_text": expected_text,
        "status": status,
        "confidence": confidence,
        "observed_text": observed,
        "reason": reason,
    }


def _summarize_image_verify_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"match": 0, "mismatch": 0, "unclear": 0}
    for item in results:
        status = str(item.get("status") or "unclear").strip().lower()
        if status not in counts:
            status = "unclear"
        counts[status] += 1
    return {
        "total_checks": len(results),
        "match_count": counts["match"],
        "mismatch_count": counts["mismatch"],
        "unclear_count": counts["unclear"],
    }


def _resolve_transcript_source_image_path(
    *,
    dossier_id: str,
    source_transcript_ref: str,
    requested_image_path: str | None,
) -> str | None:
    if requested_image_path:
        path = Path(requested_image_path)
        if path.exists():
            return str(path)

    source_path = Path(source_transcript_ref)
    inferred_dossier = _infer_dossier_id_from_transcript_ref(source_path)
    dossier = inferred_dossier or (dossier_id if dossier_id != "adhoc" else None)
    transcription_id = _infer_transcription_id_from_transcript_ref(source_path)
    if not dossier or not transcription_id:
        return None
    assoc_path = dossiers_associations_root() / f"assoc_{dossier}.json"
    assoc = _read_json_dict(assoc_path)
    if not isinstance(assoc, dict):
        return None
    associations = assoc.get("associations")
    if not isinstance(associations, list):
        return None
    for entry in associations:
        if not isinstance(entry, dict):
            continue
        if _read_str(entry.get("transcription_id")) != transcription_id:
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        provenance = metadata.get("provenance") if isinstance(metadata, dict) and isinstance(metadata.get("provenance"), dict) else {}
        enhancement = provenance.get("enhancement") if isinstance(provenance, dict) and isinstance(provenance.get("enhancement"), dict) else {}
        candidates = [
            _read_str(enhancement.get("original_image_path")),
            _read_str(metadata.get("original_path")),
            _read_str(enhancement.get("processed_image_path")),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
    return None





