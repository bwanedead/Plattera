"""Mechanical draft patch targets from mapping course-leg facts (no corrected values)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

MAX_DRAFT_PATCH_TARGETS = 24
MAX_PATCH_TARGET_EVIDENCE_REFS = 8
MAX_PATCH_UPDATE_SHELLS = 8

_COURSE_UPDATE_PLACEHOLDERS = {
    "distance": "<agent-authored corrected numeric distance>",
    "bearing": "<agent-authored corrected numeric bearing>",
    "distance_raw": "<agent-authored corrected distance_raw>",
    "bearing_raw": "<agent-authored corrected bearing_raw>",
}


def _entity_value_kind(entity_id: str) -> str | None:
    lower = entity_id.lower()
    if "distance" in lower:
        return "distance"
    if "bearing" in lower:
        return "bearing"
    return None


def build_draft_patch_targets(
    *,
    course_leg_tables: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Project course-leg source entity ids into bounded CourseTraverse patch targets."""
    if not isinstance(course_leg_tables, Sequence):
        return []
    targets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for table in course_leg_tables:
        if not isinstance(table, Mapping):
            continue
        if str(table.get("operation") or "") != "CourseTraverse":
            continue
        node_id = str(table.get("feature_id") or "").strip()
        if not node_id:
            continue
        courses = table.get("courses")
        if not isinstance(courses, list):
            continue
        for course in courses:
            if not isinstance(course, Mapping):
                continue
            leg_index = course.get("leg_index")
            if not isinstance(leg_index, int) or leg_index < 1:
                continue
            entity_ids = course.get("source_entity_ids")
            if not isinstance(entity_ids, list) or not entity_ids:
                continue
            evidence_refs = _bounded_evidence_refs(course.get("evidence_refs"))
            for entity_id in entity_ids:
                if not isinstance(entity_id, str) or not entity_id.strip():
                    continue
                field = _entity_value_kind(entity_id.strip())
                if field is None:
                    continue
                patch_target_id = f"course_{field}:{entity_id.strip()}"
                if patch_target_id in seen_ids:
                    continue
                seen_ids.add(patch_target_id)
                row: dict[str, Any] = {
                    "patch_target_id": patch_target_id,
                    "source_entity_id": entity_id.strip(),
                    "node_id": node_id,
                    "operation": "CourseTraverse",
                    "course_index": leg_index,
                    "course_array_index": leg_index - 1,
                    "field": field,
                }
                current_value = course.get(field)
                if isinstance(current_value, (int, float)) and not isinstance(current_value, bool):
                    row["current_value"] = float(current_value)
                raw_key = f"{field}_raw"
                current_raw = course.get(raw_key)
                if isinstance(current_raw, str) and current_raw.strip():
                    row["current_raw"] = current_raw.strip()
                if evidence_refs:
                    row["evidence_refs"] = list(evidence_refs)
                targets.append(row)
                if len(targets) >= MAX_DRAFT_PATCH_TARGETS:
                    return targets
    return targets


def join_correction_posture_to_patch_targets(
    *,
    correction_posture: Mapping[str, Any] | None,
    draft_patch_targets: Sequence[Mapping[str, Any]] | None,
    base_draft_ref: str | None = None,
) -> dict[str, Any] | None:
    """Join candidate deltas to patch targets and emit placeholder course_updates shells."""
    if not isinstance(correction_posture, Mapping) or not correction_posture.get("active"):
        return None
    deltas = correction_posture.get("candidate_deltas")
    if not isinstance(deltas, list) or not deltas:
        return None

    targets_by_entity: dict[str, Mapping[str, Any]] = {}
    if isinstance(draft_patch_targets, Sequence):
        for target in draft_patch_targets:
            if not isinstance(target, Mapping):
                continue
            entity_id = str(target.get("source_entity_id") or "").strip()
            if entity_id and entity_id not in targets_by_entity:
                targets_by_entity[entity_id] = target

    joined_deltas: list[dict[str, Any]] = []
    shell_updates: list[dict[str, Any]] = []
    for delta in deltas:
        if not isinstance(delta, Mapping):
            continue
        row = dict(delta)
        target_entity_id = str(delta.get("target_entity_id") or "").strip()
        match = targets_by_entity.get(target_entity_id)
        if match is not None:
            patch_target_id = str(match.get("patch_target_id") or "").strip()
            if patch_target_id:
                row["matching_patch_target_id"] = patch_target_id
            # Active deltas already mean IR differs from inherited; still emit a
            # placeholder shell for copyable repair ergonomics (agent authors value).
            shell_update = _build_course_update_shell(match, delta)
            if shell_update is not None:
                shell_updates.append(shell_update)
        joined_deltas.append(row)

    result: dict[str, Any] = {
        "active": True,
        "reason_codes": list(correction_posture.get("reason_codes") or []),
        "candidate_deltas": joined_deltas,
        "candidate_delta_count": len(joined_deltas),
        "contract_ref": correction_posture.get("contract_ref"),
    }
    if shell_updates:
        shell: dict[str, Any] = {"course_updates": shell_updates[:MAX_PATCH_UPDATE_SHELLS]}
        if isinstance(base_draft_ref, str) and base_draft_ref.strip():
            shell["base_draft_ref"] = base_draft_ref.strip()
        result["patch_update_shells"] = [shell]
    return result


