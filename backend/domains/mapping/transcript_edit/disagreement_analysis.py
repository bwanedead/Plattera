from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from tooling.mapping.transcription_edit.span_seeds import load_transcript_text_for_seeds


def has_blocking_warnings(top_findings: list[dict[str, Any]]) -> bool:
    """Phase 24: use severity only — no validator finding_type / finding_id semantics."""
    for finding in top_findings:
        if not isinstance(finding, dict):
            continue
        severity = str(finding.get("severity") or "").strip().lower()
        if severity in {"error", "critical"}:
            return True
    return False


def candidate_disagreement_hints(candidate_texts: list[str]) -> dict[str, Any]:
    if not isinstance(candidate_texts, list) or len(candidate_texts) <= 1:
        return {}
    ranges: dict[str, int] = {}
    acreages: dict[str, int] = {}
    tie_distances: dict[str, int] = {}
    bearings: dict[str, int] = {}
    range_patterns = [
        re.compile(r"\brange[^()]{0,60}\((\d{1,3})\)\s*(west|east)\b", re.IGNORECASE),
        re.compile(r"\br\s*\.?\s*(\d{1,3})\s*([we])\b", re.IGNORECASE),
    ]
    acreage_pattern = re.compile(r"\b(\d+(?:\.\d+)?)\s*acres?\b", re.IGNORECASE)
    distance_pattern = re.compile(r"\b(\d{2,5}(?:\.\d+)?)\s*(?:ft|feet)\b", re.IGNORECASE)
    bearing_pattern = re.compile(r"\b[NS]\.?\s*\d{1,3}(?:\s*°\s*\d{1,2})?\s*(?:[EW]\.?|east|west)\b", re.IGNORECASE)

    def _inc(bucket: dict[str, int], key: str) -> None:
        bucket[key] = bucket.get(key, 0) + 1

    for text in candidate_texts[:10]:
        if not isinstance(text, str):
            continue
        for pat in range_patterns:
            for m in pat.finditer(text):
                number = m.group(1)
                direction = m.group(2).lower()
                direction = "w" if direction.startswith("w") else "e"
                _inc(ranges, f"r{number}{direction}")
        for m in acreage_pattern.finditer(text):
            _inc(acreages, m.group(1))
        for m in distance_pattern.finditer(text):
            _inc(tie_distances, m.group(1))
        for m in bearing_pattern.finditer(text):
            _inc(bearings, re.sub(r"\s+", " ", m.group(0).strip().lower()))

    def _sorted_counts(bucket: dict[str, int]) -> list[dict[str, Any]]:
        return [
            {"value": key, "count": count}
            for key, count in sorted(bucket.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        ]

    return {
        "candidate_count": len(candidate_texts[:10]),
        "range_values": _sorted_counts(ranges),
        "acreage_values": _sorted_counts(acreages),
        "distance_values": _sorted_counts(tie_distances),
        "bearing_values": _sorted_counts(bearings),
    }


def resolved_disagreement_hints(
    *,
    disagreement_hints: dict[str, Any],
    sticky_range_selection: int | None,
) -> dict[str, Any]:
    if not isinstance(disagreement_hints, dict):
        return {}
    resolved = dict(disagreement_hints)
    if sticky_range_selection is not None:
        token_w = f"r{sticky_range_selection}w"
        token_e = f"r{sticky_range_selection}e"
        range_values = resolved.get("range_values")
        if isinstance(range_values, list):
            selected: dict[str, Any] | None = None
            for item in range_values:
                if not isinstance(item, dict):
                    continue
                value = str(item.get("value") or "").strip().lower()
                if value in {token_w, token_e}:
                    selected = {
                        "value": value,
                        "count": _read_int(item.get("count"), 1),
                    }
                    break
            if selected is None:
                selected = {"value": token_w, "count": max(1, _read_int(resolved.get("candidate_count"), 1))}
            resolved["range_values"] = [selected]
    return resolved


def extract_numeric_literals(message: str) -> list[str]:
    out: list[str] = []
    if not isinstance(message, str):
        return out
    for token in re.findall(r"\b\d{1,5}(?:\.\d+)?\b", message):
        out.append(token)
    return out[:6]


def image_checks_from_disagreement_hints(disagreement_hints: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if not isinstance(disagreement_hints, dict):
        return checks
    range_values = disagreement_hints.get("range_values")
    if isinstance(range_values, list) and len(range_values) > 1:
        checks.append(
            {
                "check_id": "image_check_range_tokens",
                "query": (
                    "Read the deed and list all explicit range numbers shown near township/section clauses. "
                    "Include both if more than one appears."
                ),
                "expected_text": None,
            }
        )
    distance_values = disagreement_hints.get("distance_values")
    if isinstance(distance_values, list) and len(distance_values) > 1:
        checks.append(
            {
                "check_id": "image_check_tie_distance",
                "query": (
                    "What is the numeric distance in feet in the clause containing 'Northwest corner bears ... feet distant'? "
                    "Return the exact number."
                ),
                "expected_text": None,
            }
        )
    acreage_values = disagreement_hints.get("acreage_values")
    if isinstance(acreage_values, list) and len(acreage_values) > 1:
        checks.append(
            {
                "check_id": "image_check_acreage",
                "query": (
                    "What acreage value is stated for the first parcel near 'containing ... acres'? "
                    "Return the exact number."
                ),
                "expected_text": None,
            }
        )
    bearing_values = disagreement_hints.get("bearing_values")
    if isinstance(bearing_values, list) and len(bearing_values) > 1:
        checks.append(
            {
                "check_id": "image_check_bearing_tokens",
                "query": (
                    "Read the deed image and report the exact bearing token used in the tie/call clause "
                    "(for example, include degree value/minutes and direction letters exactly)."
                ),
                "expected_text": None,
            }
        )
    return checks[:6]


def image_numeric_signals(image_verification: dict[str, Any]) -> dict[str, str | None]:
    out: dict[str, str | None] = {
        "tie_distance": None,
        "tie_distance_strength": None,
        "acreage": None,
        "acreage_strength": None,
    }
    if not isinstance(image_verification, dict):
        return out
    raw_results = image_verification.get("results")
    if not isinstance(raw_results, list):
        return out
    for item in raw_results[:12]:
        if not isinstance(item, dict):
            continue
        check_id = str(item.get("check_id") or "").strip().lower()
        confidence = str(item.get("confidence") or "").strip().lower()
        observed = str(item.get("observed_text") or "")
        numbers = re.findall(r"\b\d{1,5}(?:\.\d+)?\b", observed)
        if check_id == "image_check_tie_distance" and confidence == "high":
            numeric = first_numeric_like(numbers, minimum=500.0)
            if numeric:
                out["tie_distance"] = numeric
                out["tie_distance_strength"] = confidence
        if check_id == "image_check_acreage" and confidence in {"medium", "high"}:
            numeric = first_numeric_like(numbers, minimum=0.1, maximum=1000.0)
            if numeric:
                out["acreage"] = numeric
                out["acreage_strength"] = confidence
    return out


def first_numeric_like(
    values: list[str],
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> str | None:
    for raw in values:
        try:
            value = float(raw)
        except Exception:
            continue
        if minimum is not None and value < minimum:
            continue
        if maximum is not None and value > maximum:
            continue
        return raw
    return None


def first_expected_token_from_message(message: str) -> str | None:
    if not isinstance(message, str):
        return None
    token_match = re.search(r"'([^']{1,80})'", message)
    if token_match:
        return token_match.group(1)
    number_match = re.search(r"\b\d{1,5}(?:\.\d+)?\b", message)
    if number_match:
        return number_match.group(0)
    return None


def _severity_rank(sev: str) -> int:
    s = str(sev or "").strip().lower()
    return {"critical": 0, "error": 1, "warning": 2, "info": 3, "low": 4, "debug": 5}.get(s, 9)


def prioritized_findings_for_planning(*, top_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Phase 24: order evidence by severity — no validator taxonomy ranking."""
    if not isinstance(top_findings, list):
        return []
    normalized: list[dict[str, Any]] = [finding for finding in top_findings if isinstance(finding, dict)]
    normalized.sort(key=lambda f: _severity_rank(str(f.get("severity") or "")))
    return normalized[:12]


def mapping_priority_focus(disagreement_hints: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(disagreement_hints, dict):
        return {}
    return {
        "mapping_critical_fields": [
            "plss",
            "tie_to_corner_distance",
            "bearings",
            "call_chain_closure",
            "acreage",
        ],
        "disagreement_snapshot": {
            "range_values": disagreement_hints.get("range_values") or [],
            "distance_values": disagreement_hints.get("distance_values") or [],
            "bearing_values": disagreement_hints.get("bearing_values") or [],
            "acreage_values": disagreement_hints.get("acreage_values") or [],
        },
    }


def critical_disagreement_findings(disagreement_hints: dict[str, Any]) -> list[dict[str, Any]]:
    """Phase 24: deterministic synthetic findings removed — surface disagreements via LLM/evidence only."""
    _ = disagreement_hints
    return []


def build_deterministic_consensus_plan(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    disagreement_hints: dict[str, Any],
    image_verification: dict[str, Any],
    top_findings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Phase 24: deterministic consensus edit plans are retired — planning is LLM-owned."""
    _ = (
        source_transcript_ref,
        source_transcript_hash,
        disagreement_hints,
        image_verification,
        top_findings,
    )
    return None


def deterministic_numeric_replace_op(
    *,
    text: str,
    bucket: Any,
    value_regex: str,
    value_guard,
    op_id: str,
    reason: str,
    preferred_value: str | None = None,
    preferred_strength: str | None = None,
) -> dict[str, Any] | None:
    dominant_value: str | None = None
    if preferred_value and preferred_strength == "high":
        dominant_value = str(preferred_value)
    else:
        winner = dominant_bucket_value(bucket)
        if winner is None:
            return None
        dominant_value, dominant_count, total = winner
        if total < 3 or dominant_count < max(2, total - 1):
            return None
    if dominant_value is None:
        return None
    if not value_guard(dominant_value):
        return None
    pattern = re.compile(value_regex, re.IGNORECASE)
    for match in pattern.finditer(text):
        current_value = str(match.group(1))
        unit = str(match.group(2))
        if current_value == dominant_value:
            continue
        old_excerpt = match.group(0)
        new_excerpt = f"{dominant_value} {unit}"
        return {
            "op_id": op_id,
            "op_type": "replace_span",
            "change_class": "semantic",
            "confidence": "medium",
            "review_required": True,
            "reason": reason,
            "evidence_refs": [],
            "target": {
                "locator_type": "offsets",
                "start_char": int(match.start()),
                "end_char": int(match.end()),
            },
            "expected_old": {"old_excerpt": old_excerpt},
            "new_text": new_excerpt,
        }
    return None


def dominant_bucket_value(bucket: Any) -> tuple[str, int, int] | None:
    if not isinstance(bucket, list):
        return None
    parsed: list[tuple[str, int]] = []
    for item in bucket[:8]:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        count = item.get("count")
        if value is None:
            continue
        try:
            count_i = int(count)
        except Exception:
            continue
        parsed.append((str(value), count_i))
    if len(parsed) < 2:
        return None
    total = sum(max(0, c) for _, c in parsed)
    parsed.sort(key=lambda kv: (-kv[1], kv[0]))
    return parsed[0][0], parsed[0][1], total


def merge_findings_summary_with_disagreement(
    *,
    findings_summary: dict[str, Any],
    disagreement_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = dict(findings_summary) if isinstance(findings_summary, dict) else {}
    total = int(summary.get("total") or 0)
    warnings = int(summary.get("warnings") or 0)
    errors = int(summary.get("errors") or 0)
    infos = int(summary.get("infos") or 0)
    for finding in disagreement_findings:
        severity = str(finding.get("severity") or "").strip().lower()
        total += 1
        if severity == "warning":
            warnings += 1
        elif severity == "error":
            errors += 1
        elif severity == "info":
            infos += 1
    summary["total"] = total
    summary["warnings"] = warnings
    summary["errors"] = errors
    summary["infos"] = infos
    return summary


def is_critical_tie_distance(value: Any) -> bool:
    try:
        number = float(str(value))
    except Exception:
        return False
    return number >= 900.0


def _read_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


