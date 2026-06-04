"""Derived atom ↔ point-crop ↔ delegate ref worklist (mechanical joins only).

Observability only: does not mutate resolution state or author closure/truth.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .point_crop_set_projection import project_point_crop_set_summary

KIND = "atom_evidence_worklist"

MAX_ATOMS = 64
MAX_PACKET_REFS_PER_ATOM = 4
MAX_DELEGATE_REFS_PER_ATOM = 4
MAX_UNMATCHED_PACKET_REFS = 16
MAX_EVIDENCE_REFS = 16
MAX_CANDIDATE_VALUES = 8
MAX_FIELD_CHARS = 240
MAX_RESULT_PREVIEW_KEYS = 6

_POINT_CROP_SUB_ACTIONS = frozenset({"point_crops", "point_crops_adjust"})
_STRIP_KEYS = frozenset(
    {
        "b64",
        "base64",
        "bytes",
        "binary",
        "raw_image",
        "raw_image_data",
        "image_bytes",
        "raw_prompt_text",
        "raw_llm_response_text",
        "prompt_text",
        "prompt",
        "raw_response",
        "absolute_path",
        "crop_img",
        "box_px",
        "local_box_px",
        "root_box_px",
    }
)
_BINARY_KEY_PARTS = ("b64", "base64", "bytes", "binary")
_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]|^/")

_MATCH_DIRECT_ALIAS = "direct_alias_match"
_MATCH_EVIDENCE_REF = "evidence_ref_match"
_MATCH_SHARED_EVIDENCE = "shared_evidence_ref"

_UTIL_OPEN_NO_PACKET = "open_no_packet_seen"
_UTIL_OPEN_PACKET_READY = "open_packet_ready_unused"
_UTIL_OPEN_PACKET_USED = "open_packet_used_not_determined"
_UTIL_OPEN_EVIDENCE_REF = "open_evidence_referenced_not_determined"
_UTIL_CLOSED_EVIDENCE = "closed_evidence_referenced"
_UTIL_CLOSED_NO_PACKET = "closed_no_packet_seen"


def build_atom_evidence_worklist(
    *,
    resolution_state: Mapping[str, Any] | None,
    recent_result_records: Sequence[Mapping[str, Any]] | None = None,
    delegate_result_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Join resolution atoms to point-crop and delegate refs via exact matches only."""
    atoms = _flatten_atoms(resolution_state)
    atom_ids = {a["atom_id"] for a in atoms}

    packet_crops = _collect_packet_crops(recent_result_records)
    delegates = _collect_delegate_refs(delegate_result_records)

    atom_rows, unmatched = _join_atoms(
        atoms,
        atom_ids=atom_ids,
        packet_crops=packet_crops,
        delegates=delegates,
    )

    counts = _build_counts(atom_rows, unmatched_count=len(unmatched))

    return _sanitize_worklist(
        {
            "kind": KIND,
            "counts": counts,
            "atoms": atom_rows[:MAX_ATOMS],
            "unmatched_packet_refs": unmatched[:MAX_UNMATCHED_PACKET_REFS],
        }
    )


