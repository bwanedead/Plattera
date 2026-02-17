"""Deterministic no-progress detection and per-iteration scoring helpers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Optional, Sequence

from .models import StopReason
from .policies import KernelPolicy
from .run_artifact import ArtifactRef


@dataclass(frozen=True)
class GapSignal:
    """Policy-scored gap input used for deterministic signatures."""

    gap_code: str
    base_score: float
    metadata: Optional[Mapping[str, object]] = None


@dataclass(frozen=True)
class NoProgressStatus:
    """Current no-progress detection status for repair cycles."""

    detected: bool
    stop_reason: Optional[StopReason]
    reason_code: Optional[str]
    stagnant_repair_cycles: int
    iteration_fingerprint: str


def compute_gap_signature(gaps: Sequence[GapSignal], policy: KernelPolicy) -> str:
    """Compute a deterministic hash of policy-scored gaps for one iteration."""
    scored = []
    for gap in gaps:
        weighted_score = policy.score_gap(
            gap_code=gap.gap_code,
            base_score=gap.base_score,
            metadata=gap.metadata,
        )
        scored.append(
            {
                "gap_code": gap.gap_code,
                "weighted_score": round(float(weighted_score), 8),
            }
        )
    canonical = json.dumps(
        sorted(scored, key=lambda item: (item["gap_code"], item["weighted_score"])),
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def compute_artifact_digests(artifact_refs: Mapping[str, ArtifactRef | str | None]) -> dict[str, str]:
    """Compute deterministic digests for artifact refs observed in one iteration."""
    digests: dict[str, str] = {}
    for name, ref in sorted(artifact_refs.items(), key=lambda item: item[0]):
        normalized = _normalize_artifact_ref(ref)
        digests[name] = sha256(normalized.encode("utf-8")).hexdigest()
    return digests


def build_iteration_fingerprint(gap_signature: str, artifact_digests: Mapping[str, str]) -> str:
    """Combine per-iteration gap and artifact signals into one deterministic fingerprint."""
    canonical = json.dumps(
        {
            "artifact_digests": {key: artifact_digests[key] for key in sorted(artifact_digests)},
            "gap_signature": gap_signature,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


class NoProgressDetector:
    """Tracks repeated repair fingerprints and emits deterministic no-progress stop signals."""

    def __init__(self, max_stagnant_repair_cycles: int) -> None:
        if max_stagnant_repair_cycles < 1:
            raise ValueError("max_stagnant_repair_cycles must be >= 1")
        self._max_stagnant_repair_cycles = max_stagnant_repair_cycles
        self._last_repair_fingerprint: Optional[str] = None
        self._stagnant_repair_cycles = 0

    def evaluate_repair_cycle(
        self,
        *,
        gap_signature: str,
        artifact_digests: Mapping[str, str],
    ) -> NoProgressStatus:
        iteration_fingerprint = build_iteration_fingerprint(gap_signature, artifact_digests)

        if self._last_repair_fingerprint is None or self._last_repair_fingerprint != iteration_fingerprint:
            self._last_repair_fingerprint = iteration_fingerprint
            self._stagnant_repair_cycles = 0
            return NoProgressStatus(
                detected=False,
                stop_reason=None,
                reason_code=None,
                stagnant_repair_cycles=self._stagnant_repair_cycles,
                iteration_fingerprint=iteration_fingerprint,
            )

        self._stagnant_repair_cycles += 1
        detected = self._stagnant_repair_cycles >= self._max_stagnant_repair_cycles
        return NoProgressStatus(
            detected=detected,
            stop_reason=StopReason.NO_PROGRESS if detected else None,
            reason_code="no_progress_repair_cycles_exhausted" if detected else None,
            stagnant_repair_cycles=self._stagnant_repair_cycles,
            iteration_fingerprint=iteration_fingerprint,
        )


def _normalize_artifact_ref(ref: ArtifactRef | str | None) -> str:
    if ref is None:
        return "<missing>"
    if isinstance(ref, ArtifactRef):
        payload = ref.model_dump(mode="json", exclude_none=True)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return str(ref)