def compact_draft_patch_targets_for_projection(
    targets: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if not isinstance(targets, Sequence) or not targets:
        return None
    compact: list[dict[str, Any]] = []
    for target in targets[:8]:
        if not isinstance(target, Mapping):
            continue
        row = {
            key: target.get(key)
            for key in (
                "patch_target_id",
                "source_entity_id",
                "node_id",
                "course_index",
                "course_array_index",
                "field",
                "current_value",
                "current_raw",
                "evidence_refs",
            )
            if target.get(key) is not None
        }
        if row:
            compact.append(row)
    return compact or None


def render_draft_patch_targets_timeline_lines(
    targets: Sequence[Mapping[str, Any]] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(targets, Sequence) or not targets:
        return []
    lines = [f"{indent}draft_patch_targets: {len(targets)}"]
    for target in list(targets)[:6]:
        if not isinstance(target, Mapping):
            continue
        lines.append(
            "{indent}  - {patch_id} node={node} course_index={course_index} "
            "field={field} current={current}".format(
                indent=indent,
                patch_id=target.get("patch_target_id") or "",
                node=target.get("node_id") or "",
                course_index=target.get("course_index"),
                field=target.get("field") or "",
                current=target.get("current_value")
                if target.get("current_value") is not None
                else target.get("current_raw") or "",
            )
        )
    return lines


def render_patch_update_shells_timeline_lines(
    shells: Sequence[Mapping[str, Any]] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(shells, Sequence) or not shells:
        return []
    update_count = 0
    for shell in shells:
        if isinstance(shell, Mapping):
            updates = shell.get("course_updates")
            if isinstance(updates, list):
                update_count += len(updates)
    lines = [f"{indent}patch_update_shells: {len(shells)} (course_updates={update_count})"]
    for shell in list(shells)[:2]:
        if not isinstance(shell, Mapping):
            continue
        base_ref = shell.get("base_draft_ref")
        if isinstance(base_ref, str) and base_ref.strip():
            lines.append(f"{indent}  base_draft_ref: {base_ref.strip()}")
        updates = shell.get("course_updates")
        if not isinstance(updates, list):
            continue
        for update in updates[:4]:
            if not isinstance(update, Mapping):
                continue
            lines.append(
                "{indent}  - node={node} course_index={course_index} field={field} "
                "source_entity_id={entity}".format(
                    indent=indent,
                    node=update.get("node_id") or "",
                    course_index=update.get("course_index"),
                    field=update.get("field") or "",
                    entity=update.get("source_entity_id") or "",
                )
            )
    return lines


def attach_draft_patch_targets_to_mapping_review(
    mapping_review: dict[str, Any],
    *,
    base_draft_ref: str | None = None,
) -> dict[str, Any]:
    """Attach draft_patch_targets and join active correction_posture when present."""
    sanity = mapping_review.get("sanity_review")
    course_leg_tables = None
    if isinstance(sanity, Mapping):
        tables = sanity.get("course_leg_tables")
        if isinstance(tables, list):
            course_leg_tables = tables
    targets = build_draft_patch_targets(course_leg_tables=course_leg_tables)
    if targets:
        mapping_review["draft_patch_targets"] = targets

    source_ir = base_draft_ref or mapping_review.get("source_ir_artifact_ref")
    posture = mapping_review.get("correction_posture")
    joined = join_correction_posture_to_patch_targets(
        correction_posture=posture if isinstance(posture, Mapping) else None,
        draft_patch_targets=targets,
        base_draft_ref=str(source_ir).strip() if isinstance(source_ir, str) else None,
    )
    if joined is not None:
        mapping_review["correction_posture"] = joined
    return mapping_review


def _bounded_evidence_refs(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    refs: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            continue
        text = item.strip()
        if text in seen:
            continue
        seen.add(text)
        refs.append(text)
        if len(refs) >= MAX_PATCH_TARGET_EVIDENCE_REFS:
            break
    return refs


def _build_course_update_shell(
    target: Mapping[str, Any],
    delta: Mapping[str, Any],
) -> dict[str, Any] | None:
    node_id = str(target.get("node_id") or "").strip()
    field = str(target.get("field") or "").strip()
    course_index = target.get("course_index")
    if not node_id or field not in _COURSE_UPDATE_PLACEHOLDERS:
        return None
    if not isinstance(course_index, int) or course_index < 1:
        return None
    shell: dict[str, Any] = {
        "node_id": node_id,
        "course_index": course_index,
        "field": field,
        "value": _COURSE_UPDATE_PLACEHOLDERS[field],
    }
    source_entity_id = str(target.get("source_entity_id") or delta.get("target_entity_id") or "").strip()
    if source_entity_id:
        shell["source_entity_id"] = source_entity_id
    basis_refs = delta.get("basis_refs")
    if not isinstance(basis_refs, list) or not basis_refs:
        basis_refs = target.get("evidence_refs")
    if isinstance(basis_refs, list):
        refs = [str(item).strip() for item in basis_refs if isinstance(item, str) and str(item).strip()]
        if refs:
            shell["basis_refs"] = refs[:MAX_PATCH_TARGET_EVIDENCE_REFS]
    return shell
