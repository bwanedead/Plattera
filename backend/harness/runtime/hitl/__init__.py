from .request_shape import normalize_hitl_request, validate_hitl_consumed_prompt_ids
from .transport import HitlState, HitlTransportPosture
from .watch import hitl_pending_path, run_watch, write_hitl_operator_sidecar

__all__ = [
    "HitlState",
    "HitlTransportPosture",
    "hitl_pending_path",
    "inject",
    "normalize_hitl_request",
    "run_watch",
    "validate_hitl_consumed_prompt_ids",
    "write_hitl_operator_sidecar",
]


def __getattr__(name: str):
    if name == "inject":
        from .inject import inject

        return inject
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
