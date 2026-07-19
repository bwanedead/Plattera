"""Generic completion-anchor evaluation from declarative domain closure policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from typing import Any

from domains.closure_policy import CompletionAnchorPolicy


def parse_completion_anchor_policy(
    closure_policy: Mapping[str, Any] | None,
) -> CompletionAnchorPolicy | None:
    if not isinstance(closure_policy, Mapping):
        return None
    raw = closure_policy.get("completion_anchor")
    if raw is None:
        return None
    if isinstance(raw, CompletionAnchorPolicy):
        return raw if raw.enabled else None
    if not isinstance(raw, Mapping) or not raw.get("enabled"):
        return None
    allowed = {field.name for field in fields(CompletionAnchorPolicy)}
    kwargs = {key: raw[key] for key in raw if key in allowed}
    policy = CompletionAnchorPolicy(**kwargs)
    return policy if policy.enabled else None


def collect_ref_strings(value: Any) -> set[str]:
    refs: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            text = node.strip()
            if text:
                refs.add(text)
            return
        if isinstance(node, Mapping):
            for inner in node.values():
                _walk(inner)
            return
        if isinstance(node, (list, tuple)):
            for inner in node:
                _walk(inner)

    _walk(value)
    return refs


def _ref_matches_prefix(ref: str, prefix: str) -> bool:
    return ref == prefix or ref.startswith(f"{prefix}:") or ref.startswith(prefix)


def _has_required_output_ref(ref_set: set[str], required_ref: str | None) -> bool:
    if not required_ref:
        return True
    return any(_ref_matches_prefix(ref, required_ref) for ref in ref_set)


def _nested_get(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def find_most_recent_publish_outputs(
    step_result_records: list[Any] | tuple[Any, ...] | None,
    *,
    publish_action_ids: tuple[str, ...],
) -> dict[str, Any] | None:
    if not step_result_records or not publish_action_ids:
        return None
    allowed = set(publish_action_ids)
    for row in reversed(list(step_result_records)):
        if not isinstance(row, Mapping):
            continue
        if str(row.get("action_type") or "") not in allowed:
            continue
        if str(row.get("execution_state") or "") not in {"executed", "deduped"}:
            continue
        outputs = row.get("outputs_for_continuity")
        if not isinstance(outputs, Mapping):
            continue
        if not str(outputs.get("output_revision_ref") or outputs.get("output_ref") or "").strip():
            continue
        return dict(outputs)
    return None


def is_posture_mirror_blocker(blocker: str, *, policy: CompletionAnchorPolicy) -> bool:
    text = str(blocker or "").strip()
    if not text:
        return False
    if text in policy.posture_mirror_blocker_exact:
        return True
    return any(text.startswith(prefix) for prefix in policy.posture_mirror_blocker_prefixes)


def is_publish_posture_mirror_blocker(blocker: str, *, policy: CompletionAnchorPolicy) -> bool:
    text = str(blocker or "").strip()
    if not text:
        return False
    exact = policy.publish_posture_mirror_blocker_exact or policy.posture_mirror_blocker_exact
    prefixes = policy.publish_posture_mirror_blocker_prefixes or policy.posture_mirror_blocker_prefixes
    if text in exact:
        return True
    return any(text.startswith(prefix) for prefix in prefixes)


def _publish_action_inputs(action_plan: Any) -> dict[str, Any]:
    from .action_sequence import effective_actions

    actions = effective_actions(action_plan)
    if len(actions) == 1:
        inputs = actions[0].action_inputs
        return dict(inputs) if isinstance(inputs, Mapping) else {}
    inputs = action_plan.action_inputs
    return dict(inputs) if isinstance(inputs, Mapping) else {}


def find_publish_ready_preview_outputs(
    step_result_records: list[Any] | tuple[Any, ...] | None,
    *,
    preview_ref: str,
    prepare_action_ids: tuple[str, ...] = (),
    preview_ready_field: str = "publish_ready_candidate",
) -> dict[str, Any] | None:
    target = str(preview_ref or "").strip()
    if not target or not step_result_records:
        return None
    allowed_prepare = {str(item).strip() for item in prepare_action_ids if str(item).strip()}
    for row in reversed(list(step_result_records)):
        if not isinstance(row, Mapping):
            continue
        action_type = str(row.get("action_type") or "")
        if allowed_prepare and action_type not in allowed_prepare:
            continue
        if str(row.get("execution_state") or "") not in {"executed", "deduped"}:
            continue
        outputs = row.get("outputs_for_continuity")
        if not isinstance(outputs, Mapping):
            continue
        if not bool(outputs.get(preview_ready_field)):
            continue
        candidate_refs = {
            str(outputs.get("final_package_preview_ref") or "").strip(),
            str(outputs.get("working_preview_ref") or "").strip(),
            str(outputs.get("preview_ref") or "").strip(),
        }
        candidate_refs.discard("")
        if target in candidate_refs:
            return dict(outputs)
        for ref in collect_ref_strings(outputs):
            if ref == target or ref.startswith(f"{target}:"):
                return dict(outputs)
    return None


def evaluate_preview_ready_publish_bypass(
    *,
    closure_policy: Mapping[str, Any] | None,
    action_plan: Any,
    step_result_records: list[Any] | tuple[Any, ...] | None,
) -> dict[str, Any]:
    policy = parse_completion_anchor_policy(closure_policy)
    if policy is None or not policy.preview_ready_publish_bypass:
        return {"allowed": False}
    inputs = _publish_action_inputs(action_plan)
    preview_ref = str(inputs.get("final_package_preview_ref") or "").strip()
    if not preview_ref:
        return {"allowed": False, "reason": "missing_final_package_preview_ref"}
    preview_outputs = find_publish_ready_preview_outputs(
        step_result_records,
        preview_ref=preview_ref,
        prepare_action_ids=policy.preview_prepare_action_ids,
        preview_ready_field=policy.preview_ready_field,
    )
    if preview_outputs is None:
        return {
            "allowed": False,
            "reason": "preview_not_publish_ready_or_not_found",
            "final_package_preview_ref": preview_ref,
        }
    return {
        "allowed": True,
        "final_package_preview_ref": preview_ref,
        "publish_ready_candidate": True,
        "preview_ready_summary": preview_outputs.get("preview_ready_summary"),
    }


def evaluate_completion_anchor(
    *,
    closure_policy: Mapping[str, Any] | None,
    latest_refs: Mapping[str, Any] | None,
    step_result_records: list[Any] | tuple[Any, ...] | None,
) -> dict[str, Any] | None:
    policy = parse_completion_anchor_policy(closure_policy)
    if policy is None:
        return None

    ref_set = collect_ref_strings(latest_refs or {})
    publish_outputs = find_most_recent_publish_outputs(
        step_result_records,
        publish_action_ids=policy.publish_action_ids,
    )

    required_output_ref = None
    if isinstance(closure_policy, Mapping):
        required_output_ref = str(closure_policy.get("required_output_ref_for_complete") or "").strip() or None

    ready_for_completion = False
    if isinstance(publish_outputs, Mapping):
        ready_value = _nested_get(
            publish_outputs,
            policy.publish_ready_container,
            policy.publish_ready_field,
        )
        ready_for_completion = ready_value is True

    missing_requirements: list[str] = []
    if publish_outputs is None:
        missing_requirements.append("publish_result")
    elif not ready_for_completion:
        missing_requirements.append("ready_for_completion_candidate_false")

    if not _has_required_output_ref(ref_set, required_output_ref):
        missing_requirements.append("output_ref")

    lineage: dict[str, str] = {}
    if isinstance(publish_outputs, Mapping):
        for field_name in policy.publish_lineage_ref_fields:
            value = str(publish_outputs.get(field_name) or "").strip()
            if not value:
                missing_requirements.append(f"publish_{field_name}")
                continue
            lineage[field_name] = value
            if value not in ref_set:
                missing_requirements.append(f"{field_name}_not_in_latest_refs")

    preview_ref: str | None = None
    if policy.published_preview_ref_field:
        preview_ref = (
            str(publish_outputs.get(policy.published_preview_ref_field) or "").strip()
            if isinstance(publish_outputs, Mapping)
            else ""
        ) or None
        if policy.require_published_preview_ref:
            if not preview_ref:
                missing_requirements.append("published_preview_ref")
            elif preview_ref not in ref_set:
                missing_requirements.append("preview_lineage_mismatch")

    satisfied = not missing_requirements
    anchor: dict[str, Any] = {
        "satisfied": satisfied,
        "ready_for_completion_candidate": ready_for_completion,
    }
    if satisfied and policy.expected_next:
        anchor["expected_next"] = policy.expected_next
    if required_output_ref:
        anchor["output_ref"] = required_output_ref
    if preview_ref:
        anchor["preview_ref"] = preview_ref
    mapping_ref = lineage.get("mapping_artifact_ref")
    if mapping_ref:
        anchor["mapping_ref"] = mapping_ref
    ir_ref = lineage.get("ir_artifact_ref")
    if ir_ref:
        anchor["ir_artifact_ref"] = ir_ref
    if isinstance(publish_outputs, Mapping):
        if publish_outputs.get("output_revision_ref"):
            anchor["output_revision_ref"] = publish_outputs.get("output_revision_ref")
        elif publish_outputs.get("output_ref"):
            anchor["output_revision_ref"] = publish_outputs.get("output_ref")
    if missing_requirements:
        anchor["missing_requirements"] = missing_requirements
    return anchor


def apply_completion_anchor_to_closure_readiness(
    projection: Mapping[str, Any],
    *,
    anchor: Mapping[str, Any],
    closure_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    policy = parse_completion_anchor_policy(closure_policy)
    if policy is None:
        if isinstance(projection, Mapping):
            out = dict(projection)
            out["completion_anchor"] = dict(anchor)
            return out
        return {"complete_run_blockers": [], "publish_blockers": []}
    if not isinstance(projection, Mapping):
        return {"complete_run_blockers": [], "publish_blockers": []}
    out = dict(projection)
    if not anchor.get("satisfied"):
        out["completion_anchor"] = dict(anchor)
        return out

    blockers = [
        str(item).strip()
        for item in (out.get("complete_run_blockers") or [])
        if str(item).strip()
    ]
    suppressed: list[str] = []
    kept: list[str] = []
    for blocker in blockers:
        if is_posture_mirror_blocker(blocker, policy=policy):
            suppressed.append(blocker)
        else:
            kept.append(blocker)
    out["complete_run_blockers"] = kept
    publish_blockers = [
        str(item).strip()
        for item in (out.get("publish_blockers") or [])
        if str(item).strip()
    ]
    publish_suppressed: list[str] = []
    publish_kept: list[str] = []
    for blocker in publish_blockers:
        if is_publish_posture_mirror_blocker(blocker, policy=policy):
            publish_suppressed.append(blocker)
        else:
            publish_kept.append(blocker)
    out["publish_blockers"] = publish_kept
    anchor_out = dict(anchor)
    if suppressed:
        anchor_out["completion_anchor_suppressed_flags"] = [
            {
                "flag": "complete_run_blockers_present",
                "reason": policy.suppressed_flag_reason,
                "suppressed_blockers": suppressed[:8],
            }
        ]
    if publish_suppressed:
        existing = list(anchor_out.get("completion_anchor_suppressed_flags") or [])
        existing.append(
            {
                "flag": "publish_blockers_present",
                "reason": policy.suppressed_flag_reason,
                "suppressed_blockers": publish_suppressed[:8],
            }
        )
        anchor_out["completion_anchor_suppressed_flags"] = existing
    out["completion_anchor"] = anchor_out
    return out


def render_completion_anchor_timeline_lines(
    anchor: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(anchor, Mapping) or not anchor:
        return []
    lines = [f"{indent}completion_anchor:"]
    for key in (
        "output_ref",
        "preview_ref",
        "mapping_ref",
        "output_revision_ref",
        "ir_artifact_ref",
    ):
        if anchor.get(key):
            lines.append(f"{indent}  {key}: {anchor.get(key)}")
    if anchor.get("ready_for_completion_candidate") is not None:
        lines.append(
            f"{indent}  ready_for_completion_candidate: "
            f"{str(bool(anchor.get('ready_for_completion_candidate'))).lower()}"
        )
    if anchor.get("expected_next"):
        lines.append(f"{indent}  expected_next: {anchor.get('expected_next')}")
    if anchor.get("satisfied") is False and anchor.get("missing_requirements"):
        missing = anchor.get("missing_requirements")
        if isinstance(missing, list) and missing:
            lines.append(f"{indent}  missing_requirements: {', '.join(str(x) for x in missing[:8])}")
    suppressed = anchor.get("completion_anchor_suppressed_flags")
    if isinstance(suppressed, list) and suppressed:
        lines.append(f"{indent}completion_anchor_suppressed_flags:")
        for row in suppressed[:4]:
            if not isinstance(row, Mapping):
                continue
            flag = row.get("flag")
            reason = row.get("reason")
            if flag and reason:
                lines.append(f"{indent}  - {flag}: {reason}")
    return lines
