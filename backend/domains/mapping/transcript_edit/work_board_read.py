"""Read helpers for generic work-board rows (projected from the ledger).

Callers should treat the ledger as authoritative; the board is a normalized read view.
"""
from __future__ import annotations

from typing import Any


def board_item_id(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict):
        return None
    raw = str(item.get("item_id") or "").strip()
    return raw or None


def board_state(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict):
        return None
    raw = str(item.get("state") or "").strip().lower()
    return raw or None


def board_materiality(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict):
        return None
    raw = str(item.get("materiality") or "").strip().lower()
    return raw or None


def board_blocking_impact(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict):
        return None
    bi = item.get("blocking_impact")
    if bi is None:
        return None
    return str(bi).strip().lower() or None


def board_resolution_condition(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict):
        return None
    rc = item.get("resolution_condition")
    if rc is None:
        return None
    s = str(rc).strip()
    return s[:400] or None


def board_evidence_refs(item: dict[str, Any] | None, *, limit: int = 12) -> list[str]:
    if not isinstance(item, dict):
        return []
    raw = item.get("evidence_refs")
    if not isinstance(raw, list):
        return []
    out = [str(x).strip() for x in raw if str(x).strip()]
    return out[:limit]


def board_dependencies(item: dict[str, Any] | None, *, limit: int = 8) -> list[str]:
    if not isinstance(item, dict):
        return []
    raw = item.get("dependencies")
    if not isinstance(raw, list):
        return []
    out = [str(x).strip() for x in raw if str(x).strip()]
    return out[:limit]


def board_is_mapping_blocking(item: dict[str, Any] | None) -> bool:
    return board_blocking_impact(item) == "mapping_blocking"


def board_domain_decision_key(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict):
        return None
    dp = item.get("domain_payload")
    if not isinstance(dp, dict):
        return None
    raw = str(dp.get("decision_key") or "").strip().lower()
    return raw or None


def ledger_board_parity(
    decision_key: str,
    ledger_item: dict[str, Any] | None,
    board_item: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compact linkage status between authoritative ledger row and projected board item."""
    key = str(decision_key or "").strip().lower()
    if not key:
        return {
            "identity_aligned": False,
            "posture_aligned": False,
            "code": "no_decision_key",
            "detail": "No focus key; ledger remains authoritative.",
            "ledger_projected_item_id": None,
        }
    if not isinstance(ledger_item, dict):
        return {
            "identity_aligned": False,
            "posture_aligned": False,
            "code": "ledger_item_missing",
            "detail": "Ledger row missing for key; packet degraded.",
            "ledger_projected_item_id": None,
        }
    if not isinstance(board_item, dict):
        return {
            "identity_aligned": False,
            "posture_aligned": False,
            "code": "board_item_missing",
            "detail": "Projection did not yield board item; using ledger-only posture.",
            "ledger_projected_item_id": None,
        }
    b_key = board_domain_decision_key(board_item)
    identity_aligned = bool(b_key == key)
    cr = ledger_item.get("closure_requirement") if isinstance(ledger_item.get("closure_requirement"), dict) else {}
    ledger_mb = bool(cr.get("mapping_blocking", ledger_item.get("blocking")))
    board_mb = board_is_mapping_blocking(board_item)
    posture_aligned = ledger_mb == board_mb
    item_id = board_item_id(board_item)
    if not identity_aligned:
        return {
            "identity_aligned": False,
            "posture_aligned": posture_aligned,
            "code": "board_domain_key_mismatch",
            "detail": f"domain_payload.decision_key={b_key!r} expected {key!r}.",
            "ledger_projected_item_id": item_id,
        }
    if not posture_aligned:
        return {
            "identity_aligned": True,
            "posture_aligned": False,
            "code": "posture_mismatch",
            "detail": "Ledger mapping_blocking disagrees with board blocking_impact; prefer ledger for gates.",
            "ledger_projected_item_id": item_id,
        }
    return {
        "identity_aligned": True,
        "posture_aligned": True,
        "code": "ok",
        "detail": None,
        "ledger_projected_item_id": item_id,
    }


def generic_knowns_snapshot(board_item: dict[str, Any] | None) -> dict[str, Any] | None:
    """Bounded snapshot for investigation brief / prompts (no deed-native harness slots)."""
    if not isinstance(board_item, dict):
        return None
    return {
        "item_id": board_item_id(board_item),
        "state": board_state(board_item),
        "materiality": board_materiality(board_item),
        "blocking_impact": board_blocking_impact(board_item),
        "resolution_condition": board_resolution_condition(board_item),
        "evidence_refs": board_evidence_refs(board_item, limit=6),
        "dependencies": board_dependencies(board_item, limit=6),
    }
