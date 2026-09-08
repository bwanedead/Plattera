"""Pure exact-match transcript edit application and decision provenance reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    TRANSCRIPT_EDIT_DECISIONS_FIELD,
    TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION,
    TRANSCRIPT_EDIT_LANES,
)
from tooling.mapping.transcript_edit.apply_transcript_edits_contract import (
    ValidatedApplyTranscriptEditsRequest,
)
from tooling.mapping.transcript_edit.transcript_edit_decisions_validate import (
    PersistedProvenanceError,
    assert_revision_and_payload_evidence_coherent,
    validate_persisted_transcript_edit_decisions,
)


class ApplyTranscriptEditsEngineError(Exception):
    """Refusal while resolving or applying exact edits (no mutation yet)."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = str(reason_code)
        self.detail = str(detail or "")
        message = self.reason_code if not self.detail else f"{self.reason_code}: {self.detail}"
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedEdit:
    decision_id: str
    lane: str
    start: int
    end: int
    expected_text: str
    replacement_text: str
    context_before: str | None
    context_after: str | None


@dataclass(frozen=True)
class AppliedEditRecord:
    lane: str
    expected_text: str
    replacement_text: str
    context_before: str | None
    context_after: str | None
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class ApplyTranscriptEditsEngineResult:
    payload: dict[str, Any]
    revision_evidence_refs: list[str]
    applied_decision_ids: tuple[str, ...]
    changed_lanes: dict[str, int]


def apply_transcript_edits_to_payload(
    *,
    base_payload: dict[str, Any],
    base_revision_evidence_refs: list[str],
    base_revision_ref: str,
    request: ValidatedApplyTranscriptEditsRequest,
) -> ApplyTranscriptEditsEngineResult:
    """Resolve and apply all edits against one base payload; return new payload + evidence."""
    if type(base_payload) is not dict:
        raise ApplyTranscriptEditsEngineError(
            "malformed_base_payload",
            "Base revision payload must be an object.",
        )

    # Fail closed on any present managed-provenance field; validate fully before edits.
    try:
        existing = validate_persisted_transcript_edit_decisions(payload=base_payload) or []
        assert_revision_and_payload_evidence_coherent(
            revision_evidence_refs=list(base_revision_evidence_refs),
            payload=base_payload,
        )
    except PersistedProvenanceError as exc:
        raise ApplyTranscriptEditsEngineError(exc.reason_code, exc.detail) from exc

    lane_text = _extract_lane_strings(base_payload)
    resolved = _resolve_all_edits(lane_text=lane_text, request=request)
    _refuse_foreign_decision_span_overlap(
        resolved=resolved,
        existing=existing,
        addressed_ids={d.decision_id for d in request.decisions},
    )
    _refuse_intra_request_overlaps(resolved)

    new_lanes, applied_by_decision = _apply_resolved_edits(
        lane_text=lane_text,
        resolved=resolved,
    )
    surviving = _shift_surviving_decisions(
        existing=existing,
        addressed_ids={d.decision_id for d in request.decisions},
        resolved=resolved,
    )
    new_decision_records = _build_request_decision_records(
        request=request,
        base_revision_ref=base_revision_ref,
        applied_by_decision=applied_by_decision,
    )
    merged_decisions = surviving + new_decision_records

    new_payload = dict(base_payload)
    for lane, text in new_lanes.items():
        new_payload[lane] = text

    provenance = {
        "schema_version": TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION,
        "decisions": merged_decisions,
    }
    new_payload[TRANSCRIPT_EDIT_DECISIONS_FIELD] = provenance

    decision_evidence: list[str] = []
    for record in merged_decisions:
        refs = record.get("evidence_refs")
        if isinstance(refs, list):
            for ref in refs:
                if type(ref) is str and ref.strip():
                    decision_evidence.append(ref.strip())

    revision_evidence = _stable_dedupe(
        list(base_revision_evidence_refs) + decision_evidence
    )
    # After validation, mechanically sync payload evidence to the canonical union.
    if "evidence_refs" in new_payload or decision_evidence:
        new_payload["evidence_refs"] = list(revision_evidence)

    changed_lanes: dict[str, int] = {}
    for lane in TRANSCRIPT_EDIT_LANES:
        before = lane_text.get(lane)
        after = new_lanes.get(lane)
        if before is not None and after is not None and before != after:
            changed_lanes[lane] = sum(
                1 for r in resolved if r.lane == lane and r.expected_text != r.replacement_text
            )
            if changed_lanes[lane] == 0:
                changed_lanes[lane] = sum(1 for r in resolved if r.lane == lane)

    return ApplyTranscriptEditsEngineResult(
        payload=new_payload,
        revision_evidence_refs=revision_evidence,
        applied_decision_ids=tuple(d.decision_id for d in request.decisions),
        changed_lanes=changed_lanes,
    )


