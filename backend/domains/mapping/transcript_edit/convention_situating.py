from __future__ import annotations

import re
from typing import Any

_CONVENTIONS = {"plss", "metes_and_bounds", "lot_block", "hybrid", "unknown"}

_PLSS_PATTERNS = [
    r"\btownship\b",
    r"\brange\b",
    r"\bsection\b",
    r"\bt\.\s*\d+",
    r"\br\.\s*\d+",
    r"\bsec\.\s*\d+",
]
_METES_AND_BOUNDS_PATTERNS = [
    r"\bthence\b",
    r"\bpoint of beginning\b",
    r"\bpob\b",
    r"\bbearing\b",
    r"\bdegrees?\b",
    r"\bminutes?\b",
    r"\bseconds?\b",
    r"\bfeet\b",
    r"\bchains?\b",
]
_LOT_BLOCK_PATTERNS = [
    r"\blot\b",
    r"\bblock\b",
    r"\bsubdivision\b",
    r"\bplat\b",
    r"\baddition\b",
    r"\bplat book\b",
]


def situate_document_convention(
    *,
    orient_items: list[dict[str, Any]] | None,
    findings: list[dict[str, Any]] | None = None,
    source_text_excerpt: str | None = None,
) -> dict[str, Any]:
    texts = _collect_text_signals(
        orient_items=orient_items or [],
        findings=findings or [],
        source_text_excerpt=source_text_excerpt,
    )
    plss_hits = _match_patterns(texts=texts, patterns=_PLSS_PATTERNS)
    mab_hits = _match_patterns(texts=texts, patterns=_METES_AND_BOUNDS_PATTERNS)
    lot_hits = _match_patterns(texts=texts, patterns=_LOT_BLOCK_PATTERNS)
    scores = {
        "plss": len(plss_hits),
        "metes_and_bounds": len(mab_hits),
        "lot_block": len(lot_hits),
    }
    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_name, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1]
    if top_score <= 0:
        convention = "unknown"
    elif second_score > 0 and abs(top_score - second_score) <= 1:
        convention = "hybrid"
    else:
        convention = top_name
    confidence = _confidence_from_scores(top_score=top_score, second_score=second_score, convention=convention)
    signals = []
    for value in plss_hits[:4]:
        signals.append({"family": "plss", "signal": value})
    for value in mab_hits[:4]:
        signals.append({"family": "metes_and_bounds", "signal": value})
    for value in lot_hits[:4]:
        signals.append({"family": "lot_block", "signal": value})
    signals = signals[:8]
    return {
        "document_convention": convention if convention in _CONVENTIONS else "unknown",
        "convention_confidence": confidence,
        "convention_signals": signals,
        "menu_family_candidates": _menu_families_for_convention(convention),
        "convention_scorecard": scores,
    }


def _collect_text_signals(
    *,
    orient_items: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    source_text_excerpt: str | None,
) -> str:
    chunks: list[str] = []
    if source_text_excerpt:
        chunks.append(str(source_text_excerpt))
    for row in orient_items:
        if not isinstance(row, dict):
            continue
        chunks.append(str(row.get("key") or ""))
        chunks.append(str(row.get("label") or ""))
        chunks.append(str(row.get("selected_value") or ""))
        chunks.extend(str(value) for value in list(row.get("alternatives") or []))
        chunks.append(str(row.get("required_information") or ""))
        chunks.append(str(row.get("minimal_user_action") or ""))
    for row in findings:
        if not isinstance(row, dict):
            continue
        chunks.append(str(row.get("message") or ""))
        chunks.append(str(row.get("finding_type") or ""))
    return " \n ".join(chunk for chunk in chunks if str(chunk).strip())


def _match_patterns(*, texts: str, patterns: list[str]) -> list[str]:
    if not texts:
        return []
    out: list[str] = []
    lowered = texts.lower()
    for pattern in patterns:
        if re.search(pattern, lowered):
            out.append(pattern)
    return out


def _confidence_from_scores(*, top_score: int, second_score: int, convention: str) -> float:
    if convention == "unknown":
        return 0.2
    spread = max(0, int(top_score) - int(second_score))
    return round(min(0.95, 0.5 + 0.08 * int(top_score) + 0.05 * spread), 2)


def _menu_families_for_convention(convention: str) -> list[str]:
    normalized = str(convention or "").strip().lower()
    if normalized == "plss":
        return ["plss", "source_quality", "cross_convention_core"]
    if normalized == "metes_and_bounds":
        return ["metes_and_bounds", "source_quality", "cross_convention_core"]
    if normalized == "lot_block":
        return ["lot_block", "source_quality", "cross_convention_core"]
    if normalized == "hybrid":
        return ["hybrid", "plss", "metes_and_bounds", "lot_block", "source_quality", "cross_convention_core"]
    return ["unknown", "source_quality", "cross_convention_core"]
