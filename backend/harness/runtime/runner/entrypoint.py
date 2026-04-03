"""Generic runtime entrypoint for launching domain-selected runs.

This module stays harness-owned and uses dynamic imports only. It resolves a
surface-only adapter factory or loader by string, binds the selected opaque
domain id, and delegates to ``run_runtime_from_env``.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import asdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .runner import RuntimeRunnerError, run_runtime_from_env

DEFAULT_ADAPTER_FACTORY_REF = "domains:require_domain_adapter_factory"


def main(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="harness.runtime.runner.entrypoint",
        description="Launch a harness runtime run from an opaque domain id and launch-context JSON.",
    )
    parser.add_argument("--domain-id", required=True, help="Opaque domain id used to select the adapter.")
    parser.add_argument(
        "--launch-context-json",
        required=True,
        help="Opaque launch-context JSON passed through to the selected adapter.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--adapter-factory-ref",
        default=DEFAULT_ADAPTER_FACTORY_REF,
        help="Dynamic import ref for a provider that returns a zero-arg adapter factory when called with domain id.",
    )
    group.add_argument(
        "--adapter-loader-ref",
        default=None,
        help="Dynamic import ref for a loader called as loader(domain_id, launch_context) -> adapter.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    domain_id = str(args.domain_id or "").strip()
    if not domain_id:
        raise RuntimeRunnerError("domain_id_required")

    launch_context = _parse_launch_context(args.launch_context_json)
    if args.adapter_loader_ref:
        loader = _load_callable_ref(args.adapter_loader_ref)

        def adapter_loader(opaque_launch_context: Mapping[str, Any]):
            return loader(domain_id, opaque_launch_context)

        result = run_runtime_from_env(
            adapter_loader=adapter_loader,
            opaque_launch_context=launch_context,
        )
    else:
        factory_provider = _load_callable_ref(args.adapter_factory_ref or DEFAULT_ADAPTER_FACTORY_REF)
        adapter_factory = factory_provider(domain_id)
        if not callable(adapter_factory):
            raise RuntimeRunnerError("adapter_factory_not_callable")

        def bound_adapter_factory(_: Mapping[str, Any]):
            return adapter_factory()

        result = run_runtime_from_env(
            adapter_factory=bound_adapter_factory,
            opaque_launch_context=launch_context,
        )

    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
    return result


def _load_callable_ref(ref: str) -> Callable[..., Any]:
    target = str(ref or "").strip()
    if not target:
        raise RuntimeRunnerError("callable_ref_required")
    module_name, attr_name = _split_ref(target)
    module = importlib.import_module(module_name)
    attr = getattr(module, attr_name)
    if not callable(attr):
        raise RuntimeRunnerError(f"callable_ref_not_callable:{target}")
    return attr


def _split_ref(ref: str) -> tuple[str, str]:
    if ":" in ref:
        module_name, attr_name = ref.split(":", 1)
        module_name = module_name.strip()
        attr_name = attr_name.strip()
    else:
        module_name, attr_name = ref.rsplit(".", 1)
    if not module_name or not attr_name:
        raise RuntimeRunnerError(f"invalid_callable_ref:{ref}")
    return module_name, attr_name


def _parse_launch_context(raw_json: str) -> dict[str, Any]:
    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeRunnerError("invalid_launch_context_json") from exc
    if not isinstance(decoded, dict):
        raise RuntimeRunnerError("launch_context_json_must_decode_to_object")
    return decoded


if __name__ == "__main__":
    main()
