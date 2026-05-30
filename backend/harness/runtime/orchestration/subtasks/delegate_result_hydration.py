"""Hydrate ``subtask:*`` refs via stored delegate results before domain artifact hydration."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ....execution.contracts import ActionDispatchResult, ExecutionStepRequest
from .delegate_result_refs import hydrate_delegate_result_refs, is_delegate_result_ref

GetRecordsFn = Callable[[], Sequence[Mapping[str, Any]]]
HydrationHandler = Callable[[ExecutionStepRequest | Any], Any]

_WRAPPED_ATTR = "_delegate_result_hydration_wrapped"
_PROVIDER_ATTR = "_delegate_result_records_provider"


class DelegateResultRecordsProvider:
    """Mutable records source so executor reuse can refresh loop memory per run."""

    def __init__(self, get_records: GetRecordsFn | None = None) -> None:
        self._get_records: GetRecordsFn = get_records or (lambda: [])

    def set_get_records(self, get_records: GetRecordsFn) -> None:
        self._get_records = get_records

    def records(self) -> Sequence[Mapping[str, Any]]:
        return self._get_records()


def install_delegate_result_hydration(
    executor: Any,
    get_records: GetRecordsFn,
) -> None:
    """Wrap ``hydrate_artifact_refs`` on *executor* to resolve ``subtask:*`` refs first."""
    handlers = getattr(executor, "handlers", None)
    if not isinstance(handlers, dict):
        return
    current = handlers.get("hydrate_artifact_refs")
    if current is None:
        return

    existing_provider = getattr(current, _PROVIDER_ATTR, None)
    if isinstance(existing_provider, DelegateResultRecordsProvider):
        existing_provider.set_get_records(get_records)
        return

    if getattr(current, _WRAPPED_ATTR, False):
        return

    provider = DelegateResultRecordsProvider(get_records)
    wrapped = wrap_hydrate_handler_with_delegate_results(current, provider.records)
    setattr(wrapped, _WRAPPED_ATTR, True)
    setattr(wrapped, _PROVIDER_ATTR, provider)
    executor.register("hydrate_artifact_refs", wrapped)


def wrap_hydrate_handler_with_delegate_results(
    base_handler: HydrationHandler,
    get_records: GetRecordsFn,
) -> HydrationHandler:
    """Partition ref_ids; hydrate delegate refs locally and delegate the rest."""

    def handler(request: ExecutionStepRequest | Mapping[str, Any]) -> Any:
        inputs = _request_inputs(request)
        ref_ids_raw = inputs.get("ref_ids")
        if ref_ids_raw is None:
            ref_ids_raw = inputs.get("refs")
        if not isinstance(ref_ids_raw, (list, tuple)):
            return base_handler(request)

        subtask_refs: list[str] = []
        other_refs: list[str] = []
        for item in ref_ids_raw:
            text = str(item or "").strip()
            if not text:
                continue
            if is_delegate_result_ref(text):
                subtask_refs.append(text)
            else:
                other_refs.append(text)

        if not subtask_refs:
            return base_handler(request)

        delegate_results, delegate_errors = hydrate_delegate_result_refs(get_records(), subtask_refs)

        if not other_refs:
            return _merge_hydration_outputs(
                delegate_results=delegate_results,
                delegate_errors=delegate_errors,
                base_result=None,
            )

        other_request = _clone_request_with_ref_ids(request, other_refs)
        base_result = base_handler(other_request)
        return _merge_hydration_outputs(
            delegate_results=delegate_results,
            delegate_errors=delegate_errors,
            base_result=base_result,
        )

    return handler


def _merge_hydration_outputs(
    *,
    delegate_results: list[dict[str, Any]],
    delegate_errors: list[dict[str, Any]],
    base_result: Any,
) -> dict[str, Any]:
    base_outputs = _coerce_outputs(base_result)
    merged_results = list(delegate_results) + list(base_outputs.get("results") or [])
    merged_errors = list(delegate_errors) + list(base_outputs.get("errors") or [])
    cap_exceeded = bool(base_outputs.get("cap_exceeded"))
    executed = True
    if isinstance(base_result, ActionDispatchResult):
        executed = bool(base_result.executed)
    elif isinstance(base_result, Mapping):
        executed = bool(base_result.get("executed", True))

    out: dict[str, Any] = {
        "executed": executed,
        "outputs": {
            "results": merged_results,
            "errors": merged_errors,
            "cap_exceeded": cap_exceeded,
            "hydrated_count": len(merged_results),
        },
    }
    image_evidence = _coerce_image_evidence(base_result)
    if image_evidence:
        out["image_evidence"] = image_evidence
    return out


def _coerce_outputs(raw_result: Any) -> dict[str, Any]:
    if isinstance(raw_result, ActionDispatchResult):
        return dict(raw_result.outputs or {})
    if isinstance(raw_result, Mapping):
        outputs = raw_result.get("outputs")
        return dict(outputs) if isinstance(outputs, Mapping) else {}
    return {}


def _coerce_image_evidence(raw_result: Any) -> list[dict[str, Any]]:
    if isinstance(raw_result, ActionDispatchResult) and raw_result.image_evidence:
        return [dict(row) for row in raw_result.image_evidence if isinstance(row, dict)]
    if isinstance(raw_result, Mapping):
        raw = raw_result.get("image_evidence")
        if isinstance(raw, (list, tuple)):
            return [dict(row) for row in raw if isinstance(row, dict)]
    return []


def _request_inputs(request: ExecutionStepRequest | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(request, ExecutionStepRequest):
        return dict(request.inputs)
    if isinstance(request, Mapping):
        inputs = request.get("inputs")
        if isinstance(inputs, Mapping):
            return dict(inputs)
        return dict(request)
    inputs = getattr(request, "inputs", None)
    return dict(inputs) if isinstance(inputs, Mapping) else {}


def _clone_request_with_ref_ids(
    request: ExecutionStepRequest | Mapping[str, Any],
    ref_ids: list[str],
) -> ExecutionStepRequest | dict[str, Any]:
    inputs = _request_inputs(request)
    cloned_inputs = dict(inputs)
    if "ref_ids" in inputs:
        cloned_inputs["ref_ids"] = ref_ids
    elif "refs" in inputs:
        cloned_inputs["refs"] = ref_ids
    else:
        cloned_inputs["ref_ids"] = ref_ids

    if isinstance(request, ExecutionStepRequest):
        return ExecutionStepRequest(
            session_id=request.session_id,
            action_id=request.action_id,
            inputs=cloned_inputs,
            idempotency_key=request.idempotency_key,
            run_id=request.run_id,
        )
    if isinstance(request, Mapping):
        out = dict(request)
        out["inputs"] = cloned_inputs
        return out
    return {"inputs": cloned_inputs}
