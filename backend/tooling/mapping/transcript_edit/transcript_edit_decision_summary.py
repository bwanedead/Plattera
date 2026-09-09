"""Compact mechanical projection of current transcript_edit_decisions for handoff.

Reports authored facts only. Does not rank candidates, infer mapping blocks, or
mutate revision snapshots. Whole-item omission under pressure — never truncated
substring pretending to be a complete value.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    DETERMINATION_EARNED,
    DETERMINATION_PROVISIONAL,
    MAX_DECISION_SUMMARY_BASIS_CHARS,
    MAX_DECISION_SUMMARY_CANDIDATES,
    MAX_DECISION_SUMMARY_EVIDENCE_REFS,
    MAX_DECISION_SUMMARY_REPLACEMENT_CHARS,
    MAX_DECISION_SUMMARY_REPLACEMENTS,
    MAX_DECISION_SUMMARY_ROWS,
    MAX_DECISION_SUMMARY_SERIALIZED_CHARS,
    TRANSCRIPT_EDIT_DECISIONS_FIELD,
    TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION,
    TRANSCRIPT_EDIT_LANES,
)
from tooling.mapping.transcript_edit.transcript_edit_decisions_validate import (
    PersistedProvenanceError,
    validate_persisted_transcript_edit_decisions,
)


class TranscriptEditDecisionProjectionError(ValueError):
    """Malformed managed provenance cannot be projected for handoff."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = str(reason_code)
        self.detail = str(detail or "")
        message = self.reason_code if not self.detail else f"{self.reason_code}: {self.detail}"
        super().__init__(message)


def project_transcript_edit_decision_summary(
    *,
    sources: Sequence[Mapping[str, Any]],
    max_rows: int = MAX_DECISION_SUMMARY_ROWS,
    max_serialized_chars: int = MAX_DECISION_SUMMARY_SERIALIZED_CHARS,
) -> dict[str, Any]:
    """Project one or more payload-owned decision ledgers into a compact summary.

    Each source mapping may include:
      - ``payload`` (required object carrying ``transcript_edit_decisions``)
      - ``segment_id`` / ``transcription_id`` (optional identity for dossier rows)

    Absent provenance on a source contributes zero decisions (not an error).
    Present malformed provenance raises ``TranscriptEditDecisionProjectionError``.
    """
    if type(max_rows) is not int or isinstance(max_rows, bool) or max_rows < 0:
        raise TranscriptEditDecisionProjectionError(
            "invalid_projection_bound",
            "max_rows must be a non-negative int.",
        )
    if (
        type(max_serialized_chars) is not int
        or isinstance(max_serialized_chars, bool)
        or max_serialized_chars < 0
    ):
        raise TranscriptEditDecisionProjectionError(
            "invalid_projection_bound",
            "max_serialized_chars must be a non-negative int.",
        )

    collected: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        payload = source.get("payload")
        if not isinstance(payload, Mapping):
            continue
        payload_obj = dict(payload)
        try:
            decisions = validate_persisted_transcript_edit_decisions(payload=payload_obj)
        except PersistedProvenanceError as exc:
            raise TranscriptEditDecisionProjectionError(exc.reason_code, exc.detail) from exc
        if decisions is None:
            continue
        segment_id = _opt_str(source.get("segment_id"))
        transcription_id = _opt_str(source.get("transcription_id"))
        for record in decisions:
            row = _compact_row(
                record,
                segment_id=segment_id,
                transcription_id=transcription_id,
            )
            if row is not None:
                collected.append(row)
            # Rows that cannot be compacted honestly (e.g. oversize basis) still
            # count as source decisions for omission accounting via a placeholder.
            else:
                collected.append(
                    {
                        "decision_id": record.get("decision_id"),
                        "determination": record.get("determination"),
                        "_unprojectable": True,
                    }
                )

    projectable = [row for row in collected if not row.get("_unprojectable")]
    unprojectable = [row for row in collected if row.get("_unprojectable")]
    total = len(collected)
    provisional_total = sum(
        1 for row in collected if row.get("determination") == DETERMINATION_PROVISIONAL
    )
    earned_total = sum(
        1 for row in collected if row.get("determination") == DETERMINATION_EARNED
    )

    provisional_rows = [
        row for row in projectable if row.get("determination") == DETERMINATION_PROVISIONAL
    ]
    earned_rows = [
        row for row in projectable if row.get("determination") == DETERMINATION_EARNED
    ]
    ordered = provisional_rows + earned_rows

    # Mandatory counts-only envelope must fit before any row retention.
    empty_envelope = _summary_envelope(
        decisions=[],
        source_total=total,
        retained_count=0,
        omitted_count=total,
        source_provisional=provisional_total,
        source_earned=earned_total,
    )
    if _serialized_len(empty_envelope) > max_serialized_chars:
        raise TranscriptEditDecisionProjectionError(
            "projection_bound_too_small",
            "max_serialized_chars is smaller than the mandatory empty decision-summary envelope.",
        )

    retained: list[dict[str, Any]] = []
    omitted = len(unprojectable)
    for row in ordered:
        if len(retained) >= max_rows:
            omitted += 1
            continue
        trial = list(retained) + [row]
        summary_trial = _summary_envelope(
            decisions=trial,
            source_total=total,
            retained_count=len(trial),
            omitted_count=total - len(trial),
            source_provisional=provisional_total,
            source_earned=earned_total,
        )
        if _serialized_len(summary_trial) > max_serialized_chars:
            omitted += 1
            continue
        retained.append(row)

    summary = _summary_envelope(
        decisions=retained,
        source_total=total,
        retained_count=len(retained),
        omitted_count=omitted,
        source_provisional=provisional_total,
        source_earned=earned_total,
    )
    # Defensive: never return a result exceeding the caller bound.
    if _serialized_len(summary) > max_serialized_chars:
        raise TranscriptEditDecisionProjectionError(
            "projection_bound_too_small",
            "Compact decision summary exceeds max_serialized_chars after fitting.",
        )
    assert summary["counts"]["source"] == (
        summary["counts"]["retained"] + summary["counts"]["omitted"]
    )
    return summary


