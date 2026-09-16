"""Prompt-only ref windowing: exact refs for actionable context, summaries for cold tails."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_HOT_LATEST_REF_KEYS = frozenset(
    {
        "final",
        "working",
        "last_output",
        "latest_output",
        "active",
        "primary",
    }
)
_MAX_EXAMPLE_REFS = 2


def build_hot_latest_ref_keys(
    *,
    domain_closure_policy: Mapping[str, Any] | None = None,
    latest_refs: Mapping[str, Any] | None = None,
) -> frozenset[str]:
    """Mechanical latest-ref keys that must stay exact in prompt projection."""
    keys: set[str] = set(_HOT_LATEST_REF_KEYS)
    policy = domain_closure_policy if isinstance(domain_closure_policy, Mapping) else {}
    required_key = policy.get("required_output_ref_for_complete")
    if type(required_key) is str and required_key:
        keys.add(required_key)
        family_prefix = _output_family_prefix(required_key)
        if family_prefix and isinstance(latest_refs, Mapping):
            for raw_key, value in latest_refs.items():
                if type(raw_key) is not str:
                    continue
                if _is_output_family_working_tier(raw_key, family=family_prefix):
                    keys.add(raw_key)
                    continue
                ref_token = _string_token_for_working_tier_match(value)
                if ref_token is not None and _is_output_family_working_tier(
                    ref_token, family=family_prefix
                ):
                    keys.add(raw_key)
    return frozenset(keys)


def _output_family_prefix(required_output_key: Any) -> str | None:
    """Derive ``<family>`` from ``<family>:output``. Actual strings only."""
    if type(required_output_key) is not str:
        return None
    suffix = ":output"
    if not required_output_key.endswith(suffix):
        return None
    family = required_output_key[: -len(suffix)]
    return family or None


def _string_token_for_working_tier_match(value: Any) -> str | None:
    """Extract an actual string token for working-tier matching (no strip/coerce)."""
    if type(value) is str:
        return value
    if isinstance(value, Mapping):
        for key in ("ref", "artifact_ref", "derived_ref", "source_ref"):
            raw = value.get(key)
            if type(raw) is str:
                return raw
    return None


def _is_output_family_working_tier(token: Any, *, family: str) -> bool:
    """True when ``token`` is a delimiter-bounded member of ``<family>:working`` tier.

    Matches only:
    - ``<family>:working``
    - ``<family>:working:<suffix>``
    - ``<wrapper>:<family>:working``
    - ``<wrapper>:<family>:working:<suffix>``

    Requires an actual string. No ``str()`` coercion, case folding, strip, or
    bare substring matching across family boundaries.
    """
    if type(token) is not str or type(family) is not str or not family:
        return False
    bare = f"{family}:working"
    if token == bare or token.startswith(f"{bare}:"):
        return True
    wrapped = f":{family}:working"
    if token.endswith(wrapped):
        return True
    return f"{wrapped}:" in token


def _normalize_ref(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, Mapping):
        for key in ("ref", "artifact_ref", "derived_ref", "source_ref"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


def _ref_kind_prefix(ref: str) -> str:
    if "://" in ref:
        return ref.split("://", 1)[0]
    if ref.startswith("@"):
        return "@placeholder"
    return "other"


def collect_hot_refs_for_prompt(
    *,
    latest_refs: Mapping[str, Any] | None = None,
    pinned_refs_projection: Mapping[str, Any] | None = None,
    agent_requested_hydration: Mapping[str, Any] | None = None,
    recent_action_sequence_result: Mapping[str, Any] | None = None,
    delegate_subtask_results: Sequence[Mapping[str, Any]] | None = None,
    resolution_items: Sequence[Mapping[str, Any]] | None = None,
    active_item_id: str | None = None,
    hot_latest_ref_keys: frozenset[str] | None = None,
) -> frozenset[str]:
    """Mechanically gather refs that must stay exact in prompt projection."""
    hot: set[str] = set()
    hot_keys = hot_latest_ref_keys or _HOT_LATEST_REF_KEYS

    if isinstance(latest_refs, Mapping):
        for key, value in latest_refs.items():
            ref = _normalize_ref(value)
            if ref and str(key) in hot_keys:
                hot.add(ref)

    if isinstance(pinned_refs_projection, Mapping):
        for section in ("active", "expired"):
            rows = pinned_refs_projection.get(section) or []
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, Mapping):
                        ref = _normalize_ref(row.get("ref"))
                        if ref:
                            hot.add(ref)

    if isinstance(agent_requested_hydration, Mapping):
        for key in ("requested_refs", "resolved_refs"):
            refs = agent_requested_hydration.get(key) or []
            if isinstance(refs, list):
                for entry in refs:
                    ref = _normalize_ref(entry)
                    if ref:
                        hot.add(ref)

    if isinstance(recent_action_sequence_result, Mapping):
        items = recent_action_sequence_result.get("items") or []
        if isinstance(items, list):
            for row in items:
                if not isinstance(row, Mapping):
                    continue
                for key in ("artifact_ref", "derived_ref", "source_ref", "latest_artifact_ref"):
                    ref = _normalize_ref(row.get(key))
                    if ref:
                        hot.add(ref)
                refs = row.get("artifact_refs") or []
                if isinstance(refs, list):
                    for entry in refs:
                        ref = _normalize_ref(entry)
                        if ref:
                            hot.add(ref)
                delegate_ref = row.get("delegate_result_ref")
                if isinstance(delegate_ref, str) and delegate_ref.strip():
                    hot.add(delegate_ref.strip())

    if delegate_subtask_results:
        for record in delegate_subtask_results:
            if isinstance(record, Mapping):
                ref_id = _normalize_ref(record.get("ref_id"))
                if ref_id:
                    hot.add(ref_id)

    if resolution_items:
        for item in resolution_items:
            if not isinstance(item, Mapping):
                continue
            if active_item_id and item.get("item_id") == active_item_id:
                _collect_refs_from_mapping(item, hot)
            status = str(item.get("status") or "").strip().lower()
            if status in {"open", "active", "blocked", "in_review", "failed", "rejected"}:
                _collect_refs_from_mapping(item, hot)

    return frozenset(hot)


def _collect_refs_from_mapping(node: Mapping[str, Any], out: set[str]) -> None:
    refs = node.get("evidence_refs")
    if isinstance(refs, list):
        for entry in refs:
            ref = _normalize_ref(entry)
            if ref:
                out.add(ref)
    units = node.get("covered_units") or []
    if isinstance(units, list):
        for unit in units:
            if isinstance(unit, Mapping):
                status = str(unit.get("status") or "").strip().lower()
                if status in {"open", "active", "blocked", "in_review", "failed", "rejected"}:
                    _collect_refs_from_mapping(unit, out)


def project_refs_map_for_prompt(
    refs: Mapping[str, Any] | None,
    *,
    hot_refs: frozenset[str],
    hot_latest_ref_keys: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Window a ref map for prompt transport without mutating durable storage."""
    if not refs:
        return {}
    hot_keys = hot_latest_ref_keys or _HOT_LATEST_REF_KEYS
    exact: dict[str, Any] = {}
    counts_by_kind: dict[str, int] = {}
    omitted_count = 0
    example_refs: list[str] = []

    for key, value in refs.items():
        ref = _normalize_ref(value)
        if not ref:
            continue
        skey = str(key)
        if skey in hot_keys or ref in hot_refs:
            exact[skey] = value if isinstance(value, str) else ref
            continue
        kind = _ref_kind_prefix(ref)
        counts_by_kind[kind] = counts_by_kind.get(kind, 0) + 1
        omitted_count += 1
        if len(example_refs) < _MAX_EXAMPLE_REFS:
            example_refs.append(_short_ref_display(ref))

    out: dict[str, Any] = {}
    if exact:
        out["exact_refs"] = exact
    if omitted_count:
        out["summarized_refs"] = {
            "omitted_count": omitted_count,
            "counts_by_kind": counts_by_kind,
        }
        if example_refs:
            out["summarized_refs"]["example_refs"] = example_refs
    return out


def project_ref_list_for_prompt(
    refs: Sequence[Any] | None,
    *,
    hot_refs: frozenset[str],
    max_exact: int = 8,
) -> dict[str, Any]:
    """Window a flat ref list (e.g. evidence_refs) for cold prompt rows."""
    if not refs:
        return {}
    exact: list[str] = []
    counts_by_kind: dict[str, int] = {}
    omitted = 0
    for entry in refs:
        ref = _normalize_ref(entry)
        if not ref:
            continue
        if ref in hot_refs and len(exact) < max_exact:
            exact.append(ref)
            continue
        if ref in hot_refs:
            continue
        kind = _ref_kind_prefix(ref)
        counts_by_kind[kind] = counts_by_kind.get(kind, 0) + 1
        omitted += 1
    out: dict[str, Any] = {"evidence_ref_count": len(list(refs))}
    if exact:
        out["evidence_refs"] = exact
    if omitted:
        out["evidence_refs_summarized"] = {
            "omitted_count": omitted,
            "counts_by_kind": counts_by_kind,
        }
    return out


def _short_ref_display(ref: str, *, max_len: int = 72) -> str:
    if len(ref) <= max_len:
        return ref
    return ref[: max_len - 3] + "..."
