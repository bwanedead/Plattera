from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from time import time
from typing import Any


class RunInspectionMirror:
    def __init__(
        self,
        *,
        run_id: str,
        max_runs: int = 5,
        base_dir: Path | None = None,
    ) -> None:
        root = base_dir if isinstance(base_dir, Path) else Path(__file__).resolve().parents[1] / "run_inspection"
        self._root = root
        self._max_runs = max(1, int(max_runs))
        self._run_id = str(run_id or "").strip()
        self._run_dir = self._root / self._run_id
        self._manifest_path = self._run_dir / "run_manifest.json"
        self._known_source_paths: set[str] = set()
        self._manifest: dict[str, Any] = {
            "run_id": self._run_id,
            "created_at_epoch_seconds": int(time()),
            "updated_at_epoch_seconds": int(time()),
            "status": "running",
            "reason_code": None,
            "artifacts": [],
        }
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._write_manifest()
        self._prune_old_runs()

    def capture_event(self, *, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        phase = str(event.get("phase") or "").strip().lower()
        detail = event.get("detail") if isinstance(event.get("detail"), dict) else {}
        iteration = int(event.get("iteration") or 0)
        feedback_focus_meta = self._focused_image_metadata_from_feedback_event(event)
        refs: list[tuple[str, str]] = []
        refs.extend(self._extract_refs_from_detail(detail))
        refs.extend(self._extract_refs_from_latest_refs(event.get("latest_refs")))
        refs.extend(self._extract_refs_from_feedback_prompt(event))
        if not refs:
            return
        for ref_kind, source in refs:
            source_path = str(source or "").strip()
            if not source_path:
                continue
            detail_lineage = detail.get("region_lineage") if isinstance(detail.get("region_lineage"), dict) else {}
            mirrored = self._mirror_artifact(
                source_path=source_path,
                iteration=iteration,
                phase=phase,
                detail=detail,
                ref_kind=ref_kind,
            )
            if mirrored is None:
                continue
            source_key = str(Path(source_path))
            entry = {
                "run_id": self._run_id,
                "iteration": iteration,
                "phase": phase or None,
                "decision_key": str(detail.get("decision_key") or detail.get("focus_decision_key") or "").strip().lower() or None,
                "evidence_kind": str(detail.get("evidence_kind") or "").strip().lower() or None,
                "mode": str(detail.get("mode") or "").strip().lower() or None,
                "check_id": str(detail.get("check_id") or "").strip() or None,
                "source_artifact_path": source_path,
                "mirrored_path": str(mirrored),
                "created_or_reused": "reused" if source_key in self._known_source_paths else "created",
                "zoom_factor": detail.get("zoom_factor"),
                "selector_type": (
                    str(detail.get("selector_type") or "").strip().lower()
                    or str(feedback_focus_meta.get("selector_type") or "").strip().lower()
                    or None
                ),
                "source_image_path": (
                    str(detail.get("source_image_path") or "").strip()
                    or str(detail_lineage.get("source_image_path") or "").strip()
                    or str(feedback_focus_meta.get("source_image_path") or "").strip()
                    or None
                ),
                "parent_region_ref": (
                    detail.get("parent_region_ref")
                    if isinstance(detail.get("parent_region_ref"), dict)
                    else (
                        detail_lineage.get("parent_region_ref")
                        if isinstance(detail_lineage.get("parent_region_ref"), dict)
                        else (
                            feedback_focus_meta.get("parent_region_ref")
                            if isinstance(feedback_focus_meta.get("parent_region_ref"), dict)
                            else None
                        )
                    )
                ),
                "crop_box": (
                    detail.get("crop_box")
                    if isinstance(detail.get("crop_box"), dict)
                    else (
                        detail_lineage.get("crop_box")
                        if isinstance(detail_lineage.get("crop_box"), dict)
                        else None
                    )
                ),
                "ref_kind": ref_kind,
            }
            self._known_source_paths.add(source_key)
            artifacts = self._manifest.get("artifacts")
            if not isinstance(artifacts, list):
                artifacts = []
                self._manifest["artifacts"] = artifacts
            artifacts.append(entry)
        self._manifest["updated_at_epoch_seconds"] = int(time())
        self._write_manifest()

    def finalize(self, *, status: str, reason_code: str | None) -> None:
        self._manifest["status"] = str(status or "").strip() or "unknown"
        self._manifest["reason_code"] = str(reason_code or "").strip() or None
        self._manifest["updated_at_epoch_seconds"] = int(time())
        self._write_manifest()
        self._prune_old_runs()

    def _extract_refs_from_detail(self, detail: dict[str, Any]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for key in ("tx_image_evidence_region_ref", "tx_image_evidence_context_ref"):
            ref = self._read_ref_path(detail.get(key))
            if ref:
                out.append((key, ref))
        regions = detail.get("image_evidence_regions") if isinstance(detail.get("image_evidence_regions"), list) else []
        for row in regions:
            if not isinstance(row, dict):
                continue
            for key in ("tx_image_evidence_region_ref", "tx_image_evidence_context_ref"):
                ref = self._read_ref_path(row.get(key))
                if ref:
                    out.append((key, ref))
        return out

    def _extract_refs_from_latest_refs(self, latest_refs: Any) -> list[tuple[str, str]]:
        if not isinstance(latest_refs, dict):
            return []
        out: list[tuple[str, str]] = []
        for key in ("tx_image_evidence_region_ref", "tx_image_evidence_context_ref"):
            ref = self._read_ref_path(latest_refs.get(key))
            if ref:
                out.append((key, ref))
        return out

    def _extract_refs_from_feedback_prompt(self, event: dict[str, Any]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if str(event.get("phase") or "").strip().lower() != "human_feedback_needed":
            return out
        context = event.get("context") if isinstance(event.get("context"), dict) else {}
        # Backward/compat fallback for nested wrapper shapes.
        if not context:
            prompt = event.get("feedback_prompt") if isinstance(event.get("feedback_prompt"), dict) else {}
            context = prompt.get("context") if isinstance(prompt.get("context"), dict) else {}
        focused = context.get("focused_image_evidence") if isinstance(context.get("focused_image_evidence"), dict) else {}
        for key in ("tx_image_evidence_region_ref", "tx_image_evidence_context_ref"):
            ref = self._read_ref_path(focused.get(key))
            if ref:
                out.append((f"hitl_{key}", ref))
        return out

    def _focused_image_metadata_from_feedback_event(self, event: dict[str, Any]) -> dict[str, Any]:
        if str(event.get("phase") or "").strip().lower() != "human_feedback_needed":
            return {}
        context = event.get("context") if isinstance(event.get("context"), dict) else {}
        if not context:
            prompt = event.get("feedback_prompt") if isinstance(event.get("feedback_prompt"), dict) else {}
            context = prompt.get("context") if isinstance(prompt.get("context"), dict) else {}
        focused = context.get("focused_image_evidence") if isinstance(context.get("focused_image_evidence"), dict) else {}
        if not focused:
            return {}
        region_lineage = focused.get("region_lineage") if isinstance(focused.get("region_lineage"), dict) else {}
        return {
            "selector_type": str(focused.get("selector_type") or "").strip().lower() or None,
            "source_image_path": (
                str(focused.get("source_image_path") or "").strip()
                or str(region_lineage.get("source_image_path") or "").strip()
                or None
            ),
            "parent_region_ref": (
                focused.get("parent_region_ref")
                if isinstance(focused.get("parent_region_ref"), dict)
                else (
                    region_lineage.get("parent_region_ref")
                    if isinstance(region_lineage.get("parent_region_ref"), dict)
                    else None
                )
            ),
        }

    def _mirror_artifact(
        self,
        *,
        source_path: str,
        iteration: int,
        phase: str,
        detail: dict[str, Any],
        ref_kind: str,
    ) -> Path | None:
        src = Path(source_path)
        if not src.exists() or not src.is_file():
            return None
        mode = str(detail.get("mode") or "").strip().lower() or "unknown"
        evidence_kind = str(detail.get("evidence_kind") or "").strip().lower().replace(":", "_") or "none"
        suffix = src.suffix or ".bin"
        stem = f"iteration_{max(0, int(iteration)):02d}_{phase or 'phase'}_{evidence_kind}_{mode}_{ref_kind}{suffix}"
        target = self._run_dir / stem
        if target.exists():
            return target
        try:
            os.link(str(src), str(target))
        except Exception:
            shutil.copy2(src, target)
        return target

    def _write_manifest(self) -> None:
        self._manifest_path.write_text(
            json.dumps(self._manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _prune_old_runs(self) -> None:
        if not self._root.exists():
            return
        run_dirs = [p for p in self._root.iterdir() if p.is_dir()]
        run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in run_dirs[self._max_runs :]:
            shutil.rmtree(stale, ignore_errors=True)

    @staticmethod
    def _read_ref_path(raw: Any) -> str | None:
        if isinstance(raw, dict):
            value = str(raw.get("artifact_path") or "").strip()
            return value or None
        if isinstance(raw, str):
            value = raw.strip()
            return value or None
        return None
