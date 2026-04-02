"""Generic runtime runner.

The runner owns process/lifecycle mechanics and artifact emission only.
It resolves a surface-only adapter, composes one mechanical turn surface, and
stops there. It must not learn domain semantics, closure doctrine, or pack-
specific workflow language.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from ..composition import ComposedTurnInput, DefaultTurnComposer, TurnSurface
from .contracts import RuntimeAdapter, RuntimeArtifactTargets, RuntimeRunResult


class RuntimeRunnerError(RuntimeError):
    """Raised when the mechanical runner cannot complete its lifecycle."""


class RuntimeRunner:
    def __init__(
        self,
        *,
        adapter: RuntimeAdapter | None = None,
        adapter_factory: Callable[[Mapping[str, Any]], RuntimeAdapter] | None = None,
        adapter_loader: Callable[[Mapping[str, Any]], RuntimeAdapter] | None = None,
        targets: RuntimeArtifactTargets | None = None,
    ) -> None:
        self._adapter = adapter
        self._adapter_factory = adapter_factory
        self._adapter_loader = adapter_loader
        self._targets = targets

    def run(self, *, launch_context: Mapping[str, Any] | None = None) -> RuntimeRunResult:
        context = dict(launch_context or {})
        targets = self._targets or RuntimeArtifactTargets.from_env()

        try:
            adapter = self._resolve_adapter(context)
            surface = self._resolve_turn_surface(adapter, context)
            composed = DefaultTurnComposer().compose(surface)
            result = RuntimeRunResult(
                status="completed",
                reason_code="turn_surface_composed",
                result_payload=_build_result_payload(surface=surface, composed=composed),
                done_payload=_build_done_payload(surface=surface, composed=composed),
            )
        except Exception as exc:
            result = RuntimeRunResult(
                status="failed",
                reason_code="runner_exception",
                result_payload={"error": str(exc)},
                done_payload={"error": str(exc)},
            )
            self._write_artifacts(targets=targets, result=result)
            raise RuntimeRunnerError("runtime_runner_failed") from exc

        self._write_artifacts(targets=targets, result=result)
        return result

    def _resolve_adapter(self, launch_context: Mapping[str, Any]) -> RuntimeAdapter:
        if self._adapter is not None:
            return self._adapter
        if self._adapter_factory is not None:
            return self._adapter_factory(launch_context)
        if self._adapter_loader is not None:
            return self._adapter_loader(launch_context)
        raise RuntimeRunnerError("adapter_required")

    def _resolve_turn_surface(self, adapter: RuntimeAdapter, launch_context: Mapping[str, Any]) -> TurnSurface:
        surface = adapter.build_turn_surface(launch_context)
        if not isinstance(surface, TurnSurface):
            raise RuntimeRunnerError("turn_surface_required")
        return surface

    def _write_artifacts(self, *, targets: RuntimeArtifactTargets, result: RuntimeRunResult) -> None:
        _write_json(targets.result_file, _build_result_document(result))
        _write_json(targets.done_file, _build_done_document(result))


def run_runtime_from_env(
    *,
    adapter: RuntimeAdapter | None = None,
    adapter_factory: Callable[[Mapping[str, Any]], RuntimeAdapter] | None = None,
    adapter_loader: Callable[[Mapping[str, Any]], RuntimeAdapter] | None = None,
    opaque_launch_context: Mapping[str, Any] | None = None,
) -> RuntimeRunResult:
    return RuntimeRunner(
        adapter=adapter,
        adapter_factory=adapter_factory,
        adapter_loader=adapter_loader,
    ).run(launch_context=opaque_launch_context)


def _build_result_payload(*, surface: TurnSurface, composed: ComposedTurnInput) -> dict[str, Any]:
    return {
        "mechanical_surface": _surface_document(surface),
        "mechanical_turn_input": _composition_document(composed),
    }


def _build_done_payload(*, surface: TurnSurface, composed: ComposedTurnInput) -> dict[str, Any]:
    return {
        "mechanical_surface": _surface_document(surface),
        "mechanical_turn_input": {
            "block_count": len(composed.blocks),
            "surface_ids": tuple(composed.surface_payloads.keys()),
            "tool_ids": tuple(composed.tool_handlers.keys()),
        },
    }


def _surface_document(surface: TurnSurface) -> dict[str, Any]:
    return {
        "surface_id": surface.surface_id,
        "blocks": [
            {
                "content": block.content,
                "metadata": dict(block.metadata),
            }
            for block in surface.blocks
        ],
        "payload": dict(surface.payload),
        "tool_ids": [binding.tool_id for binding in surface.tool_bindings],
    }


def _composition_document(composed: ComposedTurnInput) -> dict[str, Any]:
    return {
        "block_count": len(composed.blocks),
        "blocks": [
            {
                "content": block.content,
                "metadata": dict(block.metadata),
            }
            for block in composed.blocks
        ],
        "surface_payloads": dict(composed.surface_payloads),
        "tool_ids": list(composed.tool_handlers.keys()),
    }


def _build_result_document(result: RuntimeRunResult) -> dict[str, Any]:
    payload = dict(result.result_payload)
    if "status" not in payload:
        payload["status"] = result.status
    if result.reason_code is not None and "reason_code" not in payload:
        payload["reason_code"] = result.reason_code
    return payload


def _build_done_document(result: RuntimeRunResult) -> dict[str, Any]:
    payload = dict(result.done_payload)
    if "status" not in payload:
        payload["status"] = result.status
    if result.reason_code is not None and "reason_code" not in payload:
        payload["reason_code"] = result.reason_code
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
