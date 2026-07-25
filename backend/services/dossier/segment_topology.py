"""Read-only mechanical dossier segment/run topology.

Exposes ordered segments and every transcription run binding without choosing a
best/first/consensus run or mutating dossier/association storage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class DossierSegmentTopologyError(Exception):
    """Hard structural refusal for invalid dossier segment topology."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail or "")
        message = self.code if not self.detail else f"{self.code}: {self.detail}"
        super().__init__(message)


@dataclass(frozen=True)
class DossierSegmentRunBinding:
    transcription_id: str
    position: int | None
    association_present: bool


@dataclass(frozen=True)
class DossierSegmentBinding:
    segment_id: str
    position: int
    runs: tuple[DossierSegmentRunBinding, ...]


@dataclass(frozen=True)
class DossierSegmentTopologyDiagnostic:
    code: str
    segment_id: str | None = None
    transcription_id: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class DossierSegmentTopology:
    dossier_id: str
    segments: tuple[DossierSegmentBinding, ...]
    topology_fingerprint: str
    diagnostics: tuple[DossierSegmentTopologyDiagnostic, ...]


@dataclass(frozen=True)
class TopologyRunInput:
    transcription_id: str
    position: int | None = None


@dataclass(frozen=True)
class TopologySegmentInput:
    segment_id: str
    position: int
    runs: tuple[TopologyRunInput, ...]


def build_dossier_segment_topology(
    *,
    dossier_id: str,
    segments: Sequence[TopologySegmentInput],
    association_positions: Mapping[str, int] | None = None,
) -> DossierSegmentTopology:
    """Build a validated read-only topology from explicit segment/run bindings."""
    did = _require_identity_str(dossier_id, field="dossier_id")
    assoc_positions = _normalize_association_positions(association_positions)

    validated_segments = [_validate_segment_input(segment) for segment in segments]
    ordered = sorted(validated_segments, key=lambda s: s.position)

    segment_ids: set[str] = set()
    positions: set[int] = set()
    transcription_owners: dict[str, str] = {}
    diagnostics: list[DossierSegmentTopologyDiagnostic] = []
    out_segments: list[DossierSegmentBinding] = []

    for segment in ordered:
        if segment.segment_id in segment_ids:
            raise DossierSegmentTopologyError("duplicate_segment_id", segment.segment_id)
        segment_ids.add(segment.segment_id)
        if segment.position in positions:
            raise DossierSegmentTopologyError(
                "duplicate_segment_position",
                str(segment.position),
            )
        positions.add(segment.position)

        run_bindings: list[DossierSegmentRunBinding] = []
        run_positions: set[int] = set()
        seen_tids_in_segment: set[str] = set()
        ordered_runs = sorted(
            segment.runs,
            key=lambda r: (
                r.position is None,
                r.position if r.position is not None else 0,
                r.transcription_id,
            ),
        )
        for run in ordered_runs:
            tid = run.transcription_id
            if tid in seen_tids_in_segment:
                raise DossierSegmentTopologyError(
                    "duplicate_transcription_id_in_segment",
                    f"{segment.segment_id}:{tid}",
                )
            seen_tids_in_segment.add(tid)
            if tid in transcription_owners and transcription_owners[tid] != segment.segment_id:
                raise DossierSegmentTopologyError(
                    "transcription_bound_to_multiple_segments",
                    f"{tid}: {transcription_owners[tid]} vs {segment.segment_id}",
                )
            transcription_owners[tid] = segment.segment_id

            run_position = run.position
            if run_position is not None:
                if run_position in run_positions:
                    raise DossierSegmentTopologyError(
                        "duplicate_run_position",
                        f"{segment.segment_id}:{run_position}",
                    )
                run_positions.add(run_position)

            association_present = tid in assoc_positions
            if not association_present:
                diagnostics.append(
                    DossierSegmentTopologyDiagnostic(
                        code="missing_run_association",
                        segment_id=segment.segment_id,
                        transcription_id=tid,
                        detail="Run is declared on a segment but absent from associations.",
                    )
                )
            run_bindings.append(
                DossierSegmentRunBinding(
                    transcription_id=tid,
                    position=run_position,
                    association_present=association_present,
                )
            )

        out_segments.append(
            DossierSegmentBinding(
                segment_id=segment.segment_id,
                position=segment.position,
                runs=tuple(run_bindings),
            )
        )

    for tid, assoc_position in sorted(assoc_positions.items(), key=lambda item: (item[1], item[0])):
        if tid not in transcription_owners:
            diagnostics.append(
                DossierSegmentTopologyDiagnostic(
                    code="unbound_association",
                    transcription_id=tid,
                    detail=f"Association position {assoc_position} is not bound to any dossier segment run.",
                )
            )

    fingerprint = _topology_fingerprint(did, out_segments)
    return DossierSegmentTopology(
        dossier_id=did,
        segments=tuple(out_segments),
        topology_fingerprint=fingerprint,
        diagnostics=tuple(diagnostics),
    )


