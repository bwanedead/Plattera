from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from agents.common.contracts import CompileReport, CompileStatus


@dataclass
class SchemaMappingValidator:
    """
    v0 placeholder validator.

    In v1 this will call deterministic pipelines and convert results to a CompileReport.
    """

    def validate(self, schema_payload: Dict[str, Any]) -> CompileReport:
        # Skeleton only: always returns partial with a placeholder diagnostic.
        return CompileReport(
            status=CompileStatus.PARTIAL,
            diagnostics=[{"kind": "unimplemented", "message": "validator skeleton only"}],
        )