def _extract_lane_strings(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for lane in TRANSCRIPT_EDIT_LANES:
        if lane not in payload:
            continue
        value = payload[lane]
        if type(value) is not str:
            raise ApplyTranscriptEditsEngineError(
                "transcript_lane_not_string",
                f"Lane {lane!r} must already exist as a string.",
            )
        out[lane] = value
    return out


def _resolve_all_edits(
    *,
    lane_text: dict[str, str],
    request: ValidatedApplyTranscriptEditsRequest,
) -> list[ResolvedEdit]:
    resolved: list[ResolvedEdit] = []
    for decision in request.decisions:
        for edit in decision.edits:
            if edit.lane not in lane_text:
                raise ApplyTranscriptEditsEngineError(
                    "transcript_lane_missing",
                    f"Lane {edit.lane!r} is not present as a string on the base revision.",
                )
            start, end = _unique_match(
                text=lane_text[edit.lane],
                expected=edit.expected_text,
                context_before=edit.context_before,
                context_after=edit.context_after,
            )
            resolved.append(
                ResolvedEdit(
                    decision_id=decision.decision_id,
                    lane=edit.lane,
                    start=start,
                    end=end,
                    expected_text=edit.expected_text,
                    replacement_text=edit.replacement_text,
                    context_before=edit.context_before,
                    context_after=edit.context_after,
                )
            )
    return resolved


def _unique_match(
    *,
    text: str,
    expected: str,
    context_before: str | None,
    context_after: str | None,
) -> tuple[int, int]:
    matches: list[int] = []
    start = 0
    while True:
        idx = text.find(expected, start)
        if idx < 0:
            break
        matches.append(idx)
        start = idx + 1
    if context_before is not None or context_after is not None:
        filtered: list[int] = []
        for idx in matches:
            before_ok = True
            after_ok = True
            if context_before is not None:
                before_ok = text[max(0, idx - len(context_before)) : idx] == context_before
            if context_after is not None:
                end = idx + len(expected)
                after_ok = text[end : end + len(context_after)] == context_after
            if before_ok and after_ok:
                filtered.append(idx)
        matches = filtered
    if not matches:
        raise ApplyTranscriptEditsEngineError(
            "edit_target_not_found",
            "expected_text did not uniquely match with the provided context.",
        )
    if len(matches) > 1:
        raise ApplyTranscriptEditsEngineError(
            "edit_target_ambiguous",
            "expected_text matched multiple locations; provide context_before/context_after.",
        )
    idx = matches[0]
    return idx, idx + len(expected)


def _refuse_intra_request_overlaps(resolved: list[ResolvedEdit]) -> None:
    by_lane: dict[str, list[ResolvedEdit]] = {}
    for item in resolved:
        by_lane.setdefault(item.lane, []).append(item)
    for lane, items in by_lane.items():
        ordered = sorted(items, key=lambda r: (r.start, r.end))
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                a, b = ordered[i], ordered[j]
                if a.end > b.start:
                    raise ApplyTranscriptEditsEngineError(
                        "overlapping_edit_ranges",
                        f"Overlapping edits in lane {lane!r}.",
                    )


def _refuse_foreign_decision_span_overlap(
    *,
    resolved: list[ResolvedEdit],
    existing: list[dict[str, Any]],
    addressed_ids: set[str],
) -> None:
    foreign_spans: list[tuple[str, str, int, int]] = []
    for record in existing:
        did = record.get("decision_id")
        if type(did) is not str or did in addressed_ids:
            continue
        for edit in record.get("edits") or []:
            if type(edit) is not dict:
                continue
            lane = edit.get("lane")
            start = edit.get("start_offset")
            end = edit.get("end_offset")
            if type(lane) is not str or type(start) is not int or type(end) is not int:
                continue
            foreign_spans.append((did, lane, start, end))

    for item in resolved:
        for did, lane, start, end in foreign_spans:
            if lane != item.lane:
                continue
            if item.end > start and end > item.start:
                raise ApplyTranscriptEditsEngineError(
                    "overlaps_other_decision_span",
                    f"Edit overlaps current span of decision {did!r}; "
                    "include that decision_id in the request to revise it.",
                )


def _apply_resolved_edits(
    *,
    lane_text: dict[str, str],
    resolved: list[ResolvedEdit],
) -> tuple[dict[str, str], dict[str, list[AppliedEditRecord]]]:
    new_lanes = dict(lane_text)
    applied_by_decision: dict[str, list[AppliedEditRecord]] = {}

    by_lane: dict[str, list[ResolvedEdit]] = {}
    for item in resolved:
        by_lane.setdefault(item.lane, []).append(item)

    for lane, items in by_lane.items():
        text = new_lanes[lane]
        # Apply right-to-left so earlier offsets stay valid.
        for item in sorted(items, key=lambda r: r.start, reverse=True):
            if text[item.start : item.end] != item.expected_text:
                raise ApplyTranscriptEditsEngineError(
                    "edit_target_drift",
                    "Exact match drifted before application.",
                )
            text = text[: item.start] + item.replacement_text + text[item.end :]
        new_lanes[lane] = text

        # Recompute post-application offsets for provenance (left-to-right with shifts).
        shift = 0
        for item in sorted(items, key=lambda r: r.start):
            start = item.start + shift
            end = start + len(item.replacement_text)
            applied_by_decision.setdefault(item.decision_id, []).append(
                AppliedEditRecord(
                    lane=item.lane,
                    expected_text=item.expected_text,
                    replacement_text=item.replacement_text,
                    context_before=item.context_before,
                    context_after=item.context_after,
                    start_offset=start,
                    end_offset=end,
                )
            )
            shift += len(item.replacement_text) - (item.end - item.start)

    return new_lanes, applied_by_decision


def _shift_surviving_decisions(
    *,
    existing: list[dict[str, Any]],
    addressed_ids: set[str],
    resolved: list[ResolvedEdit],
) -> list[dict[str, Any]]:
    surviving: list[dict[str, Any]] = []
    for record in existing:
        did = record.get("decision_id")
        if type(did) is not str or did in addressed_ids:
            continue
        updated = dict(record)
        edits_out: list[dict[str, Any]] = []
        for edit in record.get("edits") or []:
            if type(edit) is not dict:
                raise ApplyTranscriptEditsEngineError(
                    "malformed_provenance",
                    "Decision edit records must be objects.",
                )
            lane = edit.get("lane")
            start = edit.get("start_offset")
            end = edit.get("end_offset")
            if type(lane) is not str or type(start) is not int or type(end) is not int:
                raise ApplyTranscriptEditsEngineError(
                    "malformed_provenance",
                    "Decision edit locations must include lane/start_offset/end_offset.",
                )
            shift = 0
            for applied in resolved:
                if applied.lane != lane:
                    continue
                # Applied entirely before this span → shift.
                if applied.end <= start:
                    shift += len(applied.replacement_text) - (applied.end - applied.start)
                elif applied.start < end and applied.end > start:
                    # Should have been caught as foreign overlap.
                    raise ApplyTranscriptEditsEngineError(
                        "overlaps_other_decision_span",
                        f"Edit overlaps current span of decision {did!r}.",
                    )
            edit_copy = dict(edit)
            edit_copy["start_offset"] = start + shift
            edit_copy["end_offset"] = end + shift
            edits_out.append(edit_copy)
        updated["edits"] = edits_out
        surviving.append(updated)
    return surviving


def _build_request_decision_records(
    *,
    request: ValidatedApplyTranscriptEditsRequest,
    base_revision_ref: str,
    applied_by_decision: dict[str, list[AppliedEditRecord]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for decision in request.decisions:
        edits = [
            {
                "lane": e.lane,
                "expected_text": e.expected_text,
                "replacement_text": e.replacement_text,
                "context_before": e.context_before,
                "context_after": e.context_after,
                "start_offset": e.start_offset,
                "end_offset": e.end_offset,
            }
            for e in applied_by_decision.get(decision.decision_id, [])
        ]
        record: dict[str, Any] = {
            "decision_id": decision.decision_id,
            "determination": decision.determination,
            "verification_basis": decision.verification_basis,
            "evidence_refs": list(decision.evidence_refs),
            "base_revision_ref": base_revision_ref,
            "edits": edits,
        }
        if decision.candidate_values is not None:
            record["candidate_values"] = list(decision.candidate_values)
        records.append(record)
    return records


def _stable_dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
