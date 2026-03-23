"""Transcript-edit domain execution action ids (owned by the domain pack, not the harness core).

Use these strings with ``KernelStepRequest.action_type`` and provider registration — they are
not members of ``agent_kernel.harness_action_ids.HarnessAction``.
"""

from __future__ import annotations

TX_AUDIT_TRANSCRIPT = "tx_audit_transcript"
TX_ORIENT_AND_BASELINE = "tx_orient_and_baseline"
TX_OPEN_TRANSCRIPT_SPANS = "tx_open_transcript_spans"
TX_VERIFY_TRANSCRIPT_WITH_IMAGE = "tx_verify_transcript_with_image"
TX_SAVE_TRANSCRIPT_SPAN_SEEDS = "tx_save_transcript_span_seeds"
TX_APPLY_EDIT_PLAN = "tx_apply_edit_plan"
TX_PROMOTE_TRANSCRIPT_FOR_MAPPING = "tx_promote_transcript_for_mapping"