def project_decision_summary_from_payload(
    payload: Mapping[str, Any] | None,
    *,
    segment_id: str | None = None,
    transcription_id: str | None = None,
    max_rows: int = MAX_DECISION_SUMMARY_ROWS,
    max_serialized_chars: int = MAX_DECISION_SUMMARY_SERIALIZED_CHARS,
) -> dict[str, Any]:
    """Project a single revision payload's current decision ledger."""
    source: dict[str, Any] = {"payload": dict(payload or {})}
    if segment_id:
        source["segment_id"] = segment_id
    if transcription_id:
        source["transcription_id"] = transcription_id
    return project_transcript_edit_decision_summary(
        sources=[source],
        max_rows=max_rows,
        max_serialized_chars=max_serialized_chars,
    )


def _summary_envelope(
    *,
    decisions: list[dict[str, Any]],
    source_total: int,
    retained_count: int,
    omitted_count: int,
    source_provisional: int,
    source_earned: int,
) -> dict[str, Any]:
    return {
        "schema_version": TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION,
        "decisions": list(decisions),
        "counts": {
            "source": source_total,
            "retained": retained_count,
            "provisional": sum(
                1 for row in decisions if row.get("determination") == DETERMINATION_PROVISIONAL
            ),
            "earned": sum(
                1 for row in decisions if row.get("determination") == DETERMINATION_EARNED
            ),
            "omitted": omitted_count,
            "source_provisional": source_provisional,
            "source_earned": source_earned,
        },
    }


def minimum_decision_summary_serialized_chars(
    *,
    source_total: int = 0,
    source_provisional: int = 0,
    source_earned: int = 0,
) -> int:
    """Serialized size of the mandatory empty (counts-only) envelope for given totals."""
    return _serialized_len(
        _summary_envelope(
            decisions=[],
            source_total=source_total,
            retained_count=0,
            omitted_count=source_total,
            source_provisional=source_provisional,
            source_earned=source_earned,
        )
    )


