"""Concrete tool dependency implementations for step-driven kernel actions."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root
from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView
from corpus.virtual_provider import VirtualCorpusProvider

from .run_artifact import ArtifactRef


@dataclass
class CorpusDeedHydrator:
    """Hydrate deed text through the shared corpus provider surface."""

    provider: VirtualCorpusProvider = field(default_factory=VirtualCorpusProvider)

    def hydrate_deed(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        ref = _resolve_deed_ref(inputs)
        if ref is None:
            return {"artifact_ref": None, "reason_codes": ["hydrate_deed_missing_ref_inputs"]}
        entry = self.provider.hydrate_entry(ref)
        provenance_error = str((entry.provenance or {}).get("error") or "").strip()
        if provenance_error:
            return {"artifact_ref": None, "reason_codes": [f"hydrate_deed_failed:{provenance_error}"]}

        artifact_ref = _persist_json_artifact(
            category="hydrated_deeds",
            dossier_id=entry.ref.dossier_id,
            payload={
                "artifact_type": "hydrated_deed",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "entry_ref": _entry_ref_to_dict(entry.ref),
                "text": entry.text,
                "title": entry.title,
                "content_hash": entry.content_hash,
                "provenance": entry.provenance,
            },
        )
        return {"artifact_ref": artifact_ref, "reason_codes": ["deed_hydrated"]}


@dataclass
class CorpusArtifactOpener:
    """Open artifact references with bounded summaries for controller inspection."""

    provider: VirtualCorpusProvider = field(default_factory=VirtualCorpusProvider)

    def open_artifact(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        corpus_ref = _parse_corpus_entry_ref(inputs.get("corpus_entry_ref"))
        if corpus_ref is not None:
            entry = self.provider.hydrate_entry(corpus_ref)
            error = str((entry.provenance or {}).get("error") or "").strip()
            if error:
                return {"reason_codes": [f"artifact_open_failed:{error}"], "summary": ""}
            return {
                "reason_codes": ["artifact_opened"],
                "summary": _summarize_text(entry.text),
                "artifact_ref": None,
            }

        artifact_ref = _coerce_artifact_ref(inputs.get("artifact_ref") or inputs.get("artifact_path"))
        if artifact_ref is None:
            return {"reason_codes": ["artifact_open_missing_ref"], "summary": ""}
        path = Path(artifact_ref.artifact_path)
        if not path.exists():
            return {"reason_codes": ["artifact_open_not_found"], "summary": ""}
        summary = _summarize_path(path)
        return {
            "reason_codes": ["artifact_opened"],
            "summary": summary,
            "artifact_ref": artifact_ref,
        }


@dataclass
class DraftIRFilesystemProposer:
    """Persist deterministic draft-IR stubs as durable artifact refs."""

    def draft_ir(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        dossier_id = _read_str(inputs.get("dossier_id")) or "unknown"
        source_ref = _coerce_artifact_ref(inputs.get("hydrated_deed_artifact_ref"))
        if source_ref is None:
            source_ref = _coerce_artifact_ref(inputs.get("deed_artifact_ref"))

        payload = {
            "artifact_type": "ir_draft_stub",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dossier_id": dossier_id,
            "source_artifact_ref": source_ref.model_dump(mode="json") if source_ref is not None else None,
            "graph": {
                "metadata": {
                    "drafted_by": "kernel_step_tool_stub",
                    "dossier_id": dossier_id,
                },
                "nodes": [],
                "edges": [],
            },
        }
        return _persist_json_artifact(
            category="ir_drafts",
            dossier_id=dossier_id,
            payload=payload,
        )


def _resolve_deed_ref(inputs: Mapping[str, Any]) -> CorpusEntryRef | None:
    raw = inputs.get("source_entry_ref")
    ref = _parse_corpus_entry_ref(raw)
    if ref is not None:
        return ref

    raw_dossier_id = _read_str(inputs.get("dossier_id"))
    if not raw_dossier_id:
        return None
    return CorpusEntryRef(
        view=CorpusView.FINALIZED,
        entry_id=f"final:{raw_dossier_id}",
        kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
        dossier_id=raw_dossier_id,
    )


def _parse_corpus_entry_ref(raw: Any) -> CorpusEntryRef | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        try:
            return CorpusEntryRef(
                view=CorpusView(str(raw.get("view", CorpusView.EVERYTHING.value))),
                entry_id=str(raw.get("entry_id", "")),
                kind=CorpusEntryKind(str(raw.get("kind", CorpusEntryKind.TRANSCRIPT.value))),
                dossier_id=_read_str(raw.get("dossier_id")),
                transcription_id=_read_str(raw.get("transcription_id")),
                segment_id=_read_str(raw.get("segment_id")),
                draft_id=_read_str(raw.get("draft_id")),
                artifact_type=_read_str(raw.get("artifact_type")),
                artifact_id=_read_str(raw.get("artifact_id")),
                metadata=dict(raw.get("metadata") or {}),
            )
        except Exception:
            return None

    raw_str = _read_str(raw)
    if not raw_str:
        return None
    if raw_str.startswith("draft:head:"):
        parts = raw_str.split(":")
        if len(parts) == 4:
            dossier_id = parts[2]
            transcription_id = parts[3]
            return CorpusEntryRef(
                view=CorpusView.EVERYTHING,
                entry_id=raw_str,
                kind=CorpusEntryKind.TRANSCRIPT,
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                draft_id=raw_str,
            )
    if raw_str.startswith("final:"):
        dossier_id = raw_str.split(":", maxsplit=1)[1].strip()
        if dossier_id:
            return CorpusEntryRef(
                view=CorpusView.FINALIZED,
                entry_id=raw_str,
                kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
                dossier_id=dossier_id,
            )
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
        os.replace(tmp_path, str(path))
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    return ArtifactRef(artifact_path=str(path))


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


def _read_str(raw: Any) -> str | None:
    if isinstance(raw, str):
        v = raw.strip()
        return v if v else None
    return None
