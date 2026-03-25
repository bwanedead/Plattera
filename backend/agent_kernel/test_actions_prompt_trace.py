from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.actions import ActionExecutor, ActionExecutorDeps, RegisteredProviderAction


class _TraceAwareProvider:
    def __init__(self) -> None:
        self.wired_cb: Any | None = None

    def wire_identity_trace_cb(self, cb: Any | None) -> None:
        self.wired_cb = cb

    def custom_action(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        del inputs
        return {"ok": True}


def test_action_executor_wires_identity_trace_cb_to_provider_handlers() -> None:
    provider = _TraceAwareProvider()
    executor = ActionExecutor(
        deps=ActionExecutorDeps(
            provider_actions={
                "custom_action": RegisteredProviderAction(
                    output_key="custom_ref",
                    reason_code="custom_done",
                    missing_reason="missing_custom",
                    handler=provider.custom_action,
                )
            }
        )
    )

    marker = object()
    executor.wire_identity_trace_cb(marker)  # type: ignore[arg-type]

    assert provider.wired_cb is marker