def _serialized_len(summary: Mapping[str, Any]) -> int:
    return len(
        json.dumps(
            summary,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )


def _compact_row(
    record: Mapping[str, Any],
    *,
    segment_id: str | None,
    transcription_id: str | None,
) -> dict[str, Any] | None:
    """Build one compact row, or None when a required whole value cannot fit."""
    determination = record.get("determination")
    reasons = record.get("uncertainty_reasons")
    if type(reasons) is not list:
        reasons = []
    candidates = record.get("candidate_values")
    evidence = record.get("evidence_refs")
    edits = record.get("edits") if isinstance(record.get("edits"), list) else []

    replacements_out: list[dict[str, str]] = []
    replacement_omitted = 0
    lanes: list[str] = []
    for edit in edits:
        if not isinstance(edit, Mapping):
            continue
        lane = edit.get("lane")
        if type(lane) is not str or lane not in TRANSCRIPT_EDIT_LANES:
            continue
        if lane not in lanes:
            lanes.append(lane)
        replacement = edit.get("replacement_text")
        if type(replacement) is not str:
            continue
        if len(replacement) > MAX_DECISION_SUMMARY_REPLACEMENT_CHARS:
            replacement_omitted += 1
            continue
        if len(replacements_out) >= MAX_DECISION_SUMMARY_REPLACEMENTS:
            replacement_omitted += 1
            continue
        replacements_out.append({"lane": lane, "replacement_text": replacement})

    basis = record.get("verification_basis")
    basis_out: str | None = None
    if type(basis) is str and basis.strip():
        stripped = basis.strip()
        if len(stripped) > MAX_DECISION_SUMMARY_BASIS_CHARS:
            return None
        basis_out = stripped

    candidates_out: list[str] = []
    candidates_omitted = 0
    if isinstance(candidates, list):
        for value in candidates:
            if type(value) is not str or not value:
                continue
            if len(value) > MAX_DECISION_SUMMARY_REPLACEMENT_CHARS:
                candidates_omitted += 1
                continue
            if len(candidates_out) >= MAX_DECISION_SUMMARY_CANDIDATES:
                candidates_omitted += 1
                continue
            candidates_out.append(value)

    evidence_out: list[str] = []
    evidence_omitted = 0
    if isinstance(evidence, list):
        for ref in evidence:
            if type(ref) is not str or not ref.strip():
                continue
            text = ref.strip()
            if len(text) > MAX_DECISION_SUMMARY_REPLACEMENT_CHARS:
                evidence_omitted += 1
                continue
            if len(evidence_out) >= MAX_DECISION_SUMMARY_EVIDENCE_REFS:
                evidence_omitted += 1
                continue
            evidence_out.append(text)

    row: dict[str, Any] = {
        "decision_id": record.get("decision_id"),
        "determination": determination,
        "uncertainty_reasons": [r for r in reasons if type(r) is str],
        "affected_lanes": lanes,
        "replacements": replacements_out,
    }
    if candidates_out:
        row["candidate_values"] = candidates_out
    if candidates_omitted:
        row["candidate_values_omitted_count"] = candidates_omitted
    if evidence_out:
        row["evidence_refs"] = evidence_out
    if evidence_omitted:
        row["evidence_refs_omitted_count"] = evidence_omitted
    if replacement_omitted:
        row["replacement_edits_omitted_count"] = replacement_omitted
    if basis_out is not None:
        row["verification_basis"] = basis_out
    if segment_id:
        row["segment_id"] = segment_id
    if transcription_id:
        row["transcription_id"] = transcription_id
    return row


def provenance_block_present(payload: Mapping[str, Any] | None) -> bool:
    return isinstance(payload, Mapping) and TRANSCRIPT_EDIT_DECISIONS_FIELD in payload


def _opt_str(value: Any) -> str | None:
    if type(value) is not str:
        return None
    text = value.strip()
    return text or None
