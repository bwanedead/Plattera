"""Deed-to-IR capability requirements.

This is the domain-owned declaration surface for what the deed pack needs.
Product composition still owns the concrete provider wiring.
"""

from __future__ import annotations

from domains.common.domain_pack_contracts import CapabilityRequirement


def build_deed_to_ir_capability_requirements() -> tuple[CapabilityRequirement, ...]:
    """Return the capability requirements the deed pack declares."""

    return (
        CapabilityRequirement(
            capability_id="retrieve_evidence",
            required=True,
            category="evidence",
            notes="Needs bounded evidence retrieval and artifact inspection.",
        ),
        CapabilityRequirement(
            capability_id="edit_application",
            required=True,
            category="execution",
            notes="Needs kernel-backed action execution for deed steps.",
        ),
        CapabilityRequirement(
            capability_id="feedback_prompting",
            required=False,
            category="feedback",
            notes="May prompt for human choice when transition is blocked.",
        ),
    )