def load_dossier_segment_topology(dossier_id: str) -> DossierSegmentTopology:
    """Load topology via existing management + association services (read-only)."""
    from services.dossier.association_service import TranscriptionAssociationService
    from services.dossier.management_service import DossierManagementService

    did = _require_identity_str(dossier_id, field="dossier_id")

    dossier = DossierManagementService().get_dossier(did)
    if dossier is None:
        raise DossierSegmentTopologyError("dossier_not_found", did)

    associations = TranscriptionAssociationService().get_dossier_transcriptions(did)
    association_positions = _association_positions_from_entries(associations)

    segment_inputs: list[TopologySegmentInput] = []
    for segment in getattr(dossier, "segments", []) or []:
        runs: list[TopologyRunInput] = []
        for run in getattr(segment, "runs", []) or []:
            tid = getattr(run, "transcription_id", None)
            if tid is None:
                tid = getattr(run, "transcriptionId", None)
            runs.append(
                TopologyRunInput(
                    transcription_id=tid,
                    position=getattr(run, "position", None),
                )
            )
        segment_inputs.append(
            TopologySegmentInput(
                segment_id=getattr(segment, "id", None),
                position=getattr(segment, "position", None),
                runs=tuple(runs),
            )
        )

    return build_dossier_segment_topology(
        dossier_id=did,
        segments=segment_inputs,
        association_positions=association_positions,
    )


def _require_identity_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise DossierSegmentTopologyError(f"invalid_{field}", repr(value))
    text = value.strip()
    if not text:
        raise DossierSegmentTopologyError(f"{field}_required")
    return text


def _require_nonnegative_int(value: Any, *, code: str) -> int:
    if type(value) is not int or value < 0:
        raise DossierSegmentTopologyError(code, repr(value))
    return value


def _require_positive_int(value: Any, *, code: str) -> int:
    if type(value) is not int or value < 1:
        raise DossierSegmentTopologyError(code, repr(value))
    return value


def _validate_segment_input(segment: TopologySegmentInput) -> TopologySegmentInput:
    if not isinstance(segment, TopologySegmentInput):
        raise DossierSegmentTopologyError("invalid_segment_input", repr(segment))
    segment_id = _require_identity_str(segment.segment_id, field="segment_id")
    position = _require_nonnegative_int(
        segment.position,
        code="invalid_segment_position",
    )
    if not isinstance(segment.runs, tuple):
        raise DossierSegmentTopologyError("invalid_segment_runs", repr(segment.runs))
    runs: list[TopologyRunInput] = []
    for run in segment.runs:
        if not isinstance(run, TopologyRunInput):
            raise DossierSegmentTopologyError("invalid_run_input", repr(run))
        tid = _require_identity_str(run.transcription_id, field="transcription_id")
        run_position = run.position
        if run_position is not None:
            run_position = _require_nonnegative_int(
                run_position,
                code="invalid_run_position",
            )
        runs.append(TopologyRunInput(transcription_id=tid, position=run_position))
    return TopologySegmentInput(
        segment_id=segment_id,
        position=position,
        runs=tuple(runs),
    )


def _normalize_association_positions(
    association_positions: Mapping[str, int] | None,
) -> dict[str, int]:
    if association_positions is None:
        return {}
    if not isinstance(association_positions, Mapping):
        raise DossierSegmentTopologyError(
            "invalid_association_positions",
            repr(association_positions),
        )
    out: dict[str, int] = {}
    for tid_raw, pos_raw in association_positions.items():
        tid = _require_identity_str(tid_raw, field="association_transcription_id")
        if tid in out:
            raise DossierSegmentTopologyError("duplicate_association_transcription_id", tid)
        pos = _require_positive_int(pos_raw, code="invalid_association_position")
        out[tid] = pos
    return out


def _association_positions_from_entries(associations: Sequence[Any]) -> dict[str, int]:
    raw: dict[str, int] = {}
    for entry in associations:
        tid = getattr(entry, "transcription_id", None)
        pos = getattr(entry, "position", None)
        if not isinstance(tid, str):
            raise DossierSegmentTopologyError(
                "invalid_association_transcription_id",
                repr(tid),
            )
        tid_norm = _require_identity_str(tid, field="association_transcription_id")
        if tid_norm in raw:
            raise DossierSegmentTopologyError(
                "duplicate_association_transcription_id",
                tid_norm,
            )
        raw[tid_norm] = _require_positive_int(pos, code="invalid_association_position")
    return raw


def _topology_fingerprint(dossier_id: str, segments: Sequence[DossierSegmentBinding]) -> str:
    payload: dict[str, Any] = {
        "dossier_id": dossier_id,
        "segments": [
            {
                "segment_id": segment.segment_id,
                "position": segment.position,
                "runs": [
                    {
                        "transcription_id": run.transcription_id,
                        "position": run.position,
                    }
                    for run in segment.runs
                ],
            }
            for segment in segments
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
