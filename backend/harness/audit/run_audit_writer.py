"""Per-turn forensic audit writer for harness CLI runs.

Collects raw LLM I/O for each choose-action turn (via the adapter callback) and writes:
- ``audit/turn_NNNN.json``   — per-turn record
- ``audit/index.json``       — run-level summary
- ``audit/review.md``        — human-readable review

Designed to be a lightweight side-channel: all I/O is best-effort (exceptions suppressed
after logging) so audit failures never block run completion.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .event_log import AuditEventLog
from .human_timeline import write_human_timeline
from .normalize import audit_jsonable
from harness.terminal_taxonomy import classify_terminal_artifact_posture

_LOG = logging.getLogger(__name__)


class RunAuditWriter:
    """Accumulates per-turn raw LLM I/O and writes audit artifacts at finalization.

    Pass ``run_dir=None`` to create a no-op instance (useful in test/stub contexts).
    """

    def __init__(
        self,
        run_dir: Path | str | None,
        *,
        run_id: str = "",
        session_id: str = "",
        request_id: str = "",
        upstream_run_lineage: dict[str, Any] | None = None,
    ) -> None:
        self._dir: Path | None = Path(run_dir) / "audit" if run_dir is not None else None
        self._run_id = run_id
        self._session_id = session_id
        self._request_id = request_id
        self._upstream_run_lineage = upstream_run_lineage
        self._turns: list[dict[str, Any]] = []
        # Index: turn_index → position in _turns list for O(1) supplement lookup.
        self._turn_index_map: dict[int, int] = {}
        self._event_log = AuditEventLog(run_dir)

    # ------------------------------------------------------------------
    # RawLlmIoObserver surface
    # ------------------------------------------------------------------

    def observe_llm_io(self, data: dict[str, Any]) -> None:
        """Receive one raw I/O record per choose-action turn from the adapter."""
        if self._dir is None:
            return
        record = _normalize_turn_record(data)
        # Turn file: stamp only missing canonical fields (preserves caller-supplied values).
        turn_record = self._stamp_canonical_identity(record)
        turn_index = int(turn_record.get("turn_index") or 0)
        pos = len(self._turns)
        self._turns.append(turn_record)
        self._turn_index_map[turn_index] = pos
        # JSONL event log: overwrite identity fields so payload matches top-level meta.
        self._event_log.append(
            "llm_io", self._canonicalize_payload_identity(record),
            turn_index=turn_index,
            **self._canonical_meta(),
        )
        self._write_turn_record(turn_index, turn_record)

    # ------------------------------------------------------------------
    # TurnCompletionObserver surface
    # ------------------------------------------------------------------

    def observe_turn_completed(self, data: dict[str, Any]) -> None:
        """Supplement the matching LLM I/O turn record with post-execution data."""
        if self._dir is None:
            return
        record = _normalize_turn_record(data)
        # Turn file: stamp only missing canonical fields (preserves caller-supplied values).
        turn_record = self._stamp_canonical_identity(record)
        turn_index = int(turn_record.get("turn_index") or 0)
        pos = self._turn_index_map.get(turn_index)
        if pos is None:
            # No matching LLM I/O record (e.g. turn was skipped before choose_action).
            # Create a minimal stub so we don't lose the tool/state data.
            stub: dict[str, Any] = {"turn_index": turn_index}
            stub.update({k: v for k, v in turn_record.items() if k != "turn_index"})
            self._turns.append(stub)
            self._turn_index_map[turn_index] = len(self._turns) - 1
            self._event_log.append(
                "turn_completed", self._canonicalize_payload_identity(stub),
                turn_index=turn_index,
                **self._canonical_meta(),
            )
            self._write_turn_record(turn_index, stub)
            return
        self._turns[pos].update({k: v for k, v in turn_record.items() if k != "turn_index"})
        self._event_log.append(
            "turn_completed", self._canonicalize_payload_identity(record),
            turn_index=turn_index,
            **self._canonical_meta(),
        )
        self._write_turn_record(turn_index, self._turns[pos])

    # ------------------------------------------------------------------
    # Canonical identity helpers
    # ------------------------------------------------------------------

    def _canonical_meta(self) -> dict[str, Any]:
        """Return only the non-empty canonical identity fields for event_log **meta."""
        meta: dict[str, Any] = {}
        if self._run_id:
            meta["run_id"] = self._run_id
        if self._session_id:
            meta["session_id"] = self._session_id
        if self._request_id:
            meta["request_id"] = self._request_id
        return meta

    def _stamp_canonical_identity(self, record: dict[str, Any]) -> dict[str, Any]:
        """Inject canonical identity fields into a turn record if not already present.

        Used for turn files only — preserves any caller-supplied identity values.
        """
        stamped = dict(record)
        if self._run_id and "run_id" not in stamped:
            stamped["run_id"] = self._run_id
        if self._session_id and "session_id" not in stamped:
            stamped["session_id"] = self._session_id
        if self._request_id and "request_id" not in stamped:
            stamped["request_id"] = self._request_id
        return stamped

    def _canonicalize_payload_identity(self, record: dict[str, Any]) -> dict[str, Any]:
        """Overwrite identity fields with canonical values for event_log payloads.

        Used for JSONL event log only — ensures the payload matches the canonical
        top-level meta so a single events.jsonl row never carries split lineage.
        """
        canonicalized = dict(record)
        if self._run_id:
            canonicalized["run_id"] = self._run_id
        if self._session_id:
            canonicalized["session_id"] = self._session_id
        if self._request_id:
            canonicalized["request_id"] = self._request_id
        return canonicalized

    # ------------------------------------------------------------------
    # Finalization (call once, at run completion or failure)
    # ------------------------------------------------------------------

    def finalize(
        self,
        *,
        terminal_class: str,
        reason_code: str,
        iterations: int,
        latest_refs: dict[str, Any],
        trace_events: list[dict[str, Any]],
        run_id: str = "",
    ) -> None:
        """Write all audit artifacts.  Never raises — exceptions are logged and suppressed."""
        if self._dir is None:
            return
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            merged_turns = self._merge_turns_with_disk()
            self._write_index(run_id, terminal_class, reason_code, iterations, latest_refs, merged_turns)
            self._write_review(terminal_class, reason_code, iterations, trace_events, latest_refs, merged_turns)
            write_human_timeline(
                self._dir,
                merged_turns,
                upstream_run_lineage=self._upstream_run_lineage,
            )
        except Exception:
            _LOG.warning("RunAuditWriter.finalize failed; audit artifacts may be incomplete", exc_info=True)

    # ------------------------------------------------------------------
    # Disk-merge helper
    # ------------------------------------------------------------------

    def _merge_turns_with_disk(self) -> list[dict[str, Any]]:
        """Return complete turn list by merging in-memory turns with existing disk turn files.

        In-memory records take precedence for the same turn_index because
        ``observe_turn_completed`` supplements them after the initial write.
        Disk-only turns (present in forensic files but not in memory) are included
        so finalization always projects the full run even when the writer was
        reconstructed mid-run.
        """
        disk_turns = _load_turn_records(self._dir) if self._dir else []
        if not disk_turns:
            return list(self._turns)
        mem_by_index: dict[int, dict[str, Any]] = {
            int(t.get("turn_index") or 0): t for t in self._turns
        }
        merged: dict[int, dict[str, Any]] = {}
        for dt in disk_turns:
            tidx = int(dt.get("turn_index") or 0)
            merged[tidx] = dt
        merged.update(mem_by_index)  # in-memory wins on collision
        return sorted(merged.values(), key=lambda t: int(t.get("turn_index") or 0))

    # ------------------------------------------------------------------
    # Internal writers
    # ------------------------------------------------------------------

    def _write_turn_record(self, turn_idx: int, record: dict[str, Any]) -> None:
        _write_json_atomic(self._dir / f"turn_{turn_idx:04d}.json", record)  # type: ignore[arg-type]
        self._refresh_human_timeline()

    def _refresh_human_timeline(self) -> None:
        if self._dir is None:
            return
        write_human_timeline(
            self._dir,
            self._turns,
            upstream_run_lineage=self._upstream_run_lineage,
        )

    def _write_index(
        self,
        run_id: str,
        terminal_class: str,
        reason_code: str,
        iterations: int,
        latest_refs: dict[str, Any],
        turns: list[dict[str, Any]] | None = None,
    ) -> None:
        turns = turns if turns is not None else self._turns
        repairs = sum(1 for t in turns if t.get("repair_attempted"))
        terminal_artifact_posture = classify_terminal_artifact_posture(
            terminal_class=terminal_class or None,
            ref_keys=list(latest_refs.keys()),
        )
        index_payload: dict[str, Any] = {
            "run_id": run_id,
            "terminal_class": terminal_class,
            "terminal_artifact_posture": terminal_artifact_posture,
            "reason_code": reason_code,
            "iterations": iterations,
            "turn_count": len(turns),
            "repairs_attempted": repairs,
            "latest_refs": latest_refs,
        }
        if isinstance(self._upstream_run_lineage, dict):
            index_payload["upstream_run_lineage"] = self._upstream_run_lineage
        _write_json_atomic(
            self._dir / "index.json",  # type: ignore[arg-type]
            index_payload,
        )

    def _write_review(
        self,
        terminal_class: str,
        reason_code: str,
        iterations: int,
        trace_events: list[dict[str, Any]],
        latest_refs: dict[str, Any],
        turns: list[dict[str, Any]] | None = None,
    ) -> None:
        turns = turns if turns is not None else self._turns
        lines = _build_review_lines(
            turns=turns,
            terminal_class=terminal_class,
            reason_code=reason_code,
            iterations=iterations,
            trace_events=trace_events,
            latest_refs=latest_refs,
            run_terminal_override=None,
        )
        (self._dir / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")  # type: ignore[operator]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_tool_sequence(trace_events: list[dict[str, Any]]) -> list[str]:
    """Pull action_type per executed tool_execution event, in iteration order."""
    out: list[str] = []
    for ev in trace_events:
        if ev.get("event_kind") != "tool_execution":
            continue
        payload = ev.get("payload") or {}
        action_type = str(payload.get("action_type") or "")
        state = str(payload.get("execution_state") or "")
        iteration = ev.get("iteration_index")
        label = f"iter {iteration}: {action_type} [{state}]" if iteration is not None else f"{action_type} [{state}]"
        out.append(label)
    return out


def rewrite_terminal_artifacts(
    run_dir: Path | str | None,
    *,
    terminal_class: str,
    reason_code: str,
    iterations: int,
    latest_refs: dict[str, Any],
    trace_events: list[dict[str, Any]],
    terminal_decision: str | None = None,
    run_id: str = "",
) -> None:
    """Rewrite audit terminal artifacts after an outer lifecycle reclassification."""
    if run_dir is None:
        return
    audit_dir = Path(run_dir) / "audit"
    if not audit_dir.is_dir():
        return
    try:
        turns = _load_turn_records(audit_dir)
        event_log = AuditEventLog(run_dir)
        last_turn_index = int(turns[-1].get("turn_index") or 0) if turns else None
        session_id = str((turns[-1].get("session_id") if turns else "") or "")
        request_id = str((turns[-1].get("request_id") if turns else "") or "")
        override_payload = {
            "terminal_class": terminal_class,
            "reason_code": reason_code,
            "iterations": iterations,
            "latest_refs": latest_refs,
            "terminal_decision": terminal_decision,
            "run_id": run_id or None,
            "session_id": session_id or None,
            "request_id": request_id or None,
        }
        existing_lineage = _read_existing_upstream_run_lineage(audit_dir)
        write_human_timeline(
            audit_dir,
            turns,
            run_terminal_override=override_payload,
            upstream_run_lineage=existing_lineage,
        )
        terminal_artifact_posture = classify_terminal_artifact_posture(
            terminal_class=terminal_class or None,
            ref_keys=list(latest_refs.keys()),
        )
        index_payload: dict[str, Any] = {
            "run_id": run_id,
            "terminal_class": terminal_class,
            "terminal_artifact_posture": terminal_artifact_posture,
            "reason_code": reason_code,
            "iterations": iterations,
            "turn_count": len(turns),
            "repairs_attempted": sum(1 for t in turns if t.get("repair_attempted")),
            "latest_refs": latest_refs,
        }
        if existing_lineage is not None:
            index_payload["upstream_run_lineage"] = existing_lineage
        _write_json_atomic(
            audit_dir / "index.json",
            index_payload,
        )
        event_log.append(
            "run_terminal_override",
            override_payload,
            turn_index=last_turn_index,
            run_id=run_id,
            session_id=session_id or None,
            request_id=request_id or None,
        )
        lines = _build_review_lines(
            turns=turns,
            terminal_class=terminal_class,
            reason_code=reason_code,
            iterations=iterations,
            trace_events=trace_events,
            latest_refs=latest_refs,
            run_terminal_override=override_payload,
        )
        (audit_dir / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        _LOG.warning("rewrite_terminal_artifacts failed", exc_info=True)


def _read_existing_upstream_run_lineage(audit_dir: Path) -> dict[str, Any] | None:
    index_path = audit_dir / "index.json"
    if not index_path.is_file():
        return None
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    lineage = payload.get("upstream_run_lineage")
    return dict(lineage) if isinstance(lineage, dict) else None


def _build_review_lines(
    *,
    turns: list[dict[str, Any]],
    terminal_class: str,
    reason_code: str,
    iterations: int,
    trace_events: list[dict[str, Any]],
    latest_refs: dict[str, Any],
    run_terminal_override: dict[str, Any] | None = None,
) -> list[str]:
    tool_seq = _extract_tool_sequence(trace_events)
    repairs = sum(1 for t in turns if t.get("repair_attempted"))
    parse_failures = sum(1 for t in turns if not t.get("parse_ok") and not t.get("repair_records"))
    total_duration = _total_observed_duration_seconds(turns)
    final_artifact_posture = _final_artifact_posture(turns)
    lines: list[str] = [
        "# Run Review",
        "",
        f"**Terminal:** `{terminal_class}`",
        f"**Reason:** `{reason_code}`",
        f"**Iterations:** {iterations}",
        f"**LLM turns recorded:** {len(turns)}",
        f"**Repairs attempted:** {repairs}",
        f"**Parse failures (unrecovered):** {parse_failures}",
    ]
    if total_duration is not None:
        lines.append(f"**Total observed duration:** {_format_duration(total_duration)}")
    if final_artifact_posture is not None:
        lines.append(f"**Final artifact posture:** `{final_artifact_posture}`")
    lines += ["", "## Tool Sequence"]
    if tool_seq:
        lines.extend(f"- {entry}" for entry in tool_seq)
    else:
        lines.append("*(none recorded)*")
    if run_terminal_override:
        lines += [
            "",
            "## Run-Level Terminal Override",
            f"- terminal_class: `{run_terminal_override.get('terminal_class') or 'unknown'}`",
            f"- reason_code: `{run_terminal_override.get('reason_code') or 'unknown'}`",
            f"- terminal_decision: `{run_terminal_override.get('terminal_decision') or 'unknown'}`",
        ]
    lines += ["", "## Per-Turn Summary"]
    for t in turns:
        tidx = t.get("turn_index", "?")
        action = (t.get("tool_request") or {}).get("action_type") or (
            "complete_run" if t.get("terminal_decision") == "complete_run"
            else ("wait_for_human" if t.get("terminal_decision") == "wait_for_human" else "—")
        )
        repair_flag = " [repaired]" if t.get("repair_attempted") else ""
        terminal_flag = f" [{t['terminal_decision']}]" if t.get("terminal_decision") else ""
        refs_before = t.get("latest_refs_before") or {}
        refs_after = t.get("latest_refs_after") or {}
        new_keys = sorted(set(refs_after) - set(refs_before))
        refs_note = f" refs+[{', '.join(new_keys)}]" if new_keys else ""
        patch_fb = t.get("state_patch_feedback") or {}
        patch_note = f" patch:{patch_fb.get('outcome', '')}" if patch_fb.get("outcome") else ""
        lines.append(f"- turn {tidx}: `{action}`{repair_flag}{terminal_flag}{refs_note}{patch_note}")
    lines += ["", "## Latest Refs"]
    if latest_refs:
        lines.extend(f"- `{k}`: {v}" for k, v in latest_refs.items())
    else:
        lines.append("*(empty)*")
    return lines


def _total_observed_duration_seconds(turns: list[dict[str, Any]]) -> float | None:
    starts: list[float] = []
    finishes: list[float] = []
    for turn in turns:
        try:
            started = turn.get("started_at_epoch_seconds")
            finished = turn.get("finished_at_epoch_seconds")
            if started is not None:
                starts.append(float(started))
            if finished is not None:
                finishes.append(float(finished))
        except (TypeError, ValueError):
            continue
    if not starts or not finishes:
        return None
    duration = max(finishes) - min(starts)
    return duration if duration >= 0 else None


def _format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds:.3f}s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60.0)
    return f"{int(minutes)}m {remainder:.1f}s"


def _final_artifact_posture(turns: list[dict[str, Any]]) -> str | None:
    for turn in reversed(turns):
        tool_request = turn.get("tool_request") or {}
        tool_result = turn.get("tool_result_raw") or {}
        action_type = tool_request.get("action_type")
        execution_state = tool_result.get("execution_state")
        artifact_refs = tool_result.get("artifact_refs") or []
        if execution_state != "executed" or not artifact_refs:
            continue
        if action_type == "publish_workspace_artifact":
            return "published"
        if action_type == "save_workspace_artifact":
            return "working"
    return None


def _load_turn_records(audit_dir: Path) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for path in sorted(audit_dir.glob("turn_*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict):
            turns.append(raw)
    return turns


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Atomic JSON write: temp file → os.replace to avoid partial files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(audit_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _normalize_turn_record(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize turn records to JSON-safe primitives before persistence."""
    return dict(audit_jsonable(dict(data)))
