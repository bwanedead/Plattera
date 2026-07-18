"""Orchestration bridge for BR-017 pending-result delivery (mechanical only).

Admits typed ActionDispatchResult rows, projects them into prompt structured_state,
and acknowledges real model contacts. Does not interpret schema IDs, continuity-key
prefixes, or domain payloads.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from harness.execution.contracts import ExecutionStepResult
from harness.runtime.memory.result_delivery import (
    MAX_CONTACT_ID_CHARS,
    ContactReceipt,
    admit_pending_result_delivery,
    acknowledge_result_delivery_contacts,
    project_latest_action_results,
)

_LOG = logging.getLogger(__name__)

_PRIMARY_KERNEL_PROMPT_SURFACE = "orchestration_kernel_choose_action"


@dataclass(frozen=True)
class ResultDeliveryContactMetadata:
    """Non-serialized prompt-document metadata for later contact acknowledgement."""

    contact_id: str
    contact_receipt: ContactReceipt
    active_attention_refs: tuple[str, ...]


def make_result_delivery_contact_id(
    *,
    request_id_prefix: str,
    iteration: int,
    prompt_mode: str,
) -> str:
    """Stable, bounded contact ID for one semantic prompt surface.

    Same (prefix, iteration, mode) always yields the same ID so replay cannot
    falsely satisfy the two-contact requirement. Does not derive from prompt body.
    """
    prefix = str(request_id_prefix or "").strip() or "req"
    mode = str(prompt_mode or "").strip() or "full_choose_action"
    raw = f"{prefix}|{int(iteration)}|{mode}|{_PRIMARY_KERNEL_PROMPT_SURFACE}"
    if len(raw) <= MAX_CONTACT_ID_CHARS:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def admit_recorded_execution_result(
    deliveries: list[dict[str, Any]],
    *,
    step_result: ExecutionStepResult,
    source_turn_index: int,
    action_index: int,
    action_alias: str,
) -> None:
    """Admit one recorded execution result when a typed ActionDispatchResult exists.

    No-ops when there is no recorded result (dispatch exceptions, skips, empty
    records). Rejected admissions log a mechanical warning and do not rewrite the
    action result.
    """
    if step_result.record is None:
        return
    alias = str(action_alias or "").strip() or f"action{int(action_index)}"
    outcome = admit_pending_result_delivery(
        deliveries,
        result=step_result.record.result,
        source_turn_index=int(source_turn_index),
        action_index=int(action_index),
        action_alias=alias,
        execution_state=step_result.execution_state.value,
    )
    if outcome.status == "rejected":
        _LOG.warning(
            "pending_result_delivery_admission_rejected reason_code=%s delivery_id=%s "
            "source_turn_index=%s action_index=%s action_alias=%s",
            outcome.reason_code,
            outcome.delivery_id,
            int(source_turn_index),
            int(action_index),
            alias,
        )


def project_pending_results_for_prompt(
    pending_result_deliveries: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]] | None, ContactReceipt]:
    """Pure projection helper. Returns (lane_or_None, receipt). Never mutates state."""
    projection = project_latest_action_results(list(pending_result_deliveries))
    if not projection.latest_action_results:
        return None, ContactReceipt()
    return projection.latest_action_results, projection.contact_receipt


def build_result_delivery_contact_metadata(
    *,
    request_id_prefix: str,
    iteration: int,
    prompt_mode: str,
    contact_receipt: ContactReceipt,
    active_attention_refs: Sequence[str] | frozenset[str] | set[str],
) -> ResultDeliveryContactMetadata | None:
    """Attach contact metadata when the projected lane exposed any delivery rows."""
    if (
        not contact_receipt.content_exposed_delivery_ids
        and not contact_receipt.lane_budget_delivery_ids
    ):
        return None
    refs = tuple(
        sorted(
            {
                str(item).strip()
                for item in active_attention_refs
                if isinstance(item, str) and item.strip()
            }
        )
    )
    return ResultDeliveryContactMetadata(
        contact_id=make_result_delivery_contact_id(
            request_id_prefix=request_id_prefix,
            iteration=iteration,
            prompt_mode=prompt_mode,
        ),
        contact_receipt=contact_receipt,
        active_attention_refs=refs,
    )


def acknowledge_prompt_result_delivery_contact(
    deliveries: list[dict[str, Any]],
    *,
    metadata: ResultDeliveryContactMetadata | None,
) -> None:
    """Acknowledge a real model contact for the exact projected lane. Mutates deliveries."""
    if metadata is None:
        return
    acknowledge_result_delivery_contacts(
        deliveries,
        contact_id=metadata.contact_id,
        receipt=metadata.contact_receipt,
        active_attention_refs=metadata.active_attention_refs,
    )
