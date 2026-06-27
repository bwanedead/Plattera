"""Append-only deed-to-IR published output persistence and publication."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from domains.mapping.deed_to_ir.payloads.published_output import (
    DeedToIrOutputSource,
    DeedToIrPublishedOutput,
)
from services.feature_graph.feature_graph_mapping_sidecar_service import FeatureGraphMappingSidecarService
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

from .output_package_validation import (
    PublishPayloadValidationError,
    PUBLISH_PAYLOAD_VALIDATION_FAILED,
    resolve_mapping_publish_package,
    validate_agent_output_rows,
)
from .output_refs import OUTPUT_REF, build_output_revision_ref
from .paths import (
    UnsafeDeedToIrPathSegmentError,
    deed_to_ir_output_dir,
    deed_to_ir_output_latest_pointer_path,
    deed_to_ir_output_revision_path,
)


def resolve_workspace_key(*, workspace_id: str | None, run_id: str | None) -> str | None:
    workspace = str(workspace_id or "").strip()
    if workspace:
        return workspace
    run = str(run_id or "").strip()
    return run or None


def publish_deed_to_ir_output(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    transcript_edit_source_revision_ref: str | None,
    resolution_state_ref: str | None,
    mapping_artifact_ref: str,
    scope_results: Any | None = None,
    external_dependencies: Any | None = None,
    closure_dimensions: Any | None = None,
    notes: Any | None = None,
    persistence: FeatureGraphPersistenceService | None = None,
) -> dict[str, Any]:
    if not dossier_id:
        raise ValueError("dossier_id_required")
    if not str(transcription_id or "").strip():
        return _refusal("transcription_id_required", "transcription_id is required to publish deed-to-IR output.")
    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not workspace_key:
        return _refusal(
            "workspace_identity_required",
            "Provide workspace_id or run_id to scope deed-to-IR output storage.",
        )
    if not str(mapping_artifact_ref or "").strip():
        return _refusal("mapping_artifact_ref_required", "mapping_artifact_ref is required.")

    service = persistence or FeatureGraphPersistenceService()
    sidecars = FeatureGraphMappingSidecarService(artifacts_root=service.artifacts_root)
    try:
        package = resolve_mapping_publish_package(
            dossier_id=dossier_id,
            mapping_artifact_ref=str(mapping_artifact_ref).strip(),
            persistence=service,
            sidecars=sidecars,
        )
    except ValueError as exc:
        return _refusal(str(exc).strip(), str(exc).strip())

    try:
        scopes, deps, closure, note_rows = validate_agent_output_rows(
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
        )
    except PublishPayloadValidationError as exc:
        return _validation_failure_refusal(exc)

    source_ref = str(transcript_edit_source_revision_ref or "").strip()
    if not source_ref:
        return _refusal(
            "transcript_edit_source_revision_ref_required",
            "Startup handoff must include transcript_edit source revision ref.",
        )

    published = DeedToIrPublishedOutput(
        source=DeedToIrOutputSource(
            transcript_edit_source_revision_ref=source_ref,
            resolution_state_ref=str(resolution_state_ref).strip() if resolution_state_ref else None,
        ),
        selected_artifacts=package.selected_artifacts,
        scope_results=scopes,  # type: ignore[arg-type]
        external_dependencies=deps,  # type: ignore[arg-type]
        closure_dimensions=closure,  # type: ignore[arg-type]
        notes=note_rows,
    )

    revision_digits: str
    revision_ref: str
    try:
        safe_transcription_id = str(transcription_id).strip()
        output_dir = deed_to_ir_output_dir(dossier_id, safe_transcription_id, workspace_key)
        with _workspace_publish_lock(output_dir):
            revision_digits = _next_revision_digits(output_dir=output_dir)
            revision_path = deed_to_ir_output_revision_path(
                dossier_id,
                safe_transcription_id,
                workspace_key,
                revision_digits,
            )
            if revision_path.exists():
                return _refusal("output_revision_exists", "Output revision already exists.")
            _atomic_write_json(revision_path, published.model_dump(mode="json"))

            try:
                service.mark_final_artifacts(
                    dossier_id=dossier_id,
                    targets={
                        "ir": package.ir_artifact.artifact_id,
                        "mapping": package.mapping.artifact_id,
                    },
                )
            except Exception as exc:
                _rollback_revision_file(revision_path)
                message = str(exc).strip() or "final_pointer_write_failed"
                return _refusal("final_pointer_write_failed", message)

            pointer_path = deed_to_ir_output_latest_pointer_path(
                dossier_id,
                safe_transcription_id,
                workspace_key,
            )
            _atomic_write_json(
                pointer_path,
                {
                    "schema_version": "1.0",
                    "revision_digits": revision_digits,
                    "revision_ref": build_output_revision_ref(revision_digits),
                    "output_ref": OUTPUT_REF,
                    "published_at": _utc_now_iso(),
                },
            )
            revision_ref = build_output_revision_ref(revision_digits)
    except UnsafeDeedToIrPathSegmentError as exc:
        return _refusal("invalid_scope_path", str(exc))
    except ValueError as exc:
        code = str(exc).strip()
        if code in {"publication_in_progress", "output_revision_exists"}:
            return _refusal(code, code)
        raise

    selected = package.selected_artifacts
    artifact_refs = [
        OUTPUT_REF,
        revision_ref,
        selected.mapping_artifact_ref,
        selected.control_render_ref,
        selected.clean_render_ref,
        selected.geometry_ref,
        selected.compile_artifact_ref,
        selected.judge_artifact_ref,
        selected.ir_artifact_ref,
    ]
    scope_status_counts = _status_counts(scopes)
    closure_dimension_statuses = [
        {"dimension_id": row["dimension_id"], "status": row["status"]}
        for row in closure
    ]
    return {
        "executed": True,
        "artifact_refs": artifact_refs,
        "outputs": {
            "output_ref": OUTPUT_REF,
            "output_revision_ref": revision_ref,
            "mapping_artifact_ref": selected.mapping_artifact_ref,
            "ir_artifact_ref": selected.ir_artifact_ref,
            "compile_artifact_ref": selected.compile_artifact_ref,
            "judge_artifact_ref": selected.judge_artifact_ref,
            "geometry_ref": selected.geometry_ref,
            "clean_render_ref": selected.clean_render_ref,
            "control_render_ref": selected.control_render_ref,
            "scope_result_count": len(scopes),
            "scope_status_counts": scope_status_counts,
            "external_dependency_count": len(deps),
            "closure_dimension_count": len(closure),
            "closure_dimension_statuses": closure_dimension_statuses,
            "note_count": len(note_rows),
        },
    }


def load_published_output(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    revision_digits: str | None = None,
) -> dict[str, Any] | None:
    if revision_digits is None:
        pointer = _read_json(
            deed_to_ir_output_latest_pointer_path(dossier_id, transcription_id, workspace_id)
        )
        if pointer is None:
            return None
        revision_digits = str(pointer.get("revision_digits") or "")
    if not revision_digits:
        return None
    return _read_json(
        deed_to_ir_output_revision_path(dossier_id, transcription_id, workspace_id, revision_digits)
    )


def _rollback_revision_file(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _next_revision_digits(*, output_dir: Path) -> str:
    highest = 0
    for path in output_dir.glob("rev_*.json"):
        stem = path.stem.replace("rev_", "")
        if len(stem) == 4 and stem.isdigit():
            highest = max(highest, int(stem))
    return f"{highest + 1:04d}"


@contextmanager
def _workspace_publish_lock(output_dir: Path) -> Iterator[None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / ".publish.lock"
    handle = open(lock_path, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise ValueError("publication_in_progress") from exc
    try:
        yield
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="deed_output_",
        suffix=".json",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, str(path))
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _refusal(code: str, message: str) -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {
            "reason_code": code,
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"error": {"code": code, "message": message}},
    }


def _validation_failure_refusal(exc: PublishPayloadValidationError) -> dict[str, Any]:
    reason_code = exc.reason_code or PUBLISH_PAYLOAD_VALIDATION_FAILED
    validation_errors = list(exc.validation_errors)
    return {
        "executed": False,
        "reason_codes": [reason_code],
        "refusal": {
            "reason_code": reason_code,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": PUBLISH_PAYLOAD_VALIDATION_FAILED,
                "message": "publish payload validation failed",
            },
            "validation_errors": validation_errors,
        },
    }
