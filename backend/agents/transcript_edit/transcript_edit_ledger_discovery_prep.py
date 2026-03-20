"""Discovery-first native ledger items for transcript-edit (bounded merge).

**Spec (transcript-edit discovery contribution)**

A *discovered* row is a native checklist ``items[]`` entry with:

- ``key``: stable id ``discovery:<kind>:<fingerprint>`` (never collides with seed keys like ``range``).
- ``provenance``: :data:`DISCOVERY_ITEM_PROVENANCE` (vs seed ``deterministic``, harness emergent rows).
- ``discovery_meta``: ``{ "kind", "finding_id", "version", "signal_fp", "posture", "evidence_touch_count" }`` —
  audit/diagnostic lineage + **posture** (``fresh`` → ``touched`` → ``stable`` / ``escalated``) — not harness ontology.
- Same closure/scope fields as other native rows so projection → ``te:ledger:*`` and closure/read paths work.

This differs from:

- **Bootstrap seed** rows — pre-authored default checklist slots; ``provenance`` is typically ``deterministic``.
- **Harness-emergent** rows — live on ``harness_emergent_board_items`` and merge in the unified envelope at read time.
- **Notes/context** — not durable checklist rows; do not use this merge for free-form blurbs.

Do **not** import ``transcript_edit_default_checklist_seed`` here.
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Any

from .decision_ledger_scope import _ensure_ledger_shape
from .decision_ledger_state import reconcile_ledger_derived_fields

DISCOVERY_ITEM_PROVENANCE = "transcript_edit.discovery.v1"
DISCOVERY_KEY_PREFIX = "discovery:"

# Caps — anti-sprawl: discovery must not become unbounded append-only noise.
_MAX_DISCOVERY_ROWS_TOTAL = 24
_MAX_NEW_ROWS_PER_MERGE = 4
_MAX_INFER_PER_AUDIT = 2

# Per-kind ceilings (existing + new) so one class cannot crowd out others.
_MAX_DISCOVERY_PER_KIND: dict[str, int] = {
    "contradiction_cluster": 8,
    "dependency": 6,
    "source_integrity": 5,
    "scope_orientation": 5,
}

# Minimum message length so trivial findings stay in notes/support-state, not durable rows.
_MIN_MESSAGE_CHARS = 24

_SKIP_FINDING_SEVERITIES = frozenset({"info", "low", "debug"})

# Focus sort: subtract from effective priority so mature discovery competes ahead of fresh rows (bounded).
DISCOVERY_MATURITY_PRIORITY_BONUS: dict[str, int] = {
    "fresh": 0,
    "touched": 1,
    "escalated": 2,
    "stable": 3,
}

# Demote weak bootstrap seed rows (no evidence, no dispute) so they do not crowd out discovery work.
WEAK_SEED_SCAFFOLDING_PRIORITY_PENALTY = 40

_DISCOVERY_KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("dependency", re.compile(r"\b(depended|dependency|depends on|depends|prerequisite)\b", re.I)),
    # Match stems so "contradiction" / "conflicting" resolve (avoid `\bcontradict\b` missing "contradiction").
    ("contradiction_cluster", re.compile(r"\b(contradict|conflict|disagree|mismatch)", re.I)),
    ("source_integrity", re.compile(r"\b(truncat|integrity|ocr|illegible|scan)\b", re.I)),
    ("scope_orientation", re.compile(r"\b(scope|outside target|orientation|boundary)\b", re.I)),
]


def _normalize_for_dedupe(message: str) -> str:
    return " ".join(str(message).lower().split())[:400]


def discovery_maturity_priority_bonus(discovery_meta: dict[str, Any] | None) -> int:
    """Higher bonus → lower effective priority number in ascending focus sort (more central work)."""
    if not isinstance(discovery_meta, dict):
        return 0
    p = str(discovery_meta.get("posture") or "fresh").strip().lower()
    return int(DISCOVERY_MATURITY_PRIORITY_BONUS.get(p, 0))


def is_weak_seed_scaffolding_row(
    *,
    item: dict[str, Any],
    contradiction_rank: int,
) -> bool:
    """True when a bootstrap checklist row is an idle placeholder (Phase 13 seed demotion)."""
    key = str(item.get("key") or "")
    if key.startswith(DISCOVERY_KEY_PREFIX):
        return False
    prov = str(item.get("provenance") or "").strip().lower()
    if prov == DISCOVERY_ITEM_PROVENANCE:
        return False
    if prov not in {"", "deterministic"}:
        return False
    state = str(item.get("state") or "").strip().lower()
    if state == "disputed":
        return False
    if contradiction_rank != 0:
        return False
    evc = len([x for x in list(item.get("evidence_refs") or []) if str(x).strip()])
    if evc > 0:
        return False
    alts = [str(v).strip() for v in list(item.get("alternatives") or []) if str(v).strip()]
    if len(alts) > 1:
        return False
    return True


def refresh_discovery_posture_fields(item: dict[str, Any]) -> None:
    """Recompute ``discovery_meta.posture`` from evidence touches and closure shape (native only)."""
    if not isinstance(item, dict):
        return
    prov = str(item.get("provenance") or "").strip()
    key = str(item.get("key") or "")
    if prov != DISCOVERY_ITEM_PROVENANCE and not key.startswith(DISCOVERY_KEY_PREFIX):
        return
    dm = item.get("discovery_meta")
    if not isinstance(dm, dict):
        return
    touch = int(dm.get("evidence_touch_count") or 0)
    kind = str(dm.get("kind") or "")
    state = str(item.get("state") or "").strip().lower()
    cr = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
    br = str(cr.get("block_reason") or "").strip().lower()
    if state == "disputed" and ("contradiction" in kind or br == "contradiction"):
        dm["posture"] = "escalated"
    elif touch >= 4:
        dm["posture"] = "stable"
    elif touch >= 2:
        dm["posture"] = "touched"
    else:
        dm.setdefault("posture", "fresh")


def signal_fingerprint(*, kind: str, message: str) -> str:
    """Stable fingerprint for semantic de-dupe (same kind + same normalized message text)."""
    n = _normalize_for_dedupe(message)
    return hashlib.sha256(f"{kind}|{n}".encode("utf-8")).hexdigest()[:12]


def discovery_fingerprint(*, kind: str, finding_id: str, message: str) -> str:
    """Stable short fingerprint for key suffix (deterministic across runs for same inputs)."""
    base = f"{kind}|{finding_id}|{message[:200]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]


def _append_unique_evidence(item: dict[str, Any], ref: str, *, cap: int = 8) -> None:
    refs = list(item.get("evidence_refs") or [])
    if ref and ref not in refs:
        refs.append(ref)
    item["evidence_refs"] = refs[-cap:]


def _discovery_kind_count(items: list[Any], kind: str) -> int:
    n = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        dm = it.get("discovery_meta") if isinstance(it.get("discovery_meta"), dict) else {}
        if str(dm.get("kind") or "") == kind:
            n += 1
    return n


def _existing_signal_index(items: list[Any]) -> dict[str, str]:
    """Map signal_fp -> native key for near-duplicate merges."""
    out: dict[str, str] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        k = str(it.get("key") or "").strip()
        if not k.startswith(DISCOVERY_KEY_PREFIX):
            continue
        dm = it.get("discovery_meta") if isinstance(it.get("discovery_meta"), dict) else {}
        fp = str(dm.get("signal_fp") or "").strip()
        if fp:
            out.setdefault(fp, k)
    return out


def _native_row_for_discovery(
    *,
    kind: str,
    fingerprint: str,
    finding_id: str,
    message_excerpt: str,
) -> dict[str, Any]:
    key = f"{DISCOVERY_KEY_PREFIX}{kind}:{fingerprint}"
    excerpt = str(message_excerpt or "").strip()[:280]
    sig_fp = signal_fingerprint(kind=kind, message=excerpt)
    block_reason = "contradiction" if "contradiction" in kind else "dependency" if kind == "dependency" else "ambiguity"
    layer = "layer3_dependency" if kind == "dependency" else "layer1_canonical_recovery"
    label = f"Discovered {kind.replace('_', ' ')} ({finding_id or 'audit'})"[:240]
    now = int(time.time())
    return {
        "key": key,
        "label": label,
        "state": "unknown",
        "selected_value": None,
        "alternatives": [],
        "confidence": None,
        "blocking": True,
        "evidence_refs": [f"finding:{finding_id}"] if finding_id else [],
        "user_override_state": "none",
        "layer_tag": layer,
        "operational_impact": "mapping_blocking",
        "provenance": DISCOVERY_ITEM_PROVENANCE,
        "verification_required": True,
        "scope_id": "target_scope",
        "scope_label": "Target scope",
        "scope_priority": 42,
        "in_target_scope": True,
        "scope_proof": [],
        "closure_requirement": {
            "mapping_blocking": True,
            "scope_status": "in_target",
            "block_reason": block_reason,
            "required_information": excerpt or f"Resolve discovered {kind} from audit evidence.",
            "minimal_user_action": "Review audit finding and integrate supporting evidence.",
        },
        "discovery_meta": {
            "kind": kind,
            "finding_id": finding_id,
            "version": 1,
            "signal_fp": sig_fp,
            "last_merged_epoch": now,
            "posture": "fresh",
            "evidence_touch_count": 0,
            "lifecycle_hint": "active",
        },
    }


def _discovery_row_count(items: list[Any]) -> int:
    n = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        k = str(it.get("key") or "")
        if k.startswith(DISCOVERY_KEY_PREFIX) or str(it.get("provenance") or "") == DISCOVERY_ITEM_PROVENANCE:
            n += 1
    return n


def _init_merge_stats(merge_stats: dict[str, Any] | None) -> dict[str, Any]:
    if merge_stats is None:
        return {}
    merge_stats.clear()
    merge_stats.update(
        {
            "schema_version": "discovery_merge_stats.v1",
            "added_keys": [],
            "evidence_only_keys": [],
            "signal_merged_into_keys": [],
            "rejected_kind_cap": 0,
            "rejected_near_duplicate_signal": 0,
            "rejected_low_signal": 0,
            "rejected_severity": 0,
            "skipped_total_cap": False,
        }
    )
    return merge_stats


def merge_discovered_native_items(
    ledger: dict[str, Any] | None,
    contributions: list[dict[str, Any]] | None,
    *,
    max_additions: int = _MAX_NEW_ROWS_PER_MERGE,
    merge_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge validated discovery rows into the native store (mutation). Idempotent by ``key``.

    When ``merge_stats`` is provided, it is cleared and filled with bounded outcomes for continuity/logging.

    Returns the same ledger dict (mutated in place and reconciled).
    """
    _init_merge_stats(merge_stats)
    if not contributions:
        return ledger if isinstance(ledger, dict) else {}
    working = _ensure_ledger_shape(ledger)
    items = working.get("items")
    if not isinstance(items, list):
        items = []
        working["items"] = items

    by_key: dict[str, dict[str, Any]] = {
        str(it.get("key")): it for it in items if isinstance(it, dict) and str(it.get("key") or "").strip()
    }
    signal_to_key = _existing_signal_index(items)
    current_discovery = _discovery_row_count(items)
    added = 0
    now = int(time.time())
    for raw in contributions:
        if not isinstance(raw, dict):
            continue
        if added >= max_additions:
            break
        if current_discovery >= _MAX_DISCOVERY_ROWS_TOTAL:
            if merge_stats is not None:
                merge_stats["skipped_total_cap"] = True
            break
        key = str(raw.get("key") or "").strip()
        if not key.startswith(DISCOVERY_KEY_PREFIX):
            continue
        if str(raw.get("provenance") or "") != DISCOVERY_ITEM_PROVENANCE:
            continue
        dm_in = raw.get("discovery_meta") if isinstance(raw.get("discovery_meta"), dict) else {}
        kind = str(dm_in.get("kind") or "").strip()
        sig_fp = str(dm_in.get("signal_fp") or "").strip()
        if sig_fp and sig_fp in signal_to_key and signal_to_key[sig_fp] != key:
            # Same semantic signal as an existing row — merge evidence into canonical row, do not add.
            canon = by_key.get(signal_to_key[sig_fp])
            if isinstance(canon, dict):
                for ref in list(raw.get("evidence_refs") or [])[:8]:
                    if isinstance(ref, str) and ref.strip():
                        _append_unique_evidence(canon, ref.strip())
                cdm = canon.get("discovery_meta") if isinstance(canon.get("discovery_meta"), dict) else {}
                cdm = dict(cdm)
                cdm["last_merged_epoch"] = now
                cdm["evidence_touch_count"] = int(cdm.get("evidence_touch_count") or 0) + 1
                canon["discovery_meta"] = cdm
                refresh_discovery_posture_fields(canon)
                if merge_stats is not None:
                    merge_stats["rejected_near_duplicate_signal"] = int(
                        merge_stats["rejected_near_duplicate_signal"]
                    ) + 1
                    merge_stats["signal_merged_into_keys"].append(signal_to_key[sig_fp])
            continue
        if kind in _MAX_DISCOVERY_PER_KIND:
            cap_k = _MAX_DISCOVERY_PER_KIND[kind]
            if _discovery_kind_count(items, kind) >= cap_k and key not in by_key:
                if merge_stats is not None:
                    merge_stats["rejected_kind_cap"] = int(merge_stats["rejected_kind_cap"]) + 1
                continue
        if key in by_key:
            existing = by_key[key]
            for ref in list(raw.get("evidence_refs") or [])[:8]:
                if isinstance(ref, str) and ref.strip():
                    _append_unique_evidence(existing, ref.strip())
            edm = existing.get("discovery_meta") if isinstance(existing.get("discovery_meta"), dict) else {}
            edm = dict(edm)
            edm["last_merged_epoch"] = now
            edm["evidence_touch_count"] = int(edm.get("evidence_touch_count") or 0) + 1
            existing["discovery_meta"] = edm
            refresh_discovery_posture_fields(existing)
            if merge_stats is not None:
                merge_stats["evidence_only_keys"].append(key)
            continue
        by_key[key] = raw
        edm = raw.get("discovery_meta") if isinstance(raw.get("discovery_meta"), dict) else {}
        edm = dict(edm)
        edm["last_merged_epoch"] = now
        raw["discovery_meta"] = edm
        refresh_discovery_posture_fields(raw)
        if sig_fp:
            signal_to_key[sig_fp] = key
        items.append(raw)
        if merge_stats is not None:
            merge_stats["added_keys"].append(key)
        added += 1
        current_discovery += 1

    for it in items:
        if isinstance(it, dict):
            refresh_discovery_posture_fields(it)

    return reconcile_ledger_derived_fields(working)


