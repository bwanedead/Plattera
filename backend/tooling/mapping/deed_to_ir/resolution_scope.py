"""Public mechanical resolution-scope helpers for deed-to-IR tooling.

Normalize and resolve parcel/scope identifiers from explicitly supported signals.
Deterministic code never invents scope when signals conflict or are absent.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_PARCEL_CANONICAL = re.compile(r"^parcel_(\d+)$", re.IGNORECASE)
_PARCEL_ID_PREFIX = re.compile(r"^parcel_(\d+)(?:_|$)", re.IGNORECASE)
_P_PREFIX = re.compile(r"^p(\d+)_", re.IGNORECASE)
_PARCEL_PROSE = re.compile(r"\bParcel\s+(\d+)\b", re.IGNORECASE)

SCOPE_SIGNALS_CONFLICT_CODE = "dependency_candidate_scope_signals_conflict"


def is_resolution_scope_blocker(item: Mapping[str, Any]) -> bool:
    """True when a resolution item is mechanically treated as a scope blocker."""
    if item.get("blocking") is True:
        return True
    if item.get("no_further_progress") is True:
        return True
    return str(item.get("status") or "").lower() == "blocked"


def normalize_scope_signal(raw: Any) -> str | None:
    """Normalize one supported identifier-like signal to ``parcel_<n>``."""
    text = str(raw or "").strip()
    if not text:
        return None
    for pattern in (_PARCEL_CANONICAL, _PARCEL_ID_PREFIX, _P_PREFIX):
        match = pattern.match(text)
        if not match:
            continue
        number = int(match.group(1))
        if number > 0:
            return f"parcel_{number}"
    return None


def normalize_issue_scope_prose(raw: Any) -> str | None:
    """Bounded prose parse from an issue ``scope`` field only."""
    text = str(raw or "").strip()
    if not text:
        return None
    match = _PARCEL_PROSE.search(text)
    if not match:
        # Also accept already-canonical forms appearing as the whole field.
        return normalize_scope_signal(text)
    number = int(match.group(1))
    if number > 0:
        return f"parcel_{number}"
    return None


def collect_resolution_scope_signals(
    *,
    item: Mapping[str, Any] | None = None,
    issue: Mapping[str, Any] | None = None,
    block_targets: Sequence[str] | None = None,
    identifier_sources: Sequence[str] | None = None,
) -> list[str]:
    """Collect normalized scope signals from explicitly supported sources only.

    Sources:
    - item scalars: ``scope_id``, ``affected_scope``, ``parcel_id``
    - issue scalars: ``scope_id``, ``affected_scope``, ``scope`` (prose allowed)
    - ``blocks`` relation target identifiers
    - established identifier forms in item/parent/relation ids
    """
    signals: list[str] = []

    def _add(normalized: str | None) -> None:
        if normalized and normalized not in signals:
            signals.append(normalized)

    if isinstance(item, Mapping):
        for key in ("scope_id", "affected_scope", "parcel_id"):
            _add(normalize_scope_signal(item.get(key)))

    if isinstance(issue, Mapping):
        for key in ("scope_id", "affected_scope"):
            _add(normalize_scope_signal(issue.get(key)))
        _add(normalize_issue_scope_prose(issue.get("scope")))

    for target in block_targets or []:
        _add(normalize_scope_signal(target))

    for source in identifier_sources or []:
        _add(normalize_scope_signal(source))

    return signals


def resolve_unambiguous_scope_id(
    signals: Sequence[str] | None,
) -> dict[str, Any]:
    """Resolve scope when all normalized signals agree; otherwise omit.

    Returns:
      ``scope_id`` — canonical id when unambiguous, else ``None``
      ``observed_scope_ids`` — distinct normalized signals (sorted)
      ``conflict`` — True when multiple distinct normalized signals exist
    """
    observed = sorted(
        {
            str(item).strip()
            for item in (signals or [])
            if str(item or "").strip()
        }
    )
    if not observed:
        return {"scope_id": None, "observed_scope_ids": [], "conflict": False}
    if len(observed) == 1:
        return {
            "scope_id": observed[0],
            "observed_scope_ids": observed,
            "conflict": False,
        }
    return {
        "scope_id": None,
        "observed_scope_ids": observed,
        "conflict": True,
    }


def infer_scope_id_from_identifiers(*sources: str) -> str | None:
    """First unambiguous identifier-form match among ordered sources (operands)."""
    for source in sources:
        normalized = normalize_scope_signal(source)
        if normalized:
            return normalized
    return None
