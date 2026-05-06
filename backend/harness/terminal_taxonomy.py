from __future__ import annotations

from typing import Literal

TerminalClass = Literal[
    "completed",
    "blocked",
    "waiting_human",
    "waiting_evidence",
    "exhausted",
    "failed",
    "paused",
    "stopped",
]

TerminalArtifactPosture = Literal[
    "completed_with_output",
    "completed_with_working_artifact",
    "blocked_with_working_artifact",
    "failed_or_recoverable_error",
]


def _is_working_ref(key: str) -> bool:
    return (
        key == "working"
        or key.startswith("working:")
        or key.endswith(":working")
        or ":working:" in key
    )


def classify_terminal_artifact_posture(
    terminal_class: TerminalClass | None,
    ref_keys: list[str],
) -> TerminalArtifactPosture | None:
    """Classify the run's artifact posture from terminal class and ref key names.

    Ref keys ending with ":output" are final output-tier deliverables.
    Ref keys starting with "working:" are working/draft-tier artifacts.
    All other refs (evidence, source, derived images, etc.) are not classified.
    Returns None when posture cannot be determined.
    """
    if not terminal_class:
        return None
    has_output_ref = any(k and k.endswith(":output") for k in ref_keys)
    has_working_ref = any(k and _is_working_ref(k) for k in ref_keys)
    if terminal_class == "completed":
        if has_output_ref:
            return "completed_with_output"
        if has_working_ref:
            return "completed_with_working_artifact"
        return None
    if terminal_class in {"blocked", "waiting_human", "waiting_evidence", "exhausted"}:
        if has_working_ref:
            return "blocked_with_working_artifact"
        return None
    if terminal_class in {"failed", "paused", "stopped"}:
        return "failed_or_recoverable_error"
    return None
