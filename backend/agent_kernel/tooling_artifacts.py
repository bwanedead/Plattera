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


def _tool_refusal_result(
    reason_code: str,
    *,
    missing_inputs: list[str] | None = None,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "artifact_ref": None,
        "reason_codes": [reason_code],
        "kernel_refusal": {
            "reason_code": reason_code,
            "missing_inputs": missing_inputs or [],
            "retryable": True,
            "blocked_by_budget": False,
            "blocked_by_invariant": False,
        },
    }
    if isinstance(diagnostics, Mapping):
        out["diagnostics"] = dict(diagnostics)
    return out


def _read_json_dict(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_str(raw: Any) -> str | None:
    if isinstance(raw, str):
        v = raw.strip()
        return v if v else None
    return None


def _coerce_artifact_ref(raw: Any) -> ArtifactRef | None:
    if isinstance(raw, ArtifactRef):
        return raw
    if isinstance(raw, dict):
        try:
            return ArtifactRef.model_validate(raw)
        except Exception:
            return None
    raw_str = _read_str(raw)
    if raw_str:
        return ArtifactRef(artifact_path=raw_str)
    return None


def _entry_ref_to_dict(ref: CorpusEntryRef) -> dict[str, Any]:
    return {
        "view": ref.view.value,
        "entry_id": ref.entry_id,
        "kind": ref.kind.value,
        "dossier_id": ref.dossier_id,
        "transcription_id": ref.transcription_id,
        "segment_id": ref.segment_id,
        "draft_id": ref.draft_id,
        "artifact_type": ref.artifact_type,
        "artifact_id": ref.artifact_id,
        "metadata": ref.metadata,
    }


def _persist_json_artifact(
    *,
    category: str,
    dossier_id: str | None,
    payload: dict[str, Any],
) -> ArtifactRef:
    root = agent_kernel_artifacts_root() / "tool_outputs" / category / str(dossier_id or "unknown")
    root.mkdir(parents=True, exist_ok=True)
    artifact_name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}.json"
    path = root / artifact_name

    fd, tmp_path = tempfile.mkstemp(prefix="kernel_tool_", suffix=".json", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, str(path))
        except PermissionError:
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    return ArtifactRef(artifact_path=str(path))


def _persist_text_artifact(
    *,
    category: str,
    dossier_id: str | None,
    text: str,
    suffix: str,
) -> ArtifactRef:
    root = agent_kernel_artifacts_root() / "tool_outputs" / category / str(dossier_id or "unknown")
    root.mkdir(parents=True, exist_ok=True)
    artifact_name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}{suffix}"
    path = root / artifact_name

    fd, tmp_path = tempfile.mkstemp(prefix="kernel_tool_", suffix=suffix, dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, str(path))
        except PermissionError:
            path.write_text(text, encoding="utf-8", newline="\n")
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    return ArtifactRef(artifact_path=str(path))


def _persist_binary_artifact(
    *,
    category: str,
    dossier_id: str | None,
    data: bytes,
    suffix: str,
) -> ArtifactRef:
    root = agent_kernel_artifacts_root() / "tool_outputs" / category / str(dossier_id or "unknown")
    root.mkdir(parents=True, exist_ok=True)
    artifact_name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}{suffix}"
    path = root / artifact_name
    fd, tmp_path = tempfile.mkstemp(prefix="kernel_tool_", suffix=suffix, dir=str(root))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, str(path))
        except PermissionError:
            path.write_bytes(data)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    return ArtifactRef(artifact_path=str(path))


def _infer_dossier_id_from_transcript_ref(path: Path) -> str | None:
    parts = list(path.parts)
    try:
        idx = parts.index("transcriptions")
    except ValueError:
        return None
    if idx + 1 >= len(parts):
        return None
    value = str(parts[idx + 1]).strip()
    return value or None


def _infer_transcription_id_from_transcript_ref(path: Path) -> str | None:
    parts = list(path.parts)
    try:
        idx = parts.index("transcriptions")
    except ValueError:
        return None
    if idx + 2 >= len(parts):
        return None
    value = str(parts[idx + 2]).strip()
    return value or None


def _infer_dossier_id_from_feature_graph_artifact_path(path_value: str) -> str | None:
    try:
        path = Path(path_value).resolve()
        root = dossiers_feature_graphs_artifacts_root().resolve()
    except Exception:
        return None
    if path == root or root not in path.parents:
        return None
    try:
        rel = path.relative_to(root)
    except Exception:
        return None
    if not rel.parts:
        return None
    candidate = str(rel.parts[0]).strip()
    return candidate or None


def _infer_dossier_id_for_agent_kernel_artifact(path_value: str) -> str | None:
    try:
        path = Path(path_value).resolve()
        root = agent_kernel_artifacts_root().resolve()
    except Exception:
        return None
    if path == root or root not in path.parents:
        return None
    try:
        rel = path.relative_to(root)
    except Exception:
        return None
    parts = list(rel.parts)
    if len(parts) >= 4 and parts[0] == "tool_outputs":
        candidate = str(parts[2]).strip()
        return candidate or None
    return None


def _infer_parent_artifact_ids(inputs: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("ir_artifact_ref", "compile_artifact_ref", "judge_artifact_ref", "bundle_artifact_ref"):
        ref = _coerce_artifact_ref(inputs.get(key))
        if ref is None:
            continue
        stem = Path(ref.artifact_path).stem
        if stem:
            refs.append(stem)
    return refs


def _summarize_path(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return f"artifact_open_unreadable:{path.name}"
    raw = raw.strip()
    if not raw:
        return "artifact_open_empty"
    try:
        parsed = json.loads(raw)
        keys = list(parsed.keys()) if isinstance(parsed, dict) else []
        if keys:
            return f"json_keys={','.join(str(k) for k in keys[:12])}"
        return "json_value_loaded"
    except Exception:
        return _summarize_text(raw)


def _summarize_text(text: str) -> str:
    compact = " ".join((text or "").split())
    return compact[:512]