def _flatten_atoms(resolution_state: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(resolution_state, Mapping):
        return []
    items = resolution_state.get("items")
    if not isinstance(items, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        item_id = _norm_id(item.get("item_id"))
        if item_id:
            rows.append(_atom_row_from_node(item, atom_id=item_id, parent_item_id=None))
        covered = item.get("covered_units")
        if not isinstance(covered, list):
            continue
        for unit in covered:
            if not isinstance(unit, Mapping):
                continue
            unit_id = _norm_id(unit.get("unit_id"))
            if not unit_id:
                continue
            rows.append(
                _atom_row_from_node(
                    unit,
                    atom_id=unit_id,
                    parent_item_id=item_id,
                )
            )
    return rows[:MAX_ATOMS]


def _atom_row_from_node(
    node: Mapping[str, Any],
    *,
    atom_id: str,
    parent_item_id: str | None,
) -> dict[str, Any]:
    status = _bound_text(node.get("status"))
    determination = _bound_text(node.get("determination"))
    title = _bound_text(node.get("title") or node.get("label") or atom_id)
    evidence_refs = _bounded_str_list(node.get("evidence_refs"), limit=MAX_EVIDENCE_REFS)
    candidates = _bounded_str_list(node.get("candidate_values"), limit=MAX_CANDIDATE_VALUES)
    determined = node.get("determined_value")
    determined_value = _bound_text(determined) if determined is not None else None

    return {
        "atom_id": atom_id,
        "parent_item_id": parent_item_id,
        "title": title,
        "status": status,
        "determined_value": determined_value,
        "candidate_values": candidates or None,
        "evidence_refs": evidence_refs,
        "is_closed_like": _is_closed_like(status, determination),
        "is_blocked": _is_blocked(status),
    }


def _is_closed_like(status: str | None, determination: str | None) -> bool:
    if str(status or "").strip().lower() == "closed":
        return True
    return str(determination or "").strip().lower() == "earned"


def _is_blocked(status: str | None) -> bool:
    return str(status or "").strip().lower() == "blocked"


def _collect_packet_crops(
    recent_result_records: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    crops: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    if not recent_result_records:
        return crops

    for record in recent_result_records:
        if not isinstance(record, Mapping):
            continue
        turn = _turn_index(record)
        top_summary = record.get("point_crop_set_summary")
        if isinstance(top_summary, Mapping):
            _append_crops_from_summary(
                crops,
                top_summary,
                created_turn=turn,
                seen_refs=seen_refs,
            )
        for container in _record_output_containers(record):
            summary = container.get("point_crop_set_summary")
            if isinstance(summary, Mapping):
                _append_crops_from_summary(
                    crops,
                    summary,
                    created_turn=turn,
                    seen_refs=seen_refs,
                )
            projected = project_point_crop_set_summary(container)
            if projected is not None:
                _append_crops_from_summary(
                    crops,
                    projected,
                    created_turn=turn,
                    seen_refs=seen_refs,
                )
    return crops


def _record_output_containers(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    containers: list[Mapping[str, Any]] = []
    for key in ("outputs_for_continuity", "outputs"):
        raw = record.get(key)
        if isinstance(raw, Mapping):
            containers.append(raw)
    return containers


def _append_crops_from_summary(
    crops: list[dict[str, Any]],
    summary: Mapping[str, Any],
    *,
    created_turn: int | None,
    seen_refs: set[str],
) -> None:
    sub_action = str(summary.get("sub_action") or "").strip()
    if sub_action == "point_crops_view":
        return
    if sub_action and sub_action not in _POINT_CROP_SUB_ACTIONS:
        return

    overlay_ref = summary.get("master_overlay_ref")
    if not isinstance(overlay_ref, str) or not overlay_ref.strip():
        return
    overlay_ref = overlay_ref.strip()

    points = summary.get("points")
    if not isinstance(points, list):
        return

    for point in points:
        if not isinstance(point, Mapping):
            continue
        crop_ref = point.get("crop_ref")
        if not isinstance(crop_ref, str) or not crop_ref.strip():
            continue
        crop_ref = crop_ref.strip()
        if crop_ref in seen_refs:
            continue
        seen_refs.add(crop_ref)
        alias = _norm_id(point.get("alias"))
        row: dict[str, Any] = {
            "crop_ref": crop_ref,
            "overlay_ref": overlay_ref,
            "source_alias": alias,
            "letter": _bound_text(point.get("letter"), max_chars=8),
            "created_turn": created_turn,
        }
        point_norm = point.get("point_norm") or point.get("local_point_norm")
        if isinstance(point_norm, list) and len(point_norm) == 2:
            row["point_norm"] = point_norm
        box_norm = point.get("box_norm") or point.get("local_box_norm")
        if isinstance(box_norm, list) and len(box_norm) == 4:
            row["box_norm"] = box_norm
        root_source_ref = point.get("root_source_ref")
        if isinstance(root_source_ref, str) and root_source_ref.strip():
            row["root_source_ref"] = root_source_ref.strip()
        root_point_norm = point.get("root_point_norm")
        if isinstance(root_point_norm, list) and len(root_point_norm) == 2:
            row["root_point_norm"] = root_point_norm
        root_box_norm = point.get("root_box_norm")
        if isinstance(root_box_norm, list) and len(root_box_norm) == 4:
            row["root_box_norm"] = root_box_norm
        crops.append(row)


def _collect_delegate_refs(
    delegate_result_records: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not delegate_result_records:
        return rows
    for record in delegate_result_records:
        if not isinstance(record, Mapping):
            continue
        ref_id = str(record.get("ref_id") or "").strip()
        if not ref_id.startswith("subtask:"):
            continue
        rows.append(
            {
                "delegate_ref": ref_id,
                "delegate_alias": _bound_text(record.get("alias")),
                "delegate_status": _bound_text(record.get("status"), max_chars=64),
                "context_refs": _bounded_str_list(record.get("context_refs"), limit=8),
                "created_turn": _turn_index(record),
                "result_preview": _safe_result_preview(record.get("result")),
            }
        )
    return rows


def _join_atoms(
    atoms: list[dict[str, Any]],
    *,
    atom_ids: set[str],
    packet_crops: list[dict[str, Any]],
    delegates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    crop_by_ref = {c["crop_ref"]: c for c in packet_crops if c.get("crop_ref")}
    cited_crop_refs: set[str] = set()

    for atom in atoms:
        for ref in atom.get("evidence_refs") or []:
            text = str(ref).strip()
            if text.startswith("image:"):
                cited_crop_refs.add(text)

    matched_crop_refs: set[str] = set()
    out_atoms: list[dict[str, Any]] = []

    for atom in atoms:
        atom_id = atom["atom_id"]
        evidence_refs = set(atom.get("evidence_refs") or [])
        packet_refs, atom_delegates = _packet_and_delegate_refs_for_atom(
            atom_id=atom_id,
            evidence_refs=evidence_refs,
            packet_crops=packet_crops,
            delegates=delegates,
            crop_by_ref=crop_by_ref,
        )
        for pref in packet_refs:
            matched_crop_refs.add(pref["crop_ref"])
        utilization = _utilization_status(
            atom,
            packet_refs=packet_refs,
            atom_delegate_refs=atom_delegates,
        )
        out_atoms.append(
            {
                "atom_id": atom_id,
                "parent_item_id": atom.get("parent_item_id"),
                "title": atom.get("title"),
                "status": atom.get("status"),
                "determined_value": atom.get("determined_value"),
                "candidate_values": atom.get("candidate_values"),
                "utilization_status": utilization,
                "packet_refs": packet_refs[:MAX_PACKET_REFS_PER_ATOM],
                "delegate_refs": atom_delegates[:MAX_DELEGATE_REFS_PER_ATOM],
            }
        )

    unmatched: list[dict[str, Any]] = []
    for crop in packet_crops:
        crop_ref = crop.get("crop_ref")
        if not crop_ref or crop_ref in matched_crop_refs:
            continue
        alias = crop.get("source_alias")
        if alias and alias in atom_ids:
            continue
        if crop_ref in cited_crop_refs:
            continue
        unmatched.append(
            _unmatched_packet_row(
                crop,
                delegates=_delegates_for_crop_ref(crop_ref, delegates),
            )
        )

    return out_atoms, unmatched


def _packet_and_delegate_refs_for_atom(
    *,
    atom_id: str,
    evidence_refs: set[str],
    packet_crops: list[dict[str, Any]],
    delegates: list[dict[str, Any]],
    crop_by_ref: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    packet_by_ref: dict[str, dict[str, Any]] = {}
    atom_delegates: list[dict[str, Any]] = []
    seen_atom_delegate_refs: set[str] = set()
    seen_nested_delegate_refs: set[str] = set()

    def ensure_packet(crop: Mapping[str, Any], *, match_kind: str, referenced: bool) -> dict[str, Any]:
        crop_ref = str(crop.get("crop_ref") or "").strip()
        existing = packet_by_ref.get(crop_ref)
        if existing is not None:
            if referenced:
                existing["referenced_in_state"] = True
            if match_kind == _MATCH_DIRECT_ALIAS and existing["match_kind"] != _MATCH_DIRECT_ALIAS:
                existing["match_kind"] = _MATCH_DIRECT_ALIAS
            return existing
        row = {
            "crop_ref": crop_ref,
            "overlay_ref": crop.get("overlay_ref"),
            "source_alias": crop.get("source_alias"),
            "letter": crop.get("letter"),
            "match_kind": match_kind,
            "created_turn": crop.get("created_turn"),
            "referenced_in_state": referenced,
            "delegate_refs": [],
        }
        packet_by_ref[crop_ref] = row
        return row

    for crop in packet_crops:
        alias = crop.get("source_alias")
        crop_ref = str(crop.get("crop_ref") or "").strip()
        if alias == atom_id:
            ensure_packet(crop, match_kind=_MATCH_DIRECT_ALIAS, referenced=crop_ref in evidence_refs)
        elif crop_ref and crop_ref in evidence_refs:
            kind = _MATCH_SHARED_EVIDENCE if alias and alias != atom_id else _MATCH_EVIDENCE_REF
            ensure_packet(crop, match_kind=kind, referenced=True)

    for delegate in delegates:
        delegate_ref = delegate.get("delegate_ref")
        if not delegate_ref:
            continue
        linked = False
        if delegate.get("delegate_alias") == atom_id:
            linked = True
        if delegate_ref in evidence_refs:
            linked = True
        context = delegate.get("context_refs") or []
        for context_ref in context:
            crop = crop_by_ref.get(str(context_ref).strip())
            if crop is None:
                continue
            alias = crop.get("source_alias")
            if alias == atom_id or str(context_ref).strip() in evidence_refs:
                linked = True
                packet_row = ensure_packet(
                    crop,
                    match_kind=_MATCH_DIRECT_ALIAS if alias == atom_id else _MATCH_EVIDENCE_REF,
                    referenced=str(context_ref).strip() in evidence_refs
                    or str(crop.get("crop_ref") or "") in evidence_refs,
                )
                _attach_delegate_to_packet(
                    packet_row,
                    delegate,
                    seen_nested_delegate_refs,
                )

        if linked and delegate_ref not in seen_atom_delegate_refs:
            seen_atom_delegate_refs.add(delegate_ref)
            atom_delegates.append(_compact_delegate_ref(delegate))

    packet_refs = list(packet_by_ref.values())
    for packet in packet_refs:
        packet["delegate_refs"] = packet["delegate_refs"][:MAX_DELEGATE_REFS_PER_ATOM]
    return packet_refs, atom_delegates


def _attach_delegate_to_packet(
    packet_row: dict[str, Any],
    delegate: Mapping[str, Any],
    seen_delegate_refs: set[str],
) -> None:
    delegate_ref = delegate.get("delegate_ref")
    if not delegate_ref or delegate_ref in seen_delegate_refs:
        return
    nested = packet_row.setdefault("delegate_refs", [])
    if len(nested) >= MAX_DELEGATE_REFS_PER_ATOM:
        return
    seen_delegate_refs.add(delegate_ref)
    nested.append(_compact_delegate_ref(delegate))


def _compact_delegate_ref(delegate: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "delegate_ref": delegate.get("delegate_ref"),
        "delegate_alias": delegate.get("delegate_alias"),
        "delegate_status": delegate.get("delegate_status"),
        "context_refs": _bounded_str_list(delegate.get("context_refs"), limit=4),
    }
    if delegate.get("created_turn") is not None:
        row["created_turn"] = delegate.get("created_turn")
    preview = delegate.get("result_preview")
    if preview:
        row["result_preview"] = preview
    return row


def _utilization_status(
    atom: Mapping[str, Any],
    *,
    packet_refs: list[dict[str, Any]],
    atom_delegate_refs: list[dict[str, Any]],
) -> str:
    closed = bool(atom.get("is_closed_like"))
    evidence_refs = set(atom.get("evidence_refs") or [])

    has_packet = bool(packet_refs)
    has_direct_alias = any(p.get("match_kind") == _MATCH_DIRECT_ALIAS for p in packet_refs)
    has_evidence_packet = any(p.get("referenced_in_state") for p in packet_refs)
    has_delegate = bool(atom_delegate_refs) or any(p.get("delegate_refs") for p in packet_refs)
    cites_crop_or_delegate = any(
        str(ref).startswith("image:") or str(ref).startswith("subtask:")
        for ref in evidence_refs
    )

    if closed:
        if has_packet or cites_crop_or_delegate:
            return _UTIL_CLOSED_EVIDENCE
        return _UTIL_CLOSED_NO_PACKET

    if has_delegate:
        return _UTIL_OPEN_PACKET_USED
    if has_direct_alias and not has_evidence_packet and not cites_crop_or_delegate:
        return _UTIL_OPEN_PACKET_READY
    if has_packet or cites_crop_or_delegate or has_evidence_packet:
        return _UTIL_OPEN_EVIDENCE_REF
    return _UTIL_OPEN_NO_PACKET


def _delegates_for_crop_ref(
    crop_ref: str,
    delegates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Delegates whose context_refs cite this crop (exact ref match only)."""
    text = str(crop_ref or "").strip()
    if not text:
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for delegate in delegates:
        context_refs = delegate.get("context_refs") or []
        if text not in {str(ref).strip() for ref in context_refs}:
            continue
        delegate_ref = str(delegate.get("delegate_ref") or "").strip()
        if not delegate_ref or delegate_ref in seen:
            continue
        seen.add(delegate_ref)
        rows.append(_compact_delegate_ref(delegate))
        if len(rows) >= MAX_DELEGATE_REFS_PER_ATOM:
            break
    return rows


def _unmatched_packet_row(
    crop: Mapping[str, Any],
    *,
    delegates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "crop_ref": crop.get("crop_ref"),
        "overlay_ref": crop.get("overlay_ref"),
        "source_alias": crop.get("source_alias"),
        "letter": crop.get("letter"),
        "created_turn": crop.get("created_turn"),
    }
    if delegates:
        row["delegate_refs"] = delegates[:MAX_DELEGATE_REFS_PER_ATOM]
    return row


def _build_counts(atom_rows: list[dict[str, Any]], *, unmatched_count: int) -> dict[str, int]:
    open_count = 0
    closed_count = 0
    blocked_count = 0
    packet_ready = 0
    packet_used = 0

    for row in atom_rows:
        atom = row
        status = str(atom.get("status") or "").strip().lower()
        utilization = str(atom.get("utilization_status") or "")
        if status == "blocked":
            blocked_count += 1
        elif utilization.startswith("closed_"):
            closed_count += 1
        else:
            open_count += 1
        if utilization == _UTIL_OPEN_PACKET_READY:
            packet_ready += 1
        elif utilization == _UTIL_OPEN_PACKET_USED:
            packet_used += 1

    return {
        "atoms_total": len(atom_rows),
        "open": open_count,
        "closed": closed_count,
        "blocked": blocked_count,
        "packet_ready_unused": packet_ready,
        "packet_used_not_determined": packet_used,
        "unmatched_packet_refs": unmatched_count,
    }


def _safe_result_preview(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, Mapping) or not result:
        return None
    preview: dict[str, Any] = {}
    for key, value in list(result.items())[:MAX_RESULT_PREVIEW_KEYS]:
        if isinstance(value, str):
            preview[str(key)] = _bound_text(value, max_chars=120)
        elif isinstance(value, (int, float, bool)):
            preview[str(key)] = value
    return preview or None


def _sanitize_worklist(payload: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize_value(payload)  # type: ignore[return-value]


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_value(raw)
            for key, raw in value.items()
            if not _should_strip_key(str(key), raw)
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        if _ABSOLUTE_PATH_RE.match(text):
            return None
        return _bound_text(text) if len(text) > MAX_FIELD_CHARS else text
    return value


def _should_strip_key(key: str, value: Any) -> bool:
    lowered = key.lower()
    if lowered in _STRIP_KEYS:
        return True
    if any(part in lowered for part in _BINARY_KEY_PARTS):
        return True
    if isinstance(value, str) and _ABSOLUTE_PATH_RE.match(value.strip()):
        return True
    return False


def _turn_index(record: Mapping[str, Any]) -> int | None:
    for key in ("kernel_turn_index", "turn_index", "created_at_turn"):
        raw = record.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _norm_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _bound_text(value: Any, *, max_chars: int = MAX_FIELD_CHARS) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def _bounded_str_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        out.append(_bound_text(text, max_chars=MAX_FIELD_CHARS) or text)
        if len(out) >= limit:
            break
    return out