def infer_discovery_items_from_audit_findings(
    findings: list[dict[str, Any]] | None,
    *,
    max_items: int = _MAX_INFER_PER_AUDIT,
    existing_items: list[dict[str, Any]] | None = None,
    infer_stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Heuristic, bounded inference of discovery rows from validator findings (not full NLP).

    Produces 0–*max_items* contributions per audit pass. Intentionally conservative to limit sprawl.
    """
    out: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    seen_signal: set[str] = set()
    existing = [x for x in (existing_items or []) if isinstance(x, dict)]
    sig_index = _existing_signal_index(existing)
    for fp in sig_index:
        seen_signal.add(fp)

    if infer_stats is not None:
        infer_stats.clear()
        infer_stats.update({"rejected_low_signal": 0, "rejected_severity": 0, "rejected_kind_cap": 0})

    for f in findings or []:
        if len(out) >= max_items:
            break
        if not isinstance(f, dict):
            continue
        sev = str(f.get("severity") or "").strip().lower()
        if sev in _SKIP_FINDING_SEVERITIES:
            if infer_stats is not None:
                infer_stats["rejected_severity"] = int(infer_stats.get("rejected_severity") or 0) + 1
            continue
        fid = str(f.get("finding_id") or f.get("id") or "").strip()
        msg = str(f.get("message") or "")
        msg_trim = str(msg).strip()
        if len(msg_trim) < _MIN_MESSAGE_CHARS:
            if infer_stats is not None:
                infer_stats["rejected_low_signal"] = int(infer_stats.get("rejected_low_signal") or 0) + 1
            continue
        kind: str | None = None
        for knd, pat in _DISCOVERY_KIND_PATTERNS:
            if pat.search(msg):
                kind = knd
                break
        if kind is None:
            continue
        cap_k = _MAX_DISCOVERY_PER_KIND.get(kind, 999)
        if _discovery_kind_count(existing + out, kind) >= cap_k:
            if infer_stats is not None:
                infer_stats["rejected_kind_cap"] = int(infer_stats.get("rejected_kind_cap") or 0) + 1
            continue
        # Match _native_row_for_discovery excerpt cap so signal_fp aligns infer ↔ merge.
        sig_fp = signal_fingerprint(kind=kind, message=msg_trim[:280])
        if sig_fp in seen_signal:
            continue
        fp = discovery_fingerprint(kind=kind, finding_id=fid, message=msg)
        key = f"{DISCOVERY_KEY_PREFIX}{kind}:{fp}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        seen_signal.add(sig_fp)
        out.append(
            _native_row_for_discovery(
                kind=kind,
                fingerprint=fp,
                finding_id=fid,
                message_excerpt=msg,
            )
        )
    return out


def merge_discovery_from_audit_findings(
    ledger: dict[str, Any] | None,
    findings: list[dict[str, Any]] | None,
    *,
    merge_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convenience: infer from findings + merge into native ledger (used after ``update_ledger_from_iteration``)."""
    working = ledger if isinstance(ledger, dict) else {}
    items_raw = working.get("items") if isinstance(working.get("items"), list) else []
    existing_items = [x for x in items_raw if isinstance(x, dict)]
    infer_stats_inner: dict[str, Any] = {}
    inferred = infer_discovery_items_from_audit_findings(
        findings,
        existing_items=existing_items,
        infer_stats=infer_stats_inner,
    )
    merged = merge_discovered_native_items(ledger, inferred, merge_stats=merge_stats)
    if merge_stats is not None:
        merge_stats["infer"] = infer_stats_inner
    return merged


def append_discovery_merge_continuity(
    continuity_log: list[dict[str, Any]],
    *,
    iteration: int,
    merge_stats: dict[str, Any] | None,
) -> None:
    """Append one bounded row when discovery merge did something worth recording."""
    if not isinstance(continuity_log, list) or merge_stats is None:
        return
    added = merge_stats.get("added_keys") or []
    merged = merge_stats.get("signal_merged_into_keys") or []
    ev_only = merge_stats.get("evidence_only_keys") or []
    if not added and not merged and not ev_only:
        if int(merge_stats.get("rejected_near_duplicate_signal") or 0) == 0:
            return
    row = {
        "decision_key": str(added[0][:200] if added else merged[0][:200] if merged else "")[:200],
        "move": "discovery_ledger_merge",
        "outcome": "discovery_merge",
        "iteration": int(iteration),
        "focus_source": None,
        "discovery_merge": {
            "added_keys": [str(x)[:120] for x in added[:4]],
            "signal_merged_into_keys": [str(x)[:120] for x in merged[:4]],
            "evidence_only_keys": [str(x)[:120] for x in ev_only[:4]],
            "rejected_near_duplicate_signal": int(merge_stats.get("rejected_near_duplicate_signal") or 0),
            "rejected_kind_cap": int(merge_stats.get("rejected_kind_cap") or 0),
            "skipped_total_cap": bool(merge_stats.get("skipped_total_cap")),
        },
    }
    continuity_log.append(row)
    if len(continuity_log) > 50:
        del continuity_log[:-50]
