"""Continuity memory compaction subsystem.

Owns the full compaction cycle: trigger decision, prompt fitting and construction,
LLM response parsing, and continuity state update after a successful compaction run.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..orchestration.llm_prompt_builder import build_compaction_prompt_document
from .continuity import OrchestrationContinuity
from .continuity_journal import (
    clamp_compacted_summary_text,
    clamp_compaction_prior_for_prompt,
    fold_rows_not_yet_sent_to_compaction,
    kernel_turn_index_of,
    max_kernel_turn_in_rows,
    partition_continuity_for_compaction,
    recent_journal_entries_for_prompt,
    recent_step_records_for_prompt,
    recent_step_result_records_for_prompt,
)
from .openai_model_limits import estimate_prompt_tokens_from_chars, resolve_context_window_tokens

_LOG = logging.getLogger(__name__)


@dataclass
class PreparedContinuityCompaction:
    """All data required to execute and trace a single compaction LLM call."""

    compact_prompt: str
    j_send: list[dict[str, Any]]
    s_send: list[dict[str, Any]]
    r_send: list[dict[str, Any]]
    trigger_mode: str
    trace_threshold: int | None
    est_chars: int
    est_tokens: int | None
    cw_tokens: int | None
    used_fb: bool | None
    occ_frac: float | None
    trigger_fraction: float | None


def prepare_continuity_compaction(
    *,
    cont: OrchestrationContinuity,
    choose_action_prompt: str,
    model_name: str,
    trigger_fraction: float | None,
    char_threshold: int | None,
    max_compact_chars: int | None,
    keep_n: int,
) -> PreparedContinuityCompaction | None:
    """Evaluate trigger criteria and build a compaction prompt; returns ``None`` to skip."""
    use_fraction = trigger_fraction is not None and float(trigger_fraction) > 0
    use_legacy = not use_fraction and char_threshold is not None and int(char_threshold) > 0
    if not use_fraction and not use_legacy:
        return None

    est_chars = len(choose_action_prompt)
    trace_threshold: int | None = None
    trigger_mode: str
    est_tokens: int | None = None
    cw_tokens: int | None = None
    used_fb: bool | None = None
    occ_frac: float | None = None
    resolved_fraction: float | None = None
    max_compact: int

    if use_fraction:
        est_chars = _occupancy_char_estimate(
            choose_action_prompt=choose_action_prompt,
            compacted_continuity_summary=cont.compacted_continuity_summary,
            continuity_journal_entries=cont.continuity_journal_entries,
            kernel_step_records=cont.kernel_step_records,
            kernel_step_result_records=cont.kernel_step_result_records,
            keep_n=keep_n,
        )
        cw_tokens, used_fb = resolve_context_window_tokens(model_name)
        est_tokens = estimate_prompt_tokens_from_chars(est_chars)
        occ_frac = float(est_tokens) / float(cw_tokens)
        resolved_fraction = float(trigger_fraction)  # type: ignore[arg-type]
        if occ_frac < resolved_fraction:
            return None
        if max_compact_chars is None or max_compact_chars <= 0:
            max_compact = max(48_000, min(200_000, int(cw_tokens) * 2))
        else:
            max_compact = max_compact_chars
        trigger_mode = "occupancy_fraction"
    else:
        assert char_threshold is not None
        if est_chars < int(char_threshold):
            return None
        if max_compact_chars is None or max_compact_chars <= 0:
            max_compact = max(int(char_threshold) * 2, 48_000)
        else:
            max_compact = max_compact_chars
        trace_threshold = int(char_threshold)
        trigger_mode = "legacy_char_threshold"

    target_summary_chars = _target_summary_char_budget(max_compact)
    j_fold, s_fold, r_fold = partition_continuity_for_compaction(
        cont.continuity_journal_entries,
        cont.kernel_step_records,
        cont.kernel_step_result_records,
        keep_n=keep_n,
    )
    j_fold, s_fold, r_fold = fold_rows_not_yet_sent_to_compaction(
        j_fold,
        s_fold,
        r_fold,
        covered_through_turn_index=cont.kernel_compaction_covered_through_turn_index,
    )
    if not j_fold and not s_fold and not r_fold:
        return None

    fit = _fit_compaction_prompt_parts(
        cont.compacted_continuity_summary,
        j_fold,
        s_fold,
        r_fold,
        max_chars=max_compact,
        target_compacted_summary_chars=target_summary_chars,
    )
    if fit is None:
        return None
    prior_out, j_send, s_send, r_send = fit
    if not j_send and not s_send and not r_send:
        return None

    compact_prompt = _build_compaction_prompt(
        prior_compacted_continuity_summary=prior_out,
        journal_entries_to_fold=j_send,
        kernel_step_records_to_fold=s_send,
        kernel_step_result_records_to_fold=r_send,
        target_compacted_summary_chars=target_summary_chars,
    )
    return PreparedContinuityCompaction(
        compact_prompt=compact_prompt,
        j_send=j_send,
        s_send=s_send,
        r_send=r_send,
        trigger_mode=trigger_mode,
        trace_threshold=trace_threshold,
        est_chars=est_chars,
        est_tokens=est_tokens,
        cw_tokens=cw_tokens,
        used_fb=used_fb,
        occ_frac=occ_frac,
        trigger_fraction=resolved_fraction,
    )


def parse_compaction_response(raw_response: Mapping[str, Any] | str) -> str:
    """Parse a raw LLM compaction response into a summary string; raises ``ValueError`` on failure."""
    text = _extract_compaction_text(raw_response)
    try:
        payload = json.loads(text)
    except Exception as exc:
        raise ValueError("compaction output was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("compaction output must be a JSON object")
    extra = set(payload.keys()) - {"compacted_continuity_summary"}
    if extra:
        raise ValueError(f"unexpected compaction keys: {', '.join(sorted(extra))}")
    raw_summary = payload.get("compacted_continuity_summary")
    if not isinstance(raw_summary, str):
        raise ValueError("compacted_continuity_summary must be a string")
    out = clamp_compacted_summary_text(raw_summary)
    if out is None:
        raise ValueError("compacted_continuity_summary was empty")
    return out


def apply_continuity_compaction_result(
    cont: OrchestrationContinuity,
    prepared: PreparedContinuityCompaction,
    summary: str,
) -> None:
    """Write compaction summary and advance the watermark in continuity memory."""
    cont.compacted_continuity_summary = summary
    mx = max_kernel_turn_in_rows(prepared.j_send, prepared.s_send, prepared.r_send)
    if mx is not None:
        cont.kernel_compaction_covered_through_turn_index = max(
            int(cont.kernel_compaction_covered_through_turn_index),
            int(mx),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _target_summary_char_budget(max_prompt_chars: int) -> int:
    return min(12_000, max(800, int(max_prompt_chars) // 6))


def _occupancy_char_estimate(
    *,
    choose_action_prompt: str,
    compacted_continuity_summary: str | None,
    continuity_journal_entries: list[dict[str, Any]],
    kernel_step_records: list[dict[str, Any]],
    kernel_step_result_records: list[dict[str, Any]],
    keep_n: int,
) -> int:
    """Upper-bound occupancy estimate: prompt + full carriage - double-counted verbatim tail."""
    carriage_blob = json.dumps(
        {
            "compacted_continuity_summary": compacted_continuity_summary,
            "continuity_journal_entries": continuity_journal_entries,
            "kernel_step_records": kernel_step_records,
            "kernel_step_result_records": kernel_step_result_records,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    overlap_payload = {
        "compacted_continuity_summary": compacted_continuity_summary,
        "recent_continuity_journal_entries": recent_journal_entries_for_prompt(
            continuity_journal_entries, kernel_step_records, kernel_step_result_records, keep_n=keep_n,
        ),
        "recent_kernel_step_records": recent_step_records_for_prompt(
            continuity_journal_entries, kernel_step_records, kernel_step_result_records, keep_n=keep_n,
        ),
        "recent_kernel_step_result_records": recent_step_result_records_for_prompt(
            continuity_journal_entries, kernel_step_records, kernel_step_result_records, keep_n=keep_n,
        ),
    }
    overlap_blob = json.dumps(overlap_payload, ensure_ascii=False, sort_keys=True, default=str)
    combined = len(choose_action_prompt) + len(carriage_blob) - len(overlap_blob)
    return max(combined, len(choose_action_prompt))


def _fit_compaction_prompt_parts(
    prior_full: str | None,
    j_fold: list[dict[str, Any]],
    s_fold: list[dict[str, Any]],
    r_fold: list[dict[str, Any]],
    max_chars: int,
    *,
    target_compacted_summary_chars: int,
) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Mechanically fit compaction prompt under ``max_chars``: drop newest fold turns first, then shorten prior."""
    prior = clamp_compaction_prior_for_prompt(prior_full) if prior_full else None
    j_src, s_src, r_src = list(j_fold), list(s_fold), list(r_fold)
    turns = sorted(
        {t for row in j_src + s_src + r_src for t in [kernel_turn_index_of(row)] if t is not None}
    )
    active: set[int] = set(turns)
    while True:
        j = [e for e in j_src if kernel_turn_index_of(e) in active]
        s = [r for r in s_src if kernel_turn_index_of(r) in active]
        rr = [x for x in r_src if kernel_turn_index_of(x) in active]
        plen = len(
            _build_compaction_prompt(
                prior_compacted_continuity_summary=prior,
                journal_entries_to_fold=j,
                kernel_step_records_to_fold=s,
                kernel_step_result_records_to_fold=rr,
                target_compacted_summary_chars=target_compacted_summary_chars,
            )
        )
        if plen <= max_chars:
            return prior, j, s, rr
        if active:
            active.remove(max(active))
            continue
        if prior:
            if len(prior) <= 500:
                prior = None
            else:
                prior = prior[: max(len(prior) - 4000, 0)].strip() or None
            continue
        _LOG.warning("compaction prompt cannot fit under max_chars=%s; skipping", max_chars)
        return None


def _build_compaction_prompt(
    *,
    prior_compacted_continuity_summary: str | None,
    journal_entries_to_fold: list[dict[str, Any]],
    kernel_step_records_to_fold: list[dict[str, Any]],
    kernel_step_result_records_to_fold: list[dict[str, Any]],
    target_compacted_summary_chars: int,
) -> str:
    return build_compaction_prompt_document(
        prior_compacted_continuity_summary=prior_compacted_continuity_summary,
        journal_entries_to_fold=journal_entries_to_fold,
        kernel_step_records_to_fold=kernel_step_records_to_fold,
        kernel_step_result_records_to_fold=kernel_step_result_records_to_fold,
        target_compacted_summary_chars=target_compacted_summary_chars,
    ).prompt_text


def _extract_compaction_text(raw_response: Mapping[str, Any] | str) -> str:
    if isinstance(raw_response, str):
        text = raw_response.strip()
        if not text:
            raise ValueError("compaction model output was empty")
        return text
    if raw_response.get("success") is False:
        raise ValueError(str(raw_response.get("error") or "compaction model caller reported failure"))
    for key in ("text", "content", "output_text"):
        value = raw_response.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("compaction model caller did not return text")
