"""Discovery row lifecycle hints (Phase 16, transcript-edit native only).

Not harness contract. Complements ``discovery_meta.posture`` with a bounded
``lifecycle_hint`` for stale / low-touch rows so they do not dominate focus forever.
"""
from __future__ import annotations

import time
from typing import Any

# Match ``transcript_edit_ledger_discovery_prep`` (avoid import cycles at module load).
_DISCOVERY_PROVENANCE = "transcript_edit.discovery.v1"
_DISCOVERY_PREFIX = "discovery:"

_UNRESOLVED = frozenset({"unknown", "candidate_found", "disputed", "accepted_with_risk"})

# Unresolved discovery with zero evidence touches older than this → ``cooling``.
_DEFAULT_COOLING_AGE_SECONDS = 604800  # 7 days

# Bounded focus demotion when ``lifecycle_hint == \"cooling\"`` (added to effective priority).
_LIFECYCLE_COOLING_PRIORITY_PENALTY = 12


def discovery_lifecycle_priority_penalty(discovery_meta: dict[str, Any] | None) -> int:
    """Higher → less urgent in ascending focus sort (larger effective_focus_priority)."""
    if not isinstance(discovery_meta, dict):
        return 0
    h = str(discovery_meta.get("lifecycle_hint") or "").strip().lower()
    if h == "cooling":
        return _LIFECYCLE_COOLING_PRIORITY_PENALTY
    return 0


def _is_discovery_row(item: dict[str, Any]) -> bool:
    k = str(item.get("key") or "")
    prov = str(item.get("provenance") or "").strip()
    return k.startswith(_DISCOVERY_PREFIX) or prov == _DISCOVERY_PROVENANCE


def refresh_discovery_lifecycle_hints(
    item: dict[str, Any],
    *,
    now_epoch: int,
    cooling_age_seconds: int = _DEFAULT_COOLING_AGE_SECONDS,
) -> None:
    """Set ``discovery_meta.lifecycle_hint`` for unresolved discovery rows (native only)."""
    if not isinstance(item, dict) or not _is_discovery_row(item):
        return
    st = str(item.get("state") or "").strip().lower()
    dm = item.get("discovery_meta") if isinstance(item.get("discovery_meta"), dict) else {}
    dm = dict(dm)
    if st not in _UNRESOLVED:
        dm.pop("lifecycle_hint", None)
        item["discovery_meta"] = dm
        return
    touch = int(dm.get("evidence_touch_count") or 0)
    last = int(dm.get("last_merged_epoch") or 0)
    if touch == 0 and last > 0 and cooling_age_seconds > 0 and (now_epoch - last) >= cooling_age_seconds:
        dm["lifecycle_hint"] = "cooling"
    else:
        dm["lifecycle_hint"] = "active"
    item["discovery_meta"] = dm


def apply_discovery_lifecycle_hygiene(
    ledger: dict[str, Any] | None,
    *,
    now_epoch: int | None = None,
    cooling_age_seconds: int = _DEFAULT_COOLING_AGE_SECONDS,
) -> dict[str, Any] | None:
    """Recompute lifecycle hints for every native row (idempotent)."""
    if not isinstance(ledger, dict):
        return ledger
    now = int(now_epoch if now_epoch is not None else time.time())
    items = ledger.get("items")
    if not isinstance(items, list):
        return ledger
    for it in items:
        if isinstance(it, dict):
            refresh_discovery_lifecycle_hints(it, now_epoch=now, cooling_age_seconds=cooling_age_seconds)
    return ledger
